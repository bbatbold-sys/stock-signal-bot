import os
from dotenv import load_dotenv

load_dotenv()

# --- Asset Watchlist ---
STOCKS = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "JNJ"]
COMMODITIES = {"Gold": "GC=F", "Oil": "CL=F", "Silver": "SI=F"}
CRYPTO = {"BTC": "BTC-USD", "ETH": "ETH-USD"}

# Friendly names for display
ASSET_DISPLAY_NAMES = {
    **{s: s for s in STOCKS},
    **{v: k for k, v in COMMODITIES.items()},
    **{v: k for k, v in CRYPTO.items()},
}

# All tickers for news collection
ALL_TICKERS = STOCKS + list(COMMODITIES.values()) + list(CRYPTO.values())

# Keyword search terms for NewsAPI (map ticker -> search keywords)
SEARCH_KEYWORDS = {
    **{s: s for s in STOCKS},
    "GC=F": "gold commodity",
    "CL=F": "crude oil",
    "SI=F": "silver commodity",
    "BTC-USD": "bitcoin BTC",
    "ETH-USD": "ethereum ETH",
}

# --- News Sources ---
YAHOO_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
BLOOMBERG_MARKETS_URL = "https://www.bloomberg.com/markets"

# --- NewsAPI ---
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
NEWSAPI_DOMAINS = "reuters.com,cnbc.com,bloomberg.com,wsj.com,marketwatch.com,finance.yahoo.com"

# --- Email ---
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "") or GMAIL_ADDRESS
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# --- Signal Thresholds ---
# Tuned via backtester.py (2026-02-09): 83.3% accuracy vs 75% with old defaults
BUY_THRESHOLD = 0.2
SELL_THRESHOLD = -0.05
MIN_ARTICLES = 1

# --- Scheduler ---
DAILY_RUN_TIME = "07:00"  # 24h format

# --- Logging ---
LOG_FILE = "stock_signal_bot.log"
