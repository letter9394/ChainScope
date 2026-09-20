import pytest

import app.services.news as news_service
from app.config import Settings
from app.services.news import RawNews, analyze_with_rules, parse_rss, translate_news


def article(title: str, description: str = "") -> RawNews:
    return RawNews(
        title=title,
        url="https://example.com/story",
        description=description,
        published_at="2026-09-20T00:00:00+00:00",
        image_url=None,
    )


def test_positive_news_rule() -> None:
    result = analyze_with_rules(article("Bitcoin gains as adoption rises"))
    assert result.sentiment == "positive"
    assert "BTC" in result.related_symbols


def test_negative_news_rule() -> None:
    result = analyze_with_rules(article("Ethereum falls after major hack warning"))
    assert result.sentiment == "negative"
    assert "ETH" in result.related_symbols


def test_neutral_news_rule() -> None:
    result = analyze_with_rules(article("Solana developers meet for annual conference"))
    assert result.sentiment == "neutral"
    assert "SOL" in result.related_symbols


def test_gold_news_rule() -> None:
    result = analyze_with_rules(article("Gold bullion holds steady as XAU demand rises"))
    assert "XAU" in result.related_symbols


def test_summary_is_bounded() -> None:
    result = analyze_with_rules(article("Bitcoin update", "x" * 300))
    assert len(result.summary) <= 180


def test_rss_parser_extracts_items() -> None:
    xml = """<?xml version="1.0"?><rss><channel><item>
    <title>Bitcoin market update</title><link>https://example.com/a</link>
    <description><![CDATA[<p>Market details.</p>]]></description>
    <pubDate>Sun, 20 Sep 2026 00:00:00 +0000</pubDate>
    </item></channel></rss>"""
    result = parse_rss(xml)
    assert len(result) == 1
    assert result[0].description == "Market details."


@pytest.mark.anyio
async def test_news_translation_returns_bilingual_content(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_translate(text: str, settings: Settings) -> str:
        return f"译文：{text}"

    monkeypatch.setattr(news_service, "_translate_text", fake_translate)
    result = await translate_news("Gold rises", "Markets move higher", Settings())

    assert result.title_zh == "译文：Gold rises"
    assert result.summary_zh == "译文：Markets move higher"
    assert result.provider == "MyMemory"
