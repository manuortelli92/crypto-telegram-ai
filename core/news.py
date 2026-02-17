import xml.etree.ElementTree as ET
from typing import List, Dict
import requests

RSS_FEEDS = [
    ("CoinDesk", "https://feeds.feedburner.com/CoinDesk"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("CryptoPanic", "https://cryptopanic.com/feed/"),
]

def fetch_rss(url: str, timeout: int = 20) -> str:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text

def parse_rss(xml_text: str, max_items: int = 5) -> List[Dict]:
    items: List[Dict] = []
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return items

    for it in channel.findall("item")[:max_items]:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        if title:
            items.append({"title": title, "link": link, "pubDate": pub})
    return items

def get_news(max_total: int = 8) -> List[Dict]:
    out: List[Dict] = []
    per_feed = max(2, max_total // max(1, len(RSS_FEEDS)))

    for source, url in RSS_FEEDS:
        try:
            xml = fetch_rss(url)
            items = parse_rss(xml, max_items=per_feed)
            for x in items:
                x["source"] = source
                out.append(x)
        except Exception:
            continue

    return out[:max_total]