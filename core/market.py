def verify_prices(rows: List[Dict]) -> Tuple[List[Dict], Dict]:
    enriched = []
    verified_count = 0
    
    for r in rows:
        try:
            # Si verify_price_multi_source falla o no devuelve lo esperado, 
            # asumimos 1 fuente (CoinGecko) para que no explote el engine
            ok_count, sources_str = verify_price_multi_source(r["price"], r["symbol"])
        except Exception:
            ok_count, sources_str = 1, "coingecko"
            
        rr = dict(r)
        rr["verified"] = ok_count >= 2
        rr["price_anchor"] = r["price"]
        rr["sources_ok"] = ok_count
        enriched.append(rr)
        
        if rr["verified"]:
            verified_count += 1
            
    stats = {
        "total": len(rows),
        "verified": verified_count,
        "verified_pct": (verified_count / len(rows) * 100) if rows else 0
    }
    return enriched, stats
