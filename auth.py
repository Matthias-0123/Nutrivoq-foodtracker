
import re
import sqlite3

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from database import get_database
from extensions import limiter

auth = Blueprint("auth", __name__)

EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


@auth.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if (
            len(email) > 254
            or not EMAIL_PATTERN.fullmatch(email)
            or not 8 <= len(password) <= 128
        ):
            flash(
                "Enter a valid email and a password "
                "between 8 and 128 characters."
            )
            return render_template("register.html")

        password_hash = generate_password_hash(password)

        try:
            with get_database() as connection:
                connection.execute(
                    """
                    INSERT INTO users (email, password_hash)
                    VALUES (?, ?)
                    """,
                    (email, password_hash)
                )

        except sqlite3.IntegrityError:
            flash("An account with this email already exists.")
            return render_template("register.html")

        flash("Account created successfully. Please log in.")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = None

        if len(email) <= 254 and len(password) <= 128:
            with get_database() as connection:
                user = connection.execute(
                    """
                    SELECT id, email, password_hash
                    FROM users
                    WHERE email = ?
                    """,
                    (email,)
                ).fetchone()

        if user and check_password_hash(
            user["password_hash"],
            password
        ):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["email"] = user["email"]

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


@auth.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
