
import logging
import os
import json
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from dotenv import load_dotenv

import stripe
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
import re


# --------------------------------------------------
# App configuration
# --------------------------------------------------
project_root = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(project_root, ".env")
load_dotenv(dotenv_path=dotenv_path)  # Load environment variables from local .env file.

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "auxwars-secret")


logging.basicConfig(level=logging.INFO)

#-- Stripe APIs put here--
stripe.api_key = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
if not stripe.api_key:
    logging.warning("STRIPE_API_KEY is not configured. Stripe requests will fail.")
if not STRIPE_WEBHOOK_SECRET:
    logging.warning("STRIPE_WEBHOOK_SECRET is not configured. Webhook verification will fail.")

# --------------------------------------------------
# Database setup
# --------------------------------------------------


# --------------------------------------------------
# Token product definitions
# --------------------------------------------------
TOKEN_PACKAGES = {
    "package_1": {
        "label": "1000 Tokens",
        "token_amount": 1000,
        "dollar_amount": Decimal("4.99"),
    },
    "package_2": {
        "label": "2000 Tokens",
        "token_amount": 2000,
        "dollar_amount": Decimal("9.99"),
    },
    "package_3": {
        "label": "4000 Tokens",
        "token_amount": 4000,
        "dollar_amount": Decimal("19.99"),
    },
}

# --------------------------------------------------
# Models
# --------------------------------------------------






# --------------------------------------------------
# Auth helper
# --------------------------------------------------

def get_current_user():
    """Return the logged-in user's account_management row, or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        return supabase_get_account(user_id)
    except Exception as e:
        logging.exception("Failed to fetch account for %s: %s", user_id, e)
        return None


# --------------------------------------------------
# Home and existing app routes
# --------------------------------------------------
# Leaderboard mock data - only used by /leaderboard (leaderboard.html).
mock_leaderboard_players = [
    {
        "name": "NEONPHONK",
        "elo": 2134,
        "genre": "Underground",
        "wins": 91,
        "streak": 7,
    },
    {
        "name": "BASSLINE.exe",
        "elo": 1998,
        "genre": "Hyperpop",
        "wins": 73,
        "streak": 3,
    },
    {
        "name": "VINYL_GHOST",
        "elo": 1850,
        "genre": "Hip Hop",
        "wins": 66,
        "streak": 12,
    },
]

# --------------------------------------------------
# Supabase helpers
# --------------------------------------------------

def supabase_transaction_exists(stripe_session_id):
    rows = supabase_fetch(
        "token_transactions",
        {
            "select": "id",
            "stripe_session_id": f"eq.{stripe_session_id}",
        },
    )
    return bool(rows)


def supabase_fetch(table, query_params=None):
    """Run a GET request against a Supabase (PostgREST) table."""

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError("Supabase not configured (missing SUPABASE_URL / SUPABASE_KEY).")

    rest_url = f"{supabase_url}/rest/v1/{table}"
    if query_params:
        rest_url = f"{rest_url}?{urlencode(query_params)}"

    req = Request(
        rest_url,
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Accept": "application/json",
        },
        method="GET",
    )

    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def supabase_patch(table, row_id, data):
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    url = f"{supabase_url}/rest/v1/{table}?id=eq.{row_id}"
    body = json.dumps(data).encode("utf-8")
    req = Request(url, data=body, headers={
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }, method="PATCH")
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def supabase_post(table, data):
    """Insert a row into a Supabase table using the REST API."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError("Supabase not configured (missing SUPABASE_URL / SUPABASE_KEY).")

    rest_url = f"{supabase_url}/rest/v1/{table}"
    body = json.dumps(data).encode("utf-8")

    req = Request(
        rest_url,
        data=body,
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        method="POST",
    )

    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def supabase_auth_signup(email, password, username):
    url = f"{os.getenv('SUPABASE_URL')}/auth/v1/signup"
    body = json.dumps({
        "email": email,
        "password": password,
        "data": {"username": username},
    }).encode("utf-8")
    req = Request(url, data=body, headers={
        "apikey": os.getenv("SUPABASE_KEY"),
        "Content-Type": "application/json",
    }, method="POST")
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

#login auth functions 
def supabase_auth_login(email, password):
    url = f"{os.getenv('SUPABASE_URL')}/auth/v1/token?grant_type=password"
    body = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = Request(url, data=body, headers={
        "apikey": os.getenv("SUPABASE_KEY"),
        "Content-Type": "application/json",
    }, method="POST")
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

#functions for getting the needed var

def supabase_get_account(user_id):
    rows = supabase_fetch("account_management", {"select": "*", "id": f"eq.{user_id}"})
    return rows[0] if rows else None




def fetch_supabase_leaderboard(limit: int = 20):
    return supabase_fetch(
        "leaderboard_view",
        {"select": "*", "order": "elo.desc", "limit": str(limit)},
    )


def fetch_tournament_names():
    """Distinct tournament names from match_history.which_tourney."""

    rows = supabase_fetch("match_history", {"select": "which_tourney"})
    names = {
        row["which_tourney"]
        for row in rows
        if row.get("which_tourney") is not None
    }
    return sorted(names, key=str)


def fetch_matches_for_tournament(which_tourney):
    """All match_history rows for one tournament, ordered by round."""

    return supabase_fetch(
        "match_history",
        {
            "select": "*",
            "which_tourney": f"eq.{which_tourney}",
            "order": "which_round.asc",
        },
    )

mock_battles = [
    {
        "id": 1,
        "left_name": "NEONPHONK",
        "right_name": "BASSLINE.exe",
        "genre": "Hyperpop",
        "viewers": 412,
    },
    {
        "id": 2,
        "left_name": "VINYL_GHOST",
        "right_name": "808KILLA",
        "genre": "Hip Hop",
        "viewers": 891,
    },
    {
        "id": 3,
        "left_name": "CYBERWAVE",
        "right_name": "STATIC BLOOM",
        "genre": "Underground",
        "viewers": 237,
    },
]


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/leaderboard")
def leaderboard_page():
    try:
        rows = fetch_supabase_leaderboard(limit=20)
    except Exception as e:
        logging.exception("Supabase leaderboard fetch failed: %s", e)
        rows = []

    if not rows:
        # Fallback for local dev when Supabase isn't configured yet.
        sorted_players = sorted(
            mock_leaderboard_players, key=lambda x: x["elo"], reverse=True
        )
        return render_template("leaderboard.html", players=sorted_players)

    # Map Supabase row -> template fields.
    # If your table uses different column names, adjust these fallbacks.
    mapped = []
    for r in rows:
        mapped.append(
            {
                "name": (
                    r.get("name")
                    or r.get("username")
                    or r.get("display_name")
                    or r.get("player_name")
                    or r.get("id")
                ),
                "elo": r.get("elo"),
            }
        )

    return render_template("leaderboard.html", players=mapped)


@app.route("/match-history")
def match_history_page():
    tournaments = []
    matches = []
    columns = []
    selected_tournament = request.args.get("which_tourney", "")
    error = None

    try:
        tournaments = fetch_tournament_names()
        if selected_tournament:
            matches = fetch_matches_for_tournament(selected_tournament)
            if matches:
                columns = list(matches[0].keys())
    except Exception as e:
        logging.exception("Match history fetch failed: %s", e)
        error = str(e)

    return render_template(
        "match_history.html",
        tournaments=tournaments,
        matches=matches,
        columns=columns,
        selected_tournament=selected_tournament,
        error=error,
    )


@app.route("/dashboard")
def dashboard_page():
    # Require an explicit logged-in session to view the dashboard
    if not session.get("user_id"):
        flash("Please log in to view the dashboard.", "error")
        return redirect(url_for("login"))

    user = get_current_user()
    return render_template("dashboard.html", user=user)


@app.route("/battles")
def battles():
    if not session.get("user_id"):
        flash("Please log in to view battles.", "error")
        return redirect(url_for("login"))

    return render_template("battles.html", battles=mock_battles)


@app.route("/battle/<int:battle_id>")
def battle_detail(battle_id):
    battle = next((b for b in mock_battles if b["id"] == battle_id), None)
    if battle is None:
        return redirect(url_for("battles"))
    return render_template("battle.html", battle=battle)


@app.route("/spectator/<int:battle_id>")
def spectator(battle_id):
    battle = next((b for b in mock_battles if b["id"] == battle_id), None)
    if battle is None:
        return redirect(url_for("battles"))
    return render_template("spectator.html", battle=battle)


# --------------------------------------------------
# Token purchase routes
# --------------------------------------------------

@app.route("/buy-tokens")
def buy_tokens_page():
    user = get_current_user()
    return render_template("buy_tokens.html", user=user, packages=TOKEN_PACKAGES)


@app.route("/token-balance")
def token_balance_page():
    user = get_current_user()
    if not user:
        flash("Please log in.", "error")
        return redirect(url_for("login"))
    transactions = supabase_fetch("token_transactions", {
        "select": "*", "user_id": f"eq.{user['id']}",
        "order": "created_at.desc", "limit": "10",
    })
    return render_template("token_balance.html", user=user, transactions=transactions)

@app.route("/api/tokens/balance")
def api_token_balance():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify({"token_balance": user.get("tokens", 0)})


@app.route("/purchase-success")
def purchase_success():
    session_id = request.args.get("session_id")
    product = None
    checkout_session = None

    if session_id:
        try:
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            package_id = checkout_session["metadata"]["package_id"] if "metadata" in checkout_session and "package_id" in checkout_session["metadata"] else None
            product = TOKEN_PACKAGES.get(package_id) if package_id else None
        except Exception as error:
            logging.error("Error retrieving Stripe session %s: %s", session_id, error)

    return render_template(
        "purchase_success.html",
        checkout_session=checkout_session,
        product=product,
    )


@app.route("/purchase-cancel")
def purchase_cancel():
    return render_template("purchase_cancel.html")


@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in."}), 401

    data = request.get_json(force=True, silent=True) or {}
    package_id = data.get("package_id")
    package = TOKEN_PACKAGES.get(package_id)

    if not package:
        return jsonify({"error": "Invalid token package."}), 400

    try:
        session_data = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            success_url=(
                url_for("purchase_success", _external=True)
                + "?session_id={CHECKOUT_SESSION_ID}"
            ),
            cancel_url=url_for("purchase_cancel", _external=True),
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": package["label"],
                            "description": f"{package['token_amount']} tokens package",
                        },
                        "unit_amount": int(package["dollar_amount"] * 100),
                    },
                    "quantity": 1,
                }
            ],
            metadata={
                "user_id": user["id"],   # UUID string now, not str(int)
                "package_id": package_id,
            },
        )
        return jsonify({"checkout_url": session_data.url})
    except Exception as error:
        logging.exception("Stripe checkout session creation failed")
        return jsonify({"error": "Unable to create Stripe checkout session."}), 500


@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    if not STRIPE_WEBHOOK_SECRET:
        logging.warning("No webhook secret configured. Rejecting webhook attempt.")
        return "Webhook secret not configured", 400

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        logging.error("Invalid webhook payload")
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        logging.error("Invalid webhook signature")
        return "Invalid signature", 400

    logging.info("Stripe webhook event received: %s", event["type"])

    def credit_tokens(user_id, package_id, stripe_session_id):
        if supabase_transaction_exists(stripe_session_id):
            logging.info("Already processed session %s", stripe_session_id)
            return

        package = TOKEN_PACKAGES.get(package_id)
        if not package:
            logging.error("Unknown package_id in webhook: %s", package_id)
            return

        account = supabase_get_account(user_id)
        if not account:
            logging.error("Unable to find account %s for session %s", user_id, stripe_session_id)
            return

        new_balance = account.get("tokens", 0) + package["token_amount"]
        supabase_patch("account_management", user_id, {"tokens": new_balance})
        supabase_post("token_transactions", {
            "user_id": user_id,
            "amount": package["token_amount"],
            "reason": "stripe_purchase",
            "stripe_session_id": stripe_session_id,
        })
        logging.info("Added %s tokens to user %s", package["token_amount"], user_id)

    if event["type"] == "checkout.session.completed":
        session_object = event["data"]["object"]
        metadata = session_object.get("metadata", {})
        user_id = metadata.get("user_id")
        package_id = metadata.get("package_id")
        stripe_session_id = session_object["id"]

        if not user_id or not package_id:
            logging.error("Missing metadata in session %s: %s", stripe_session_id, metadata)
            return "Missing metadata", 400

        credit_tokens(user_id, package_id, stripe_session_id)

    elif event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        metadata = payment_intent.get("metadata", {})
        user_id = metadata.get("user_id")
        package_id = metadata.get("package_id")
        stripe_session_id = metadata.get("checkout_session_id")

        if not stripe_session_id or not user_id or not package_id:
            logging.warning("Missing metadata in payment_intent")
            return jsonify({"received": True}), 200

        credit_tokens(user_id, package_id, stripe_session_id)

    return jsonify({"received": True}), 200


# --------------------------------------------------
# API endpoints
# --------------------------------------------------




@app.route("/api/tokens/history")
def api_token_history():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401
    rows = supabase_fetch("token_transactions", {
        "select": "*", "user_id": f"eq.{user['id']}", "order": "created_at.desc",
    })
    return jsonify(rows)


# ----------------------
# Authentication routes
# ----------------------

#register page

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    if not username or not email or not password or not confirm:
        flash("Please fill in all fields.", "error")
        return render_template("register.html")

    if len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return render_template("register.html")

    if password != confirm:
        flash("Passwords do not match.", "error")
        return render_template("register.html")

    email_re = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    if not re.match(email_re, email):
        flash("Please provide a valid email address.", "error")
        return render_template("register.html")

    try:
        supabase_auth_signup(email, password, username)
        flash("Account created. Please check your email to confirm, then log in.", "success")
        return redirect(url_for("login"))
    except HTTPError as e:
        body = json.loads(e.read().decode("utf-8"))
        msg = body.get("msg") or body.get("error_description") or "Unable to create account."
        flash(msg, "error")
        return render_template("register.html")
    except Exception as e:
        logging.exception("Error registering user: %s", e)
        flash("Unable to create account right now.", "error")
        return render_template("register.html")

#login page
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("username", "").strip()  # rename field to email in login.html
    password = request.form.get("password", "")
    remember = request.form.get("remember")

    if not email or not password:
        flash("Please enter email and password.", "error")
        return render_template("login.html")

    try:
        result = supabase_auth_login(email, password)
        session["user_id"] = result["user"]["id"]
        session["access_token"] = result["access_token"]
        session.permanent = bool(remember)
        return redirect(url_for("login_success"))
    except HTTPError as e:
        flash("Invalid email or password.", "error")
        return render_template("login.html")
    except Exception as e:
        logging.exception("Error during login: %s", e)
        flash("Login failed due to an internal error.", "error")
        return render_template("login.html")

#go to login success page
@app.route("/login-success")
def login_success():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    return render_template("login_success.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/battle")
def battle_redirect():
    # Friendly route to send users to the battles listing
    return redirect(url_for("battles"))


if __name__ == "__main__":
    app.run(debug=True)
