import sqlite3
import requests
import secrets
import json
import shutil
import re
import nh3
import os
from collections import defaultdict
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = secrets.token_hex(64)

API_KEY = os.environ['MAPSAPI']


def openDB():
    conn = sqlite3.connect('toPooList.db')
    cursor = conn.cursor()
    return (conn, cursor)


def closeDB(conn):
    conn.commit()
    conn.close()
    conditionalBackup()


def log(message: str, log_dir="./Logs"):
    now = datetime.now()
    log_file = os.path.join(log_dir, f"{now.strftime('%Y-%m-%d')}.log")
    with open(log_file, "a") as f:
        f.write(f"[{now.strftime('%H:%M:%S')}] {message}\n")


def clean_sessions():
    conn, cursor = openDB()
    cursor.execute("DELETE FROM sessions WHERE created_at <= DATETIME('now', '-1 hour')")
    closeDB(conn)


def sanitize_text(value, max_length=255):
    if not value:
        return value
    return nh3.clean(value.strip())[:max_length]


def authenticate_admin():
    user_id = authenticate()
    if not user_id:
        return False
    conn, cursor = openDB()
    cursor.execute("SELECT isAdmin FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    closeDB(conn)
    return bool(result and result[0])


def getCoords():
    data = requests.get_json()
    lat = data.get('latitude')
    lon = data.get('longitude')
    return (lat, lon)


def IDfromSession():
    token = request.cookies.get("session_token")
    conn, cursor = openDB()
    cursor.execute("SELECT user_id FROM sessions WHERE token = ?", (token,))
    user_id = cursor.fetchone()
    closeDB(conn)
    return user_id


def usernameFromSession():
    user_id = IDfromSession()
    if user_id:
        return getUsername(user_id[0])
    else:
        return None


def isAdmin():
    token = request.cookies.get("session_token")
    conn, cursor = openDB()
    cursor.execute("SELECT user_id FROM sessions WHERE token = ?", (token,))
    user_id = cursor.fetchone()
    if user_id:
        cursor.execute('SELECT isAdmin FROM users WHERE id = ?', (user_id,))
    closeDB(conn)


def getUsername(user_id):
    conn, cursor = openDB()
    cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    username = cursor.fetchone()
    closeDB(conn)
    if username:
        return username[0]
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


def verify_recaptcha(token):
    url = "https://www.google.com/recaptcha/api/siteverify"
    payload = {
        "secret": "6Lc74mksAAAAADpDeQndK344kWqk3pURzX4SM_Dq",
        "response": token
    }
    r = requests.post(url, data=payload)
    result = r.json()
    return result.get("success", False)


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

    cursor.execute('''CREATE TABLE IF NOT EXISTS endorsements (
                    user_id INTEGER NOT NULL,
                    bathroom_id INTEGER NOT NULL,
                    PRIMARY KEY (user_id, bathroom_id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (bathroom_id) REFERENCES bathrooms(id)
                    )''')

    closeDB(conn)
    clean_sessions()


def conditionalBackup(db_path="toPooList.db", backup_dir="./Backups"):
    now = datetime.now()

    existing = [
        f for f in os.listdir(backup_dir)
        if f.startswith("topoolist_") and f.endswith(".db")
    ]

    if existing:
        latest = max(existing, key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)))
        last_backup = datetime.fromtimestamp(os.path.getmtime(os.path.join(backup_dir, latest)))
        if now - last_backup < timedelta(days=1):
            print(f"Backup skipped — last backup was {last_backup}")
            return

    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"topoolist_{timestamp}.db"
    shutil.copy2(db_path, os.path.join(backup_dir, backup_filename))
    print(f"Backup created: {backup_filename}")

    backups = sorted(
        [
            (datetime.strptime(f, "topoolist_%Y-%m-%d_%H-%M-%S.db"), f)
            for f in os.listdir(backup_dir)
            if f.startswith("topoolist_") and f.endswith(".db") and f != backup_filename
        ],
        reverse=True
    )

    week      = now - timedelta(days=7)
    fortnight = now - timedelta(days=14)
    keep      = set()

    for dt, filename in backups:
        if dt >= week:
            keep.add(filename)

    if not any(dt >= fortnight for dt, _ in backups):
        if backups:
            keep.add(backups[0][1])

    monthly = defaultdict(list)
    for dt, filename in backups:
        monthly[(dt.year, dt.month)].append((dt, filename))
    for month_backups in monthly.values():
        keep.add(max(month_backups)[1])

    deleted = [f for _, f in backups if f not in keep]
    for filename in deleted:
        os.remove(os.path.join(backup_dir, filename))

    if deleted:
        print(f"Deleted {len(deleted)} old backup/s. Amount left: {len(keep) + 1}")
    else:
        print(f"No backups deleted. {len(keep) + 1} total.")


def authenticate():
    token = request.cookies.get("session_token")
    return validate_session(token)


def get_map_url(lat, lon, zoom=15, size="600x400"):
    return f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lon}&zoom={zoom}&size={size}&markers=color:red%7C{lat},{lon}&key={API_KEY}"


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


@app.route('/administration')
def admininstration():
    if authenticate_admin():
        toilets = getBathrooms()
        return render_template('admin-view.html', toilets=toilets, getUsername=getUsername)
    else:
        return redirect("/")


@app.route("/delete_toilet", methods=['POST', 'GET'])
def delete_toilet():
    if not authenticate_admin():
        return redirect("/")
    toilet_id = request.form.get("id")
    log(f"ID {IDfromSession()[0]} deleted toilet {toilet_id}")
    conn, cursor = openDB()
    cursor.execute("DELETE FROM bathrooms WHERE id = ?", (toilet_id,))
    closeDB(conn)
    return redirect('/administration')


@app.route("/logout")
def logout():
    token = request.cookies.get("session_token")
    log(f"ID {IDfromSession()[0]} Logged Out")
    if token:
        delete_session(token)
    response = redirect("/login")
    response.delete_cookie("session_token")
    return response


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
        log(f"ID {user[0]} logged in")
        return resp
    else:
        flash("Username or Password incorrect", "error")
        return redirect("/login")


@app.route("/add_user", methods=["POST"])
def addUser():
    special = "!@#$%^&*()-+?+,"
    username = sanitize_text(request.form.get("username"), max_length=32)
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


@app.route('/endorse')
def endorse():
    selected = request.args.get("toilet_id", "")
    user_id = authenticate()
    if not selected or not user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    conn, cursor = openDB()
    cursor.execute("SELECT 1 FROM endorsements WHERE user_id = ? AND bathroom_id = ?", (user_id, selected))
    already = cursor.fetchone()

    if already:
        cursor.execute("DELETE FROM endorsements WHERE user_id = ? AND bathroom_id = ?", (user_id, selected))
        cursor.execute("UPDATE bathrooms SET verifications = verifications - 1 WHERE id = ?", (selected,))
        closeDB(conn)
        return jsonify({"success": True, "action": "removed"})
    else:
        cursor.execute("INSERT INTO endorsements (user_id, bathroom_id) VALUES (?, ?)", (user_id, selected))
        cursor.execute("UPDATE bathrooms SET verifications = verifications + 1 WHERE id = ?", (selected,))
        closeDB(conn)
        return jsonify({"success": True, "action": "added"})


@app.route('/lander')
def lander():
    return render_template("lander.html")


@app.route('/api/add_toilet', methods=['POST'])
def addToilet():
    user_id = authenticate()
    if not user_id:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    try:
        data = request.get_json()

        address = sanitize_text(data.get('address'), max_length=255)
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
        toiletID = cursor.lastrowid
        log(f"Toilet {toiletID} created by {user_id}")
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
    is_admin = False
    endorsed = set()
    user_id = IDfromSession()

    if authenticate():
        session["username"] = usernameFromSession()
        if user_id:
            conn, cursor = openDB()
            cursor.execute("SELECT isAdmin FROM users WHERE id = ?", (user_id[0],))
            result = cursor.fetchone()
            is_admin = bool(result and result[0])
            cursor.execute("SELECT bathroom_id FROM endorsements WHERE user_id = ?", (user_id[0],))
            endorsed = {row[0] for row in cursor.fetchall()}
            closeDB(conn)

    search = sanitize_text(request.args.get("search", ""), max_length=100)
    sort = request.args.get("sort", "id")
    features = [f for f in request.args.getlist("features") if f in {"Accessible", "Baby Changing", "Free", "Soap", "Hand Dryer"}]

    valid_sorts = {"id", "cleanliness", "verifications"}
    if sort not in valid_sorts:
        sort = "id"

    conn, cursor = openDB()
    query = "SELECT * FROM bathrooms WHERE 1=1"
    params = []

    if search:
        query += " AND address LIKE ?"
        params.append(f"%{search}%")

    for feature in features:
        query += " AND features LIKE ?"
        params.append(f"%{feature}%")

    query += f" ORDER BY {sort} DESC"

    cursor.execute(query, params)
    toilets = cursor.fetchall()
    closeDB(conn)

    return render_template("index.html", bathrooms=toilets, search=search, sort=sort,
                           selected_features=features, getUsername=getUsername,
                           is_admin=is_admin, endorsed=endorsed)


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
