"""Demo target app: a simple, correctly-written user lookup endpoint.

This is the baseline seeded onto the demo repo's default branch by
scripts/seed_demo_pr.py. The PR that introduces app_after_vulnerable.py's
SQL-injection bug is the one the recorded demo reviews.
"""
import sqlite3

from fastapi import FastAPI

app = FastAPI()


def get_db():
    return sqlite3.connect("users.db")


@app.get("/users/{user_id}")
def lookup_user(user_id: int):
    conn = get_db()
    cursor = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return {"error": "not found"}
    return {"id": row[0], "name": row[1], "email": row[2]}
