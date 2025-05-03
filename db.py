import sqlite3
from datetime import datetime

DB_FILE = "pnl.db"

def create_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS pnl (
        pair TEXT,
        amount REAL,
        currency TEXT,
        timestamp TEXT
    )''')
    conn.commit()
    conn.close()

def save_to_db(pair: str, amount: float, currency: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('INSERT INTO pnl (pair, amount, currency, timestamp) VALUES (?, ?, ?, ?)',
                   (pair, amount, currency, timestamp))
    conn.commit()
    conn.close()

def calculate_daily_summary():
    conn = sqlite3.connect("pnl.db")
    cursor = conn.cursor()
    cursor.execute('SELECT currency, amount FROM pnl')
    all_rows = cursor.fetchall()
    conn.close()

    summary = {}  # словник: { 'USDT': {'profit': x, 'loss': y, 'net': z}, ... }

    for currency, amount in all_rows:
        if currency not in summary:
            summary[currency] = {'profit': 0, 'loss': 0}
        if amount >= 0:
            summary[currency]['profit'] += amount
        else:
            summary[currency]['loss'] += amount

    # Рахуємо net після збору
    for val in summary.values():
        val['net'] = val['profit'] + val['loss']

    return summary
