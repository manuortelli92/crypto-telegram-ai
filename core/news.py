import time
import requests
import xml.etree.ElementTree as ET
import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "OrtelliCryptoAI/1.0", "Accept": "application/xml, text/xml"}
TIMEOUT = 12

# RSS Feeds seleccionados por calidad de info
RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
]

_TTL = 900  # 15 minutos
_CACHE: Dict[str, tuple] = {}

def _cache_get(key: str):
    item = _CACHE.get(key)
    if not item: return None
    ts, val = item
    if time.time() - ts < _TTL:
        return val
    return None

def _cache_set(key: str, val):
    if val:
        _CACHE[key] = (time.time(), val)

def clean_html(text: str) -> str:
    """Limpia etiquetas HTML y entidades raras de las descripciones RSS."""
    if not text: return ""
    # Quita tags HTML
    text = re.sub(r'<[^>]*>', '', text)
    # Quita espacios extra
    return " ".join(text.split())

def fetch_rss(url: str) -> List[Dict]:
    """Descarga y parsea noticias con manejo de errores de encoding."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        
        # Reparación: CoinTelegraph y otros a veces mandan bytes que ElementTree no quiere
        content = r.content.decode('utf-8', errors='ignore')
        root = ET.fromstring(content)
        
        items = []
        for it in root.findall(".//item"):
            title = clean_html(it.findtext("title") or "")
            link = (it.findtext("link") or "").strip()
            source_domain = url.split("/")[2].replace("www.", "")
            
            if title and link:
                items.append({
                    "title": title,
                    "link": link,
                    "source": source_domain
                })
        return items
    except Exception as e:
        logger.warning(f"⚠️ Fuente RSS caída o lenta ({url.split('/')[2]}): {e}")
        return []

def fetch_news(limit_total: int = 15) -> List[Dict]:
    """Motor de noticias con deduplicación y fallback."""
    key = "news_feed_unified"
    cached = _cache_get(key)
    if cached:
        return cached[:limit_total]

    all_items = []
    for feed in RSS_FEEDS:
        all_items.extend(fetch_rss(feed))

    if not all_items:
        # Si todo falló, intentamos devolver el cache aunque esté vencido
        old = _CACHE.get(key)
        return old[1][:limit_total] if old else []

    # Deduplicación por título (algunos feeds repiten noticias con distinto link)
    seen_titles = set()
    unique_news = []
    for it in all_items:
        t_normalized = it["title"].lower().strip()
        if t_normalized not in seen_titles:
            seen_titles.add(t_normalized)
            unique_news.append(it)

    _cache_set(key, unique_news)
    return unique_news[:limit_total]

def get_news_summary_for_llm(limit: int = 6) -> str:
    """
    Formatea las noticias para el Engine. 
    Asegura que Gemini reciba info fresca para su análisis.
    """
    news = fetch_news(limit)
    if not news:
        return "No hay noticias de impacto encontradas en la última hora."
    
    # Construcción de un bloque de texto compacto
    header = "📰 NOTICIAS RECIENTES DEL MERCADO:\n"
    lines = [f"- {n['title']} (Vía: {n['source']})" for n in news]
    
    return header + "\n".join(lines)
