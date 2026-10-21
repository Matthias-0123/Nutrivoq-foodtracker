
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

USERNAME_PATTERN = re.compile(
    r"^[A-Za-z0-9_]{3,20}$"
)


@auth.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not USERNAME_PATTERN.fullmatch(username):
            flash(
                "Username must be 3-20 characters "
                "and contain only letters, numbers or underscores."
            )
            return render_template("register.html")

        if not EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
            flash("Please enter a valid email address.")
            return render_template("register.html")

        if not 8 <= len(password) <= 128:
            flash("Password must contain 8-128 characters.")
            return render_template("register.html")

        with get_database() as connection:
            existing_username = connection.execute(
                """
                SELECT id FROM users
                WHERE username = ? COLLATE NOCASE
                """,
                (username,)
            ).fetchone()

            existing_email = connection.execute(
                """
                SELECT id FROM users
                WHERE email = ? COLLATE NOCASE
                """,
                (email,)
            ).fetchone()

        if existing_username:
            flash("This username is already taken.")
            return render_template("register.html")

        if existing_email:
            flash("An account with this email already exists.")
            return render_template("register.html")

        password_hash = generate_password_hash(password)

        try:
            with get_database() as connection:
                connection.execute(
                    """
                    INSERT INTO users (
                        username, email, password_hash
                    )
                    VALUES (?, ?, ?)
                    """,
                    (username, email, password_hash)
                )

        except sqlite3.IntegrityError:
            flash("Username or email is already in use.")
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
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        user = None

        if (
            identifier
            and len(identifier) <= 254
            and len(password) <= 128
        ):
            with get_database() as connection:
                user = connection.execute(
                    """
                    SELECT id, username, email, password_hash
                    FROM users
                    WHERE username = ? COLLATE NOCASE
                       OR email = ? COLLATE NOCASE
                    LIMIT 1
                    """,
                    (identifier, identifier)
                ).fetchone()

        if user and check_password_hash(
            user["password_hash"],
            password
        ):
            session.clear()
            session.permanent = True

            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["email"] = user["email"]

            return redirect(url_for("dashboard"))

        flash("Invalid username, email or password.")

    return render_template("login.html")


@auth.route("/username", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def change_username():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()

        if not USERNAME_PATTERN.fullmatch(username):
            flash(
                "Username must be 3-20 characters "
                "and contain only letters, numbers or underscores."
            )
            return render_template("change_username.html")

        try:
            with get_database() as connection:
                connection.execute(
                    """
                    UPDATE users
                    SET username = ?
                    WHERE id = ?
                    """,
                    (username, session["user_id"])
                )

        except sqlite3.IntegrityError:
            flash("This username is already taken.")
            return render_template("change_username.html")

        session["username"] = username

        flash("Username updated successfully.")
        return redirect(url_for("dashboard"))

    return render_template("change_username.html")


@auth.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
