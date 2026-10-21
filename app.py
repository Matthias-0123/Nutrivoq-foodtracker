import math
import os
import re
import requests
import traceback

from datetime import date, datetime, timedelta
from dotenv import load_dotenv

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify
)
from flask_wtf.csrf import CSRFProtect

from auth import auth
from extensions import limiter
from database import get_database, initialize_database
from nutrition import calculate_calorie_goal, calculate_macros
from food import (
    add_food,
    get_daily_food,
    calculate_daily_totals,
    delete_food
)
from favorites import (
    save_favorite,
    get_favorites,
    add_favorite_to_daily_tracker,
    delete_favorite
)
from product_api import search_products, get_product
from progress import progress


load_dotenv()

app = Flask(__name__)

app.secret_key = os.environ["SECRET_KEY"]

is_production = os.getenv("FLASK_ENV") == "production"

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=is_production,
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    WTF_CSRF_TIME_LIMIT=3600
)

csrf = CSRFProtect(app)
limiter.init_app(app)

app.register_blueprint(auth)
app.register_blueprint(progress)

initialize_database()


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(self), microphone=(), geolocation=()"
    )

    if is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000"
        )

    if "user_id" in session:
        response.headers["Cache-Control"] = "no-store"

    return response


@app.errorhandler(413)
def request_too_large(error):
    return "Request too large.", 413


@app.errorhandler(429)
def too_many_requests(error):
    return "Too many requests. Please try again later.", 429


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
@limiter.limit("30 per minute")
def search_products_api():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    query = request.args.get("query", "").strip()

    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid page"}), 400

    if page < 1 or page > 1000:
        return jsonify({"error": "Invalid page"}), 400

    if len(query) < 3:
        return jsonify({
            "products": [],
            "page": 1,
            "total_pages": 0,
            "total_results": 0
        })

    if len(query) > 100:
        return jsonify({"error": "Search query too long"}), 400

    try:
        results = search_products(query, page)
        return jsonify(results)

    except Exception:
        app.logger.exception("Product search failed")
        return jsonify({
            "error": "Product search unavailable"
        }), 502




@app.route("/setup", methods=["GET", "POST"])
def setup():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    user_id = session["user_id"]

    with get_database() as connection:
        current_goals = connection.execute(
            "SELECT * FROM user_goals WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    if request.method == "POST":
        try:
            weight = float(request.form["weight"])
            height = float(request.form["height"])
            age = int(request.form["age"])
            sex = request.form["sex"]
            activity_level = request.form["activity_level"]
            goal = request.form.get("goal", "maintain")

            if not all(
                math.isfinite(value)
                for value in (weight, height)
            ):
                raise ValueError

            if not 30 <= weight <= 400:
                raise ValueError

            if not 100 <= height <= 250:
                raise ValueError

            if not 18 <= age <= 120:
                raise ValueError

            if sex not in ("male", "female"):
                raise ValueError

            valid_activity_levels = {
                "sedentary": 1.2,
                "light": 1.375,
                "moderate": 1.55,
                "active": 1.725,
                "very_active": 1.9
            }

            if activity_level in valid_activity_levels:
                activity_multiplier = valid_activity_levels[activity_level]
            else:
                activity_multiplier = float(activity_level)

                if not math.isfinite(activity_multiplier):
                    raise ValueError

                if activity_multiplier not in valid_activity_levels.values():
                    raise ValueError

            if goal not in ("gain", "maintain", "lose"):
                raise ValueError

        except (ValueError, TypeError, KeyError):
            flash("Please enter valid profile information.")
            return redirect(url_for("setup"))

        calorie_goal = calculate_calorie_goal(
            weight,
            height,
            age,
            sex,
            activity_multiplier,
            goal
        )

        goals = calculate_macros(
            calorie_goal,
            weight,
            goal
        )

        with get_database() as connection:
            connection.execute(
                """
                INSERT INTO user_goals (
                    user_id,
                    calories,
                    protein,
                    carbs,
                    fat,
                    goal,
                    age,
                    sex,
                    height,
                    weight,
                    activity_level
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    calories = excluded.calories,
                    protein = excluded.protein,
                    carbs = excluded.carbs,
                    fat = excluded.fat,
                    goal = excluded.goal,
                    age = excluded.age,
                    sex = excluded.sex,
                    height = excluded.height,
                    weight = excluded.weight,
                    activity_level = excluded.activity_level
                """,
                (
                    user_id,
                    goals["calories"],
                    goals["protein"],
                    goals["carbs"],
                    goals["fat"],
                    goal,
                    age,
                    sex,
                    height,
                    weight,
                    activity_level
                )
            )

        flash("Your nutrition goals have been updated.")
        return redirect(url_for("dashboard"))

    return render_template(
        "index.html",
        current_goals=current_goals
    )


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

            nutrition_values = (
                calories, protein, carbs, fat
            )

            if not all(
                math.isfinite(value) and 0 <= value <= 100000
                for value in nutrition_values
            ):
                raise ValueError

        except (ValueError, KeyError):
            flash("Please enter valid food information.")
            return redirect(url_for("search_food", tab="manual"))

        add_food(
            session["user_id"],
            food_name,
            amount,
            calories,
            protein,
            carbs,
            fat
        )

        return redirect(url_for("search_food", tab="manual"))

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

    user_id = session["user_id"]
    selected_date = request.args.get("date", date.today().isoformat())

    try:
        datetime.strptime(selected_date, "%Y-%m-%d")
    except ValueError:
        selected_date = date.today().isoformat()

    history_entries = get_daily_food(user_id, selected_date)
    history_totals = calculate_daily_totals(history_entries)

    with get_database() as connection:
        goals = connection.execute(
            "SELECT * FROM user_goals WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    return render_template(
        "search_food.html",
        favorites=get_favorites(user_id),
        history_entries=history_entries,
        history_totals=history_totals,
        history_goals=goals,
        selected_date=selected_date,
        active_tab=request.args.get("tab", "search")
    )


@app.route("/food/select/<barcode>", methods=["GET", "POST"])
@limiter.limit("60 per minute")
def select_food(barcode):
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    if not re.fullmatch(r"[0-9]{8,14}", barcode):
        return "Invalid barcode.", 400

    try:
        product = get_product(barcode)
    except (
        requests.RequestException,
        ValueError,
        TypeError
    ):
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

        nutrition_values = (
            calories, protein, carbs, fat
        )

        if not all(
            math.isfinite(value) and 0 <= value <= 100000
            for value in nutrition_values
        ):
            flash("Invalid nutritional information.")
            return redirect(url_for("select_food", barcode=barcode))

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


@app.route("/favorites")
def favorites_page():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    favorites = get_favorites(session["user_id"])

    return render_template(
        "favorites.html",
        favorites=favorites
    )


@app.route("/favorites/save/<int:entry_id>", methods=["POST"])
def save_favorite_entry(entry_id):
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    saved = save_favorite(session["user_id"], entry_id)

    if saved:
        flash("Food saved to favorites.")
    else:
        flash("Food entry not found.")

    return redirect(url_for("dashboard"))


@app.route("/favorites/add/<int:favorite_id>", methods=["POST"])
def add_favorite_entry(favorite_id):
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    try:
        amount = float(request.form["amount"])

        if not math.isfinite(amount) or not 0 < amount <= 10000:
            raise ValueError

    except (ValueError, KeyError):
        flash("Please enter a valid amount.")
        return redirect(url_for("search_food", tab="favorites"))

    added = add_favorite_to_daily_tracker(
        session["user_id"],
        favorite_id,
        amount
    )

    if added:
        flash("Favorite added to today's food.")
        return redirect(url_for("search_food", tab="favorites"))

    flash("Favorite not found.")
    return redirect(url_for("search_food", tab="favorites"))


@app.route("/favorites/delete/<int:favorite_id>", methods=["POST"])
def delete_favorite_entry(favorite_id):
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    delete_favorite(session["user_id"], favorite_id)

    flash("Favorite removed.")
    return redirect(url_for("search_food", tab="favorites"))


@app.route("/food/scan")
def scan_food():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    return render_template("scan_food.html")


if __name__ == "__main__":
    app.run(debug=not is_production)
