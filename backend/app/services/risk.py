import math
import statistics
from datetime import UTC, datetime

from app.models import DerivativesSnapshot, HistoryPoint, NewsArticle, RiskAssessment, RiskMetric


def _daily_returns(prices: list[float]) -> list[float]:
    return [
        (current / previous) - 1
        for previous, current in zip(prices, prices[1:])
        if previous > 0
    ]


def _annualized_volatility(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    return statistics.stdev(returns) * math.sqrt(365) * 100


def _maximum_drawdown(prices: list[float]) -> float:
    if not prices:
        return 0.0
    peak = prices[0]
    worst = 0.0
    for price in prices:
        peak = max(peak, price)
        if peak > 0:
            worst = min(worst, (price / peak) - 1)
    return abs(worst) * 100


def _volume_ratio(volumes: list[float]) -> float:
    clean = [value for value in volumes if value > 0]
    if len(clean) < 2:
        return 1.0
    baseline = statistics.mean(clean[:-1][-7:])
    return clean[-1] / baseline if baseline > 0 else 1.0


def _score_volatility(value: float) -> int:
    if value < 40:
        return 8
    if value < 70:
        return 18
    if value < 100:
        return 30
    return 40


def _score_drawdown(value: float) -> int:
    if value < 8:
        return 4
    if value < 15:
        return 12
    if value < 25:
        return 23
    return 35


def _score_volume(value: float) -> int:
    if value < 1.5:
        return 0
    if value < 2.5:
        return 7
    return 15


def _score_momentum(value: float) -> int:
    absolute = abs(value)
    if absolute < 4:
        return 0
    if absolute < 8:
        return 5
    return 10


def _score_funding(value: float | None) -> int:
    absolute = abs(value or 0)
    if absolute < 0.01:
        return 0
    if absolute < 0.03:
        return 3
    if absolute < 0.06:
        return 6
    return 8


def _score_open_interest(value: float | None) -> int:
    absolute = abs(value or 0)
    if absolute < 1:
        return 0
    if absolute < 3:
        return 3
    if absolute < 7:
        return 6
    return 8


def _score_crowding(long_percent: float | None, short_percent: float | None) -> int:
    if long_percent is None or short_percent is None:
        return 0
    crowded_side = max(long_percent, short_percent)
    if crowded_side < 55:
        return 0
    if crowded_side < 60:
        return 2
    if crowded_side < 70:
        return 5
    return 7


def _score_fear_greed(value: int | None) -> int:
    distance = abs((value if value is not None else 50) - 50)
    if distance < 10:
        return 0
    if distance < 20:
        return 1
    if distance < 30:
        return 3
    return 4


def _score_news(articles: list[NewsArticle] | None) -> tuple[int, float]:
    if not articles:
        return 0, 0.0
    negative_ratio = sum(item.sentiment == "negative" for item in articles) / len(articles)
    if negative_ratio < 0.2:
        score = 0
    elif negative_ratio < 0.4:
        score = 1
    elif negative_ratio < 0.7:
        score = 2
    else:
        score = 3
    return score, negative_ratio * 100


def assess_risk(
    coin_id: str,
    symbol: str,
    history: list[HistoryPoint],
    derivatives: DerivativesSnapshot | None = None,
    news_articles: list[NewsArticle] | None = None,
) -> RiskAssessment:
    if len(history) < 2:
        raise ValueError("At least two history points are required")

    prices = [point.price for point in history if point.price > 0]
    if len(prices) < 2:
        raise ValueError("At least two positive prices are required")

    returns = _daily_returns(prices)
    volatility = _annualized_volatility(returns)
    drawdown = _maximum_drawdown(prices)
    momentum = ((prices[-1] / prices[-2]) - 1) * 100
    volume_ratio = _volume_ratio([
        point.volume for point in history if point.volume is not None
    ])

    volatility_score = _score_volatility(volatility)
    drawdown_score = _score_drawdown(drawdown)
    volume_score = _score_volume(volume_ratio)
    momentum_score = _score_momentum(momentum)
    enhanced = derivatives is not None and derivatives.available
    if enhanced:
        volatility_score = round(volatility_score * 0.7)
        drawdown_score = round(drawdown_score * 0.7)
        volume_score = round(volume_score * 0.7)
        momentum_score = round(momentum_score * 0.7)

    score = volatility_score + drawdown_score + volume_score + momentum_score

    metrics = [
        RiskMetric(
            key="volatility",
            label="年化波动率",
            value=round(volatility, 2),
            display_value=f"{volatility:.1f}%",
            contribution=volatility_score,
            explanation="价格日收益率的离散程度，越高表示短期价格越不稳定。",
        ),
        RiskMetric(
            key="drawdown",
            label="区间最大回撤",
            value=round(drawdown, 2),
            display_value=f"{drawdown:.1f}%",
            contribution=drawdown_score,
            explanation="观察期内从阶段高点到随后低点的最大跌幅。",
        ),
        RiskMetric(
            key="volume",
            label="成交量异常倍数",
            value=round(volume_ratio, 2),
            display_value=f"{volume_ratio:.2f}x",
            contribution=volume_score,
            explanation="最新成交量相对前7个样本平均值的倍数。",
        ),
        RiskMetric(
            key="momentum",
            label="最近一期涨跌",
            value=round(momentum, 2),
            display_value=f"{momentum:+.1f}%",
            contribution=momentum_score,
            explanation="最近两个数据点之间的价格变化，剧烈上涨或下跌都会增加风险。",
        ),
    ]

    if enhanced and derivatives is not None:
        funding_score = _score_funding(derivatives.funding_rate_percent)
        interest_score = _score_open_interest(derivatives.open_interest_change_5m_percent)
        crowding_score = _score_crowding(
            derivatives.long_account_percent,
            derivatives.short_account_percent,
        )
        sentiment_score = _score_fear_greed(derivatives.fear_greed_value)
        news_score, negative_news_percent = _score_news(news_articles)
        score += funding_score + interest_score + crowding_score + sentiment_score + news_score
        metrics.extend([
            RiskMetric(
                key="funding_rate",
                label="永续合约资金费率",
                value=derivatives.funding_rate_percent or 0,
                display_value=(
                    f"{derivatives.funding_rate_percent:+.4f}%"
                    if derivatives.funding_rate_percent is not None else "暂不可用"
                ),
                contribution=funding_score,
                explanation="每8小时多空双方支付的费用；绝对值过高代表杠杆方向过度拥挤。",
            ),
            RiskMetric(
                key="open_interest",
                label="5分钟持仓量变化",
                value=derivatives.open_interest_change_5m_percent or 0,
                display_value=(
                    f"{derivatives.open_interest_change_5m_percent:+.2f}%"
                    if derivatives.open_interest_change_5m_percent is not None else "暂不可用"
                ),
                contribution=interest_score,
                explanation="未平仓合约价值快速增加通常表示杠杆正在堆积。",
            ),
            RiskMetric(
                key="position_crowding",
                label="多空账户拥挤度",
                value=max(
                    derivatives.long_account_percent or 0,
                    derivatives.short_account_percent or 0,
                ),
                display_value=(
                    f"多 {derivatives.long_account_percent:.1f}% / 空 {derivatives.short_account_percent:.1f}%"
                    if derivatives.long_account_percent is not None and derivatives.short_account_percent is not None
                    else "暂不可用"
                ),
                contribution=crowding_score,
                explanation="任一方向账户比例过高时，反向波动可能引发连锁平仓。",
            ),
            RiskMetric(
                key="fear_greed",
                label="市场恐慌与贪婪",
                value=float(derivatives.fear_greed_value or 50),
                display_value=(
                    f"{derivatives.fear_greed_value} · {derivatives.fear_greed_label}"
                    if derivatives.fear_greed_value is not None else "暂不可用"
                ),
                contribution=sentiment_score,
                explanation="情绪越接近极端恐慌或极端贪婪，反转和踩踏风险越高。",
            ),
            RiskMetric(
                key="news_sentiment",
                label="负面新闻占比",
                value=round(negative_news_percent, 2),
                display_value=f"{negative_news_percent:.0f}%" if news_articles else "暂不可用",
                contribution=news_score,
                explanation="当前资产最近新闻中被规则判定为负面的比例。",
            ),
        ])

    score = min(100, score)

    if score < 30:
        level, level_label = "low", "较低"
    elif score < 60:
        level, level_label = "medium", "中等"
    else:
        level, level_label = "high", "较高"

    top_drivers = sorted(metrics, key=lambda item: item.contribution, reverse=True)[:2]
    driver_text = "、".join(item.label for item in top_drivers if item.contribution > 0)
    summary = (
        f"{symbol} 当前风险等级为{level_label}，主要关注{driver_text}。"
        if driver_text
        else f"{symbol} 当前风险等级为{level_label}，暂未出现明显异常。"
    )

    return RiskAssessment(
        coin_id=coin_id,
        symbol=symbol,
        score=score,
        level=level,
        level_label=level_label,
        summary=summary,
        metrics=metrics,
        sample_days=len(prices),
        calculated_at=datetime.now(UTC).isoformat(),
        market_context=derivatives,
    )
