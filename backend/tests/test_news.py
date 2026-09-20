from app.services.news import RawNews, analyze_with_rules, parse_rss


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
