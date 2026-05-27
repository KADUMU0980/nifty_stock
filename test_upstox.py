"""Quick test to check Upstox API responses directly."""
import requests
import sys

TOKEN = input("Paste your Upstox access token: ").strip()
if not TOKEN:
    print("No token provided!")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Api-Version": "2.0",
}

BASE = "https://api.upstox.com/v2"

print("\n--- Test 1: Option Contract (expiries) ---")
try:
    r = requests.get(
        f"{BASE}/option/contract",
        params={"instrument_key": "NSE_INDEX|Nifty 50"},
        headers=headers,
        timeout=10,
    )
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:600]}")
except Exception as e:
    print(f"Error: {e}")

print("\n--- Test 2: Market Quotes (VIX + Nifty) ---")
try:
    r = requests.get(
        f"{BASE}/market-quote/quotes",
        params={"instrument_key": "NSE_INDEX|Nifty 50,NSE_INDEX|India VIX"},
        headers=headers,
        timeout=10,
    )
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:600]}")
except Exception as e:
    print(f"Error: {e}")

print("\n--- Test 3: Option Chain ---")
try:
    r = requests.get(
        f"{BASE}/option/chain",
        params={"instrument_key": "NSE_INDEX|Nifty 50", "expiry_date": "2026-05-29"},
        headers=headers,
        timeout=15,
    )
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:600]}")
except Exception as e:
    print(f"Error: {e}")
