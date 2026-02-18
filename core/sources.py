import time
import requests
import logging
import os
from typing import Dict, Optional, Tuple, List
from core.cache import TTLCache

logger = logging.getLogger(__name__)

# Cache de 10 minutos para proteger la IP del servidor en Railway
_cache = TTLCache(ttl_seconds=600, max_items=1024)

# Configuración de Endpoints
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3/coins/markets"
CG_API_KEY = os.getenv("CG_API_KEY") 

# Usamos Session para reutilizar la conexión TCP y ganar velocidad
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "OrtelliCryptoBot/2.0"})

def _get_json(url: str, params: Optional[dict] = None, timeout: int = 25) -> Optional[dict]:
    """Maneja la comunicación HTTP con headers de seguridad."""
    headers = {}
    if CG_API_KEY:
        headers["x-cg-demo-api-key"] = CG_API_KEY
    
    try:
        r = _SESSION.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        if r.status_code == 429:
            logger.error("🛑 Rate Limit alcanzado en CoinGecko (429).")
        raise e
    except Exception as e:
        logger.error(f"❌ Error de red: {e}")
        raise

def fetch_coingecko_top100(vs: str = "usd") -> list:
    """Obtiene el Top 100 con lógica de resiliencia ante caídas."""
    key = f"cg:top100:{vs}"
    cached = _cache.get(key)
    if cached is not None:
        return cached

    params = {
        "vs_currency": vs,
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "24h,7d,30d", # Agregamos 24h para el Engine
    }

    # Estrategia de reintentos: 0s, 10s, 25s
    for wait in (0, 10, 25):
        if wait:
            logger.warning(f"⏳ Reintentando CoinGecko en {wait}s...")
            time.sleep(wait)
        try:
            data = _get_json(COINGECKO_BASE_URL, params=params)
            if data and isinstance(data, list):
                # Limpieza rápida: asegurar tipos de datos
                for coin in data:
                    coin["current_price"] = float(coin.get("current_price") or 0)
                    coin["symbol"] = coin.get("symbol", "").upper()
                
                _cache.set(key, data)
                return data
        except Exception as e:
            if "429" not in str(e):
                break # Si no es saturación, salimos para no perder tiempo
            continue

    # Si todo falla, el 'allow_stale' nos salva: devuelve la última data aunque haya expirado
    logger.critical("⚠️ Fallo total de API. Usando datos históricos del caché.")
    return _cache.get(key, allow_stale=True) or []

def verify_price_multi_source(anchor_price: float, symbol: str) -> Tuple[int, str]:
    """
    Sistema de validación. Por ahora confía en CG, pero está listo 
    para expandirse a Binance/Kraken sin romper el Engine.
    """
    if anchor_price <= 0:
        return 0, "invalid_price"
    return 1, "coingecko_verified"

# Fallbacks para compatibilidad con el Arquitecto de Mercado
def kraken_spot_price_usd(symbol: str): return None
def coinbase_spot_price_usd(symbol: str): return None
