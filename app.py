# app.py
import logging
import os
import json
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from datetime import datetime, timedelta, timezone

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
        account = supabase_get_account(user_id)
        if account is not None:
            # Normalize so all pages can consistently use user.token_balance,
            # regardless of the underlying Supabase column name ("tokens").
            account["tokens"] = account.get("tokens", 0)
        return account
    except Exception as e:
        logging.exception("Failed to fetch account for %s: %s", user_id, e)
        return None
    

# --------------------------------------------------
# Template context processor
# --------------------------------------------------
@app.context_processor
def inject_user():
    """Inject current user info into all pages."""
    user = get_current_user()
    return {"current_user": user}


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

from urllib.error import HTTPError







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

    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        print("FAILED URL:", req.full_url, flush=True)
        print("STATUS:", e.code, flush=True)
        print("BODY:", e.read().decode(), flush=True)
        raise

def supabase_fetch_one(table, query={}):
    results = supabase_fetch(table, query)

    if results and len(results) > 0:
        return results[0]

    return None


def supabase_patch(table, record_id, data, id_column="id"):
    """Update a row in a Supabase table by a given id column (default: id)."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError("Supabase not configured (missing SUPABASE_URL / SUPABASE_KEY).")

    rest_url = f"{supabase_url}/rest/v1/{table}?{id_column}=eq.{record_id}"
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
        method="PATCH",
    )

    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        print("FAILED URL:", rest_url, flush=True)
        print("STATUS:", e.code, flush=True)
        print("BODY:", e.read().decode(), flush=True)
        raise



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

    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        print("FAILED URL:", rest_url, flush=True)
        print("STATUS:", e.code, flush=True)
        print("BODY:", e.read().decode(), flush=True)
        raise

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


import re

def extract_spotify_embed_url(raw_input):
    """Accepts either a raw Spotify embed URL or a full <iframe> snippet
    and returns just the embed URL."""

    raw_input = raw_input.strip()

    # If it's already a plain URL, just return it as-is.
    if raw_input.startswith("http"):
        return raw_input

    # Otherwise, try to pull the src="..." value out of an iframe tag.
    match = re.search(r'src="([^"]+)"', raw_input)
    if match:
        return match.group(1)

    return raw_input  # fallback: return as-is, will fail validation below

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

    if not session.get("user_id"):
        flash("Please log in to view the dashboard.", "error")
        return redirect(url_for("login"))

    user = get_current_user()

    transactions = supabase_fetch(
        "token_transactions",
        {
            "select": "*",
            "user_id": f"eq.{user['id']}",
            "order": "created_at.desc",
            "limit": "10",
        },
    )

    return render_template(
        "dashboard.html",
        user=user,
        transactions=transactions,
    )


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
    return render_template("spectator_page.html", battle=battle)


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
    return jsonify({"token_balance": user.get("tokens")})


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

    # fill all the field error
    if not username or not email or not password or not confirm:
        flash("Please fill in all fields.", "error")
        return render_template("register.html")

    # pass less than 6 error 
    if len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return render_template("register.html")

    # pass not equal to confirm pass error
    if password != confirm:
        flash("Passwords do not match.", "error")
        return render_template("register.html")
    
    #valid email error

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

    email = request.form.get("email", "").strip()  # rename field to email in login.html
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

@app.route("/tournaments")
def tournaments_page():

    try:
        tournaments = supabase_fetch(
            "tournaments",
            {
                "select": "id,title,genre,topic,buy_in,status,current_players,started,max_players,created_at,champion_seat,champion_username",
                "order": "created_at.desc",
            },
        )
    except Exception as e:
        logging.exception("Failed fetching tournaments: %s", e)
        tournaments = []
        flash("Unable to load tournaments right now. Please try again later.", "error")

    return render_template(
        "tournament_browse.html",
        tournaments=tournaments,
    )

@app.route("/create-tournament")
def create_tournament_page():

    return render_template("create_tournament.html")

@app.route("/create-tournament", methods=["POST"])
def create_tournament():

    user = get_current_user()

    title = request.form.get("title")
    genre = request.form.get("genre")
    topic = request.form.get("topic")
    buy_in = int(request.form.get("buy_in"))

    tournament = supabase_post(
        "tournaments",
        {
            "title": title,
            "genre": genre,
            "topic": topic,
            "buy_in": buy_in,
            "max_players": 8,
            "current_players": 0,
        },
    )

    return redirect(url_for("tournaments_page"))



@app.route("/submit-songs/<tournament_id>", methods=["GET", "POST"])
def submit_songs(tournament_id):

    if request.method == "GET":

        tournament = supabase_fetch_one(
            "tournaments",
            {
                "id": f"eq.{tournament_id}",
            },
        )

        return render_template(
            "song_submission.html",
            tournament=tournament,
        )

    # POST logic below

    user = get_current_user()

    if not user:
        flash("Please log in to submit songs.", "error")
        return redirect(url_for("login"))

    embed1 = extract_spotify_embed_url(request.form.get("embed1", ""))
    embed2 = extract_spotify_embed_url(request.form.get("embed2", ""))
    embed3 = extract_spotify_embed_url(request.form.get("embed3", ""))

    if not embed1 or not embed2 or not embed3:
        flash("Please submit all three Spotify embed links.", "error")
        return redirect(
            url_for(
                "submit_songs",
                tournament_id=tournament_id,
            )
        )

    valid_prefix = "https://open.spotify.com/embed/"
    for embed in (embed1, embed2, embed3):
        if not embed.startswith(valid_prefix):
            flash("Please submit valid Spotify embed links (Share → Embed track).", "error")
            return redirect(
                url_for(
                    "submit_songs",
                    tournament_id=tournament_id,
                )
            )

    supabase_post(
        "song_submissions",
        {
            "tournament_id": tournament_id,
            "user_id": user["id"],
            "spotify_embed_1": embed1,
            "spotify_embed_2": embed2,
            "spotify_embed_3": embed3,
            "submitted_at": datetime.utcnow().isoformat() + "Z",
        },
    )

    return redirect(
        url_for(
            "battle_accept_page",
            tournament_id=tournament_id,
        )
    )

@app.route("/battle-accept/<tournament_id>")
def battle_accept_page(tournament_id):

    user = get_current_user()

    tournament = supabase_fetch_one(
        "tournaments",
        {
            "id": f"eq.{tournament_id}",
        },
    )

    players = supabase_fetch(
    "tournament_players",
    {
        "select": "*",
        "tournament_id": f"eq.{tournament_id}",
    },

    )

    return render_template(
        "battle_accept.html",
        tournament=tournament,
        players=players,
        user=user,
    )


from flask import jsonify

@app.route("/tournament-status/<tournament_id>")
def tournament_status(tournament_id):

    tournament = supabase_fetch_one(
        "tournaments",
        {
            "id": f"eq.{tournament_id}",
        },
    )

    players = supabase_fetch(
        "tournament_players",
        {
            "select": "*",
            "tournament_id": f"eq.{tournament_id}",
        },
    )

    return jsonify({
        "current_players": tournament["current_players"],
        "started": tournament["started"],
        "players": players,
    })



import random

@app.route("/join-tournament/<tournament_id>", methods=["POST"])
def join_tournament(tournament_id):

    user = get_current_user()

    tournament = supabase_fetch_one(
        "tournaments",
        {
            "id": f"eq.{tournament_id}",
        },
    )

    buy_in = tournament["buy_in"]

    if user["tokens"] < buy_in:
        flash("Not enough tokens.", "error")
        return redirect(url_for("tournaments_page"))

    new_balance = user["tokens"] - buy_in

    supabase_patch(
        "account_management",
        user["id"],
        {
            "tokens": new_balance,
        },
    )

    current_players = tournament["current_players"] + 1

    supabase_patch(
        "tournaments",
        tournament_id,
        {
            "current_players": current_players,
        },
    )

    seat_number = current_players

    supabase_post(
        "tournament_players",
        {
            "tournament_id": tournament_id,
            "user_id": user["id"],
            "seat_number": seat_number,
        },
    )

    supabase_post(
        "token_transactions",
        {
            "user_id": user["id"],
            "amount": -buy_in,
            "match_id": None,
            "stripe_session_id": None,
            "transaction_type": "debit",
            "tournament_id": tournament_id,
            "description": tournament["title"],
            "reason": "tournament_buyin",
        },
    )

    if current_players >= 8:

        supabase_patch(
            "tournaments",
            tournament_id,
            {
                "started": True,
                "status": "active",
            },
        )

        generate_bracket(tournament_id)

    return redirect(
        url_for(
            "tournament_waiting_page",
            tournament_id=tournament_id,
        )
    )


def generate_bracket(tournament_id):
    players = supabase_fetch(
        "tournament_players",
        {"select": "*", "tournament_id": f"eq.{tournament_id}"},
    )

    shuffled = players.copy()
    random.shuffle(shuffled)

    for i in range(0, len(shuffled), 2):
        p1 = shuffled[i]
        p2 = shuffled[i + 1]
        slot = (i // 2) + 1

        p1_submission = supabase_fetch_one(
            "song_submissions",
            {"tournament_id": f"eq.{tournament_id}", "user_id": f"eq.{p1['user_id']}"},
        )
        p2_submission = supabase_fetch_one(
            "song_submissions",
            {"tournament_id": f"eq.{tournament_id}", "user_id": f"eq.{p2['user_id']}"},
        )

        is_first_match = (slot == 1)

        supabase_post(
            "match_history",
            {
                "which_tourney": tournament_id,
                "which_round": 4,
                "bracket_slot": slot,
                "player1_id": p1["user_id"],
                "player2_id": p2["user_id"],
                "p1_seat": p1["seat_number"],
                "p2_seat": p2["seat_number"],
                "p1_song": p1_submission["spotify_embed_1"] if p1_submission else None,
                "p2_song": p2_submission["spotify_embed_1"] if p2_submission else None,
                "p1_votes": 0,
                "p2_votes": 0,
                # Only match 1 is live; the rest wait their turn.
                "current_phase": "live" if is_first_match else "pending",
                "voting_ends_at": None,
                "processed": False,
            },
        )


@app.route("/waiting/<tournament_id>")
def tournament_waiting_page(tournament_id):

    tournament = supabase_fetch_one(
        "tournaments",
        {
            "id": f"eq.{tournament_id}",
        },
    )

    players = supabase_fetch(
        "tournament_players",
        {
            "select": "*",
            "tournament_id": f"eq.{tournament_id}",
        },
    )

    return render_template(
        "tournament_waiting.html",
        tournament=tournament,
        players=players,
    )

def build_bracket_layout(all_matches, username_by_id):
    """Builds a fixed 4->2->1 bracket tree. Winners of completed matches are
    projected into their next-round slot immediately, even if the actual
    next-round match_history row hasn't been created yet by advance_rounds()."""

    BOX_W = 200
    BOX_H = 72
    ROW_H = 36
    PAIR_GAP = 48
    COL_GAP = 80

    def real_match(round_, slot):
        return next(
            (mm for mm in all_matches if mm["which_round"] == round_ and mm["bracket_slot"] == slot),
            None,
        )

    def display_from_real(m, label_winner=False):
        p1_won = m["current_phase"] == "complete" and (m.get("p1_votes") or 0) >= (m.get("p2_votes") or 0)
        p2_won = m["current_phase"] == "complete" and not p1_won
        return {
            "p1_username": username_by_id.get(m["player1_id"], "Unknown"),
            "p2_username": username_by_id.get(m["player2_id"], "Unknown"),
            "p1_seat": m["p1_seat"], "p2_seat": m["p2_seat"],
            "p1_won": p1_won, "p2_won": p2_won,
            "p1_label": " WINNER" if (p1_won and label_winner) else "",
            "p2_label": " WINNER" if (p2_won and label_winner) else "",
            "p1_filled": True, "p2_filled": True,
            "complete": m["current_phase"] == "complete",
        }

    def empty_slot():
        return {
            "p1_username": "TBD", "p2_username": "TBD",
            "p1_seat": None, "p2_seat": None,
            "p1_won": False, "p2_won": False,
            "p1_label": "", "p2_label": "",
            "p1_filled": False, "p2_filled": False,
            "complete": False,
        }

    def advanced_occupant(slot_display):
        """Returns (seat, username) of the winner of a completed slot, or None."""
        if not slot_display["complete"]:
            return None
        if slot_display["p1_won"]:
            return slot_display["p1_seat"], slot_display["p1_username"]
        return slot_display["p2_seat"], slot_display["p2_username"]

    def project_slot(left, right):
        """Builds a display dict for a not-yet-created next-round match,
        filling in whichever side(s) have a known winner already."""
        slot = empty_slot()
        occ1 = advanced_occupant(left)
        occ2 = advanced_occupant(right)
        if occ1:
            slot["p1_seat"], slot["p1_username"] = occ1
            slot["p1_filled"] = True
        if occ2:
            slot["p2_seat"], slot["p2_username"] = occ2
            slot["p2_filled"] = True
        return slot

    # Quarterfinals always exist once the bracket is generated.
    qf = []
    for i in range(1, 5):
        m = real_match(4, i)
        qf.append(display_from_real(m) if m else empty_slot())

    # Semis: use the real row if the cron has created it; otherwise project
    # from the two feeding QF matches so a winner shows up as soon as their
    # own match ends, without waiting on their future opponent.
    semi = []
    for i in range(1, 3):
        m = real_match(2, i)
        if m:
            semi.append(display_from_real(m))
        else:
            semi.append(project_slot(qf[(i - 1) * 2], qf[(i - 1) * 2 + 1]))

    # Final: same idea, and this is the ONLY box that gets the "WINNER" label.
    m = real_match(1, 1)
    if m:
        final = [display_from_real(m, label_winner=True)]
    else:
        final = [project_slot(semi[0], semi[1])]

    qf_top = [i * (BOX_H + PAIR_GAP) for i in range(4)]
    qf_center = [t + BOX_H / 2 for t in qf_top]

    semi_center = [
        (qf_center[0] + qf_center[1]) / 2,
        (qf_center[2] + qf_center[3]) / 2,
    ]
    semi_top = [c - BOX_H / 2 for c in semi_center]

    final_center = (semi_center[0] + semi_center[1]) / 2
    final_top = final_center - BOX_H / 2

    col_x = [40, 40 + BOX_W + COL_GAP, 40 + 2 * (BOX_W + COL_GAP)]

    boxes = []
    for i, m in enumerate(qf):
        boxes.append({**m, "x": col_x[0], "y": qf_top[i], "w": BOX_W, "h": BOX_H, "row_h": ROW_H})
    for i, m in enumerate(semi):
        boxes.append({**m, "x": col_x[1], "y": semi_top[i], "w": BOX_W, "h": BOX_H, "row_h": ROW_H})
    boxes.append({**final[0], "x": col_x[2], "y": final_top, "w": BOX_W, "h": BOX_H, "row_h": ROW_H})

    connectors = []
    mid_x_1 = col_x[0] + BOX_W + COL_GAP / 2
    for pair_idx in range(2):
        top_c = qf_center[pair_idx * 2]
        bot_c = qf_center[pair_idx * 2 + 1]
        target_c = semi_center[pair_idx]
        connectors.append({"x1": col_x[0] + BOX_W, "y1": top_c, "x2": mid_x_1, "y2": top_c})
        connectors.append({"x1": col_x[0] + BOX_W, "y1": bot_c, "x2": mid_x_1, "y2": bot_c})
        connectors.append({"x1": mid_x_1, "y1": top_c, "x2": mid_x_1, "y2": bot_c})
        connectors.append({"x1": mid_x_1, "y1": target_c, "x2": col_x[1], "y2": target_c})

    mid_x_2 = col_x[1] + BOX_W + COL_GAP / 2
    connectors.append({"x1": col_x[1] + BOX_W, "y1": semi_center[0], "x2": mid_x_2, "y2": semi_center[0]})
    connectors.append({"x1": col_x[1] + BOX_W, "y1": semi_center[1], "x2": mid_x_2, "y2": semi_center[1]})
    connectors.append({"x1": mid_x_2, "y1": semi_center[0], "x2": mid_x_2, "y2": semi_center[1]})
    connectors.append({"x1": mid_x_2, "y1": final_center, "x2": col_x[2], "y2": final_center})

    return {
        "boxes": boxes,
        "connectors": connectors,
        "width": col_x[2] + BOX_W + 40,
        "height": qf_top[3] + BOX_H + 80,
        "final_center": final_center,
    }

@app.route("/battle-start/<tournament_id>")
def battle_start_page(tournament_id):

    tournament = supabase_fetch_one("tournaments", {"id": f"eq.{tournament_id}"})

    all_matches = supabase_fetch(
        "match_history",
        {
            "select": "*",
            "which_tourney": f"eq.{tournament_id}",
            "order": "which_round.asc,bracket_slot.asc",
        },
    )

    if not all_matches:
        flash("No matches found.", "error")
        return redirect(url_for("tournaments_page"))

    # Tournament fully complete: final match (round 1) is complete.
    final_match = next((m for m in all_matches if m["which_round"] == 1), None)
    tournament_complete = final_match is not None and final_match["current_phase"] == "complete"

    user_ids = list({m["player1_id"] for m in all_matches} | {m["player2_id"] for m in all_matches})
    ids_filter = ",".join(user_ids)
    accounts = supabase_fetch("account_management", {"select": "id,username", "id": f"in.({ids_filter})"})
    username_by_id = {a["id"]: a["username"] for a in accounts}

    bracket_layout = build_bracket_layout(all_matches, username_by_id)

    champion = None
    if tournament_complete:
        p1_won = (final_match.get("p1_votes") or 0) >= (final_match.get("p2_votes") or 0)
        champ_id = final_match["player1_id"] if p1_won else final_match["player2_id"]
        champ_seat = final_match["p1_seat"] if p1_won else final_match["p2_seat"]
        champ_acct = supabase_get_account(champ_id)
        champion = {"seat": champ_seat, "username": champ_acct["username"] if champ_acct else "Unknown"}

        supabase_patch("tournaments", tournament_id, {
            "status": "complete",
            "champion_seat": champ_seat,
            "champion_username": champion["username"],
        })

    return render_template(
        "battle_start.html",
        tournament=tournament,
        bracket_layout=bracket_layout,
        tournament_complete=tournament_complete,
        champion=champion,
    )

@app.route("/battle-game-redirect/<tournament_id>")
def battle_game_redirect(tournament_id):
    matches = supabase_fetch(
        "match_history",
        {
            "select": "*",
            "which_tourney": f"eq.{tournament_id}",
            "current_phase": "eq.live",   # <-- key change: phase, not round
            "limit": "1",
        },
    )

    if not matches:
        flash("No active match found.", "error")
        return redirect(url_for("tournaments_page"))

    match = matches[0]

    return redirect(
        url_for("battle_game_page", match_index=match["index"])
    )




import uuid

@app.route("/battle-game/<match_index>")
def battle_game_page(match_index):
    try:
        uuid.UUID(match_index)
    except ValueError:
        flash("Invalid match link.", "error")
        return redirect(url_for("tournaments_page"))

    match = supabase_fetch_one(
        "match_history",
        {"index": f"eq.{match_index}"},
    )

    if not match:
        flash("Match not found.", "error")
        return redirect(url_for("tournaments_page"))

    if match["current_phase"] != "live":
        flash("This match isn't live right now.", "error")
        return redirect(
            url_for("battle_game_redirect", tournament_id=match["which_tourney"])
        )

    p1_account = supabase_get_account(match["player1_id"])
    p2_account = supabase_get_account(match["player2_id"])

    return render_template(
        "battle_game.html",
        match=match,
        p1_username=p1_account["username"] if p1_account else "Unknown",
        p2_username=p2_account["username"] if p2_account else "Unknown",
    )

    
@app.route("/vote/<match_index>/<side>", methods=["POST"])
def cast_vote(match_index, side):
    if side not in ("p1", "p2"):
        return jsonify({"error": "Invalid side"}), 400

    match = supabase_fetch_one("match_history", {"index": f"eq.{match_index}"})

    if not match:
        return jsonify({"error": "Match not found"}), 404

    if match["current_phase"] != "voting":
        return jsonify({"error": "Voting closed"}), 400

    voting_ends_at = datetime.fromisoformat(match["voting_ends_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > voting_ends_at:
        return jsonify({"error": "Voting window has ended"}), 400

    if side == "p1":
        new_votes = (match.get("p1_votes") or 0) + 1
        supabase_patch("match_history", match_index, {"p1_votes": new_votes}, id_column="index")
    else:
        new_votes = (match.get("p2_votes") or 0) + 1
        supabase_patch("match_history", match_index, {"p2_votes": new_votes}, id_column="index")

    return jsonify({
        "p1_votes": new_votes if side == "p1" else match.get("p1_votes") or 0,
        "p2_votes": new_votes if side == "p2" else match.get("p2_votes") or 0,
    })



@app.route("/start-voting/<match_index>", methods=["POST"])
def start_voting(match_index):
    match = supabase_fetch_one("match_history", {"index": f"eq.{match_index}"})
    if not match or match["current_phase"] != "live":
        return jsonify({"error": "Invalid match state"}), 400

    supabase_patch("match_history", match_index, {
        "current_phase": "voting",
        "voting_ends_at": (datetime.utcnow() + timedelta(seconds=30)).isoformat() + "Z",
    }, id_column="index")

    return jsonify({"status": "voting_started"})



@app.route("/next-match-ready/<tournament_id>")
def next_match_ready(tournament_id):
    live_match = supabase_fetch(
        "match_history",
        {"select": "index", "which_tourney": f"eq.{tournament_id}",
         "current_phase": "eq.live", "limit": "1"},
    )
    tournament = supabase_fetch_one("tournaments", {"id": f"eq.{tournament_id}"})
    return jsonify({
        "ready": bool(live_match),
        "match_index": live_match[0]["index"] if live_match else None,
        "tournament_complete": tournament.get("status") == "complete",
    })


@app.route("/match-status/<match_index>")
def match_status(match_index):
    match = supabase_fetch_one("match_history", {"index": f"eq.{match_index}"})
    if not match:
        return jsonify({"error": "Match not found"}), 404

    winner = None
    if match["current_phase"] == "complete":
        winner = "p1" if (match.get("p1_votes") or 0) >= (match.get("p2_votes") or 0) else "p2"

    return jsonify({
        "current_phase": match["current_phase"],
        "which_tourney": match["which_tourney"],
        "p1_votes": match.get("p1_votes") or 0,
        "p2_votes": match.get("p2_votes") or 0,
        "voting_ends_at": match.get("voting_ends_at"),
        "winner": winner,
    })


# --------------------------------------------------
# Dev-only testing helpers
# --------------------------------------------------

def seed_dev_tournament():
    tournament = supabase_post("tournaments", {
        "title": "DEV TEST",
        "genre": "Test",
        "topic": "Test topic",
        "buy_in": 0,
        "status": "active",
        "current_players": 7,
        "started": False,
        "max_players": 8,
    })
    tournament_id = tournament[0]["id"]

    for i in range(1, 8):
        acct = supabase_post("account_management", {
            "id": str(uuid.uuid4()),
            "username": f"DEVPLAYER{i}",
            "tokens": 1000,
            "elo": 1000,
        })[0]

        supabase_post("tournament_players", {
            "tournament_id": tournament_id,
            "user_id": acct["id"],
            "seat_number": i,
        })
        supabase_post("song_submissions", {
            "tournament_id": tournament_id,
            "user_id": acct["id"],
            "spotify_embed_1": "https://open.spotify.com/embed/track/4uLU6hMCjMI75M1A2tKUQC",
            "spotify_embed_2": "https://open.spotify.com/embed/track/4uLU6hMCjMI75M1A2tKUQC",
            "spotify_embed_3": "https://open.spotify.com/embed/track/4uLU6hMCjMI75M1A2tKUQC",
            "submitted_at": datetime.utcnow().isoformat() + "Z",
        })

    logging.info("Seeded dev tournament: %s", tournament_id)
    return tournament_id


@app.route("/dev/seed-tournament", methods=["POST"])
def dev_seed_tournament():
    if not app.debug:
        abort(404)

    cleanup_dev_tournament()

    tournament_id = seed_dev_tournament()

    return jsonify({"tournament_id": tournament_id})


def supabase_delete_by_filter(table, query_params):
    """Run a DELETE request against a Supabase (PostgREST) table."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    rest_url = f"{supabase_url}/rest/v1/{table}?{urlencode(query_params)}"

    req = Request(
        rest_url,
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        },
        method="DELETE",
    )
    try:
        with urlopen(req, timeout=10) as resp:
            resp.read()
    except HTTPError as e:
        logging.error("Cleanup delete failed for %s: %s", table, e.read().decode())


def cleanup_dev_tournament():
    logging.info("Cleaning old dev tournament...")

    tournament = supabase_fetch_one(
        "tournaments",
        {
            "title": "eq.DEV TEST",
        }
    )

    if tournament:
        tid = tournament["id"]

        supabase_delete_by_filter(
            "match_history",
            {"which_tourney": f"eq.{tid}"}
        )

        supabase_delete_by_filter(
            "song_submissions",
            {"tournament_id": f"eq.{tid}"}
        )

        supabase_delete_by_filter(
            "tournament_players",
            {"tournament_id": f"eq.{tid}"}
        )

        supabase_delete_by_filter(
            "tournaments",
            {"id": f"eq.{tid}"}
        )

    supabase_delete_by_filter(
        "account_management",
        {"username": "like.DEVPLAYER%"}
    )

    logging.info("Cleanup complete.")

if __name__ == "__main__":
    app.run(debug=True)