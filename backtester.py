"""
Backtest FinBERT sentiment signals against actual price movements.

Collects historical news via Yahoo RSS, runs FinBERT sentiment analysis,
fetches real price data via yfinance, and finds optimal signal thresholds.

Usage:
    python backtester.py
"""

import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import feedparser
import yfinance as yf

import config
from sentiment_analyzer import analyze_sentiment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("backtester")

SENTIMENT_SCORES = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}

LOOKBACK_DAYS = 30


def collect_historical_news() -> list[dict]:
    """Fetch news from Yahoo RSS for all tickers, preserving published dates."""
    all_articles = []
    for ticker in config.ALL_TICKERS:
        url = config.YAHOO_RSS_URL.format(ticker=ticker)
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                if published is None:
                    continue  # skip articles without dates
                all_articles.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "source": "Yahoo Finance",
                    "ticker": ticker,
                    "published": published,
                    "link": entry.get("link", ""),
                })
            logger.info("Yahoo RSS for %s: %d articles", ticker, len(feed.entries))
        except Exception:
            logger.exception("Error fetching Yahoo RSS for %s", ticker)

    # Filter out empty titles
    all_articles = [a for a in all_articles if a["title"].strip()]

    # Deduplicate by title
    seen = set()
    unique = []
    for art in all_articles:
        key = art["title"].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(art)

    logger.info("Collected %d unique articles with dates", len(unique))
    return unique


def fetch_price_data(tickers: list[str], days: int = LOOKBACK_DAYS) -> dict:
    """Fetch daily closing prices for each ticker via yfinance.

    Returns dict: {ticker: {date_str: close_price, ...}}
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days + 10)  # extra buffer for weekends

    prices = {}
    for ticker in tickers:
        try:
            df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                             end=end.strftime("%Y-%m-%d"), progress=False)
            if df.empty:
                logger.warning("No price data for %s", ticker)
                continue
            # Flatten MultiIndex columns if present (yfinance returns MultiIndex for single ticker too)
            if hasattr(df.columns, 'levels'):
                df.columns = df.columns.get_level_values(0)
            daily = {}
            for idx, row in df.iterrows():
                date_str = idx.strftime("%Y-%m-%d")
                daily[date_str] = float(row["Close"])
            prices[ticker] = daily
            logger.info("Price data for %s: %d days", ticker, len(daily))
        except Exception:
            logger.exception("Error fetching price data for %s", ticker)

    return prices


def compute_next_day_change(prices: dict, date_str: str) -> float | None:
    """Given a dict of {date_str: price}, find the % change from date_str to the next trading day."""
    sorted_dates = sorted(prices.keys())
    if date_str not in sorted_dates:
        # Find the nearest trading day on or after date_str
        candidates = [d for d in sorted_dates if d >= date_str]
        if not candidates:
            return None
        date_str = candidates[0]

    idx = sorted_dates.index(date_str)
    if idx + 1 >= len(sorted_dates):
        return None  # no next day available

    price_today = prices[sorted_dates[idx]]
    price_next = prices[sorted_dates[idx + 1]]
    if price_today == 0:
        return None
    return ((price_next - price_today) / price_today) * 100


def compute_sentiment_score(articles: list[dict]) -> float:
    """Compute weighted sentiment score for a group of articles (same formula as signal_generator)."""
    weighted_sum = 0.0
    weight_total = 0.0
    for art in articles:
        score = SENTIMENT_SCORES.get(art.get("sentiment", "neutral"), 0.0)
        conf = art.get("confidence", 0.5)
        weighted_sum += score * conf
        weight_total += conf
    return weighted_sum / weight_total if weight_total > 0 else 0.0


def build_backtest_table(articles: list[dict], prices: dict) -> list[dict]:
    """Build a table of [ticker, date, sentiment_score, actual_change%, article_count]."""
    # Group articles by (ticker, date)
    groups = defaultdict(list)
    for art in articles:
        pub = art["published"]
        date_str = pub.strftime("%Y-%m-%d")
        groups[(art["ticker"], date_str)].append(art)

    table = []
    for (ticker, date_str), arts in sorted(groups.items()):
        if ticker not in prices:
            continue
        change = compute_next_day_change(prices[ticker], date_str)
        if change is None:
            continue
        score = compute_sentiment_score(arts)
        table.append({
            "ticker": ticker,
            "date": date_str,
            "sentiment_score": score,
            "actual_change_pct": change,
            "article_count": len(arts),
        })

    return table


def evaluate_thresholds(table: list[dict], buy_thresh: float, sell_thresh: float,
                        min_articles: int) -> dict:
    """Evaluate accuracy for given thresholds.

    Returns dict with accuracy metrics and confusion matrix counts.
    """
    tp_buy = 0   # predicted BUY, price went up
    fp_buy = 0   # predicted BUY, price went down
    tp_sell = 0  # predicted SELL, price went down
    fp_sell = 0  # predicted SELL, price went up
    hold_count = 0
    total_signals = 0

    for row in table:
        score = row["sentiment_score"]
        change = row["actual_change_pct"]
        count = row["article_count"]

        if count < min_articles:
            hold_count += 1
            continue

        if score > buy_thresh:
            total_signals += 1
            if change > 0:
                tp_buy += 1
            else:
                fp_buy += 1
        elif score < sell_thresh:
            total_signals += 1
            if change < 0:
                tp_sell += 1
            else:
                fp_sell += 1
        else:
            hold_count += 1

    correct = tp_buy + tp_sell
    accuracy = correct / total_signals if total_signals > 0 else 0.0

    return {
        "buy_threshold": buy_thresh,
        "sell_threshold": sell_thresh,
        "min_articles": min_articles,
        "accuracy": accuracy,
        "total_signals": total_signals,
        "correct": correct,
        "tp_buy": tp_buy,
        "fp_buy": fp_buy,
        "tp_sell": tp_sell,
        "fp_sell": fp_sell,
        "hold_count": hold_count,
    }


def sweep_thresholds(table: list[dict]) -> list[dict]:
    """Sweep across threshold combinations and min_articles values."""
    results = []
    buy_range = [round(x * 0.05, 2) for x in range(1, 13)]     # 0.05 to 0.60
    sell_range = [round(-x * 0.05, 2) for x in range(1, 13)]    # -0.05 to -0.60
    min_articles_options = [1, 2, 3, 5]

    for min_art in min_articles_options:
        for bt in buy_range:
            for st in sell_range:
                result = evaluate_thresholds(table, bt, st, min_art)
                results.append(result)

    return results


def per_ticker_accuracy(table: list[dict], buy_thresh: float, sell_thresh: float,
                        min_articles: int) -> dict[str, dict]:
    """Compute accuracy per ticker."""
    by_ticker = defaultdict(list)
    for row in table:
        by_ticker[row["ticker"]].append(row)

    ticker_stats = {}
    for ticker, rows in sorted(by_ticker.items()):
        stats = evaluate_thresholds(rows, buy_thresh, sell_thresh, min_articles)
        stats["ticker"] = ticker
        ticker_stats[ticker] = stats

    return ticker_stats


def print_report(table: list[dict], current: dict, optimal: dict,
                 ticker_stats_current: dict, ticker_stats_optimal: dict):
    """Print the full backtest report."""
    print("\n" + "=" * 70)
    print("  BACKTEST REPORT: FinBERT Sentiment vs Actual Price Movements")
    print("=" * 70)

    print(f"\nData points: {len(table)} ticker-date combinations")
    tickers_seen = set(r["ticker"] for r in table)
    print(f"Tickers with data: {len(tickers_seen)}")
    date_range = sorted(set(r["date"] for r in table))
    if date_range:
        print(f"Date range: {date_range[0]} to {date_range[-1]}")

    # --- Current thresholds ---
    print("\n" + "-" * 70)
    print("  CURRENT THRESHOLDS")
    print(f"  BUY > {current['buy_threshold']}, SELL < {current['sell_threshold']}, "
          f"MIN_ARTICLES = {current['min_articles']}")
    print("-" * 70)
    print(f"  Accuracy:      {current['accuracy']:.1%}  "
          f"({current['correct']}/{current['total_signals']} signals correct)")
    print(f"  BUY signals:   {current['tp_buy']} correct, {current['fp_buy']} wrong")
    print(f"  SELL signals:  {current['tp_sell']} correct, {current['fp_sell']} wrong")
    print(f"  HOLD (no signal): {current['hold_count']}")

    # --- Optimal thresholds ---
    print("\n" + "-" * 70)
    print("  OPTIMAL THRESHOLDS (from sweep)")
    print(f"  BUY > {optimal['buy_threshold']}, SELL < {optimal['sell_threshold']}, "
          f"MIN_ARTICLES = {optimal['min_articles']}")
    print("-" * 70)
    print(f"  Accuracy:      {optimal['accuracy']:.1%}  "
          f"({optimal['correct']}/{optimal['total_signals']} signals correct)")
    print(f"  BUY signals:   {optimal['tp_buy']} correct, {optimal['fp_buy']} wrong")
    print(f"  SELL signals:  {optimal['tp_sell']} correct, {optimal['fp_sell']} wrong")
    print(f"  HOLD (no signal): {optimal['hold_count']}")

    # --- Per-ticker breakdown (optimal) ---
    print("\n" + "-" * 70)
    print("  PER-TICKER ACCURACY (optimal thresholds)")
    print("-" * 70)
    print(f"  {'Ticker':<12} {'Name':<10} {'Signals':>8} {'Correct':>8} {'Accuracy':>9}")
    for ticker, stats in ticker_stats_optimal.items():
        name = config.ASSET_DISPLAY_NAMES.get(ticker, ticker)
        sig = stats["total_signals"]
        cor = stats["correct"]
        acc = f"{stats['accuracy']:.0%}" if sig > 0 else "N/A"
        print(f"  {ticker:<12} {name:<10} {sig:>8} {cor:>8} {acc:>9}")

    # --- Confusion matrix ---
    print("\n" + "-" * 70)
    print("  CONFUSION MATRIX (optimal thresholds)")
    print("-" * 70)
    print(f"                    Actual UP    Actual DOWN")
    print(f"  Predicted BUY     {optimal['tp_buy']:>8}     {optimal['fp_buy']:>8}")
    print(f"  Predicted SELL    {optimal['fp_sell']:>8}     {optimal['tp_sell']:>8}")

    # --- Recommendations ---
    print("\n" + "-" * 70)
    print("  RECOMMENDATIONS")
    print("-" * 70)
    if optimal['accuracy'] > current['accuracy']:
        delta = optimal['accuracy'] - current['accuracy']
        print(f"  * Switch to optimal thresholds for +{delta:.1%} accuracy improvement")
    else:
        print(f"  * Current thresholds are already at or near optimal")
    print(f"  * BUY_THRESHOLD  = {optimal['buy_threshold']}")
    print(f"  * SELL_THRESHOLD = {optimal['sell_threshold']}")
    print(f"  * MIN_ARTICLES   = {optimal['min_articles']}")

    # Check if neutral articles dilute signal
    neutral_heavy = sum(1 for r in table if abs(r["sentiment_score"]) < 0.1)
    if neutral_heavy > len(table) * 0.5:
        print(f"  * WARNING: {neutral_heavy}/{len(table)} data points have near-zero sentiment")
        print(f"    Consider filtering out neutral-heavy groups or boosting non-neutral weight")

    if optimal['total_signals'] < 5:
        print(f"  * NOTE: Only {optimal['total_signals']} actionable signals found.")
        print(f"    Results may not be statistically significant. Collect more data over time.")

    print("\n" + "=" * 70)
    print()


def main():
    print("Starting backtest...\n")

    # Step 1: Collect historical news
    print("[1/4] Collecting historical news from Yahoo RSS...")
    articles = collect_historical_news()
    if not articles:
        print("ERROR: No articles collected. Cannot run backtest.")
        return

    # Step 2: Run FinBERT sentiment
    print(f"[2/4] Running FinBERT sentiment on {len(articles)} articles...")
    articles = analyze_sentiment(articles)

    # Step 3: Fetch price data
    tickers_with_articles = list(set(a["ticker"] for a in articles))
    print(f"[3/4] Fetching price data for {len(tickers_with_articles)} tickers...")
    prices = fetch_price_data(tickers_with_articles)

    # Step 4: Build comparison table
    print("[4/4] Comparing predictions vs reality...")
    table = build_backtest_table(articles, prices)

    if not table:
        print("ERROR: No data points to evaluate. Price data may not overlap with news dates.")
        return

    print(f"\nBuilt {len(table)} data points for evaluation.\n")

    # Evaluate current thresholds
    current = evaluate_thresholds(table, config.BUY_THRESHOLD, config.SELL_THRESHOLD,
                                  config.MIN_ARTICLES)

    # Sweep for optimal
    all_results = sweep_thresholds(table)
    # Filter to results with at least 3 signals to avoid noise
    viable = [r for r in all_results if r["total_signals"] >= 3]
    if not viable:
        viable = [r for r in all_results if r["total_signals"] >= 1]
    if not viable:
        print("ERROR: No viable threshold combinations found.")
        return

    # Sort by accuracy (desc), then by total_signals (desc) as tiebreaker
    viable.sort(key=lambda r: (r["accuracy"], r["total_signals"]), reverse=True)
    optimal = viable[0]

    # Per-ticker stats
    ticker_stats_current = per_ticker_accuracy(table, config.BUY_THRESHOLD,
                                               config.SELL_THRESHOLD, config.MIN_ARTICLES)
    ticker_stats_optimal = per_ticker_accuracy(table, optimal["buy_threshold"],
                                               optimal["sell_threshold"],
                                               optimal["min_articles"])

    print_report(table, current, optimal, ticker_stats_current, ticker_stats_optimal)

    # Return optimal for programmatic use
    return optimal


def auto_tune():
    """Run backtest and update config thresholds in memory if better ones are found.

    Called automatically by the daily pipeline before signal generation.
    Returns True if thresholds were updated, False otherwise.
    """
    logger.info("Auto-tune: running backtest to optimize thresholds...")

    articles = collect_historical_news()
    if not articles:
        logger.warning("Auto-tune: no articles collected, keeping current thresholds")
        return False

    articles = analyze_sentiment(articles)

    tickers_with_articles = list(set(a["ticker"] for a in articles))
    prices = fetch_price_data(tickers_with_articles)

    table = build_backtest_table(articles, prices)
    if not table:
        logger.warning("Auto-tune: no data points, keeping current thresholds")
        return False

    current = evaluate_thresholds(table, config.BUY_THRESHOLD, config.SELL_THRESHOLD,
                                  config.MIN_ARTICLES)

    all_results = sweep_thresholds(table)
    viable = [r for r in all_results if r["total_signals"] >= 3]
    if not viable:
        viable = [r for r in all_results if r["total_signals"] >= 1]
    if not viable:
        logger.warning("Auto-tune: no viable thresholds found, keeping current")
        return False

    viable.sort(key=lambda r: (r["accuracy"], r["total_signals"]), reverse=True)
    optimal = viable[0]

    if optimal["accuracy"] > current["accuracy"]:
        old = (config.BUY_THRESHOLD, config.SELL_THRESHOLD, config.MIN_ARTICLES)
        config.BUY_THRESHOLD = optimal["buy_threshold"]
        config.SELL_THRESHOLD = optimal["sell_threshold"]
        config.MIN_ARTICLES = optimal["min_articles"]
        logger.info(
            "Auto-tune: updated thresholds — BUY=%.2f (was %.2f), SELL=%.2f (was %.2f), "
            "MIN_ARTICLES=%d (was %d) — accuracy %.1f%% -> %.1f%%",
            config.BUY_THRESHOLD, old[0], config.SELL_THRESHOLD, old[1],
            config.MIN_ARTICLES, old[2],
            current["accuracy"] * 100, optimal["accuracy"] * 100,
        )
        return True
    else:
        logger.info(
            "Auto-tune: current thresholds are optimal (%.1f%% accuracy), no changes",
            current["accuracy"] * 100,
        )
        return False


if __name__ == "__main__":
    result = main()
