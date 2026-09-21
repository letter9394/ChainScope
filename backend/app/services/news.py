import asyncio
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from app.config import Settings
from app.models import NewsArticle, NewsResponse, NewsTranslationResponse
from app.services.cache import cache
from app.services.market import SUPPORTED_ASSETS


COIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bitcoin": ("bitcoin", "btc"),
    "ethereum": ("ethereum", "ether", "eth"),
    "solana": ("solana", "sol"),
    "gold": ("gold", "xau", "bullion"),
}

POSITIVE_TERMS = {
    "gain", "gains", "growth", "rally", "surge", "record", "approval",
    "adoption", "recovery", "bullish", "breakout", "rise", "rises", "upgrade",
}
NEGATIVE_TERMS = {
    "loss", "losses", "drop", "falls", "fall", "crash", "hack", "fraud",
    "lawsuit", "ban", "bearish", "selloff", "risk", "warning", "decline",
}


@dataclass
class RawNews:
    title: str
    url: str
    description: str
    published_at: str
    image_url: str | None


def _plain_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _iso_date(value: str | None) -> str:
    if not value:
        return datetime.now(UTC).isoformat()
    try:
        return parsedate_to_datetime(value).astimezone(UTC).isoformat()
    except (TypeError, ValueError):
        return datetime.now(UTC).isoformat()


def parse_rss(xml_text: str) -> list[RawNews]:
    root = ET.fromstring(xml_text)
    articles: list[RawNews] = []
    for item in root.findall("./channel/item"):
        title = _plain_text(item.findtext("title"))
        url = _plain_text(item.findtext("link"))
        if not title or not url:
            continue
        image_url = None
        for child in item:
            if child.tag.endswith("thumbnail") or child.tag.endswith("content"):
                candidate = child.attrib.get("url")
                if candidate:
                    image_url = candidate
                    break
        articles.append(
            RawNews(
                title=title,
                url=url,
                description=_plain_text(item.findtext("description")),
                published_at=_iso_date(item.findtext("pubDate")),
                image_url=image_url,
            )
        )
    return articles


def analyze_with_rules(article: RawNews) -> NewsArticle:
    combined = f"{article.title} {article.description}".lower()
    words = set(re.findall(r"[a-z]+", combined))
    positive_hits = len(words & POSITIVE_TERMS)
    negative_hits = len(words & NEGATIVE_TERMS)

    if positive_hits > negative_hits:
        sentiment, label = "positive", "偏积极"
    elif negative_hits > positive_hits:
        sentiment, label = "negative", "偏消极"
    else:
        sentiment, label = "neutral", "中性"

    related_symbols = [
        SUPPORTED_ASSETS[coin_id]
        for coin_id, keywords in COIN_KEYWORDS.items()
        if any(re.search(rf"\b{re.escape(keyword)}\b", combined) for keyword in keywords)
    ]
    summary = article.description or article.title
    if len(summary) > 180:
        summary = f"{summary[:177].rstrip()}..."

    return NewsArticle(
        id=hashlib.sha256(article.url.encode("utf-8")).hexdigest()[:16],
        title=article.title,
        url=article.url,
        source="CoinDesk",
        published_at=article.published_at,
        image_url=article.image_url,
        summary=summary,
        sentiment=sentiment,
        sentiment_label=label,
        related_symbols=related_symbols,
        analysis_mode="rules",
    )


async def _analyze_with_ai(
    articles: list[NewsArticle],
    settings: Settings,
) -> list[NewsArticle] | None:
    if not (settings.ai_api_base_url and settings.ai_api_key and settings.ai_model):
        return None

    payload_articles = [
        {"id": item.id, "title": item.title, "source_summary": item.summary}
        for item in articles
    ]
    prompt = (
        "Analyze the following cryptocurrency news. Return only a JSON array. "
        "Each item must contain id, summary_zh (max 80 Chinese characters), and sentiment "
        "with one of positive, neutral, negative. Do not add facts not present in the source.\n"
        + json.dumps(payload_articles, ensure_ascii=False)
    )
    url = f"{settings.ai_api_base_url.rstrip('/')}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.ai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.ai_model,
                    "temperature": 0.1,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
            analyzed = json.loads(content)
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    by_id = {item.id: item for item in articles}
    labels = {"positive": "偏积极", "neutral": "中性", "negative": "偏消极"}
    for result in analyzed:
        item = by_id.get(str(result.get("id", "")))
        sentiment = result.get("sentiment")
        summary = str(result.get("summary_zh", "")).strip()
        if item and sentiment in labels and summary:
            item.summary = summary[:80]
            item.sentiment = sentiment
            item.sentiment_label = labels[sentiment]
            item.analysis_mode = "ai"
    return list(by_id.values())


async def get_news(
    settings: Settings,
    coin_id: str | None = None,
    limit: int = 6,
) -> NewsResponse:
    if coin_id is not None and coin_id not in COIN_KEYWORDS:
        raise ValueError(f"Unsupported coin: {coin_id}")

    cache_key = f"news:{coin_id or 'all'}:{limit}:{bool(settings.ai_api_key)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
            response = await client.get(
                settings.news_rss_url,
                headers={"Accept": "application/rss+xml, application/xml", "User-Agent": "ChainScope/0.1"},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError("News source is temporarily unavailable") from exc

    raw_articles = parse_rss(response.text)
    if coin_id:
        keywords = COIN_KEYWORDS[coin_id]
        filtered = [
            item for item in raw_articles
            if any(re.search(rf"\b{re.escape(keyword)}\b", f"{item.title} {item.description}".lower()) for keyword in keywords)
        ]
        raw_articles = filtered or raw_articles

    rule_articles = [analyze_with_rules(item) for item in raw_articles[:limit]]
    ai_articles = await _analyze_with_ai(rule_articles, settings)
    final_articles = ai_articles or rule_articles
    mode = "ai" if any(item.analysis_mode == "ai" for item in final_articles) else "rules"
    result = NewsResponse(
        articles=final_articles,
        analysis_mode=mode,
        notice=(
            "AI摘要已启用，分析结果保留原始新闻链接供核对。"
            if mode == "ai"
            else "当前使用关键词规则分析；配置AI服务后将自动生成中文摘要。"
        ),
    )
    cache.set(cache_key, result, settings.news_cache_seconds)
    return result


async def _translate_text(text: str, settings: Settings) -> str:
    cache_key = f"translation:en-zh:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    last_error: Exception | None = None
    async with httpx.AsyncClient(
        timeout=settings.request_timeout_seconds,
        headers={"Accept": "application/json", "User-Agent": "ChainScope/0.1"},
    ) as client:
        for attempt in range(3):
            try:
                response = await client.get(
                    settings.translation_api_url,
                    params={"q": text, "langpair": "en|zh-CN", "mt": "1"},
                )
                response.raise_for_status()
                payload = response.json()
                if int(payload.get("responseStatus", 200)) != 200:
                    raise ValueError(str(payload.get("responseDetails") or "Translation rejected"))
                translated = html.unescape(str(payload["responseData"]["translatedText"])).strip()
                if not translated or translated.upper().startswith("MYMEMORY WARNING"):
                    raise ValueError("Empty or throttled translation")
                break
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.4 * (attempt + 1))
        else:
            raise RuntimeError("Translation service is temporarily unavailable") from last_error

    cache.set(cache_key, translated, settings.translation_cache_seconds)
    return translated


async def translate_news(
    title: str,
    summary: str,
    settings: Settings,
) -> NewsTranslationResponse:
    # MyMemory's anonymous endpoint may throttle simultaneous requests from the
    # same Render instance. Translate sequentially so one click remains reliable.
    title_zh = await _translate_text(title, settings)
    summary_zh = await _translate_text(summary, settings)
    return NewsTranslationResponse(
        title_zh=title_zh,
        summary_zh=summary_zh,
        provider="MyMemory",
    )
