import math
import statistics
from datetime import UTC, datetime

from app.models import HistoryPoint, RiskAssessment, RiskMetric


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


def assess_risk(
    coin_id: str,
    symbol: str,
    history: list[HistoryPoint],
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
    score = min(100, volatility_score + drawdown_score + volume_score + momentum_score)

    if score < 30:
        level, level_label = "low", "较低"
    elif score < 60:
        level, level_label = "medium", "中等"
    else:
        level, level_label = "high", "较高"

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
    )

