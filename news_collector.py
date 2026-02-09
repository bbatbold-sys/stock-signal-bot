import logging
from datetime import datetime, timedelta, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def collect_yahoo_rss(ticker: str) -> list[dict]:
    """Fetch headlines from Yahoo Finance RSS for a given ticker."""
    articles = []
    url = config.YAHOO_RSS_URL.format(ticker=ticker)
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
            articles.append({
                "title": entry.get("title", ""),
                "summary": entry.get("summary", ""),
                "source": "Yahoo Finance",
                "ticker": ticker,
                "published": published,
                "link": entry.get("link", ""),
            })
        logger.info("Yahoo RSS for %s: %d articles", ticker, len(articles))
    except Exception:
        logger.exception("Error fetching Yahoo RSS for %s", ticker)
    return articles


def collect_bloomberg() -> list[dict]:
    """Scrape public headlines from Bloomberg markets page."""
    articles = []
    try:
        resp = requests.get(config.BLOOMBERG_MARKETS_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Bloomberg uses various headline tags; grab article titles
        for tag in soup.find_all(["h1", "h2", "h3", "a"], limit=50):
            text = tag.get_text(strip=True)
            if len(text) < 15 or len(text) > 300:
                continue
            # Try to match to a watched asset
            matched_ticker = _match_ticker(text)
            if matched_ticker:
                articles.append({
                    "title": text,
                    "summary": "",
                    "source": "Bloomberg",
                    "ticker": matched_ticker,
                    "published": datetime.now(timezone.utc).isoformat(),
                    "link": "",
                })
        logger.info("Bloomberg: %d matched articles", len(articles))
    except Exception:
        logger.exception("Error scraping Bloomberg")
    return articles


def collect_newsapi() -> list[dict]:
    """Fetch articles from NewsAPI for all watched assets."""
    if not config.NEWSAPI_KEY:
        logger.warning("NewsAPI key not configured, skipping")
        return []

    articles = []
    from_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        from newsapi import NewsApiClient
        api = NewsApiClient(api_key=config.NEWSAPI_KEY)
    except Exception:
        logger.exception("Failed to initialize NewsAPI client")
        return []

    for ticker, keywords in config.SEARCH_KEYWORDS.items():
        try:
            result = api.get_everything(
                q=keywords,
                domains=config.NEWSAPI_DOMAINS,
                from_param=from_date,
                language="en",
                sort_by="relevancy",
                page_size=10,
            )
            for art in result.get("articles", []):
                articles.append({
                    "title": art.get("title", ""),
                    "summary": art.get("description", "") or "",
                    "source": f"NewsAPI ({art.get('source', {}).get('name', 'Unknown')})",
                    "ticker": ticker,
                    "published": art.get("publishedAt", ""),
                    "link": art.get("url", ""),
                })
            logger.info("NewsAPI for %s: %d articles", ticker, len(result.get("articles", [])))
        except Exception:
            logger.exception("Error querying NewsAPI for %s", keywords)
    return articles


def _match_ticker(text: str) -> str | None:
    """Check if a headline mentions any watched asset."""
    text_upper = text.upper()
    # Check stock tickers
    for ticker in config.STOCKS:
        if ticker in text_upper:
            return ticker
    # Check commodity/crypto keywords
    keyword_map = {
        "GOLD": "GC=F", "CRUDE": "CL=F", "OIL": "CL=F", "SILVER": "SI=F",
        "BITCOIN": "BTC-USD", "BTC": "BTC-USD",
        "ETHEREUM": "ETH-USD", "ETH": "ETH-USD",
    }
    for keyword, ticker in keyword_map.items():
        if keyword in text_upper:
            return ticker
    return None


def _deduplicate(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles based on title similarity."""
    seen_titles = set()
    unique = []
    for art in articles:
        # Normalize title for comparison
        normalized = art["title"].strip().lower()
        if normalized and normalized not in seen_titles:
            seen_titles.add(normalized)
            unique.append(art)
    return unique


def collect_all_news() -> list[dict]:
    """Collect news from all sources, deduplicate, and return."""
    all_articles = []

    # Yahoo Finance RSS per ticker
    for ticker in config.ALL_TICKERS:
        all_articles.extend(collect_yahoo_rss(ticker))

    # Bloomberg public headlines
    all_articles.extend(collect_bloomberg())

    # NewsAPI
    all_articles.extend(collect_newsapi())

    # Filter out articles with empty titles
    all_articles = [a for a in all_articles if a["title"].strip()]

    deduplicated = _deduplicate(all_articles)
    logger.info("Total articles collected: %d (after dedup: %d)", len(all_articles), len(deduplicated))
    return deduplicated
