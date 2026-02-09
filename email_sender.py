import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Template

import config

logger = logging.getLogger(__name__)

EMAIL_TEMPLATE = Template("""\
<!DOCTYPE html>
<html>
<head>
<style>
  body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
  .container { max-width: 700px; margin: 0 auto; background: #fff; border-radius: 8px;
               box-shadow: 0 2px 8px rgba(0,0,0,0.1); overflow: hidden; }
  .header { background: #1a1a2e; color: #fff; padding: 24px; text-align: center; }
  .header h1 { margin: 0; font-size: 22px; }
  .header p { margin: 8px 0 0; color: #aaa; font-size: 14px; }
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
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Daily Trading Signal Digest</h1>
    <p>{{ date }}</p>
  </div>

  {% for section_name, tickers in sections %}
  <div class="section">
    <h2>{{ section_name }}</h2>
    <table>
      <tr>
        <th>Asset</th>
        <th>Signal</th>
        <th>Confidence</th>
        <th>Articles</th>
        <th>Top Headline</th>
      </tr>
      {% for ticker in tickers %}
      {% set s = signals[ticker] %}
      <tr>
        <td><strong>{{ s.display_name }}</strong></td>
        <td class="{{ s.signal | lower }}">{{ s.signal }}</td>
        <td>{{ s.confidence }}%</td>
        <td>{{ s.article_count }}</td>
        <td class="headline" title="{{ s.top_headline }}">{{ s.top_headline }}</td>
      </tr>
      {% endfor %}
    </table>
  </div>
  {% endfor %}

  <div class="footer">
    <p><strong>Disclaimer:</strong> This is not financial advice. Signals are generated
    by automated sentiment analysis and should not be the sole basis for investment decisions.
    Always do your own research.</p>
  </div>
</div>
</body>
</html>
""")


def send_digest(signals: dict[str, dict]) -> bool:
    """Build and send the daily digest email."""
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        logger.error("Gmail credentials not configured in .env")
        return False

    sections = [
        ("Stocks", config.STOCKS),
        ("Commodities", list(config.COMMODITIES.values())),
        ("Crypto", list(config.CRYPTO.values())),
    ]

    html = EMAIL_TEMPLATE.render(
        date=datetime.now(timezone.utc).strftime("%B %d, %Y"),
        sections=sections,
        signals=signals,
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Trading Signals - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    msg["From"] = config.GMAIL_ADDRESS
    msg["To"] = config.RECIPIENT_EMAIL
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
            server.send_message(msg)
        logger.info("Digest email sent to %s", config.RECIPIENT_EMAIL)
        return True
    except Exception:
        logger.exception("Failed to send email")
        return False
