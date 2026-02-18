import json
import time
import requests
import os
import logging

logger = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"

# En Railway, /tmp es un buen lugar para cache temporal, 
# pero usamos una ruta configurable por si acaso.
CACHE_FILE = os.getenv("MARKET_CACHE_PATH", "/tmp/markets_top100.json")
CACHE_TTL_SEC = 300  # 5 minutos

MAJORS_SET = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE", "DOT", "TRX", "LINK"}

STABLES = {
    "USDT","USDC","DAI","TUSD","FDUSD","USDE","USDS","FRAX","LUSD","PYUSD","GUSD","USDP",
    "USD1","RLUSD","USDG","GHO", "PYUSD"
}

GOLD = {"XAUT", "PAXG"}

def _read_cache():
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.debug(f"Error leyendo cache de mercado: {e}")
        return None

def _write_cache(rows):
    try:
        obj = {"ts": int(time.time()), "rows": rows}
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"No se pudo escribir cache de mercado: {e}")

def fetch_top100_market(vs="usd"):
    # 1) Intentar usar cache fresco
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

    # 2) Petición con reintentos (Exponential Backoff)
    last_err = None
    for attempt in range(5):
        try:
            # CoinGecko a veces tarda, subimos un poco el timeout
            r = requests.get(COINGECKO_URL, params=params, timeout=30)
            
            if r.status_code == 429:
                wait = 5 + (attempt * 10) # CoinGecko es muy estricto con el 429
                logger.warning(f"429 Too Many Requests en CoinGecko. Esperando {wait}s...")
                time.sleep(wait)
                continue
                
            r.raise_for_status()
            data = r.json()

            rows = []
            for idx, coin in enumerate(data, start=1):
                symbol = (coin.get("symbol") or "").upper().strip()
                # Limpieza de datos nulos para evitar errores en el Engine
                rows.append({
                    "rank": idx,
                    "id": coin.get("id"),
                    "symbol": symbol,
                    "name": (coin.get("name") or "Unknown").strip(),
                    "price": float(coin.get("current_price") or 0),
                    "market_cap": float(coin.get("market_cap") or 0),
                    "volume_24h": float(coin.get("total_volume") or 0),
                    "mom_7d": float(coin.get("price_change_percentage_7d_in_currency") or 0),
                    "mom_30d": float(coin.get("price_change_percentage_30d_in_currency") or 0),
                })

            _write_cache(rows)
            return rows

        except Exception as e:
            last_err = e
            logger.error(f"Error en intento {attempt+1} de CoinGecko: {e}")
            time.sleep(2 ** attempt) # Espera 1, 2, 4, 8 segundos

    # 3) Fallback: Si la API falla pero tenemos cache viejo, lo usamos igual
    if cached and cached.get("rows"):
        logger.warning("Usando cache expirado como fallback por error en API.")
        return cached["rows"]

    raise last_err if last_err else RuntimeError("Fallo total al conectar con la API de mercado.")

def is_stable(row) -> bool:
    sym = (row.get("symbol") or "").upper().strip()
    if sym in STABLES: return True

    name = (row.get("name") or "").lower()
    if any(k in name for k in ["stable", "tether", "usd coin", "dai"]): return True

    # Detección por comportamiento de precio (si se mantiene cerca de 1 USD)
    try:
        p = float(row.get("price", 0))
        m7 = abs(float(row.get("mom_7d", 0)))
        if 0.98 <= p <= 1.02 and m7 < 0.5:
            return True
    except:
        pass
    return False

def is_gold(row) -> bool:
    sym = (row.get("symbol") or "").upper().strip()
    if sym in GOLD: return True
    name = (row.get("name") or "").lower()
    return "gold" in name or "pax gold" in name

def is_major(row) -> bool:
    sym = (row.get("symbol") or "").upper().strip()
    rank = int(row.get("rank", 999))
    return (sym in MAJORS_SET) or (rank <= 10)

def split_alts_and_majors(rows):
    majors, alts = [], []
    for r in rows:
        if is_major(r): majors.append(r)
        else: alts.append(r)
    return majors, alts

def estimate_risk(row) -> str:
    try:
        cap = float(row.get("market_cap", 0))
        if cap >= 50_000_000_000: return "LOW"
        if cap >= 5_000_000_000: return "MEDIUM"
        return "HIGH"
    except:
        return "HIGH"
