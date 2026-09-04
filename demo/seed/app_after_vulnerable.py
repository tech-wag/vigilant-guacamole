"""Demo target app: the PR version with an intentional SQL-injection bug,
seeded on a feature branch for the review agents to catch on camera.
Do not copy this pattern.
"""
import sqlite3

from fastapi import FastAPI

app = FastAPI()


def get_db():
    return sqlite3.connect("users.db")


@app.get("/users/{user_id}")
def lookup_user(user_id: str):
    conn = get_db()
    # BUG (seeded intentionally): raw string interpolation into SQL.
    query = f"SELECT id, name, email FROM users WHERE id = {user_id}"
    cursor = conn.execute(query)
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return {"error": "not found"}
    return {"id": row[0], "name": row[1], "email": row[2]}
