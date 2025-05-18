from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from pathlib import Path
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from auth import oauth, create_or_update_user
import sqlite3
import os

load_dotenv()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET"))
templates = Jinja2Templates(directory="templates")
DB_PATH = Path("data/plainplates.db")

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
    return RedirectResponse("/login")

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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT recipes.id, title, slug, description, ingredients, instructions, notes,
               prep_time, cook_time, COALESCE(SUM(recipe_votes.value), 0) as score
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

    cursor.execute('''
        SELECT name FROM recipe_categories
        JOIN categories ON recipe_categories.category_id = categories.id
        WHERE recipe_categories.recipe_id = ?
    ''', (row["id"],))
    recipe["tags"] = [cat["name"] for cat in cursor.fetchall()]

    conn.close()

    return templates.TemplateResponse("recipe_detail.html", {
        "request": request,
        "recipe": recipe
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

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if already favorited
    cursor.execute("""
        SELECT 1 FROM user_favorites
        WHERE user_id = ? AND recipe_id = ?
    """, (user["id"], recipe_id))

    if cursor.fetchone():
        # Remove from favorites
        cursor.execute("""
            DELETE FROM user_favorites
            WHERE user_id = ? AND recipe_id = ?
        """, (user["id"], recipe_id))
    else:
        # Add to favorites
        cursor.execute("""
            INSERT INTO user_favorites (user_id, recipe_id)
            VALUES (?, ?)
        """, (user["id"], recipe_id))

    conn.commit()
    conn.close()

    return RedirectResponse(f"/recipes/{get_recipe_slug_by_id(recipe_id)}", status_code=303)
