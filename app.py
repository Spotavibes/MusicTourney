from flask import Flask , render_template, request,\
     redirect, url_for, session
from supabase import create_client, Client
import dotenv
import os

dotenv.load_dotenv()

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Change this to a secure key

# Supabase settings
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


@app.route("/")
def home():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        response = supabase.auth.sign_up(\
            {"email": email, "password": password})

        if response.user:
            return redirect(url_for("login"))
        else:
            return render_template("register.html", \
                                   error="Registration failed. Try again.")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        response = supabase.auth.sign_in_with_password(\
            {"email": email, "password": password})

        if response.user:
            session["user"] = response.user.email
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", \
                                   error="Login failed. Wrong email or password.")
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html", user=session["user"])


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
