
# AUX WARS

Futuristic competitive music battle platform prototype built with:
- Flask
- HTML
- CSS
- JavaScript
- Socket.IO

--------------------------------------------------
INSTALLATION
--------------------------------------------------

1. Install Python 3.11+

2. Open terminal in this project folder

3. Install dependencies:

pip install -r requirements.txt

4. Set Stripe environment variables before running the app:

export STRIPE_API_KEY="your_stripe_secret_key"
export STRIPE_WEBHOOK_SECRET="your_stripe_webhook_secret"
export FLASK_SECRET_KEY="your_flask_secret_key"

You can also create a local `.env` file with these values. The app loads `.env` automatically using python-dotenv.

5. Start the app:

python app.py

5. Open browser:

http://127.0.0.1:5000

--------------------------------------------------
FUTURE EXPANSIONS
--------------------------------------------------

Recommended next upgrades:

- PostgreSQL database
- User authentication
- Spotify OAuth
- Real ELO calculations
- Matchmaking queues
- Redis
- Docker deployment
- Tournament backend
- AI anti-cheat
- Framer Motion React frontend
- Firebase realtime
- Audio visualizer engine

--------------------------------------------------
FEATURES INCLUDED
--------------------------------------------------

- Futuristic immersive UI
- Realtime voting
- Live winner reveal animations
- Floating music player
- Animated leaderboard
- Responsive layout
- Socket.IO realtime architecture
- Cinematic rave/esports aesthetic
