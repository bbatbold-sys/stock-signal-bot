import logging
from collections import defaultdict

import config

logger = logging.getLogger(__name__)

SENTIMENT_SCORES = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}


def generate_signals(articles: list[dict]) -> dict[str, dict]:
    """Aggregate article sentiments into BUY/SELL/HOLD signals per asset.

    Returns dict keyed by ticker:
    {
        "AAPL": {
            "signal": "BUY" | "SELL" | "HOLD",
            "score": float,
            "confidence": float,
            "article_count": int,
            "top_headline": str,
            "display_name": str,
        }
    }
    """
    # Group articles by ticker
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for art in articles:
        by_ticker[art["ticker"]].append(art)

    signals = {}
    for ticker in config.ALL_TICKERS:
        ticker_articles = by_ticker.get(ticker, [])
        count = len(ticker_articles)

        if count == 0:
            signals[ticker] = _empty_signal(ticker)
            continue

        # Weighted average: sentiment_score * confidence
        weighted_sum = 0.0
        weight_total = 0.0
        best_article = None
        best_confidence = 0.0

        for art in ticker_articles:
            score = SENTIMENT_SCORES.get(art.get("sentiment", "neutral"), 0.0)
            conf = art.get("confidence", 0.5)
            # Skip low-confidence neutral articles to prevent signal dilution
            if score == 0.0 and conf < 0.7:
                continue
            weighted_sum += score * conf
            weight_total += conf

            if conf > best_confidence:
                best_confidence = conf
                best_article = art

        avg_score = weighted_sum / weight_total if weight_total > 0 else 0.0
        avg_confidence = weight_total / count if count > 0 else 0.0

        # Determine signal
        if avg_score > config.BUY_THRESHOLD and count >= config.MIN_ARTICLES:
            signal = "BUY"
        elif avg_score < config.SELL_THRESHOLD and count >= config.MIN_ARTICLES:
            signal = "SELL"
        else:
            signal = "HOLD"

        signals[ticker] = {
            "signal": signal,
            "score": round(avg_score, 3),
            "confidence": round(avg_confidence * 100, 1),
            "article_count": count,
            "top_headline": best_article["title"] if best_article else "",
            "display_name": config.ASSET_DISPLAY_NAMES.get(ticker, ticker),
        }

        logger.info(
            "%s (%s): %s (score=%.3f, articles=%d, confidence=%.1f%%)",
            ticker, signals[ticker]["display_name"], signal,
            avg_score, count, signals[ticker]["confidence"],
        )

    return signals


def _empty_signal(ticker: str) -> dict:
    return {
        "signal": "HOLD",
        "score": 0.0,
        "confidence": 0.0,
        "article_count": 0,
        "top_headline": "No recent news",
        "display_name": config.ASSET_DISPLAY_NAMES.get(ticker, ticker),
    }
