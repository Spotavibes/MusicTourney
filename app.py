
from flask import Flask, render_template, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit
import random
import time

# --------------------------------------------------
# Main Flask app setup
# --------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = "auxwars-secret"
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"
)

# --------------------------------------------------
# Fake data for prototype/demo
# In production:
# - Use PostgreSQL
# - Add Spotify OAuth
# - Add Redis for matchmaking
# - Add proper anti-cheat systems
# --------------------------------------------------
mock_players = [
    {
        "name": "NEONPHONK",
        "elo": 2134,
        "genre": "Underground",
        "wins": 91,
        "streak": 7
    },
    {
        "name": "BASSLINE.exe",
        "elo": 1998,
        "genre": "Hyperpop",
        "wins": 73,
        "streak": 3
    },
    {
        "name": "VINYL_GHOST",
        "elo": 1850,
        "genre": "Hip Hop",
        "wins": 66,
        "streak": 12
    }
]

mock_battles = [
    {
        "id": 1,
        "left_name": "NEONPHONK",
        "right_name": "BASSLINE.exe",
        "genre": "Hyperpop",
        "viewers": 412
    },
    {
        "id": 2,
        "left_name": "VINYL_GHOST",
        "right_name": "808KILLA",
        "genre": "Hip Hop",
        "viewers": 891
    },
    {
        "id": 3,
        "left_name": "CYBERWAVE",
        "right_name": "STATIC BLOOM",
        "genre": "Underground",
        "viewers": 237
    }
]

# --------------------------------------------------
# Home Route
# --------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html", players=mock_players)

# --------------------------------------------------
# Example API route for leaderboard
# --------------------------------------------------
@app.route("/api/leaderboard")
def leaderboard():
    sorted_players = sorted(mock_players, key=lambda x: x["elo"], reverse=True)
    return jsonify(sorted_players)

# --------------------------------------------------
# Leaderboard Page
# --------------------------------------------------
@app.route("/leaderboard")
def leaderboard_page():
    sorted_players = sorted(mock_players, key=lambda x: x["elo"], reverse=True)
    return render_template("leaderboard.html", players=sorted_players)

# --------------------------------------------------
# Dashboard Page
# --------------------------------------------------
@app.route("/dashboard")
def dashboard_page():
    total_players = len(mock_players)
    total_wins = sum(player["wins"] for player in mock_players)
    avg_elo = sum(player["elo"] for player in mock_players) // total_players
    top_streak = max(mock_players, key=lambda x: x["streak"])

    return render_template(
        "dashboard.html",
        players=mock_players,
        total_players=total_players,
        total_wins=total_wins,
        avg_elo=avg_elo,
        top_streak=top_streak
    )

# --------------------------------------------------
# LIVE BATTLES PAGE
# --------------------------------------------------
@app.route("/battles")
def battles():
    return render_template(
        "battles.html",
        battles=mock_battles
    )

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
# WebSocket event for live vote updates
# --------------------------------------------------
@socketio.on("send_vote")
def handle_vote(data):
    # Simulate realtime updates
    updated_votes = {
        "left": random.randint(10, 100),
        "right": random.randint(10, 100)
    }

    emit("vote_update", updated_votes, broadcast=True)

# --------------------------------------------------
# Fake cinematic winner reveal event
# --------------------------------------------------
@socketio.on("battle_finish")
def battle_finish():
    winner = random.choice(["PLAYER A", "PLAYER B"])

    emit("winner_reveal", {
        "winner": winner,
        "elo_gain": random.randint(14, 32)
    }, broadcast=True)

# --------------------------------------------------
# Start server
# --------------------------------------------------
if __name__ == "__main__":
    socketio.run(app, debug=True)
