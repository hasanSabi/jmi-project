import os
import json
import boto3
import pymysql
from flask import Flask, jsonify, render_template, request
from datetime import datetime
import socket
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── DB helpers ────────────────────────────────────────────────────────────────

def get_secret():
    """Fetch DB credentials from AWS Secrets Manager (prod) or env vars (local)."""
    secret_name = os.environ.get("DB_SECRET_NAME")
    if secret_name:
        client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
        resp = client.get_secret_value(SecretId=secret_name)
        return json.loads(resp["SecretString"])
    # local dev fallback
    return {
        "username": os.environ.get("DB_USER", "appuser"),
        "password": os.environ.get("DB_PASS", "apppassword"),
        "host":     os.environ.get("DB_HOST", "127.0.0.1"),
        "dbname":   os.environ.get("DB_NAME", "appdb"),
    }

def get_db():
    creds = get_secret()
    return pymysql.connect(
        host=creds["host"],
        user=creds["username"],
        password=creds["password"],
        database=creds["dbname"],
        connect_timeout=5,
        cursorclass=pymysql.cursors.DictCursor,
    )

def init_db():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS visitors (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                ip_address VARCHAR(64),
                user_agent VARCHAR(256),
                visited_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()
    conn.close()
    logger.info("DB initialised")

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    """ALB health-check endpoint — must return 200."""
    try:
        conn = get_db()
        conn.close()
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"
    return jsonify({"status": "ok", "db": db_status, "host": socket.gethostname()}), 200

@app.route("/")
def index():
    """Main page — record visit, show stats."""
    try:
        conn = get_db()
        with conn.cursor() as cur:
            # record this visit
            cur.execute(
                "INSERT INTO visitors (ip_address, user_agent) VALUES (%s, %s)",
                (request.remote_addr, request.user_agent.string[:256])
            )
            conn.commit()
            # total visitors
            cur.execute("SELECT COUNT(*) AS total FROM visitors")
            total = cur.fetchone()["total"]
            # recent 5
            cur.execute("SELECT ip_address, visited_at FROM visitors ORDER BY id DESC LIMIT 5")
            recent = cur.fetchall()
        conn.close()
        db_ok = True
    except Exception as e:
        logger.error(f"DB error: {e}")
        total, recent, db_ok = 0, [], False

    return render_template(
        "index.html",
        hostname=socket.gethostname(),
        az=os.environ.get("AWS_AZ", "local"),
        region=os.environ.get("AWS_REGION", "local"),
        total=total,
        recent=recent,
        db_ok=db_ok,
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
    )

@app.route("/api/stats")
def stats():
    """JSON stats endpoint."""
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM visitors")
            total = cur.fetchone()["total"]
            cur.execute("""
                SELECT DATE(visited_at) AS day, COUNT(*) AS count
                FROM visitors
                GROUP BY day
                ORDER BY day DESC
                LIMIT 7
            """)
            daily = cur.fetchall()
        conn.close()
        return jsonify({"total": total, "daily": daily, "host": socket.gethostname()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
