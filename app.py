import os
import sqlite3
import requests
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_key_123")

# Use a persistent path for the database on Render if using Disks, 
# or local directory for simple hobby tier.
DB_PATH = os.environ.get("DATABASE_URL", "kitchen.db")
SPOON_API_KEY = os.environ.get("SPOONACULAR_API_KEY")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS ingredients
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         name TEXT NOT NULL, 
                         expiry_date DATE NOT NULL)''')

@app.route('/')
def index():
    limit = (datetime.now() + timedelta(hours=48)).strftime('%Y-%m-%d')
    with get_db_connection() as conn:
        items = conn.execute("SELECT * FROM ingredients ORDER BY expiry_date ASC").fetchall()
        expiring_soon = conn.execute("SELECT name FROM ingredients WHERE expiry_date <= ?", (limit,)).fetchall()
    
    return render_template('index.html', items=items, expiring_soon=[row[0] for row in expiring_soon])

@app.route('/add', methods=['POST'])
def add():
    name = request.form.get('name')
    expiry = request.form.get('expiry')
    if name and expiry:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO ingredients (name, expiry_date) VALUES (?, ?)", (name, expiry))
    return redirect(url_for('index'))

@app.route('/delete/<int:item_id>')
def delete(item_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM ingredients WHERE id = ?", (item_id,))
    return redirect(url_for('index'))

@app.route('/surprise')
def surprise():
    with get_db_connection() as conn:
        inventory = conn.execute("SELECT name FROM ingredients").fetchall()
    
    if not inventory:
        flash("Fridge is empty!")
        return redirect(url_for('index'))

    query = ",".join([row[0] for row in inventory])
    url = f"https://api.spoonacular.com/recipes/findByIngredients?ingredients={query}&number=1&apiKey={SPOON_API_KEY}"
    
    try:
        res = requests.get(url).json()
        recipe_name = res[0]['title'] if res else "No recipes found."
        flash(f"Surprise Idea: {recipe_name}")
    except:
        flash("API Error. Check your Key!")
    return redirect(url_for('index'))

# Route to trigger email alerts (You can ping this URL once a day)
@app.route('/cron/check-expiry')
def cron_check():
    limit = (datetime.now() + timedelta(hours=48)).strftime('%Y-%m-%d')
    with get_db_connection() as conn:
        items = conn.execute("SELECT name FROM ingredients WHERE expiry_date <= ?", (limit,)).fetchall()
    
    if items and os.environ.get("EMAIL_USER"):
        send_email([row[0] for row in items])
        return "Email Sent", 200
    return "No items expiring", 200

def send_email(items):
    msg = EmailMessage()
    msg.set_content(f"Use these soon: {', '.join(items)}")
    msg['Subject'] = 'Kitchen Expiry Alert'
    msg['From'] = os.environ.get("EMAIL_USER")
    msg['To'] = os.environ.get("EMAIL_USER")
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(os.environ.get("EMAIL_USER"), os.environ.get("EMAIL_PASS"))
        smtp.send_message(msg)

if __name__ == "__main__":
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
