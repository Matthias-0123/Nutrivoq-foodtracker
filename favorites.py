
from database import get_database
from food import add_food


def save_favorite(user_id, entry_id):
    with get_database() as connection:
        entry = connection.execute("""
            SELECT food_name, amount, calories, protein, carbs, fat
            FROM food_entries
            WHERE id = ? AND user_id = ?
        """, (entry_id, user_id)).fetchone()

        if entry is None:
            return False

        connection.execute("""
            INSERT INTO favorite_foods (
                user_id, food_name, amount, calories,
                protein, carbs, fat
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            entry["food_name"],
            entry["amount"],
            entry["calories"],
            entry["protein"],
            entry["carbs"],
            entry["fat"]
        ))

    return True


def get_favorites(user_id):
    with get_database() as connection:
        favorites = connection.execute("""
            SELECT *
            FROM favorite_foods
            WHERE user_id = ?
            ORDER BY id DESC
        """, (user_id,)).fetchall()

    return favorites


def add_favorite_to_daily_tracker(user_id, favorite_id, amount):
    with get_database() as connection:
        favorite = connection.execute("""
            SELECT *
            FROM favorite_foods
            WHERE id = ? AND user_id = ?
        """, (favorite_id, user_id)).fetchone()

    if favorite is None or favorite["amount"] <= 0:
        return False

    multiplier = amount / favorite["amount"]

    add_food(
        user_id,
        favorite["food_name"],
        amount,
        round(favorite["calories"] * multiplier, 1),
        round(favorite["protein"] * multiplier, 1),
        round(favorite["carbs"] * multiplier, 1),
        round(favorite["fat"] * multiplier, 1)
    )

    return True


def delete_favorite(user_id, favorite_id):
    with get_database() as connection:
        connection.execute("""
            DELETE FROM favorite_foods
            WHERE id = ? AND user_id = ?
        """, (favorite_id, user_id))
