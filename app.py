
import logging
import os
import json
from datetime import datetime
from decimal import Decimal
from urllib.request import Request, urlopen

from dotenv import load_dotenv
import stripe
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy

# --------------------------------------------------
# App configuration
# --------------------------------------------------
project_root = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(project_root, ".env")
load_dotenv(dotenv_path=dotenv_path)  # Load environment variables from local .env file.

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "auxwars-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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
db = SQLAlchemy(app)

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

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    token_balance = db.Column(db.Integer, nullable=False, default=0)
    transactions = db.relationship("TokenTransaction", back_populates="user")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "token_balance": self.token_balance,
        }


class TokenTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    transaction_type = db.Column(db.String(50), nullable=False)
    token_amount = db.Column(db.Integer, nullable=False)
    dollar_amount = db.Column(db.Numeric(10, 2), nullable=False)
    stripe_session_id = db.Column(db.String(255), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", back_populates="transactions")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "transaction_type": self.transaction_type,
            "token_amount": self.token_amount,
            "dollar_amount": float(self.dollar_amount),
            "stripe_session_id": self.stripe_session_id,
            "created_at": self.created_at.isoformat(),
        }


with app.app_context():
    db.create_all()

# --------------------------------------------------
# Auth helper
# --------------------------------------------------

def get_current_user():
    """Return the logged-in user object.

    Aadi input the user id/login info code here.
    Replace the fallback below with your auth system logic.
    """
    user = None
    user_id = session.get("user_id")

    if user_id:
        user = User.query.get(user_id)

    if not user:
        user = User.query.filter_by(username="demo").first()
        if not user:
            user = User(username="demo", token_balance=0)
            db.session.add(user)
            db.session.commit()

    return user


# --------------------------------------------------
# Home and existing app routes
# --------------------------------------------------
# Leaderboard mock data — only used by /leaderboard (leaderboard.html).
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
# Supabase leaderboard
# --------------------------------------------------
def fetch_supabase_leaderboard(limit: int = 20):
    """
    Fetch top players from Supabase ordered by highest `elo`.

    Expected table: `public.account_management`
    """

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        logging.warning("Supabase not configured (missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY).")
        return []

    # Supabase REST API (PostgREST)
    # Example: {SUPABASE_URL}/rest/v1/account_management?select=*&order=elo.desc&limit=20
    rest_url = (
        f"{supabase_url}/rest/v1/account_management"
        f"?select=*&order=elo.desc&limit={limit}"
    )

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
        raw = resp.read().decode("utf-8")
        return json.loads(raw)

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


@app.route("/dashboard")
def dashboard_page():
    user = get_current_user()
    return render_template("dashboard.html", user=user)


@app.route("/battles")
def battles():
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
    transactions = (
        TokenTransaction.query.filter_by(user_id=user.id)
        .order_by(TokenTransaction.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "token_balance.html",
        user=user,
        transactions=transactions,
    )


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
                "user_id": str(user.id),
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
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logging.error("Invalid webhook payload")
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        logging.error("Invalid webhook signature")
        return "Invalid signature", 400

    # Log all events received for debugging
    logging.info("Stripe webhook event received: %s", event["type"])

    # Handle checkout.session.completed
    if event["type"] == "checkout.session.completed":
        session_object = event["data"]["object"]
        stripe_session_id = session_object["id"]

        existing_transaction = TokenTransaction.query.filter_by(
            stripe_session_id=stripe_session_id
        ).first()
        if existing_transaction:
            logging.info(
                "Stripe webhook already processed for session %s", stripe_session_id
            )
            return jsonify({"status": "already_processed"}), 200

        metadata = session_object["metadata"] if "metadata" in session_object else {}
        
        user_id = metadata["user_id"] if "user_id" in metadata else None
        package_id = metadata["package_id"] if "package_id" in metadata else None

        if not user_id or not package_id:
            logging.error(
                "Missing metadata in Stripe session %s: %s", stripe_session_id, metadata
            )
            return "Missing metadata", 400

        package = TOKEN_PACKAGES.get(package_id)
        if not package:
            logging.error(
                "Unknown package_id in webhook: %s", package_id
            )
            return "Invalid package", 400

        user = User.query.get(int(user_id))
        if not user:
            logging.error("Unable to find user %s for Stripe session %s", user_id, stripe_session_id)
            return "User not found", 400

        user.token_balance += package["token_amount"]
        transaction = TokenTransaction(
            user_id=user.id,
            transaction_type="token_purchase",
            token_amount=package["token_amount"],
            dollar_amount=package["dollar_amount"],
            stripe_session_id=stripe_session_id,
        )

        db.session.add(transaction)
        db.session.commit()

        logging.info(
            "Added %s tokens to user %s for Stripe session %s",
            package["token_amount"],
            user.id,
            stripe_session_id,
        )

    # Handle payment_intent.succeeded as fallback (payment already processed)
    elif event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        metadata = payment_intent["metadata"] if "metadata" in payment_intent else {}
        
        user_id = metadata["user_id"] if "user_id" in metadata else None
        package_id = metadata["package_id"] if "package_id" in metadata else None
        stripe_session_id = metadata["checkout_session_id"] if "checkout_session_id" in metadata else None

        if not stripe_session_id:
            logging.warning("No checkout_session_id in payment_intent metadata")
            return jsonify({"received": True}), 200

        existing_transaction = TokenTransaction.query.filter_by(
            stripe_session_id=stripe_session_id
        ).first()
        if existing_transaction:
            logging.info(
                "Stripe webhook already processed for session %s", stripe_session_id
            )
            return jsonify({"status": "already_processed"}), 200

        if not user_id or not package_id:
            logging.error("Missing user_id or package_id in payment_intent metadata")
            return jsonify({"received": True}), 200

        package = TOKEN_PACKAGES.get(package_id)
        if not package:
            logging.error("Unknown package_id in webhook: %s", package_id)
            return jsonify({"received": True}), 200

        user = User.query.get(int(user_id))
        if not user:
            logging.error("Unable to find user %s for payment_intent", user_id)
            return jsonify({"received": True}), 200

        user.token_balance += package["token_amount"]
        transaction = TokenTransaction(
            user_id=user.id,
            transaction_type="token_purchase",
            token_amount=package["token_amount"],
            dollar_amount=package["dollar_amount"],
            stripe_session_id=stripe_session_id,
        )

        db.session.add(transaction)
        db.session.commit()

        logging.info(
            "Added %s tokens to user %s for payment_intent",
            package["token_amount"],
            user.id,
        )

    return jsonify({"received": True}), 200


# --------------------------------------------------
# API endpoints
# --------------------------------------------------

@app.route("/api/tokens/balance")
def api_token_balance():
    user = get_current_user()
    return jsonify({"token_balance": user.token_balance})


@app.route("/api/tokens/history")
def api_token_history():
    user = get_current_user()
    history = [tx.to_dict() for tx in user.transactions]
    history.sort(key=lambda row: row["created_at"], reverse=True)
    return jsonify(history)


if __name__ == "__main__":
    app.run(debug=True)
