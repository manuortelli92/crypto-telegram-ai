import time
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict

HEADERS = {"User-Agent": "OrtelliCryptoAI/1.0"}
TIMEOUT = 20

# RSS “seguros” para arrancar (podés cambiar)
RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
]

_TTL = 600  # 10 min
_CACHE = {}  # key -> (ts, val)


def _cache_get(key: str):
    item = _CACHE.get(key)
    if not item:
        return None
    ts, val = item
    if time.time() - ts < _TTL:
        return val
    return None


def _cache_set(key: str, val):
    _CACHE[key] = (time.time(), val)


def fetch_rss(url: str) -> List[Dict]:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()

    root = ET.fromstring(r.text)
    items = []
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        desc = (it.findtext("description") or "").strip()
        if title and link:
            items.append({
                "title": title,
                "link": link,
                "published": pub,
                "summary": desc,
                "source": url,
            })
    return items


def fetch_news(limit_total: int = 40) -> List[Dict]:
    key = f"news:{limit_total}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    all_items: List[Dict] = []
    for feed in RSS_FEEDS:
        try:
            all_items.extend(fetch_rss(feed))
        except Exception:
            continue

    # dedupe por link
    seen = set()
    out = []
    for it in all_items:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        out.append(it)

    out = out[:limit_total]
    _cache_set(key, out)
    return out