
from datetime import date

from database import get_database


def add_food(user_id, food_name, amount, calories, protein, carbs, fat):
    with get_database() as connection:
        connection.execute("""
            INSERT INTO food_entries (
                user_id, food_name, amount, calories,
                protein, carbs, fat, entry_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, food_name, amount, calories,
            protein, carbs, fat, date.today().isoformat()
        ))


def get_daily_food(user_id, selected_date=None):
    if selected_date is None:
        selected_date = date.today().isoformat()

    with get_database() as connection:
        entries = connection.execute("""
            SELECT * FROM food_entries
            WHERE user_id = ? AND entry_date = ?
            ORDER BY id DESC
        """, (user_id, selected_date)).fetchall()

    return entries


def calculate_daily_totals(entries):
    return {
        "calories": round(sum(entry["calories"] for entry in entries)),
        "protein": round(sum(entry["protein"] for entry in entries), 1),
        "carbs": round(sum(entry["carbs"] for entry in entries), 1),
        "fat": round(sum(entry["fat"] for entry in entries), 1)
    }


def delete_food(user_id, entry_id):
    with get_database() as connection:
        connection.execute("""
            DELETE FROM food_entries
            WHERE id = ? AND user_id = ?
        """, (entry_id, user_id))
