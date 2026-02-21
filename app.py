import sqlite3
import requests
import secrets
import re
from flask import Flask, render_template, request, redirect, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = secrets.token_hex(64)

API_KEY = ''


def openDB():
    conn = sqlite3.connect('toPooList.db')
    cursor = conn.cursor()
    return (conn, cursor)


def closeDB(conn):
    conn.commit()
    conn.close()


def clean_sessions():
    conn, cursor = openDB()
    cursor.execute("DELETE FROM sessions WHERE created_at <= DATETIME('now', '-1 hour')")
    closeDB(conn)


def IDfromSession():
    token = request.cookies.get("session_token")
    conn, cursor = openDB()
    cursor.execute("SELECT user_id FROM sessions WHERE token = ?", (token,))
    user_id = cursor.fetchone()
    closeDB(conn)
    return user_id


def getUsername(user_id):
    conn, cursor = openDB()
    cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    username = cursor.fetchone()
    closeDB(conn)
    if username:
        return username[0]
    else:
        return None


def usernameFromSession():
    user_id = IDfromSession()
    if user_id:
        return getUsername(user_id[0])
    else:
        return None


def create_session(user_id):
    token = secrets.token_hex(64)
    conn, cursor = openDB()
    cursor.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
    closeDB(conn)
    return token


def validate_session(token):
    clean_sessions()
    if not token:
        return 0
    conn, cursor = openDB()
    cursor.execute('''
        SELECT user_id FROM sessions 
        WHERE token = ? 
        AND created_at > DATETIME('now', '-1 hour')
    ''', (token,))
    row = cursor.fetchone()
    closeDB(conn)
    return row[0] if row else 0


def delete_session(token):
    conn, cursor = openDB()
    cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
    closeDB(conn)


def authenticate():
    token = request.cookies.get("session_token")
    return validate_session(token)


def initDB():
    conn, cursor = openDB()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT UNIQUE NOT NULL,
                   password TEXT NOT NULL,
                   trust_rating FLOAT NOT NULL DEFAULT 0,
                   isAdmin BOOL NOT NULL DEFAULT False
                   )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS bathrooms(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   coords TEXT NOT NULL,
                   features TEXT,
                   cleanliness INTEGER NOT NULL,
                   address TEXT,
                   verifications INTEGER NOT NULL DEFAULT 0,
                   user_id INTEGER NOT NULL,
                   FOREIGN KEY (user_id) REFERENCES users(id)
                   )''')
    closeDB(conn)
    clean_sessions()


def get_map_url(lat, lon, zoom=15, size="600x400"):
    map_url = f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lon}&zoom={zoom}&size={size}&markers=color:red%7C{lat},{lon}&key={API_KEY}"
    return map_url


def getBathrooms():
    conn, cursor = openDB()
    cursor.execute("SELECT * FROM bathrooms")
    bathrooms = cursor.fetchall()
    closeDB(conn)
    return bathrooms


def getUsers():
    conn, cursor = openDB()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    closeDB(conn)
    return users


@app.route("/login", methods=["POST", "GET"])
def login():
    return render_template("login.html")


@app.route('/sign-up')
def signUp():
    return render_template("sign-up.html")


@app.route("/get-toilet")
def get_toilet():
    if authenticate():
        return render_template("add-toilet.html")
    else:
        return redirect("/login")


@app.route('/api/get_maps_api_key')
def get_maps_api_key():
    if not authenticate():
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"api_key": API_KEY})


@app.route("/api/sign-in", methods=["POST"])
def signIn():
    username = request.form.get("username")
    password = request.form.get("password")

    conn, cursor = openDB()
    cursor.execute("SELECT id, password FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    closeDB(conn)

    if user and check_password_hash(user[1], password):
        token = create_session(user[0])
        session["username"] = username
        resp = redirect("/")
        resp.set_cookie("session_token", token, httponly=True, samesite="Lax", max_age=3600)
        return resp
    else:
        flash("Username or Password incorrect", "error")
        return redirect("/login")


@app.route("/add_user", methods=["POST"])
def addUser():
    special = "!@#$%^&*()-+?+,"
    username = request.form.get("username")
    password = request.form.get("password")  # never sanitize passwords

    if not username or not password:
        flash("Username and password required", "error")
        return redirect("/sign-up")

    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        flash("Username can only contain letters, numbers, and underscores", "error")
        return redirect("/sign-up")

    if len(password) < 8 or not any(c.isdigit() for c in password) or not any(c in special for c in password):
        flash("Password must be 8+ characters and contain a number and special character", "error")
        return redirect("/sign-up")

    conn, cursor = openDB()
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (username,))
    userExists = bool(cursor.fetchone()[0])

    if userExists:
        closeDB(conn)
        flash("Username already exists", "error")
        return redirect("/sign-up")

    hashedPassword = generate_password_hash(password)
    cursor.execute(
        "INSERT INTO users (username, password, trust_rating) VALUES (?, ?, 0)",
        (username, hashedPassword)
    )
    closeDB(conn)
    flash("User Created Successfully")
    return redirect("/login")


@app.route("/logout")
def logout():
    token = request.cookies.get("session_token")
    if token:
        delete_session(token)
    response = redirect("/login")
    response.delete_cookie("session_token")
    return response


@app.route('/api/add_toilet', methods=['POST'])
def addToilet():
    user_id = authenticate()
    if not user_id:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    try:
        data = request.get_json()

        address = data.get('address')
        lat = data.get('lat')
        lon = data.get('lon')
        features = data.get('features', [])
        coords = f"{lat},{lon}"

        try:
            cleanliness = int(data.get('cleanliness'))
            if not (1 <= cleanliness <= 5):
                return jsonify({"success": False, "error": "Cleanliness must be between 1 and 5"}), 400
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid cleanliness value"}), 400

        if not (-43.50 <= float(lat) <= -10.5):
            return jsonify({"success": False, "error": "Restroo is an Australia only service"}), 400
        if not (113.3 <= float(lon) <= 153.7):
            return jsonify({"success": False, "error": "Restroo is an Australia only service"}), 400

        valid_features = {"Accessible", "Baby Changing", "Free", "Soap", "Hand Dryer"}
        features = [f for f in features if f in valid_features]
        features_str = ','.join(features)

        conn, cursor = openDB()
        cursor.execute(
            "INSERT INTO bathrooms (address, coords, features, cleanliness, user_id) VALUES (?, ?, ?, ?, ?)",
            (address, coords, features_str, cleanliness, user_id)
        )
        closeDB(conn)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/map_image')
def map_image():
    coords = request.args.get('coords')
    if not coords:
        return "No coords provided", 400
    url = f"https://maps.googleapis.com/maps/api/staticmap?center={coords}&zoom=15&size=400x300&markers=color:red%7C{coords}&key={API_KEY}"
    response = requests.get(url)
    return response.content, 200, {'Content-Type': 'image/png'}


@app.route("/")
def index():
    if authenticate():
        session["username"] = usernameFromSession()
    toilets = getBathrooms()
    return render_template("index.html", bathrooms=toilets, getUsername=getUsername)


@app.route('/api/get_map_embed', methods=['POST'])
def api_get_map_embed():
    data = request.get_json()
    lat = data.get('lat', 0)
    lon = data.get('lon', 0)
    embed_html = f'''
        <iframe
            width="600"
            height="450"
            style="border:0"
            loading="lazy"
            allowfullscreen
            src="https://www.google.com/maps/embed/v1/place?key={API_KEY}&q={lat},{lon}&zoom=15">
        </iframe>
    '''
    return jsonify({'embed_html': embed_html})


initDB()
print("bathrooms:", getBathrooms())
app.run(debug=True)
