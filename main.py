import argparse
import logging
import sys
import time
from datetime import datetime, timezone

import schedule

import config
from news_collector import collect_all_news
from sentiment_analyzer import analyze_sentiment
from signal_generator import generate_signals
from email_sender import send_digest
from backtester import auto_tune
from publish import publish_to_github_pages


def setup_logging():
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def run_pipeline():
    """Execute the full news -> sentiment -> signals -> email pipeline."""
    logger = logging.getLogger("pipeline")
    start = time.time()
    logger.info("=" * 60)
    logger.info("Starting signal generation pipeline at %s", datetime.now(timezone.utc).isoformat())

    # Step 0: Auto-tune thresholds from recent backtest data
    logger.info("Step 0/5: Auto-tuning signal thresholds...")
    try:
        auto_tune()
    except Exception:
        logger.exception("Auto-tune failed, continuing with current thresholds")

    logger.info("Step 1/5: Collecting news...")
    articles = collect_all_news()
    if not articles:
        logger.warning("No articles collected. Skipping pipeline.")
        return

    # Step 2: Sentiment analysis
    logger.info("Step 2/5: Running sentiment analysis on %d articles...", len(articles))
    articles = analyze_sentiment(articles)

    # Step 3: Generate signals
    logger.info("Step 3/5: Generating trading signals...")
    signals = generate_signals(articles)

    # Print summary
    buy_count = sum(1 for s in signals.values() if s["signal"] == "BUY")
    sell_count = sum(1 for s in signals.values() if s["signal"] == "SELL")
    hold_count = sum(1 for s in signals.values() if s["signal"] == "HOLD")
    logger.info("Signals summary: %d BUY, %d SELL, %d HOLD", buy_count, sell_count, hold_count)

    # Step 4: Send email
    logger.info("Step 4/5: Sending email digest...")
    success = send_digest(signals)
    if success:
        logger.info("Email sent successfully!")
    else:
        logger.error("Failed to send email digest")

    # Step 5: Publish to GitHub Pages
    logger.info("Step 5/5: Publishing dashboard to GitHub Pages...")
    try:
        publish_to_github_pages(signals)
    except Exception:
        logger.exception("Failed to publish to GitHub Pages")

    elapsed = time.time() - start
    logger.info("Pipeline completed in %.1f seconds", elapsed)
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Stock/Commodity Signal Bot")
    parser.add_argument("--now", action="store_true", help="Run pipeline immediately (for testing)")
    parser.add_argument("--web", action="store_true", help="Start web dashboard at http://localhost:5000")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("main")

    if args.web:
        logger.info("Starting web dashboard mode")
        from dashboard import run_dashboard
        run_dashboard()
        return

    if args.now:
        logger.info("Running pipeline immediately (--now flag)")
        run_pipeline()
        return

    # Schedule daily run
    logger.info("Scheduling daily run at %s", config.DAILY_RUN_TIME)
    schedule.every().day.at(config.DAILY_RUN_TIME).do(run_pipeline)

    logger.info("Bot started. Waiting for scheduled run time...")
    logger.info("Press Ctrl+C to stop")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")


if __name__ == "__main__":
    main()
