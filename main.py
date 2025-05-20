from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from pathlib import Path
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from auth import oauth, create_or_update_user
from mistralai import Mistral
from better_profanity import profanity
from typing import List
import sqlite3
import os
import json
import uuid
import re

load_dotenv()
profanity.load_censor_words()
for word in ["pot", "breast", "breasts"]:
    if word in profanity.CENSOR_WORDSET:
        profanity.CENSOR_WORDSET.remove(word)


app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET"))
templates = Jinja2Templates(directory="templates")
DB_PATH = Path("data/plainplates.db")
mistral_api_key = os.getenv("MISTRAL_API_KEY")


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html")