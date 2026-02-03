import sqlite3
from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'banging_head_against_wall_emoji'

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


def initDB():
    conn, cursor = openDB()
    cursor.execute('''CREATE TABLE IF NOT EXISTS bathrooms(
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   coords TEXT NOT NULL,
                   verifications INTEGER NOT NULL,
                   user_id INTEGER NOT NULL,
                   FOREIGN KEY (user_id) REFERENCES users(id)
                   )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT UNIQUE NOT NULL,
                   password TEXT NOT NULL,
                   trust_rating FLOAT NOT NULL
                   )''')
    closeDB(conn)


def get_map_url(lat, lon, zoom=15, size="600x400"):
    map_url = f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lon}&zoom={zoom}&size={size}&markers=color:red%7C{lat},{lon}&key={API_KEY}"
    return map_url


def addUser(username, password):
    conn, cursor = openDB()
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (username,))
    userExists = bool(cursor.fetchone()[0])
    if userExists:
        print("user EXISTED")
        closeDB(conn)
        return 0
    else:
        hashedPassword = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password, trust_rating) VALUES (?,?,0)", (username, hashedPassword))
        print("user CREATED")
        closeDB(conn)
        return 1


def addToilet(user_id, coords):
    conn, cursor = openDB()
    cursor.execute()


def getUsers():
    conn, cursor = openDB()
    cursor.execute("SELECT * FROM users")
    return cursor.fetchall()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/get-toilet")
def get_toilet():
    return render_template("add-toilet.html")


initDB()
app.run(debug=True)
