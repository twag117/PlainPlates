from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from pathlib import Path
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from auth import oauth, create_or_update_user
from mistralai import Mistral
from better_profanity import profanity
import sqlite3
import os
import uuid
import re

load_dotenv()
profanity.load_censor_words()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET"))
templates = Jinja2Templates(directory="templates")
DB_PATH = Path("data/plainplates.db")
mistral_api_key = os.getenv("MISTRAL_API_KEY")

def get_categories():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT name, slug FROM categories ORDER BY name")
    categories = cursor.fetchall()
    conn.close()
    return categories

def get_recipes(filter_q=None, sort="score", limit=None, category_slug=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Build base query
    query = f"""
        SELECT recipes.id, title, slug, description, prep_time, cook_time,
               COALESCE(SUM(recipe_votes.value), 0) AS score,
               recipes.created_at
        FROM recipes
        LEFT JOIN recipe_votes ON recipes.id = recipe_votes.recipe_id
    """

    params = []
    where_clauses = []

    if filter_q:
        like = f"%{filter_q}%"
        where_clauses.append("(title LIKE ? OR description LIKE ?)")
        params.extend([like, like])

    if category_slug:
        where_clauses.append('''
            recipes.id IN (
                SELECT recipe_id FROM recipe_categories
                JOIN categories ON categories.id = recipe_categories.category_id
                WHERE categories.slug = ?
            )
        ''')
        params.append(category_slug)

    # Combine into a full WHERE clause if needed
    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    query += f" {where_clause} GROUP BY recipes.id"

    if sort == "score":
        query += " ORDER BY score DESC"
    elif sort == "created_at":
        query += " ORDER BY recipes.created_at DESC"
    else:
        query += " ORDER BY recipes.id DESC"

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query, params)
    recipes_raw = cursor.fetchall()

    recipes = []
    for row in recipes_raw:
        recipe = dict(row)
        cursor.execute("""
            SELECT name FROM recipe_categories
            JOIN categories ON recipe_categories.category_id = categories.id
            WHERE recipe_categories.recipe_id = ?
        """, (row["id"],))
        recipe["tags"] = [cat["name"] for cat in cursor.fetchall()]
        recipes.append(recipe)

    conn.close()
    return recipes


def get_recipes_popular():
    return get_recipes(sort="score", limit=10)

def get_recipes_new():
    return get_recipes(sort="created_at", limit=10)

def get_recipes_search(q):
    return get_recipes(filter_q=q)

def get_recipe_slug_by_id(recipe_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT slug FROM recipes WHERE id = ?", (recipe_id,))
    row = cursor.fetchone()
    conn.close()
    return row["slug"] if row else ""


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    categories = get_categories()
    recipes_popular = get_recipes_popular()
    recipes_new = get_recipes_new()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "categories": categories,
        "recipes_popular": recipes_popular,
        "recipes_new": recipes_new,
    })

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/login/google", response_class=HTMLResponse)
async def login_google(request: Request):
    redirect_uri = request.url_for("auth_google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback")
async def auth_google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")
    if user_info:
        user_id = create_or_update_user(
            email=user_info["email"],
            name=user_info["name"],
            google_id=user_info["sub"]
        )
        request.session["user"] = {
            "id": user_id,
            "email": user_info["email"],
            "name": user_info["name"]
        }
        return RedirectResponse("/")
    return RedirectResponse("/login")

@app.get("/logout")
def logout(request: Request):
    request.session.pop("user", None)
    referer = request.headers.get("referer")
    return RedirectResponse(referer or "/", status_code=303)

@app.get("/whoami")
def whoami(request: Request):
    user = request.session.get("user")
    if user:
        return {"logged_in": True, "email": user["email"], "name": user["name"]}
    else:
        return {"logged_in": False}

@app.get("/recipes", response_class=HTMLResponse)
def recipes_page(request: Request, q: str | None = None, category: str | None = None):
    categories = get_categories()
    recipes = get_recipes(filter_q=q, category_slug=category)
    return templates.TemplateResponse("recipes.html", {
        "request": request,
        "categories": categories,
        "recipes": recipes,
        "q": q,
        "selected_category": category
    })

@app.get("/recipes/{slug}", response_class=HTMLResponse)
def recipe_detail(slug: str, request: Request):
    user = request.session.get("user")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT recipes.id, title, slug, description, ingredients, instructions, notes,
               prep_time, cook_time, COALESCE(SUM(recipe_votes.value), 0) as score, user_id
        FROM recipes
        LEFT JOIN recipe_votes ON recipes.id = recipe_votes.recipe_id
        WHERE slug = ?
        GROUP BY recipes.id
    ''', (slug,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    recipe = dict(row)

    # Determine user's current vote
    vote = 0
    identifier = user["email"] if user else f"anon-{request.client.host}"
    cursor.execute("""
        SELECT value FROM recipe_votes
        WHERE recipe_id = ? AND identifier = ?
    """, (recipe["id"], identifier))
    vote_row = cursor.fetchone()
    vote = int(vote_row[0] / abs(vote_row[0])) if vote_row else 0

    cursor.execute('''
        SELECT name FROM recipe_categories
        JOIN categories ON recipe_categories.category_id = categories.id
        WHERE recipe_categories.recipe_id = ?
    ''', (recipe["id"],))
    recipe["tags"] = [cat["name"] for cat in cursor.fetchall()]

    # Check if this recipe is in user's favorites
    is_favorited = False

    if user:
        cursor.execute("""
            SELECT 1 FROM user_favorites
            WHERE user_id = ? AND recipe_id = ?
        """, (user["id"], recipe["id"]))
        is_favorited = cursor.fetchone() is not None


    conn.close()

    return templates.TemplateResponse("recipe_detail.html", {
        "request": request,
        "recipe": recipe,
        "is_favorited": is_favorited,
        "vote": vote
    })

@app.get("/favorites", response_class=HTMLResponse)
def favorites_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT recipes.id, recipes.title, recipes.slug, recipes.description, recipes.prep_time, recipes.cook_time, COALESCE(SUM(recipe_votes.value), 0) as score, recipes.created_at
        FROM user_favorites
        JOIN recipes on user_favorites.recipe_id = recipes.id
        LEFT JOIN recipe_votes on recipes.id = recipe_votes.recipe_id
        WHERE user_favorites.user_id = ?
        GROUP BY recipes.id
        ORDER BY recipes.created_at DESC
    ''', (user["id"],))

    recipes = []
    for row in cursor.fetchall():
        recipe = dict(row)
        cursor.execute('''
            SELECT name FROM recipe_categories
            JOIN categories ON recipe_categories.category_id = categories.id
            WHERE recipe_categories.recipe_id = ?
        ''', (recipe["id"],))
        recipe["tags"] = [cat["name"] for cat in cursor.fetchall()]
        recipes.append(recipe)
    
    conn.close()

    categories = get_categories()
    return templates.TemplateResponse("favorites.html", {
        "request": request,
        "recipes": recipes,
        "categories": categories,
        "q": None,
        "selected_category": None
    })

@app.post("/favorites/{recipe_id}")
def toggle_favorite(recipe_id: int, request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)

    identifier = user["email"]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if already favorited
    cursor.execute("""
        SELECT 1 FROM user_favorites
        WHERE user_id = ? AND recipe_id = ?
    """, (user["id"], recipe_id))
    is_favorited = cursor.fetchone() is not None

    if is_favorited:
        # Unfavorite and remove any upvote
        cursor.execute("""
            DELETE FROM user_favorites
            WHERE user_id = ? AND recipe_id = ?
        """, (user["id"], recipe_id))

        cursor.execute("""
            DELETE FROM recipe_votes
            WHERE recipe_id = ? AND identifier = ? AND value > 0
        """, (recipe_id, identifier))

    else:
        # Favorite and auto-upvote
        cursor.execute("""
            INSERT INTO user_favorites (user_id, recipe_id)
            VALUES (?, ?)
        """, (user["id"], recipe_id))

        cursor.execute("""
            INSERT OR REPLACE INTO recipe_votes (recipe_id, identifier, value)
            VALUES (?, ?, ?)
        """, (recipe_id, identifier, 5))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/recipes/{get_recipe_slug_by_id(recipe_id)}", status_code=303)


@app.get("/submit", response_class=HTMLResponse)
def submit_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("submit.html", {"request": request})


@app.post("/recipes/{recipe_id}/vote")
def vote_on_recipe(recipe_id: int, request: Request, value: int = Form(...)):
    user = request.session.get("user")
    identifier = user["email"] if user else f"anon-{request.client.host}"

    # Apply vote weighting
    weight = 5 if user else 1
    weighted_value = value * weight

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check existing vote
    cursor.execute("""
        SELECT value FROM recipe_votes
        WHERE recipe_id = ? AND identifier = ?
    """, (recipe_id, identifier))
    row = cursor.fetchone()

    if row:
        if row[0] == weighted_value:
            # Un-vote (toggle off)
            cursor.execute("""
                DELETE FROM recipe_votes
                WHERE recipe_id = ? AND identifier = ?
            """, (recipe_id, identifier))
        else:
            # Update vote
            cursor.execute("""
                UPDATE recipe_votes
                SET value = ?
                WHERE recipe_id = ? AND identifier = ?
            """, (weighted_value, recipe_id, identifier))
    else:
        # New vote
        cursor.execute("""
            INSERT INTO recipe_votes (recipe_id, identifier, value)
            VALUES (?, ?, ?)
        """, (recipe_id, identifier, weighted_value))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/recipes/{get_recipe_slug_by_id(recipe_id)}", status_code=303)


@app.post("/submit")
def submit_recipe(request: Request, title: str = Form(""), raw: str = Form(...)):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)

    client = Mistral(api_key=mistral_api_key)

    messages = [
        {
            "role": "user",
            "content": """You are a recipe parser and content cleaner. 
                Make sure output is safe, appropriate, and well-formatted. 
                Filter out any offensive language (slurs, cursing, hate speech). 
                Respond ONLY with valid JSON in this format (preserve newlines and list formatting):

                {
                "title": "...",
                "description": "...",
                "ingredients": "- item 1\\n- item 2\\n- item 3",
                "instructions": "1. Step one\\n2. Step two\\n3. Step three",
                "notes": "...",      // optional
                "prep_time": 10,
                "cook_time": 20,
                "servings": 4
                }

                Input recipe (unstructured):
                """ + raw
        }
    ]


    chat_response = client.chat.complete(
        model="mistral-medium-latest",
        messages=messages
    )


    import json

    raw_output = chat_response.choices[0].message.content.strip()

    print("Raw Mistral output:", repr(raw_output))

    # Remove markdown-style code fences if present
    if raw_output.startswith("```json"):
        raw_output = raw_output.lstrip("```json").strip()
    if raw_output.endswith("```"):
        raw_output = raw_output[:-3].strip()

    try:
        parsed = json.loads(raw_output)
    except Exception as e:
        print("Mistral parse error:", e)
        return templates.TemplateResponse("submit.html", {
            "request": request,
            "error": "Something went wrong parsing the recipe. Please try again or reformat."
        })

    title = parsed["title"]
    slug = re.sub(r"[^a-z0-9\-]+", "-", title.lower().strip().replace(" ", "-")).strip("-")
    description = parsed["description"]
    ingredients = parsed["ingredients"]
    instructions = parsed["instructions"]
    notes = parsed.get("notes", "")
    prep_time = parsed["prep_time"]
    cook_time = parsed["cook_time"]
    servings = parsed["servings"]


    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Generate a unique slug by checking for existing slugs and incrementing
    base_slug = slug
    i = 2
    while cursor.execute("SELECT 1 FROM recipes WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base_slug}-{i}"
        i += 1

    cursor.execute('''
        INSERT INTO recipes (title, slug, description, ingredients, instructions, notes,
                            prep_time, cook_time, servings, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (title or slug, slug, description, ingredients, instructions, notes,
        prep_time, cook_time, servings, user["id"]))

    recipe_id = cursor.lastrowid
    conn.commit()
    conn.close()


    return RedirectResponse(f"/recipes/{slug}", status_code=303)

@app.get("/recipes/{slug}/edit", response_class=HTMLResponse)
def edit_recipe_page(slug: str, request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM recipes WHERE slug = ?", (slug,))
    recipe = cursor.fetchone()
    if not recipe or recipe["user_id"] != user["id"]:
        conn.close()
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    conn.close()
    return templates.TemplateResponse("edit_recipe.html", {
        "request": request,
        "recipe": dict(recipe)
    })

@app.post("/recipes/{slug}/edit")
def update_recipe(slug: str, request: Request,
                  title: str = Form(...),
                  description: str = Form(...),
                  ingredients: str = Form(...),
                  instructions: str = Form(...),
                  notes: str = Form(""),
                  prep_time: int = Form(...),
                  cook_time: int = Form(...),
                  servings: int = Form(...)):

    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)

    # Basic format checks
    bad_ingredients = any(not line.strip().startswith("- ") for line in ingredients.strip().splitlines())
    lines = [line.strip() for line in instructions.strip().splitlines()]
    expected = 1
    bad_instructions = False

    for line in lines:
        match = re.match(r"^(\d+)\.\s", line)
        if not match or int(match.group(1)) != expected:
            bad_instructions = True
            break
        expected += 1

    # Check for profanity in any text field
    text_fields = [title, description, ingredients, instructions, notes]
    bad_language = any(profanity.contains_profanity(field) for field in text_fields)

    # If validation fails, re-render the form with an error
    if bad_ingredients or bad_instructions or bad_language:
        return templates.TemplateResponse("edit_recipe.html", {
            "request": request,
            "recipe": {
                "slug": slug,
                "title": title,
                "description": description,
                "ingredients": ingredients,
                "instructions": instructions,
                "notes": notes,
                "prep_time": prep_time,
                "cook_time": cook_time,
                "servings": servings
            },
            "error": (
                "Please fix formatting: "
                + ("ingredients must start with '- '" if bad_ingredients else "")
                + (" | instructions must be numbered/ordered" if bad_instructions else "")
                + (" | inappropriate language found" if bad_language else "")
            )
        })

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM recipes WHERE slug = ?", (slug,))
    row = cursor.fetchone()
    if not row or row["user_id"] != user["id"]:
        conn.close()
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    cursor.execute("""
        UPDATE recipes SET title = ?, description = ?, ingredients = ?, instructions = ?,
            notes = ?, prep_time = ?, cook_time = ?, servings = ?, updated_at = CURRENT_TIMESTAMP
        WHERE slug = ?
    """, (title, description, ingredients, instructions, notes,
          prep_time, cook_time, servings, slug))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/recipes/{slug}/edit", status_code=303)

