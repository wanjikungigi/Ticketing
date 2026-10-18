
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from flask import (
    Flask, g, render_template, request,
    redirect, url_for, flash, abort
)

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "change-this-development-secret"
)

DATABASE = os.environ.get("DATABASE_PATH", "festival.db")

DEFAULT_EVENT = {
    "name": "Your Festival",
    "tagline": "Good people. Great experiences.",
    "date": "Set your event date",
    "venue": "Set your venue",
    "primary_color": "#d4af37",
    "currency": "KES",
}


# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_db():
    db = get_db()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS event_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT NOT NULL,
            tagline TEXT NOT NULL,
            event_date TEXT NOT NULL,
            venue TEXT NOT NULL,
            primary_color TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ticket_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL CHECK (price >= 0),
            quantity INTEGER NOT NULL CHECK (quantity >= 0),
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS booth_packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            size TEXT NOT NULL,
            price INTEGER NOT NULL CHECK (price >= 0),
            quantity INTEGER NOT NULL CHECK (quantity >= 0),
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT UNIQUE NOT NULL,
            order_type TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            total_amount INTEGER NOT NULL CHECK (total_amount >= 0),
            payment_status TEXT NOT NULL DEFAULT 'PENDING',
            mpesa_checkout_id TEXT,
            mpesa_receipt TEXT,
            created_at TEXT NOT NULL
        );
    """)

    existing = db.execute(
        "SELECT id FROM event_settings WHERE id = 1"
    ).fetchone()

    if not existing:
        db.execute("""
            INSERT INTO event_settings
                (id, name, tagline, event_date, venue, primary_color)
            VALUES (1, ?, ?, ?, ?, ?)
        """, (
            DEFAULT_EVENT["name"],
            DEFAULT_EVENT["tagline"],
            DEFAULT_EVENT["date"],
            DEFAULT_EVENT["venue"],
            DEFAULT_EVENT["primary_color"],
        ))

        db.executemany("""
            INSERT INTO ticket_types (name, price, quantity, active)
            VALUES (?, ?, ?, 1)
        """, [
            ("Regular", 500, 500),
            ("VIP", 1500, 100),
        ])

        db.executemany("""
            INSERT INTO booth_packages
                (name, size, price, quantity, active)
            VALUES (?, ?, ?, ?, 1)
        """, [
            ("Standard Booth", "3m × 3m", 25000, 20),
            ("Premium Booth", "3m × 6m", 50000, 8),
        ])

    db.commit()


@app.before_request
def ensure_database():
    init_db()


def get_event_info():
    row = get_db().execute(
        "SELECT * FROM event_settings WHERE id = 1"
    ).fetchone()

    if row is None:
        return dict(
            name=DEFAULT_EVENT["name"],
            tagline=DEFAULT_EVENT["tagline"],
            event_date=DEFAULT_EVENT["date"],
            venue=DEFAULT_EVENT["venue"],
            primary_color=DEFAULT_EVENT["primary_color"],
        )

    return dict(row)


# --------------------------------------------------
# HOME PAGE
# --------------------------------------------------

@app.route("/")
def index():
    db = get_db()

    tickets = db.execute("""
        SELECT * FROM ticket_types
        WHERE active = 1 AND quantity > 0
        ORDER BY price ASC
    """).fetchall()

    booths = db.execute("""
        SELECT * FROM booth_packages
        WHERE active = 1 AND quantity > 0
        ORDER BY price ASC
    """).fetchall()

    return render_template(
        "index.html",
        event=get_event_info(),
        tickets=tickets,
        booths=booths,
    )


# --------------------------------------------------
# TICKET PAGE
# --------------------------------------------------

@app.route("/tickets")
def tickets_page():
    tickets = get_db().execute("""
        SELECT * FROM ticket_types
        WHERE active = 1 AND quantity > 0
        ORDER BY price ASC
    """).fetchall()

    return render_template(
        "tickets.html",
        event=get_event_info(),
        tickets=tickets,
    )


# --------------------------------------------------
# EXHIBITOR / BOOTH PAGE
# --------------------------------------------------

@app.route("/booths")
def booths_page():
    booths = get_db().execute("""
        SELECT * FROM booth_packages
        WHERE active = 1 AND quantity > 0
        ORDER BY price ASC
    """).fetchall()

    return render_template(
        "booths.html",
        event=get_event_info(),
        booths=booths,
    )


# --------------------------------------------------
# CREATE A BOOKING
# --------------------------------------------------

@app.route("/order/<kind>/<int:item_id>", methods=["POST"])
def create_order(kind, item_id):

    if kind not in ("ticket", "booth"):
        abort(400, description="Invalid booking type.")

    db = get_db()

    # Only allow known database tables.
    table = (
        "ticket_types"
        if kind == "ticket"
        else "booth_packages"
    )

    item = db.execute(
        f"SELECT * FROM {table} WHERE id = ? AND active = 1",
        (item_id,),
    ).fetchone()

    if item is None or item["quantity"] < 1:
        flash("Sorry, this option is no longer available.")
        destination = (
            "tickets_page" if kind == "ticket"
            else "booths_page"
        )
        return redirect(url_for(destination))

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()

    try:
        quantity = int(request.form.get("quantity", "1"))
    except (ValueError, TypeError):
        quantity = 0

    if not name or not email or not phone:
        flash("Please complete all your contact details.")
        return redirect(request.referrer or url_for("index"))

    if len(name) > 120 or len(email) > 254 or len(phone) > 30:
        flash("One or more fields are too long.")
        return redirect(request.referrer or url_for("index"))

    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        flash("Please enter a valid email address.")
        return redirect(request.referrer or url_for("index"))

    if quantity < 1:
        flash("Please choose a quantity of at least one.")
        return redirect(request.referrer or url_for("index"))

    if quantity > item["quantity"]:
        flash("There are not enough tickets or booths available.")
        return redirect(request.referrer or url_for("index"))

    total = int(item["price"]) * quantity
    reference = secrets.token_hex(5).upper()

    # Save the booking as pending until payment is verified.
    try:
        db.execute("""
            INSERT INTO orders (
                reference, order_type, customer_name, email, phone,
                item_id, item_name, quantity, total_amount,
                payment_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
        """, (
            reference,
            kind,
            name,
            email,
            phone,
            item_id,
            item["name"],
            quantity,
            total,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ))

        db.commit()

    except sqlite3.IntegrityError:
        db.rollback()
        flash("We couldn't create your booking. Please try again.")
        return redirect(request.referrer or url_for("index"))

    return redirect(
        url_for("order_detail", reference=reference)
    )


# --------------------------------------------------
# BOOKING CONFIRMATION
# --------------------------------------------------

@app.route("/order/success/<reference>")
def order_detail(reference):
    order = get_db().execute("""
        SELECT * FROM orders WHERE reference = ?
    """, (reference,)).fetchone()

    if order is None:
        flash("Booking reference not found.")
        return redirect(url_for("index"))

    return render_template(
        "order.html",
        event=get_event_info(),
        order=order,
    )


# --------------------------------------------------
# ADMIN DASHBOARD
# --------------------------------------------------

@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    db = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        tagline = request.form.get("tagline", "").strip()
        event_date = request.form.get("event_date", "").strip()
        venue = request.form.get("venue", "").strip()
        primary_color = request.form.get(
            "primary_color", "#d4af37"
        ).strip()

        if (
            not name or not tagline or not event_date
            or not venue
        ):
            flash("Please complete all event settings.")
            return redirect(url_for("admin_dashboard"))

        # Accept only a six-digit hexadecimal colour.
        if (
            len(primary_color) != 7
            or not primary_color.startswith("#")
            or any(c not in "0123456789abcdefABCDEF"
                   for c in primary_color[1:])
        ):
            flash("Please enter a valid colour.")
            return redirect(url_for("admin_dashboard"))

        db.execute("""
            UPDATE event_settings
            SET name = ?, tagline = ?, event_date = ?,
                venue = ?, primary_color = ?
            WHERE id = 1
        """, (
            name, tagline, event_date, venue, primary_color
        ))

        db.commit()
        flash("Event settings saved successfully.")
        return redirect(url_for("admin_dashboard"))

    orders = db.execute("""
        SELECT * FROM orders ORDER BY id DESC
    """).fetchall()

    tickets = db.execute("""
        SELECT * FROM ticket_types ORDER BY id
    """).fetchall()

    booths = db.execute("""
        SELECT * FROM booth_packages ORDER BY id
    """).fetchall()

    totals = db.execute("""
        SELECT
            COUNT(*) AS order_count,
            COALESCE(
                SUM(CASE WHEN payment_status = 'PAID'
                    THEN total_amount ELSE 0 END), 0
            ) AS paid_total,
            COALESCE(
                SUM(CASE WHEN payment_status = 'PENDING'
                    THEN total_amount ELSE 0 END), 0
            ) AS pending_total
        FROM orders
    """).fetchone()

    return render_template(
        "admin.html",
        event=get_event_info(),
        orders=orders,
        tickets=tickets,
        booths=booths,
        totals=totals,
    )


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.route("/health")
def health():
    return {
        "status": "ok",
        "application": "Festival Registration System",
    }


# --------------------------------------------------
# START APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
