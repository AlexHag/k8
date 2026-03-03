import os
import time

import psycopg
from flask import Flask, jsonify, request, send_from_directory
from psycopg.rows import dict_row

app = Flask(__name__)

# Connection settings (override via env vars)
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "my_py_app_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "my_py_app")

masked_password = f"{DB_PASSWORD[:8]}****" if DB_PASSWORD else "(empty)"
print(
    f"Connecting to Postgres at {DB_HOST}:{DB_PORT}, "
    f"database: {DB_NAME}, user: {DB_USER}, password: {masked_password}"
)


def get_connection():
    """Return a PostgreSQL connection."""
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    )


def init_db(max_retries: int = 20, retry_delay_seconds: int = 2):
    """Create the todos table if it doesn't exist."""
    for attempt in range(1, max_retries + 1):
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS todos (
                            id SERIAL PRIMARY KEY,
                            title TEXT NOT NULL,
                            done BOOLEAN NOT NULL DEFAULT FALSE
                        )
                        """
                    )
                conn.commit()
            return
        except psycopg.OperationalError as exc:
            if attempt == max_retries:
                raise
            print(
                f"Database not ready yet (attempt {attempt}/{max_retries}), "
                f"retrying in {retry_delay_seconds}s: {exc}"
            )
            time.sleep(retry_delay_seconds)


@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/todos", methods=["GET"])
def get_todos():
    """Return all todo items."""
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT id, title, done FROM todos ORDER BY id")
            rows = cursor.fetchall()
    todos = [{"id": r["id"], "title": r["title"], "done": bool(r["done"])} for r in rows]
    return jsonify(todos)


@app.route("/todos", methods=["POST"])
def create_todo():
    """Create a new todo item. Expects JSON: {"title": "..."}"""
    body = request.get_json(silent=True) or {}
    title = body.get("title", "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "INSERT INTO todos (title) VALUES (%s) RETURNING id, title, done",
                (title,),
            )
            row = cursor.fetchone()
        conn.commit()
    todo = {"id": row["id"], "title": row["title"], "done": bool(row["done"])}
    return jsonify(todo), 201


@app.route("/todos/<int:todo_id>", methods=["DELETE"])
def delete_todo(todo_id: int):
    """Delete a todo item by id."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM todos WHERE id = %s", (todo_id,))
            deleted = cursor.rowcount
        conn.commit()

    if deleted == 0:
        return jsonify({"error": "todo not found"}), 404
    return jsonify({"deleted": todo_id}), 200


with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=False)
