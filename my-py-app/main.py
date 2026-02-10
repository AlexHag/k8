import os
import pymssql
from flask import Flask, jsonify, request

app = Flask(__name__)

# ── Connection settings (override via env vars) ──────────────────────────
DB_SERVER   = os.getenv("DB_SERVER", "mssql-service.mssql.svc.cluster.local")
DB_PORT     = os.getenv("DB_PORT", "1433")
DB_USER     = os.getenv("DB_USER", "sa")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")          # injected from K8s secret
DB_NAME     = os.getenv("DB_NAME", "TodoDB")

print(f"Connecting to MSSQL at {DB_SERVER}:{DB_PORT}, database: {DB_NAME}, user: {DB_USER}, password: {DB_PASSWORD[:8] + "****" if DB_PASSWORD else '(empty)'}")

def get_connection(database: str = DB_NAME):
    """Return a pymssql connection to the given database."""
    return pymssql.connect(
        server=DB_SERVER,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=database,
        tds_version="7.3",
    )


def init_db():
    """Create the database and Todos table if they don't exist."""
    # Connect to master to create the database
    master = get_connection(database="master")
    master.autocommit(True)
    cursor = master.cursor()
    cursor.execute(
        f"IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = '{DB_NAME}') "
        f"CREATE DATABASE [{DB_NAME}]"
    )
    cursor.close()
    master.close()

    # Connect to the app database to create the table
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        IF NOT EXISTS (
            SELECT * FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'Todos'
        )
        CREATE TABLE Todos (
            Id    INT IDENTITY(1,1) PRIMARY KEY,
            Title NVARCHAR(200) NOT NULL,
            Done  BIT DEFAULT 0
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


# ── Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return jsonify({"message": "TODO App – connected to MSSQL"})


@app.route("/todos", methods=["GET"])
def get_todos():
    """Return all todo items."""
    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    cursor.execute("SELECT Id, Title, Done FROM Todos ORDER BY Id")
    rows = cursor.fetchall()
    todos = [{"id": r["Id"], "title": r["Title"], "done": bool(r["Done"])} for r in rows]
    cursor.close()
    conn.close()
    return jsonify(todos)


@app.route("/todos", methods=["POST"])
def create_todo():
    """Create a new todo item. Expects JSON: {"title": "..."}"""
    body = request.get_json(silent=True) or {}
    title = body.get("title", "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    conn = get_connection()
    cursor = conn.cursor(as_dict=True)
    cursor.execute("INSERT INTO Todos (Title) VALUES (%s)", (title,))
    conn.commit()
    # Fetch the newly created row
    cursor.execute("SELECT TOP 1 Id, Title, Done FROM Todos ORDER BY Id DESC")
    row = cursor.fetchone()
    todo = {"id": row["Id"], "title": row["Title"], "done": bool(row["Done"])}
    cursor.close()
    conn.close()
    return jsonify(todo), 201


@app.route("/todos/<int:todo_id>", methods=["DELETE"])
def delete_todo(todo_id: int):
    """Delete a todo item by id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM Todos WHERE Id = %s", (todo_id,))
    deleted = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()

    if deleted == 0:
        return jsonify({"error": "todo not found"}), 404
    return jsonify({"deleted": todo_id}), 200


# ── Startup ───────────────────────────────────────────────────────────────

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=False)
