import os
import json
import boto3
import pymysql
from flask import Flask, jsonify, render_template, request
from datetime import datetime, timedelta
import socket
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_secret_cache = None
_secret_fetched_at = 0

def get_secret():
    global _secret_cache, _secret_fetched_at
    secret_name = os.environ.get("DB_SECRET_NAME")
    if secret_name:
        if _secret_cache and (time.time() - _secret_fetched_at) < 300:
            return _secret_cache
        client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
        resp = client.get_secret_value(SecretId=secret_name)
        _secret_cache = json.loads(resp["SecretString"])
        _secret_fetched_at = time.time()
        return _secret_cache
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

def get_instance_meta():
    return {
        "hostname": socket.gethostname(),
        "az":       os.environ.get("AWS_AZ", "local"),
        "region":   os.environ.get("AWS_REGION", "ap-south-1"),
        "now":      datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

@app.route("/health")
def health():
    try:
        conn = get_db(); conn.close(); db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"
    return jsonify({"status": "ok", "db": db_status, "host": socket.gethostname()}), 200

@app.route("/")
def index():
    meta = get_instance_meta()
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("INSERT INTO visitors (ip_address, user_agent) VALUES (%s, %s)",
                        (request.remote_addr, request.user_agent.string[:256]))
            conn.commit()
            cur.execute("SELECT COUNT(*) AS total FROM visitors")
            total = cur.fetchone()["total"]
            cur.execute("SELECT ip_address, visited_at FROM visitors ORDER BY id DESC LIMIT 8")
            recent = cur.fetchall()
            cur.execute("""
                SELECT DATE(visited_at) AS day, COUNT(*) AS count
                FROM visitors GROUP BY day ORDER BY day DESC LIMIT 7
            """)
            daily = cur.fetchall()
        conn.close()
        db_ok = True
    except Exception as e:
        logger.error(f"DB error: {e}")
        total, recent, daily, db_ok = 0, [], [], False

    daily_map = {str(r["day"]): r["count"] for r in daily}
    chart_labels, chart_data = [], []
    for i in range(6, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        chart_labels.append((datetime.utcnow() - timedelta(days=i)).strftime("%b %d"))
        chart_data.append(daily_map.get(d, 0))

    return render_template("index.html",
        **meta, total=total, recent=recent,
        chart_labels=json.dumps(chart_labels),
        chart_data=json.dumps(chart_data),
        db_ok=db_ok)

@app.route("/architecture")
def architecture():
    return render_template("architecture.html", **get_instance_meta())

@app.route("/infrastructure")
def infrastructure():
    meta = get_instance_meta()
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM visitors")
            total = cur.fetchone()["total"]
        conn.close()
        db_ok = True
    except Exception as e:
        logger.error(f"DB error: {e}")
        total, db_ok = 0, False
    return render_template("infrastructure.html", **meta, total=total, db_ok=db_ok)

@app.route("/api/stats")
def stats():
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM visitors")
            total = cur.fetchone()["total"]
            cur.execute("""
                SELECT DATE(visited_at) AS day, COUNT(*) AS count
                FROM visitors GROUP BY day ORDER BY day DESC LIMIT 7
            """)
            daily = cur.fetchall()
        conn.close()
        return jsonify({
            "total": total, "daily": daily,
            "host": socket.gethostname(),
            "az": os.environ.get("AWS_AZ", "local"),
            "region": os.environ.get("AWS_REGION", "ap-south-1"),
            "ts": datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
