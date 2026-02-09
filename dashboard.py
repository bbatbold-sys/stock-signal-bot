import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import schedule
from flask import Flask, render_template, redirect, url_for

import config
from news_collector import collect_all_news
from sentiment_analyzer import analyze_sentiment
from signal_generator import generate_signals
from email_sender import send_digest
from backtester import auto_tune

logger = logging.getLogger(__name__)

SIGNALS_FILE = Path(__file__).parent / "signals.json"

app = Flask(__name__)


def run_pipeline_and_save():
    """Run the full pipeline and save signals to JSON."""
    logger.info("Dashboard pipeline: starting...")
    start = time.time()

    try:
        auto_tune()
    except Exception:
        logger.exception("Auto-tune failed, continuing with current thresholds")

    articles = collect_all_news()
    if not articles:
        logger.warning("No articles collected. Skipping pipeline.")
        return

    articles = analyze_sentiment(articles)
    signals = generate_signals(articles)

    # Send email digest too
    try:
        send_digest(signals)
    except Exception:
        logger.exception("Email sending failed")

    # Save signals to JSON for the dashboard
    data = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "signals": signals,
    }
    SIGNALS_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    elapsed = time.time() - start
    logger.info("Dashboard pipeline completed in %.1f seconds", elapsed)


def _scheduler_loop():
    """Background thread: run pipeline on schedule."""
    schedule.every().day.at(config.DAILY_RUN_TIME).do(run_pipeline_and_save)
    while True:
        schedule.run_pending()
        time.sleep(60)


def start_background_scheduler():
    """Start the scheduler in a daemon thread and run pipeline once immediately."""
    # Run once on startup so there's data right away
    threading.Thread(target=run_pipeline_and_save, daemon=True).start()
    # Start recurring scheduler
    threading.Thread(target=_scheduler_loop, daemon=True).start()


@app.route("/")
def index():
    """Serve the dashboard page."""
    signals = {}
    last_updated = "Never (pipeline running...)"

    if SIGNALS_FILE.exists():
        try:
            data = json.loads(SIGNALS_FILE.read_text(encoding="utf-8"))
            signals = data.get("signals", {})
            raw_ts = data.get("last_updated", "")
            if raw_ts:
                dt = datetime.fromisoformat(raw_ts)
                last_updated = dt.strftime("%B %d, %Y at %H:%M UTC")
        except Exception:
            logger.exception("Failed to read signals.json")

    sections = [
        ("Stocks", config.STOCKS),
        ("Commodities", list(config.COMMODITIES.values())),
        ("Crypto", list(config.CRYPTO.values())),
    ]

    return render_template(
        "dashboard.html",
        last_updated=last_updated,
        sections=sections,
        signals=signals,
    )


@app.route("/refresh", methods=["POST"])
def refresh():
    """Trigger a manual pipeline run in a background thread."""
    threading.Thread(target=run_pipeline_and_save, daemon=True).start()
    return redirect(url_for("index"))


def run_dashboard():
    """Entry point: start scheduler + Flask server."""
    start_background_scheduler()
    logger.info("Starting dashboard at http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
