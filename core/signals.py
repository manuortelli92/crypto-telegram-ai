from typing import List, Dict, Tuple
import re

KEYWORDS = {
    "etf": ("macro", 2),
    "sec": ("regulatorio", 2),
    "hack": ("riesgo", 3),
    "exploit": ("riesgo", 3),
    "lawsuit": ("regulatorio", 2),
    "bankrupt": ("riesgo", 3),
    "partnership": ("positivo", 1),
    "listing": ("exchange", 1),
    "delist": ("exchange", 2),
    "upgrade": ("tech", 1),
    "airdrop": ("altseason", 1),
}

SYMBOL_RE = re.compile(r"\b[A-Z]{2,6}\b")


def extract_symbols(text: str) -> List[str]:
    if not text:
        return []
    candidates = SYMBOL_RE.findall(text.upper())
    bad = {"THE", "AND", "FOR", "WITH", "THIS", "THAT", "FROM", "INTO", "ONTO", "USD"}
    out = []
    for c in candidates:
        if c in bad:
            continue
        out.append(c)
    return list(dict.fromkeys(out))


def score_article(item: Dict) -> Tuple[int, List[str], List[str]]:
    t = (item.get("title") or "").lower()
    s = (item.get("summary") or "").lower()

    tags = []
    score = 0
    for kw, (tag, w) in KEYWORDS.items():
        if kw in t or kw in s:
            tags.append(tag)
            score += w

    symbols = extract_symbols(item.get("title", ""))
    return score, list(dict.fromkeys(tags)), symbols


def build_news_signals(news: List[Dict], max_items: int = 8) -> Dict:
    scored = []
    for it in news:
        sc, tags, syms = score_article(it)
        scored.append((sc, it, tags, syms))

    scored.sort(key=lambda x: x[0], reverse=True)

    top = []
    for sc, it, tags, syms in scored:
        if sc <= 0:
            continue
        top.append(
            {"score": sc, "tags": tags, "symbols": syms[:5]}
        )
        if len(top) >= max_items:
            break

    tag_counts = {}
    sym_counts = {}
    for x in top:
        for tg in x["tags"]:
            tag_counts[tg] = tag_counts.get(tg, 0) + 1
        for sy in x["symbols"]:
            sym_counts[sy] = sym_counts.get(sy, 0) + 1

    top_syms = sorted(sym_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]

    return {
        "tag_counts": tag_counts,
        "top_symbols": [s for s, _ in top_syms],
        "n_items": len(top),
    }