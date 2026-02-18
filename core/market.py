import json
import time
import requests

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"

CACHE_FILE = "/tmp/markets_top100.json"
CACHE_TTL_SEC = 300  # 5 minutos (baja muchísimo el 429)

MAJORS_SET = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE", "DOT", "TRX", "LINK"}

STABLES = {
    "USDT","USDC","DAI","TUSD","FDUSD","USDE","USDS","FRAX","LUSD","PYUSD","GUSD","USDP",
    "USD1","RLUSD","USDG","GHO"
}

GOLD = {"XAUT", "PAXG"}


def _read_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj
    except Exception:
        return None


def _write_cache(rows):
    try:
        obj = {"ts": int(time.time()), "rows": rows}
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
    except Exception:
        pass


def fetch_top100_market(vs="usd"):
    # 1) cache fresco
    cached = _read_cache()
    if cached and (time.time() - cached.get("ts", 0) <= CACHE_TTL_SEC):
        return cached.get("rows", [])

    params = {
        "vs_currency": vs,
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "7d,30d",
    }

    # 2) retry/backoff para 429/5xx
    last_err = None
    for attempt in range(5):
        try:
            r = requests.get(COINGECKO_URL, params=params, timeout=25)
            if r.status_code == 429:
                # backoff progresivo
                time.sleep(2 + attempt * 2)
                continue
            r.raise_for_status()
            data = r.json()

            rows = []
            for idx, coin in enumerate(data, start=1):
                symbol = (coin.get("symbol") or "").upper().strip()
                name = (coin.get("name") or "").strip()
                rows.append({
                    "rank": idx,
                    "id": coin.get("id"),
                    "symbol": symbol,
                    "name": name,
                    "price": coin.get("current_price", 0) or 0,
                    "market_cap": coin.get("market_cap", 0) or 0,
                    "volume_24h": coin.get("total_volume", 0) or 0,
                    "mom_7d": coin.get("price_change_percentage_7d_in_currency", 0) or 0,
                    "mom_30d": coin.get("price_change_percentage_30d_in_currency", 0) or 0,
                })

            _write_cache(rows)
            return rows

        except Exception as e:
            last_err = e
            time.sleep(1 + attempt)

    # 3) fallback a cache viejo si existe (aunque esté pasado)
    cached = _read_cache()
    if cached and cached.get("rows"):
        return cached["rows"]

    raise last_err if last_err else RuntimeError("No se pudo obtener Top100 (sin cache).")


def is_stable(row) -> bool:
    sym = (row.get("symbol") or "").upper().strip()
    if sym in STABLES:
        return True

    name = (row.get("name") or "").lower()
    if ("stable" in name) or ("usd" in name and ("coin" in name or "dollar" in name or "stable" in name)):
        return True

    p = float(row.get("price", 0) or 0)
    m7 = float(row.get("mom_7d", 0) or 0)
    m30 = float(row.get("mom_30d", 0) or 0)
    if 0.985 <= p <= 1.015 and abs(m7) < 1.0 and abs(m30) < 2.0:
        return True

    return False


def is_gold(row) -> bool:
    sym = (row.get("symbol") or "").upper().strip()
    if sym in GOLD:
        return True
    name = (row.get("name") or "").lower()
    return "gold" in name


def is_major(row) -> bool:
    sym = (row.get("symbol") or "").upper().strip()
    rank = int(row.get("rank", 999) or 999)
    return (sym in MAJORS_SET) or (rank <= 10)


def split_alts_and_majors(rows):
    majors, alts = [], []
    for r in rows:
        (majors if is_major(r) else alts).append(r)
    return majors, alts


def estimate_risk(row) -> str:
    cap = float(row.get("market_cap", 0) or 0)
    if cap >= 200_000_000_000:
        return "LOW"
    if cap >= 30_000_000_000:
        return "MEDIUM"
    return "HIGH"