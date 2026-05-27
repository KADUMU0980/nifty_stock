"""
Upstox Option Chain – Vercel Serverless API
============================================
Single serverless function handling all /api/* routes.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import time
from datetime import date
import os

app = Flask(__name__)
CORS(app)

UPSTOX_BASE = "https://api.upstox.com/v2"

# ── Helpers ───────────────────────────────────────────────────────────
def upstox_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Api-Version": "2.0",
    }

def get_token() -> str | None:
    """Read token from request header, query param, or environment variable."""
    token = request.headers.get("X-Access-Token") or request.args.get("token")
    if not token or token == "env" or token == "server_env":
        token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    return token

# ── Expiry helper ─────────────────────────────────────────────────────
def fetch_expiries(token: str) -> list[str]:
    """Return sorted list of upcoming expiry dates for NIFTY."""
    try:
        r = requests.get(
            f"{UPSTOX_BASE}/option/contract",
            params={"instrument_key": "NSE_INDEX|Nifty 50"},
            headers=upstox_headers(token),
            timeout=10,
        )
        print(f"[DEBUG] Expiry API status: {r.status_code}")
        print(f"[DEBUG] Expiry API response: {r.text[:500]}")
        if r.status_code == 200:
            data = r.json().get("data", [])
            today = date.today().isoformat()
            expiries = sorted(
                set(d["expiry"] for d in data if d.get("expiry") and d["expiry"] >= today)
            )
            return expiries[:10]
        else:
            print(f"[DEBUG] Expiry API failed with status {r.status_code}")
    except Exception as e:
        print(f"Expiry fetch error: {e}")
    return []

# ── Data transform ─────────────────────────────────────────────────────
def transform_chain(chain_data: list, expiry: str) -> dict:
    """
    Convert Upstox option chain format -> NSE-compatible format
    so the frontend processNSEData() works without changes.
    """
    records = []
    for item in chain_data:
        strike = item.get("strike_price", 0)

        def extract(side_key: str) -> dict:
            side = item.get(side_key, {})
            md = side.get("market_data", {})
            greeks = side.get("option_greeks", {})

            ltp = md.get("ltp") or 0
            prev_close = md.get("close_price") or 0
            oi = md.get("oi") or 0
            chg_oi = md.get("net_change_in_oi")
            if chg_oi is None:
                prev_oi = md.get("prev_oi") or 0
                chg_oi = oi - prev_oi

            return {
                "openInterest": int(oi),
                "changeinOpenInterest": int(chg_oi),
                "totalTradedVolume": int(md.get("volume") or 0),
                "impliedVolatility": round(float(greeks.get("iv") or 0), 2),
                "lastPrice": round(float(ltp), 2),
                "change": round(float(ltp) - float(prev_close), 2),
                "bidprice": round(float(md.get("bid_price") or 0), 2),
                "askPrice": round(float(md.get("ask_price") or 0), 2),
            }

        row = {
            "strikePrice": strike,
            "expiryDate": expiry,
            "CE": extract("call_options"),
            "PE": extract("put_options"),
        }
        records.append(row)

    records.sort(key=lambda x: x["strikePrice"])

    return {
        "records": {
            "data": records,
            "underlyingValue": None,
            "timestamp": time.strftime("%d-%b-%Y %H:%M:%S"),
            "expiryDates": [expiry],
        }
    }

# ── Endpoints ─────────────────────────────────────────────────────────

@app.route("/api/expiries")
def api_expiries():
    token = get_token()
    if not token:
        return jsonify({"status": "error", "message": "Access token required"}), 401
    expiries = fetch_expiries(token)
    if expiries:
        return jsonify({"status": "ok", "expiries": expiries})
    return jsonify({"status": "error", "message": "Could not fetch expiry dates -- check token"}), 500


@app.route("/api/option-chain")
def option_chain():
    token = get_token()
    if not token:
        return jsonify({"status": "error", "message": "Access token required"}), 401

    expiry = request.args.get("expiry")
    if not expiry:
        expiries = fetch_expiries(token)
        if not expiries:
            return jsonify({"status": "error", "message": "Could not determine expiry"}), 500
        expiry = expiries[0]

    try:
        r = requests.get(
            f"{UPSTOX_BASE}/option/chain",
            params={"instrument_key": "NSE_INDEX|Nifty 50", "expiry_date": expiry},
            headers=upstox_headers(token),
            timeout=15,
        )
        if r.status_code == 401:
            return jsonify({"status": "error", "message": "Invalid or expired Upstox token"}), 401
        if r.status_code != 200:
            return jsonify({"status": "error", "message": f"Upstox returned {r.status_code}: {r.text[:200]}"}), 502

        raw = r.json()
        if raw.get("status") != "success":
            return jsonify({"status": "error", "message": raw.get("message", "Upstox error")}), 502

        chain_data = raw.get("data", [])
        transformed = transform_chain(chain_data, expiry)
        return jsonify({"status": "ok", "source": "upstox_live", "expiry": expiry, "data": transformed})

    except requests.Timeout:
        return jsonify({"status": "error", "message": "Upstox request timed out"}), 504
    except Exception as e:
        print(f"Option chain error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/vix")
def vix():
    token = get_token()
    if not token:
        return jsonify({"status": "error", "message": "Access token required"}), 401

    try:
        keys = "NSE_INDEX|Nifty 50,NSE_INDEX|India VIX"
        r = requests.get(
            f"{UPSTOX_BASE}/market-quote/quotes",
            params={"instrument_key": keys},
            headers=upstox_headers(token),
            timeout=10,
        )
        if r.status_code != 200:
            return jsonify({"status": "error", "message": f"Upstox VIX error {r.status_code}: {r.text[:200]}"}), 502

        data = r.json().get("data", {})

        def extract_quote(key: str) -> dict:
            q = data.get(key, {})
            return {
                "lastPrice": q.get("last_price"),
                "change": q.get("net_change"),
                "pChange": q.get("net_change_percentage"),
            }

        return jsonify({
            "status": "ok",
            "data": {
                "nifty": extract_quote("NSE_INDEX:Nifty 50"),
                "vix":   extract_quote("NSE_INDEX:India VIX"),
            }
        })
    except Exception as e:
        print(f"VIX fetch error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/health")
@app.route("/health")
def health():
    return jsonify({"status": "running", "proxy": "Upstox Option Chain Proxy v2.0"})
