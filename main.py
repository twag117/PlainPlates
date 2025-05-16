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

def get_recipes(q):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if q:
        query = f"%{q}%"
        cursor.execute("SELECT title, slug, description, prep_time, cook_time FROM recipes WHERE title LIKE ? OR description LIKE ? ORDER BY id desc", (query, query))
    else:    
        cursor.execute("SELECT title, slug, description, prep_time, cook_time, COALESCE(SUM(value), 0) AS score FROM recipes LEFT JOIN recipe_votes on recipes.id = recipe_votes.recipe_id GROUP BY recipes.id ORDER BY score desc")
    recipes = cursor.fetchall()
    conn.close()
    return recipes

def get_recipes_popular():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT
            r.id,
            r.title,
            r.slug,
            r.description,
            r.prep_time,
            r.cook_time,
            COALESCE(SUM(rv.value), 0) AS score
        FROM recipes r
        LEFT JOIN recipe_votes rv ON r.id = rv.recipe_id
        GROUP BY r.id
        ORDER BY score DESC
    ''')
    
    recipes_popular = cursor.fetchall()
    conn.close()
    return recipes_popular

def get_recipes_new():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT title, slug, description, prep_time, cook_time FROM recipes ORDER BY id desc")
    recipes_popular = cursor.fetchall()
    conn.close()
    return recipes_popular

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
def recipes_page(request: Request, q: str | None = None):
    categories = get_categories()
    recipes = get_recipes(q)
    return templates.TemplateResponse("recipes.html", {
        "request": request,
        "categories": categories,
        "recipes": recipes,
        "q": q
    })
