import time
import requests
import xml.etree.ElementTree as ET
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "OrtelliCryptoAI/1.0"}
TIMEOUT = 15

# RSS Feeds confiables
RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
]

_TTL = 900  # 15 minutos de cache (las noticias no cambian cada segundo)
_CACHE: Dict[str, tuple] = {}

def _cache_get(key: str):
    item = _CACHE.get(key)
    if not item: return None
    ts, val = item
    if time.time() - ts < _TTL:
        return val
    return None

def _cache_set(key: str, val):
    _CACHE[key] = (time.time(), val)

def fetch_rss(url: str) -> List[Dict]:
    """Descarga y parsea un feed RSS de noticias cripto."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        
        # Usamos un parser que maneje mejor posibles errores de encoding
        root = ET.fromstring(r.content)
        items = []
        
        # Buscamos los elementos 'item' dentro del canal
        for it in root.findall(".//item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            # Limpiamos el HTML básico que suele venir en las descripciones
            desc = (it.findtext("description") or "").strip()
            
            if title and link:
                items.append({
                    "title": title,
                    "link": link,
                    "published": pub,
                    "summary": desc[:300] + "..." if len(desc) > 300 else desc,
                    "source": url.split("/")[2], # Guarda solo el dominio (ej: cointelegraph.com)
                })
        return items
    except Exception as e:
        logger.error(f"Error parseando RSS de {url}: {e}")
        return []

def fetch_news(limit_total: int = 15) -> List[Dict]:
    """Obtiene noticias de todas las fuentes, las deduplica y las cachea."""
    key = f"news_feed"
    cached = _cache_get(key)
    if cached is not None:
        return cached[:limit_total]

    all_items: List[Dict] = []
    for feed in RSS_FEEDS:
        all_items.extend(fetch_rss(feed))

    # 1. Deduplicación por link o título
    seen_links = set()
    unique_news = []
    for it in all_items:
        if it["link"] not in seen_links:
            seen_links.add(it["link"])
            unique_news.append(it)

    # 2. Ordenar (si las fechas están en formato estándar, las más nuevas primero)
    # Por ahora solo limitamos
    out = unique_news[:40] # Guardamos 40 en cache
    _cache_set(key, out)
    
    return out[:limit_total]

def get_news_summary_for_llm(limit: int = 8) -> str:
    """Formatea las noticias para que Gemini las pueda leer fácilmente."""
    news = fetch_news(limit)
    if not news:
        return "No hay noticias relevantes de último momento."
    
    lines = []
    for n in news:
        lines.append(f"- {n['title']} (Fuente: {n['source']})")
    
    return "\n".join(lines)
