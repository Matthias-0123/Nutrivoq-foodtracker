
import sqlite3
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parent / "foodtracker.db"


def get_database():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    with get_database() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                username TEXT
            )
        """)

        columns = {
            column["name"]
            for column in connection.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        }

        if "username" not in columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN username TEXT"
            )

        existing_users = connection.execute("""
            SELECT id
            FROM users
            WHERE username IS NULL OR TRIM(username) = ''
            ORDER BY id
        """).fetchall()

        for user in existing_users:
            username = f"user{user['id']}"

            while connection.execute(
                """
                SELECT 1 FROM users
                WHERE username = ? COLLATE NOCASE
                """,
                (username,)
            ).fetchone():
                username += "_"

            connection.execute(
                "UPDATE users SET username = ? WHERE id = ?",
                (username, user["id"])
            )

        connection.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_users_username
            ON users(username COLLATE NOCASE)
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS user_goals (
                user_id INTEGER PRIMARY KEY,
                calories INTEGER NOT NULL,
                protein INTEGER NOT NULL,
                carbs INTEGER NOT NULL,
                fat INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS food_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                food_name TEXT NOT NULL,
                amount REAL NOT NULL,
                calories REAL NOT NULL,
                protein REAL NOT NULL,
                carbs REAL NOT NULL,
                fat REAL NOT NULL,
                entry_date TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS favorite_foods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                food_name TEXT NOT NULL,
                amount REAL NOT NULL,
                calories REAL NOT NULL,
                protein REAL NOT NULL,
                carbs REAL NOT NULL,
                fat REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS progress_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                weight REAL NOT NULL,
                taken_at TEXT NOT NULL,
                photo_filename TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)
