import os
from fastapi import Request, HTTPException, status
from authlib.integrations.starlette_client import OAuth
import sqlite3
from dotenv import load_dotenv

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url=GOOGLE_DISCOVERY_URL,
    client_kwargs={"scope": "openid email profile"}
)

def get_db():
    conn = sqlite3.connect("data/plainplates.db")
    conn.row_factory = sqlite3.Row
    return conn

def create_or_update_user(email, name, google_id):
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('UPDATE users SET name = ?, google_id = ? WHERE email = ?', (name, google_id, email))

        if cursor.rowcount == 0:
            cursor.execute('INSERT INTO users (email, name, google_id) VALUES (?, ?, ?)', (email, name, google_id))
            conn.commit()
            return cursor.lastrowid
        else:
            conn.commit()
            return cursor.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]
    finally:
        conn.close()

def login_required(request: Request):
    if "user" not in request.session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in.")
