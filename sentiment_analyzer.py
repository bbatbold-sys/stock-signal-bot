import logging

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

logger = logging.getLogger(__name__)

MODEL_NAME = "ProsusAI/finbert"

_tokenizer = None
_model = None


def _load_model():
    """Lazy-load FinBERT model and tokenizer."""
    global _tokenizer, _model
    if _tokenizer is None:
        logger.info("Loading FinBERT model (first run may download ~500MB)...")
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
        _model.eval()
        logger.info("FinBERT model loaded")


def analyze_sentiment(articles: list[dict], batch_size: int = 16) -> list[dict]:
    """Run FinBERT sentiment analysis on a list of articles.

    Adds 'sentiment' (positive/negative/neutral) and 'confidence' (0-1) to each article dict.
    """
    if not articles:
        return articles

    _load_model()

    label_map = {0: "positive", 1: "negative", 2: "neutral"}

    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        texts = []
        for art in batch:
            text = art["title"]
            if art.get("summary"):
                text += ". " + art["summary"]
            # Truncate to avoid token limit issues
            texts.append(text[:512])

        try:
            inputs = _tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            with torch.no_grad():
                outputs = _model(**inputs)
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
            predictions = torch.argmax(probs, dim=-1)

            for j, art in enumerate(batch):
                pred_idx = predictions[j].item()
                art["sentiment"] = label_map[pred_idx]
                art["confidence"] = probs[j][pred_idx].item()
        except Exception:
            logger.exception("Error in sentiment analysis batch %d", i)
            for art in batch:
                art["sentiment"] = "neutral"
                art["confidence"] = 0.0

    pos = sum(1 for a in articles if a["sentiment"] == "positive")
    neg = sum(1 for a in articles if a["sentiment"] == "negative")
    neu = sum(1 for a in articles if a["sentiment"] == "neutral")
    logger.info("Sentiment results: %d positive, %d negative, %d neutral", pos, neg, neu)
    return articles
