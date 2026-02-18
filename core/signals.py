from typing import List, Dict, Tuple
import re
import logging

logger = logging.getLogger(__name__)

# Diccionario de keywords expandido para análisis de impacto
KEYWORDS = {
    "etf": ("macro", 2),
    "sec": ("regulatorio", 2),
    "fed": ("macro", 2),
    "inflation": ("macro", 2),
    "hack": ("riesgo", 4), # Subimos peso por criticidad
    "exploit": ("riesgo", 4),
    "scam": ("riesgo", 4),
    "lawsuit": ("regulatorio", 2),
    "bankrupt": ("riesgo", 5),
    "partnership": ("positivo", 2),
    "listing": ("exchange", 2),
    "delist": ("exchange", 3),
    "upgrade": ("tech", 1),
    "airdrop": ("oportunidad", 2),
    "bullish": ("sentimiento", 1),
    "bearish": ("sentimiento", 1),
}

# Regex mejorado para evitar falsos positivos
SYMBOL_RE = re.compile(r"\b[A-Z]{3,6}\b") 

def extract_symbols(text: str) -> List[str]:
    """Extrae tickers reales evitando palabras comunes del inglés/español."""
    if not text:
        return []
    
    candidates = SYMBOL_RE.findall(text.upper())
    # Lista negra extendida
    bad = {
        "THE", "AND", "FOR", "WITH", "THIS", "THAT", "FROM", "INTO", 
        "ONTO", "USD", "USDT", "ARE", "CAN", "NEW", "ALL", "BIG", "OUT"
    }
    
    out = []
    for c in candidates:
        if c not in bad and not c.isdigit():
            out.append(c)
    return list(dict.fromkeys(out))

def score_article(item: Dict) -> Tuple[int, List[str], List[str]]:
    """Analiza una noticia y le asigna un puntaje de relevancia."""
    t = (item.get("title") or "").lower()
    s = (item.get("summary") or "").lower()
    combined = t + " " + s

    tags = []
    score = 0
    
    for kw, (tag, weight) in KEYWORDS.items():
        if kw in combined:
            tags.append(tag)
            score += weight

    symbols = extract_symbols(item.get("title", ""))
    return score, list(dict.fromkeys(tags)), symbols

def build_news_signals(news: List[Dict], max_items: int = 10) -> Dict:
    """
    Sintetiza el mar de noticias en señales claras para el Engine.
    """
    scored = []
    for it in news:
        sc, tags, syms = score_article(it)
        if sc > 0: # Solo nos interesan noticias con impacto
            scored.append((sc, it, tags, syms))

    # Ordenar por relevancia (Impacto)
    scored.sort(key=lambda x: x[0], reverse=True)

    top = []
    tag_counts = {}
    sym_counts = {}

    for sc, it, tags, syms in scored[:max_items]:
        top.append({
            "title": it.get("title")[:60] + "...",
            "score": sc,
            "tags": tags,
            "symbols": syms
        })
        
        for tg in tags:
            tag_counts[tg] = tag_counts.get(tg, 0) + 1
        for sy in syms:
            sym_counts[sy] = sym_counts.get(sy, 0) + 1

    # Obtener los 5 símbolos más mencionados
    top_syms = sorted(sym_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return {
        "signals_count": len(top),
        "dominant_tags": tag_counts,
        "hot_symbols": [s for s, _ in top_syms],
        "top_stories": top
    }
