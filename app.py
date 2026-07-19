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
# Round-based token payouts (awarded to the winner of each match)
# --------------------------------------------------

#change this to the amount you want the payout to be for each round
#right now i am using a formula where the payout doubles each round deeper you go, starting at 25 tokens for round 1

# depth 1 -> 25, depth 2 -> 50, depth 3 -> 100, depth 4 -> 200, etc.
ROUND_TOKEN_BASE_PAYOUT = 25
ROUND_TOKEN_MULTIPLIER = 2

def round_token_payout(round_depth):
    return ROUND_TOKEN_BASE_PAYOUT * (ROUND_TOKEN_MULTIPLIER ** (round_depth - 1))






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

def parse_supabase_timestamp(ts_string):
    """Parses a Supabase/Postgres timestamp string into an aware datetime.
    Supabase sometimes returns fractional seconds with a non-standard number
    of digits (e.g. 4 digits), which datetime.fromisoformat() can choke on.
    This pads/truncates the fractional part to exactly 6 digits (microseconds)
    before parsing."""

    ts_string = ts_string.replace("Z", "+00:00")

    match = re.match(r"^(.*?)(\.\d+)?([+-]\d{2}:\d{2})$", ts_string)
    if match:
        base, frac, offset = match.groups()
        if frac:
            digits = frac[1:]  # strip leading "."
            digits = (digits + "000000")[:6]  # pad/truncate to 6 digits
            ts_string = f"{base}.{digits}{offset}"

    return datetime.fromisoformat(ts_string)



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


def profile_media_url(path_or_url, bucket):
    """Turn a storage path into a public Supabase URL, or pass through full URLs."""
    object_path = extract_storage_object_path(path_or_url, bucket)
    if not object_path:
        return None
    # Prefer signed URLs because these buckets are private.
    signed = supabase_create_signed_url(bucket, object_path)
    if signed:
        return signed
    base = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    if not base:
        return None
    return f"{base}/storage/v1/object/public/{bucket}/{object_path.lstrip('/')}"


def extract_storage_object_path(path_or_url, bucket):
    """Normalize DB values into `{user_id}/avatar.png` style object paths."""
    if not path_or_url:
        return None
    value = str(path_or_url).strip()
    if not value or value.lower() == "none":
        return None

    # Strip query string (e.g. ?t=...)
    value = value.split("?", 1)[0]

    marker = f"/storage/v1/object/public/{bucket}/"
    if marker in value:
        return value.split(marker, 1)[1].lstrip("/")

    marker_auth = f"/storage/v1/object/authenticated/{bucket}/"
    if marker_auth in value:
        return value.split(marker_auth, 1)[1].lstrip("/")

    marker_sign = f"/storage/v1/object/sign/{bucket}/"
    if marker_sign in value:
        return value.split(marker_sign, 1)[1].lstrip("/")

    if value.startswith("http"):
        # Unknown absolute URL — can't safely convert.
        return None

    # Already a relative object path
    return value.lstrip("/")


def supabase_create_signed_url(bucket, object_path, expires_in=60 * 60 * 24 * 7):
    """Create a temporary signed download URL for a private storage object."""
    supabase_url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    supabase_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key or not object_path:
        return None

    rest_url = f"{supabase_url}/storage/v1/object/sign/{bucket}/{object_path.lstrip('/')}"
    body = json.dumps({"expiresIn": expires_in}).encode("utf-8")
    req = Request(
        rest_url,
        data=body,
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        signed = payload.get("signedURL") or payload.get("signedUrl")
        if not signed:
            return None
        if signed.startswith("http"):
            return signed
        return f"{supabase_url}/storage/v1{signed}"
    except Exception as e:
        logging.warning("Signed URL failed for %s/%s: %s", bucket, object_path, e)
        return None


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def supabase_storage_upload(bucket, object_path, data_bytes, content_type):
    """Upload (or overwrite) a file in a Supabase Storage bucket."""
    supabase_url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError("Supabase not configured (missing SUPABASE_URL / SUPABASE_KEY).")

    rest_url = f"{supabase_url}/storage/v1/object/{bucket}/{object_path.lstrip('/')}"

    req = Request(
        rest_url,
        data=data_bytes,
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": content_type or "application/octet-stream",
            "x-upsert": "true",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {"Key": object_path}
    except HTTPError as e:
        # Some projects reject POST upsert; retry with PUT.
        if e.code in (400, 409):
            put_req = Request(
                rest_url,
                data=data_bytes,
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": content_type or "application/octet-stream",
                    "x-upsert": "true",
                },
                method="PUT",
            )
            with urlopen(put_req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {"Key": object_path}
        print("FAILED STORAGE URL:", rest_url, flush=True)
        print("STATUS:", e.code, flush=True)
        print("BODY:", e.read().decode(), flush=True)
        raise


def supabase_storage_list(bucket, prefix):
    """List objects under a prefix in a storage bucket."""
    supabase_url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    supabase_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        return []

    rest_url = f"{supabase_url}/storage/v1/object/list/{bucket}"
    body = json.dumps({
        "prefix": prefix.rstrip("/") + "/",
        "limit": 100,
    }).encode("utf-8")

    req = Request(
        rest_url,
        data=body,
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logging.warning("Storage list failed for %s/%s: %s", bucket, prefix, e)
        return []


def find_profile_object_path(user_id, bucket, stem):
    """
    Find `{user_id}/{stem}.*` in a bucket.
    Matches the upload layout: uuid/avatar.png , uuid/banner.png
    """
    objects = supabase_storage_list(bucket, user_id)
    candidates = []
    for obj in objects:
        name = (obj.get("name") or "").lstrip("/")
        # API may return just the filename inside the prefix folder.
        filename = name.split("/")[-1]
        lower = filename.lower()
        if lower.startswith(stem.lower() + "."):
            candidates.append(f"{user_id}/{filename}")
    if not candidates:
        # Fallback to the conventional png path used by uploads.
        return f"{user_id}/{stem}.png"
    # Prefer exact stem.png, then newest-looking name.
    for preferred_ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        match = next((p for p in candidates if p.lower().endswith(preferred_ext)), None)
        if match:
            return match
    return candidates[0]


def get_or_create_profile(user):
    """Return the profiles row for this user, creating one if needed."""
    profile = supabase_fetch_one(
        "profiles",
        {"select": "*", "id": f"eq.{user['id']}"},
    )
    username = (
        user.get("username")
        or user.get("name")
        or user.get("display_name")
        or "Unknown"
    )
    if profile:
        # Keep username in sync when we know the real account name.
        if username != "Unknown" and profile.get("username") in (None, "", "Unknown"):
            try:
                supabase_patch("profiles", profile["id"], {"username": username})
                profile["username"] = username
            except Exception:
                pass
        return profile

    created = supabase_post(
        "profiles",
        {
            "id": user["id"],
            "username": username,
            "description": "",
            "avatar_url": None,
            "banner_url": None,
        },
    )
    if isinstance(created, list) and created:
        return created[0]
    return created


def resolve_profile_for_display(profile):
    if not profile:
        return None
    display = dict(profile)
    user_id = profile.get("id")

    avatar_path = extract_storage_object_path(
        profile.get("avatar_url"), "profile_pictures"
    )
    banner_path = extract_storage_object_path(
        profile.get("banner_url"), "profile_banners"
    )

    if not avatar_path and user_id:
        avatar_path = find_profile_object_path(user_id, "profile_pictures", "avatar")
    if not banner_path and user_id:
        banner_path = find_profile_object_path(user_id, "profile_banners", "banner")

    display["avatar_url"] = profile_media_url(avatar_path, "profile_pictures")
    display["banner_url"] = profile_media_url(banner_path, "profile_banners")
    return display


@app.route("/all-profiles")
def all_profiles_page():
    try:
        profiles = supabase_fetch(
            "profiles",
            {
                "select": "id,username,description,avatar_url,banner_url",
                "order": "username.asc",
            },
        )
    except Exception as e:
        logging.exception("Failed fetching profiles: %s", e)
        profiles = []
        flash("Unable to load profiles right now.", "error")

    profiles = [resolve_profile_for_display(p) for p in profiles]
    return render_template("all_profiles.html", profiles=profiles)




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

    profile = None
    try:
        profile = resolve_profile_for_display(get_or_create_profile(user))
    except Exception as e:
        logging.exception("Failed loading profile for dashboard: %s", e)

    return render_template(
        "dashboard.html",
        user=user,
        transactions=transactions,
        profile=profile,
    )


@app.route("/dashboard/update-profile-media", methods=["POST"])
def update_profile_media():
    if not session.get("user_id"):
        flash("Please log in to update your profile.", "error")
        return redirect(url_for("login"))

    user = get_current_user()
    if not user:
        flash("Please log in to update your profile.", "error")
        return redirect(url_for("login"))

    avatar_file = request.files.get("avatar")
    banner_file = request.files.get("banner")

    has_avatar = avatar_file and avatar_file.filename
    has_banner = banner_file and banner_file.filename

    if not has_avatar and not has_banner:
        flash("Choose a profile picture and/or banner to upload.", "error")
        return redirect(url_for("dashboard_page"))

    try:
        profile = get_or_create_profile(user)
        updates = {}

        def upload_image(file_storage, bucket, field_name, prefix):
            filename = file_storage.filename or ""
            _, ext = os.path.splitext(filename.lower())
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                raise ValueError("Only JPG, PNG, GIF, or WEBP images are allowed.")

            # Matches bucket layout: {user_id}/avatar.png or {user_id}/banner.png
            object_path = f"{user['id']}/{prefix}{ext}"
            data = file_storage.read()
            if not data:
                raise ValueError(f"{field_name} file was empty.")

            content_type = file_storage.mimetype or "application/octet-stream"
            supabase_storage_upload(bucket, object_path, data, content_type)

            # Store the relative object path; display code builds the public URL.
            return object_path

        if has_avatar:
            updates["avatar_url"] = upload_image(
                avatar_file, "profile_pictures", "avatar", "avatar"
            )

        if has_banner:
            updates["banner_url"] = upload_image(
                banner_file, "profile_banners", "banner", "banner"
            )

        if updates:
            patched = supabase_patch("profiles", profile["id"], updates)
            if not patched:
                raise RuntimeError(
                    "Storage upload succeeded, but profiles row was not updated. "
                    "Check RLS policies on the profiles table."
                )
            flash("Profile media updated.", "success")
    except ValueError as e:
        flash(str(e), "error")
    except Exception as e:
        logging.exception("Profile media upload failed: %s", e)
        flash("Could not upload profile media. Check storage/RLS permissions.", "error")

    return redirect(url_for("dashboard_page"))


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
@app.route("/create-tournament", methods=["GET"])
def create_tournament_page():
    return render_template("create_tournament.html")


@app.route("/create-tournament", methods=["POST"])
def create_tournament():

    user = get_current_user()

    max_players = int(request.form.get("max_players", 8))
    if max_players < 2 or (max_players & (max_players - 1)) != 0:
        flash("Make sure the amount of seats is a multiple of 2.", "error")
        return redirect(url_for("create_tournament_page"))

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
            "max_players": max_players,
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

def enrich_waiting_players(players):
    """Attach profile username/avatar/banner to tournament_players rows."""
    if not players:
        return []

    user_ids = [p["user_id"] for p in players if p.get("user_id")]
    profiles_by_id = {}

    if user_ids:
        ids_filter = ",".join(user_ids)
        try:
            profiles = supabase_fetch(
                "profiles",
                {
                    "select": "id,username,description,avatar_url,banner_url",
                    "id": f"in.({ids_filter})",
                },
            )
            for profile in profiles:
                resolved = resolve_profile_for_display(profile)
                if resolved:
                    profiles_by_id[resolved["id"]] = resolved
        except Exception as e:
            logging.exception("Failed enriching waiting-room profiles: %s", e)

    enriched = []
    for player in sorted(players, key=lambda p: p.get("seat_number") or 0):
        profile = profiles_by_id.get(player.get("user_id"), {})
        enriched.append({
            "seat_number": player.get("seat_number"),
            "user_id": player.get("user_id"),
            "username": profile.get("username") or "Unknown",
            "description": profile.get("description") or "",
            "avatar_url": profile.get("avatar_url"),
            "banner_url": profile.get("banner_url"),
        })
    return enriched


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
        "players": enrich_waiting_players(players),
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
    seat_number = current_players

    supabase_patch(
        "tournaments",
        tournament_id,
        {"current_players": current_players},
    )

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

    if current_players >= tournament["max_players"]:
        supabase_patch(
            "tournaments",
            tournament_id,
            {"started": True, "status": "active"},
        )
        generate_bracket(tournament_id, tournament["max_players"])

    return redirect(
        url_for(
            "tournament_waiting_page",
            tournament_id=tournament_id,
        )
    )

    


def generate_bracket(tournament_id, max_players):
    players = supabase_fetch("tournament_players", {"select": "*", "tournament_id": f"eq.{tournament_id}"})
    shuffled = players.copy()
    random.shuffle(shuffled)
    starting_round = max_players // 2  # matches in round 1

    for i in range(0, len(shuffled), 2):
        p1, p2 = shuffled[i], shuffled[i + 1]
        slot = (i // 2) + 1
        p1_submission = supabase_fetch_one("song_submissions", {"tournament_id": f"eq.{tournament_id}", "user_id": f"eq.{p1['user_id']}"})
        p2_submission = supabase_fetch_one("song_submissions", {"tournament_id": f"eq.{tournament_id}", "user_id": f"eq.{p2['user_id']}"})
        is_first_match = (slot == 1)

        supabase_post("match_history", {
            "which_tourney": tournament_id,
            "which_round": starting_round,
            "round_depth": 1,
            "bracket_slot": slot,
            "player1_id": p1["user_id"], "player2_id": p2["user_id"],
            "p1_seat": p1["seat_number"], "p2_seat": p2["seat_number"],
            "p1_song": p1_submission["spotify_embed_1"] if p1_submission else None,
            "p2_song": p2_submission["spotify_embed_1"] if p2_submission else None,
            "p1_votes": 0, "p2_votes": 0,
            "current_phase": "live" if is_first_match else "pending",
            "voting_ends_at": None,
            "processed": False,
        })


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
        players=enrich_waiting_players(players),
    )
def build_bracket_layout(all_matches, username_by_id, max_players):
    import math

    BOX_W = 200
    BOX_H = 72
    ROW_H = 36
    PAIR_GAP = 24
    COL_GAP = 80

    num_rounds = int(math.log2(max_players))  # e.g. 8 players -> 3 rounds
    # which_round values count down: round1 (first round) has max_players/2 matches,
    # so which_round == matches_in_round. Round order (earliest->final):
    round_sizes = [max_players // (2 ** (i + 1)) for i in range(num_rounds)]
    # e.g. max_players=8 -> round_sizes = [4, 2, 1]

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
        if not slot_display["complete"]:
            return None
        if slot_display["p1_won"]:
            return slot_display["p1_seat"], slot_display["p1_username"]
        return slot_display["p2_seat"], slot_display["p2_username"]

    def project_slot(left, right):
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

    # Build each round's column of display-slots, left to right.
    columns_display = []  # columns_display[col] = list of slot dicts
    for col, round_size in enumerate(round_sizes):
        col_slots = []
        for slot_num in range(1, round_size + 1):
            m = real_match(round_size, slot_num)
            if m:
                col_slots.append(display_from_real(m, label_winner=(round_size == 1)))
            elif col == 0:
                col_slots.append(empty_slot())
            else:
                prev = columns_display[col - 1]
                col_slots.append(project_slot(prev[(slot_num - 1) * 2], prev[(slot_num - 1) * 2 + 1]))
        columns_display.append(col_slots)

    # Layout: compute y-centers column by column, propagating up from round 1.
    col0_top = [i * (BOX_H + PAIR_GAP) for i in range(round_sizes[0])]
    col0_center = [t + BOX_H / 2 for t in col0_top]

    centers = [col0_center]
    for col in range(1, num_rounds):
        prev_centers = centers[col - 1]
        this_centers = [
            (prev_centers[i * 2] + prev_centers[i * 2 + 1]) / 2
            for i in range(len(prev_centers) // 2)
        ]
        centers.append(this_centers)

    col_x = [40 + col * (BOX_W + COL_GAP) for col in range(num_rounds)]

    boxes = []
    connectors = []
    for col in range(num_rounds):
        for i, slot in enumerate(columns_display[col]):
            top = centers[col][i] - BOX_H / 2
            boxes.append({**slot, "x": col_x[col], "y": top, "w": BOX_W, "h": BOX_H, "row_h": ROW_H})

        if col + 1 < num_rounds:
            mid_x = col_x[col] + BOX_W + COL_GAP / 2
            for pair_idx in range(len(centers[col]) // 2):
                top_c = centers[col][pair_idx * 2]
                bot_c = centers[col][pair_idx * 2 + 1]
                target_c = centers[col + 1][pair_idx]
                connectors.append({"x1": col_x[col] + BOX_W, "y1": top_c, "x2": mid_x, "y2": top_c})
                connectors.append({"x1": col_x[col] + BOX_W, "y1": bot_c, "x2": mid_x, "y2": bot_c})
                connectors.append({"x1": mid_x, "y1": top_c, "x2": mid_x, "y2": bot_c})
                connectors.append({"x1": mid_x, "y1": target_c, "x2": col_x[col + 1], "y2": target_c})

    total_height = max(col0_top[-1] + BOX_H, 0) + 80 if col0_top else BOX_H + 80

    return {
        "boxes": boxes,
        "connectors": connectors,
        "width": col_x[-1] + BOX_W + 40,
        "height": total_height,
        "final_center": centers[-1][0] if centers and centers[-1] else BOX_H / 2,
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

    bracket_layout = build_bracket_layout(all_matches, username_by_id, tournament["max_players"])

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

    user = get_current_user()
    if not user:
        return jsonify({"error": "Not logged in"}), 401

    match = supabase_fetch_one("match_history", {"index": f"eq.{match_index}"})
    if not match:
        return jsonify({"error": "Match not found"}), 404

    if match["current_phase"] != "voting":
        return jsonify({"error": "Voting closed"}), 400

    voting_ends_at = parse_supabase_timestamp(match["voting_ends_at"])
    if datetime.now(timezone.utc) > voting_ends_at:
        return jsonify({"error": "Voting window has ended"}), 400

    existing_vote = supabase_fetch_one("match_votes", {
        "match_index": f"eq.{match_index}",
        "user_id": f"eq.{user['id']}",
    })
    if existing_vote:
        return jsonify({"error": "Already voted", "already_voted": True, "side": existing_vote["side"]}), 400

    try:
        supabase_post("match_votes", {
            "match_index": match_index,
            "user_id": user["id"],
            "side": side,
        })
    except HTTPError as e:
        # Unique constraint violation = duplicate vote slipped through a race condition.
        if e.code == 409:
            return jsonify({"error": "Already voted", "already_voted": True}), 400
        raise

    if side == "p1":
        new_votes = (match.get("p1_votes") or 0) + 1
        supabase_patch("match_history", match_index, {"p1_votes": new_votes}, id_column="index")
    else:
        new_votes = (match.get("p2_votes") or 0) + 1
        supabase_patch("match_history", match_index, {"p2_votes": new_votes}, id_column="index")

    return jsonify({
        "p1_votes": new_votes if side == "p1" else match.get("p1_votes") or 0,
        "p2_votes": new_votes if side == "p2" else match.get("p2_votes") or 0,
        "voted_side": side,
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


#if user has voted for a match already
@app.route("/vote-status/<match_index>")
def vote_status(match_index):
    user = get_current_user()
    if not user:
        return jsonify({"has_voted": False})

    existing_vote = supabase_fetch_one("match_votes", {
        "match_index": f"eq.{match_index}",
        "user_id": f"eq.{user['id']}",
    })
    return jsonify({
        "has_voted": bool(existing_vote),
        "side": existing_vote["side"] if existing_vote else None,
    })

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
    tokens_awarded = 0

    if match["current_phase"] == "complete":
        winner = "p1" if (match.get("p1_votes") or 0) >= (match.get("p2_votes") or 0) else "p2"
        # Credit tokens the first time we see this match as complete.
        tokens_awarded = credit_round_tokens(match)

    return jsonify({
        "current_phase": match["current_phase"],
        "which_tourney": match["which_tourney"],
        "p1_votes": match.get("p1_votes") or 0,
        "p2_votes": match.get("p2_votes") or 0,
        "voting_ends_at": match.get("voting_ends_at"),
        "winner": winner,
        "tokens_awarded": tokens_awarded,
    })

#payout function for the winner of a match, based on the round they won in
def credit_round_tokens(match):
    """Credits the winner of a completed match with the round's token payout.
    Uses match_history.processed as a guard so this only ever runs once per match."""

    if match.get("tokens_processed"):
        return 0

    depth = match.get("round_depth", 1)
    payout = round_token_payout(depth)

    p1_won = (match.get("p1_votes") or 0) >= (match.get("p2_votes") or 0)
    winner_id = match["player1_id"] if p1_won else match["player2_id"]

    account = supabase_get_account(winner_id)
    if account:
        new_balance = account.get("tokens", 0) + payout
        supabase_patch("account_management", winner_id, {"tokens": new_balance})

    # Mark processed so re-polling never double-credits this match.
    supabase_patch("match_history", match["index"], {"tokens_processed": True}, id_column="index")

    return payout
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