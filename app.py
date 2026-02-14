import sqlite3
import requests
import secrets
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


def getCoords():
    data = requests.get_json()
    lat = data.get('latitude')
    lon = data.get('longitude')
    return (lat, lon)


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
                   trust_rating FLOAT NOT NULL DEFAULT 0
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
                   verifications INTEGER NOT NULL DEFAULT 0,
                   user_id INTEGER NOT NULL,
                   FOREIGN KEY (user_id) REFERENCES users(id)
                   )''')
    closeDB(conn)
    clean_sessions()


def get_map_url(lat, lon, zoom=15, size="600x400"):
    map_url = f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lon}&zoom={zoom}&size={size}&markers=color:red%7C{lat},{lon}&key={API_KEY}"
    return map_url


def getUsers():
    conn, cursor = openDB()
    cursor.execute("SELECT * FROM users")
    return cursor.fetchall()


@app.route("/login", methods=["POST", "GET"])
def login():
    return render_template("login.html")


@app.route('/sign-up')
def signUp():
    return render_template("sign-up.html")


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
    username = request.form.get("username")
    password = request.form.get("password")  # never sanitize passwords

    if not username or not password:
        flash("Username and password required", "error")
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


@app.route("/")
def index():
    if authenticate():
        session["username"] = usernameFromSession()
    return render_template("index.html")


@app.route("/get-toilet")
def get_toilet():
    if authenticate():
        return render_template("add-toilet.html")
    else:
        return redirect("/login")


initDB()
app.run(debug=True)
