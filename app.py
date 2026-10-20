
import os
import math
import requests

from datetime import date, datetime
from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

from flask import jsonify
from auth import auth
from database import get_database, initialize_database
from nutrition import calculate_calorie_goal, calculate_macros
from food import (
    add_food,
    get_daily_food,
    calculate_daily_totals,
    delete_food
)
from product_api import search_products, get_product


load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

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

    user_id = session["user_id"]
    selected_date = date.today().isoformat()

    with get_database() as connection:
        goals = connection.execute(
            "SELECT * FROM user_goals WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    entries = get_daily_food(user_id, selected_date)
    totals = calculate_daily_totals(entries)

    remaining = None

    if goals:
        remaining = {
            "calories": goals["calories"] - totals["calories"],
            "protein": goals["protein"] - totals["protein"],
            "carbs": goals["carbs"] - totals["carbs"],
            "fat": goals["fat"] - totals["fat"]
        }

    return render_template(
        "dashboard.html",
        goals=goals,
        entries=entries,
        totals=totals,
        remaining=remaining
    )


@app.route("/api/products/search")
def search_products_api():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    query = request.args.get("query", "").strip()

    if len(query) < 3:
        return jsonify([])

    if len(query) > 100:
        return jsonify({"error": "Search query too long"}), 400

    try:
        products = search_products(query)
        return jsonify(products)

    except (requests.RequestException, ValueError, TypeError):
        return jsonify({"error": "Product search unavailable"}), 502


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

            if not all(math.isfinite(value) for value in (
                weight, height, activity_level
            )):
                raise ValueError

            if not (0 < weight <= 500):
                raise ValueError

            if not (0 < height <= 300):
                raise ValueError

            if not (0 < age <= 120):
                raise ValueError

            if sex not in ("male", "female"):
                raise ValueError

            if activity_level not in (1.2, 1.375, 1.55, 1.725):
                raise ValueError

        except (ValueError, KeyError):
            flash("Please enter valid profile information.")
            return redirect(url_for("setup"))

        calorie_goal = calculate_calorie_goal(
            weight,
            height,
            age,
            sex,
            activity_level
        )

        goals = calculate_macros(calorie_goal, weight)

        with get_database() as connection:
            connection.execute("""
                INSERT INTO user_goals (
                    user_id,
                    calories,
                    protein,
                    carbs,
                    fat
                )
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


@app.route("/food/add", methods=["GET", "POST"])
def add_food_page():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        try:
            food_name = request.form["food_name"].strip()
            amount = float(request.form["amount"])
            calories = float(request.form["calories"])
            protein = float(request.form["protein"])
            carbs = float(request.form["carbs"])
            fat = float(request.form["fat"])

            if not food_name or len(food_name) > 100:
                raise ValueError

            if not math.isfinite(amount) or not 0 < amount <= 10000:
                raise ValueError

            nutrition_values = (calories, protein, carbs, fat)

            if not all(
                math.isfinite(value) and 0 <= value <= 100000
                for value in nutrition_values
            ):
                raise ValueError

        except (ValueError, KeyError):
            flash("Please enter valid food information.")
            return redirect(url_for("add_food_page"))

        add_food(
            session["user_id"],
            food_name,
            amount,
            calories,
            protein,
            carbs,
            fat
        )

        return redirect(url_for("dashboard"))

    return render_template("add_food.html")


@app.route("/food/delete/<int:entry_id>", methods=["POST"])
def delete_food_entry(entry_id):
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    delete_food(session["user_id"], entry_id)

    return redirect(url_for("dashboard"))


@app.route("/food/search")
def search_food():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    query = request.args.get("query", "").strip()
    products = []
    error = None

    if query:
        if len(query) > 100:
            error = "Search query is too long."
        else:
            try:
                products = search_products(query)
            except (requests.RequestException, ValueError):
                error = "Product search is temporarily unavailable."

    return render_template(
        "search_food.html",
        products=products,
        query=query,
        error=error
    )


@app.route("/food/select/<barcode>", methods=["GET", "POST"])
def select_food(barcode):
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    try:
        product = get_product(barcode)
    except (requests.RequestException, ValueError, TypeError):
        return "Unable to load product.", 502

    if product is None:
        return "Product not found or nutrition data unavailable.", 404

    if request.method == "POST":
        try:
            amount = float(request.form["amount"])

            if not math.isfinite(amount) or not 0 < amount <= 10000:
                raise ValueError

        except (ValueError, KeyError):
            flash("Please enter a valid amount.")
            return redirect(url_for("select_food", barcode=barcode))

        multiplier = amount / 100

        calories = round(product["calories"] * multiplier, 1)
        protein = round(product["protein"] * multiplier, 1)
        carbs = round(product["carbs"] * multiplier, 1)
        fat = round(product["fat"] * multiplier, 1)

        add_food(
            session["user_id"],
            product["name"],
            amount,
            calories,
            protein,
            carbs,
            fat
        )

        flash("Food added successfully.")

        return redirect(url_for("dashboard"))

    return render_template(
        "select_food.html",
        product=product
    )


@app.route("/history")
def food_history():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    selected_date = request.args.get(
        "date",
        date.today().isoformat()
    )

    try:
        datetime.strptime(selected_date, "%Y-%m-%d")
    except ValueError:
        selected_date = date.today().isoformat()

    entries = get_daily_food(
        session["user_id"],
        selected_date
    )

    totals = calculate_daily_totals(entries)

    with get_database() as connection:
        goals = connection.execute(
            "SELECT * FROM user_goals WHERE user_id = ?",
            (session["user_id"],)
        ).fetchone()

    return render_template(
        "history.html",
        entries=entries,
        totals=totals,
        goals=goals,
        selected_date=selected_date
    )


if __name__ == "__main__":
    app.run(debug=True)
