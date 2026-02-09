import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Template

import config

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).parent
SIGNALS_FILE = PROJECT_DIR / "signals.json"
OUTPUT_FILE = PROJECT_DIR / "docs" / "index.html"

PAGE_TEMPLATE = Template("""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Trading Signal Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { box-sizing: border-box; }
  body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
  .container { max-width: 700px; margin: 0 auto; background: #fff; border-radius: 8px;
               box-shadow: 0 2px 8px rgba(0,0,0,0.1); overflow: hidden; }
  .header { background: #1a1a2e; color: #fff; padding: 24px; text-align: center; }
  .header h1 { margin: 0; font-size: 22px; }
  .header p { margin: 8px 0 0; color: #aaa; font-size: 14px; }
  .updated-bar { padding: 12px 24px; background: #f0f0f0; text-align: center;
                 color: #666; font-size: 13px; }
  .section { padding: 16px 24px; }
  .section h2 { color: #1a1a2e; border-bottom: 2px solid #eee; padding-bottom: 8px;
                font-size: 18px; margin-top: 0; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
  th { text-align: left; padding: 8px; background: #f8f8f8; color: #555;
       font-size: 12px; text-transform: uppercase; }
  td { padding: 10px 8px; border-bottom: 1px solid #eee; font-size: 14px; }
  .buy { color: #00c853; font-weight: bold; }
  .sell { color: #ff1744; font-weight: bold; }
  .hold { color: #ff9800; font-weight: bold; }
  .headline { color: #666; font-size: 12px; max-width: 200px;
              overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .footer { background: #f8f8f8; padding: 16px 24px; text-align: center;
            color: #999; font-size: 11px; }
  @media (max-width: 600px) {
    body { padding: 8px; }
    .section { padding: 12px 12px; }
    td, th { padding: 6px 4px; font-size: 12px; }
    .headline { max-width: 100px; }
  }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Trading Signal Dashboard</h1>
    <p>Automated signals powered by FinBERT sentiment analysis</p>
  </div>

  <div class="updated-bar">
    Last updated: {{ last_updated }}
  </div>

  {% for section_name, tickers in sections %}
  <div class="section">
    <h2>{{ section_name }}</h2>
    <table>
      <tr>
        <th>Asset</th>
        <th>Signal</th>
        <th>Score</th>
        <th>Confidence</th>
        <th>Articles</th>
        <th>Top Headline</th>
      </tr>
      {% for ticker in tickers %}
      {% if ticker in signals %}
      {% set s = signals[ticker] %}
      <tr>
        <td><strong>{{ s.display_name }}</strong></td>
        <td class="{{ s.signal | lower }}">{{ s.signal }}</td>
        <td>{{ "%.2f" | format(s.score | float) }}</td>
        <td>{{ s.confidence }}%</td>
        <td>{{ s.article_count }}</td>
        <td class="headline" title="{{ s.top_headline }}">{{ s.top_headline }}</td>
      </tr>
      {% endif %}
      {% endfor %}
    </table>
  </div>
  {% endfor %}

  <div class="footer">
    <p><strong>Disclaimer:</strong> This is not financial advice. Signals are generated
    by automated sentiment analysis and should not be the sole basis for investment decisions.
    Always do your own research.</p>
    <p>Last updated: {{ last_updated }}</p>
  </div>
</div>
</body>
</html>
""")


def publish_to_github_pages(signals: dict):
    """Generate static HTML and push to GitHub for GitHub Pages."""
    now = datetime.now(timezone.utc)
    last_updated = now.strftime("%B %d, %Y at %H:%M UTC")

    sections = [
        ("Stocks", config.STOCKS),
        ("Commodities", list(config.COMMODITIES.values())),
        ("Crypto", list(config.CRYPTO.values())),
    ]

    html = PAGE_TEMPLATE.render(
        last_updated=last_updated,
        sections=sections,
        signals=signals,
    )

    # Save static HTML
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    logger.info("Static dashboard written to %s", OUTPUT_FILE)

    # Also save signals.json for reference
    data = {"last_updated": now.isoformat(), "signals": signals}
    SIGNALS_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    # Git commit and push (skip when running in GitHub Actions - workflow handles it)
    if os.getenv("GITHUB_ACTIONS"):
        logger.info("Running in GitHub Actions, skipping git push (workflow handles it)")
        return

    try:
        subprocess.run(["git", "add", "docs/index.html", "signals.json"],
                       cwd=PROJECT_DIR, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"Update signals - {now.strftime('%Y-%m-%d %H:%M UTC')}"],
            cwd=PROJECT_DIR, check=True, capture_output=True,
        )
        subprocess.run(["git", "push"], cwd=PROJECT_DIR, check=True, capture_output=True)
        logger.info("Pushed updated dashboard to GitHub Pages")
    except subprocess.CalledProcessError as e:
        logger.error("Git push failed: %s", e.stderr.decode() if e.stderr else str(e))
