
import os

from flask import Flask, render_template, request, redirect, url_for, session, flash

from auth import auth
from database import get_database, initialize_database
from nutrition import calculate_calorie_goal, calculate_macros

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-development-only-change-me")
app.register_blueprint(auth)

initialize_database()


@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    with get_database() as connection:
        goals = connection.execute(
            "SELECT * FROM user_goals WHERE user_id = ?",
            (session["user_id"],)
        ).fetchone()

    return render_template("dashboard.html", goals=goals)


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        try:
            weight = float(request.form["weight"])
            height = float(request.form["height"])
            age = int(request.form["age"])
            sex = request.form["sex"]
            activity_level = float(request.form["activity_level"])

            if not (weight > 0 and height > 0 and 1 <= age <= 120):
                raise ValueError()

            if sex not in ("male", "female"):
                raise ValueError()

            if activity_level not in (1.2, 1.375, 1.55, 1.725):
                raise ValueError()

        except (ValueError, KeyError):
            flash("Please enter valid personal information.")
            return render_template("index.html")

        calorie_goal = calculate_calorie_goal(
            weight, height, age, sex, activity_level
        )

        goals = calculate_macros(calorie_goal, weight)

        with get_database() as connection:
            connection.execute("""
                INSERT INTO user_goals
                    (user_id, calories, protein, carbs, fat)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    calories = excluded.calories,
                    protein = excluded.protein,
                    carbs = excluded.carbs,
                    fat = excluded.fat
            """, (
                session["user_id"],
                goals["calories"],
                goals["protein"],
                goals["carbs"],
                goals["fat"]
            ))

        return redirect(url_for("dashboard"))

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
