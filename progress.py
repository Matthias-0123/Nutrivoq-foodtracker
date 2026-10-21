
import io
import uuid
from datetime import datetime
from pathlib import Path

from flask import (
    Blueprint, abort, flash, redirect,
    render_template, request, send_file,
    session, url_for
)
from PIL import Image, ImageOps, UnidentifiedImageError

from database import get_database


progress = Blueprint("progress", __name__)

PHOTO_DIRECTORY = Path(__file__).resolve().parent / "private_progress_photos"


@progress.route("/progress", methods=["GET", "POST"])
def tracker():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        try:
            weight = float(request.form.get("weight", ""))
            taken_at = datetime.fromisoformat(request.form.get("taken_at", ""))

            if not 0 < weight <= 700 or taken_at > datetime.now():
                raise ValueError

            uploaded = request.files.get("photo")

            if not uploaded or not uploaded.filename:
                raise ValueError

            raw = uploaded.read(7 * 1024 * 1024 + 1)

            if len(raw) > 7 * 1024 * 1024:
                raise ValueError

            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ("JPEG", "PNG", "WEBP"):
                    raise ValueError

                source.verify()

            with Image.open(io.BytesIO(raw)) as source:
                photo = ImageOps.exif_transpose(source)
                photo.thumbnail((1600, 1600))
                photo = photo.convert("RGB")

                PHOTO_DIRECTORY.mkdir(parents=True, exist_ok=True)

                filename = uuid.uuid4().hex + ".jpg"
                photo.save(
                    PHOTO_DIRECTORY / filename,
                    format="JPEG",
                    quality=85
                )

            try:
                with get_database() as connection:
                    connection.execute("""
                        INSERT INTO progress_entries
                        (user_id, weight, taken_at, photo_filename)
                        VALUES (?, ?, ?, ?)
                    """, (
                        session["user_id"],
                        weight,
                        taken_at.isoformat(timespec="minutes"),
                        filename
                    ))

            except Exception:
                (PHOTO_DIRECTORY / filename).unlink(missing_ok=True)
                raise

            flash("Progress entry saved.")
            return redirect(url_for("progress.tracker"))

        except (
            ValueError,
            OSError,
            UnidentifiedImageError,
            Image.DecompressionBombError
        ):
            flash("Enter a valid weight, date and photo (max 7 MB).")

    with get_database() as connection:
        entries = [
            dict(row)
            for row in connection.execute("""
                SELECT id, weight, taken_at
                FROM progress_entries
                WHERE user_id = ?
                ORDER BY taken_at, id
            """, (session["user_id"],)).fetchall()
        ]

    return render_template(
        "progress.html",
        entries=entries,
        now=datetime.now().strftime("%Y-%m-%dT%H:%M")
    )


@progress.route("/progress/photo/<int:entry_id>")
def photo(entry_id):
    if "user_id" not in session:
        abort(403)

    with get_database() as connection:
        entry = connection.execute("""
            SELECT photo_filename
            FROM progress_entries
            WHERE id = ? AND user_id = ?
        """, (entry_id, session["user_id"])).fetchone()

    if not entry:
        abort(404)

    return send_file(
        PHOTO_DIRECTORY / entry["photo_filename"],
        mimetype="image/jpeg",
        conditional=True
    )


@progress.route("/progress/delete/<int:entry_id>", methods=["POST"])
def delete_entry(entry_id):
    if "user_id" not in session:
        abort(403)

    with get_database() as connection:
        entry = connection.execute("""
            SELECT photo_filename
            FROM progress_entries
            WHERE id = ? AND user_id = ?
        """, (entry_id, session["user_id"])).fetchone()

        if not entry:
            abort(404)

        connection.execute("""
            DELETE FROM progress_entries
            WHERE id = ? AND user_id = ?
        """, (entry_id, session["user_id"]))

    (PHOTO_DIRECTORY / entry["photo_filename"]).unlink(missing_ok=True)

    flash("Progress entry deleted.")
    return redirect(url_for("progress.tracker"))
