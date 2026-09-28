import math
import statistics
from datetime import UTC, datetime

from app.models import (
    DerivativesSnapshot, HistoryPoint, NewsArticle, RiskAssessment,
    RiskFeatureImportance, RiskFeatureModelFold, RiskFeatureModelResult,
    RiskBacktestHorizon, RiskBacktestQuality, RiskBacktestRegime,
    RiskBacktestResult, RiskBacktestSensitivity, RiskBacktestSignal,
    RiskBacktestValidation, RiskBacktestWalkForward,
    RiskBacktestWalkForwardFold, RiskMetric,
)


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


def _backtest_score_series(
    coin_id: str,
    symbol: str,
    history: list[HistoryPoint],
    window_days: int,
    last_signal_index: int,
) -> list[tuple[int, int]]:
    return [
        (
            index,
            assess_risk(
                coin_id,
                symbol,
                history[index - window_days + 1:index + 1],
            ).score,
        )
        for index in range(window_days - 1, last_signal_index + 1)
    ]


def _threshold_crossings(
    scores: list[tuple[int, int]],
    threshold: int,
) -> list[tuple[int, int]]:
    crossings: list[tuple[int, int]] = []
    previous_score: int | None = None
    for index, score in scores:
        if previous_score is not None and previous_score < threshold <= score:
            crossings.append((index, score))
        previous_score = score
    return crossings


def _future_max_drawdown(
    history: list[HistoryPoint],
    index: int,
    horizon_days: int,
) -> float:
    signal_price = history[index].price
    minimum_future_price = min(
        point.price
        for point in history[index + 1:index + horizon_days + 1]
    )
    return round(max(0.0, (signal_price - minimum_future_price) / signal_price * 100), 2)


def _hit_rate(values: list[float], hit_threshold_percent: float) -> float:
    if not values:
        return 0.0
    hits = sum(value >= hit_threshold_percent for value in values)
    return round(hits / len(values) * 100, 1)


def _classification_quality(
    history: list[HistoryPoint],
    evaluated_scores: list[tuple[int, int | float]],
    signal_points: list[tuple[int, int | float]],
    *,
    horizon_days: int,
    hit_threshold_percent: float,
) -> RiskBacktestQuality:
    evaluated_indexes = {index for index, _ in evaluated_scores}
    event_indexes = {
        index
        for index in evaluated_indexes
        if _future_max_drawdown(history, index, horizon_days) >= hit_threshold_percent
    }
    signal_indexes = {
        index
        for index, _ in signal_points
        if index in evaluated_indexes
    }
    true_positive_count = len(signal_indexes & event_indexes)
    false_positive_count = len(signal_indexes - event_indexes)
    false_negative_count = len(event_indexes - signal_indexes)
    true_negative_count = len(evaluated_indexes - event_indexes - signal_indexes)
    evaluated_days = len(evaluated_indexes)
    signal_count = len(signal_indexes)
    event_days = len(event_indexes)
    baseline_rate = event_days / evaluated_days * 100 if evaluated_days else 0.0
    accuracy = (
        (true_positive_count + true_negative_count) / evaluated_days * 100
        if evaluated_days else 0.0
    )
    precision = true_positive_count / signal_count * 100 if signal_count else 0.0
    recall = true_positive_count / event_days * 100 if event_days else 0.0
    miss_rate = false_negative_count / event_days * 100 if event_days else 0.0
    lift = precision / baseline_rate if baseline_rate else 0.0
    return RiskBacktestQuality(
        horizon_days=horizon_days,
        evaluated_days=evaluated_days,
        event_days=event_days,
        signal_count=signal_count,
        true_positive_count=true_positive_count,
        false_positive_count=false_positive_count,
        false_negative_count=false_negative_count,
        true_negative_count=true_negative_count,
        baseline_hit_rate_percent=round(baseline_rate, 1),
        accuracy_percent=round(accuracy, 1),
        precision_percent=round(precision, 1),
        recall_percent=round(recall, 1),
        miss_rate_percent=round(miss_rate, 1),
        lift=round(lift, 2),
    )


def _walk_forward_validation(
    history: list[HistoryPoint],
    score_series: list[tuple[int, int]],
    *,
    risk_threshold: int,
    horizon_days: int,
    hit_threshold_percent: float,
    fold_count: int = 3,
) -> RiskBacktestWalkForward:
    candidate_thresholds = list(range(
        max(20, risk_threshold - 20),
        min(90, risk_threshold + 20) + 1,
        5,
    ))
    initial_training_points = len(score_series) // 2
    remaining_points = len(score_series) - initial_training_points
    fold_size = max(1, remaining_points // fold_count)
    folds: list[RiskBacktestWalkForwardFold] = []
    aggregate_scores: list[tuple[int, int]] = []
    aggregate_signals: list[tuple[int, int]] = []

    for fold_index in range(fold_count):
        holdout_start_position = initial_training_points + fold_index * fold_size
        holdout_end_position = (
            len(score_series)
            if fold_index == fold_count - 1
            else min(len(score_series), holdout_start_position + fold_size)
        )
        if holdout_start_position >= holdout_end_position:
            continue

        # Purge the forecast horizon from calibration. Labels for these final
        # training rows would otherwise reach into the next holdout period.
        calibration_end = max(1, holdout_start_position - horizon_days)
        training_scores = score_series[:calibration_end]
        minimum_training_signals = max(3, round(len(training_scores) / 300))
        candidates: list[tuple[tuple[float, float, int, int], int]] = []
        for threshold in candidate_thresholds:
            training_signals = _threshold_crossings(training_scores, threshold)
            quality = _classification_quality(
                history,
                training_scores,
                training_signals,
                horizon_days=horizon_days,
                hit_threshold_percent=hit_threshold_percent,
            )
            if quality.signal_count < minimum_training_signals:
                continue
            candidates.append((
                (
                    quality.lift,
                    quality.precision_percent,
                    quality.signal_count,
                    -abs(threshold - risk_threshold),
                ),
                threshold,
            ))
        selected_threshold = max(candidates)[1] if candidates else risk_threshold

        holdout_scores = score_series[holdout_start_position:holdout_end_position]
        crossing_scores = score_series[holdout_start_position - 1:holdout_end_position]
        first_holdout_index = holdout_scores[0][0]
        holdout_signals = [
            point
            for point in _threshold_crossings(crossing_scores, selected_threshold)
            if point[0] >= first_holdout_index
        ]
        quality = _classification_quality(
            history,
            holdout_scores,
            holdout_signals,
            horizon_days=horizon_days,
            hit_threshold_percent=hit_threshold_percent,
        )
        folds.append(RiskBacktestWalkForwardFold(
            fold=fold_index + 1,
            selected_threshold=selected_threshold,
            training_points=len(training_scores),
            holdout_points=len(holdout_scores),
            holdout_start=history[holdout_scores[0][0]].timestamp,
            holdout_end=history[holdout_scores[-1][0]].timestamp,
            holdout_event_count=quality.event_days,
            holdout_signal_count=quality.signal_count,
            baseline_hit_rate_percent=quality.baseline_hit_rate_percent,
            precision_percent=quality.precision_percent,
            recall_percent=quality.recall_percent,
            lift=quality.lift,
        ))
        aggregate_scores.extend(holdout_scores)
        aggregate_signals.extend(holdout_signals)

    aggregate_quality = _classification_quality(
        history,
        aggregate_scores,
        aggregate_signals,
        horizon_days=horizon_days,
        hit_threshold_percent=hit_threshold_percent,
    )
    return RiskBacktestWalkForward(
        horizon_days=horizon_days,
        embargo_days=horizon_days,
        candidate_thresholds=candidate_thresholds,
        total_holdout_points=aggregate_quality.evaluated_days,
        event_days=aggregate_quality.event_days,
        signal_count=aggregate_quality.signal_count,
        baseline_hit_rate_percent=aggregate_quality.baseline_hit_rate_percent,
        accuracy_percent=aggregate_quality.accuracy_percent,
        precision_percent=aggregate_quality.precision_percent,
        recall_percent=aggregate_quality.recall_percent,
        miss_rate_percent=aggregate_quality.miss_rate_percent,
        lift=aggregate_quality.lift,
        folds=folds,
    )


_FEATURE_SPECS = (
    ("momentum_7d", "7日动量"),
    ("momentum_30d", "30日动量"),
    ("momentum_90d", "90日动量"),
    ("volatility_7d", "7日波动率"),
    ("volatility_ratio", "短长波动率比"),
    ("drawdown_30d", "30日回撤"),
    ("drawdown_7d", "7日回撤速度"),
    ("volume_zscore", "成交量异常"),
    ("ma20_distance", "MA20偏离"),
    ("signed_streak", "连续涨跌天数"),
)


def _risk_feature_vector(history: list[HistoryPoint], index: int) -> list[float]:
    if index < 90:
        raise ValueError("Risk features require at least 90 trailing days")
    current_price = history[index].price

    def momentum(days: int) -> float:
        previous_price = history[index - days].price
        return (current_price / previous_price - 1) * 100

    prices_30 = [point.price for point in history[index - 29:index + 1]]
    prices_7 = [point.price for point in history[index - 6:index + 1]]
    volatility_7 = _annualized_volatility(_daily_returns(
        [point.price for point in history[index - 7:index + 1]]
    ))
    volatility_30 = _annualized_volatility(_daily_returns(prices_30))
    volatility_ratio = volatility_7 / volatility_30 if volatility_30 > 0 else 1.0
    drawdown_30 = (current_price / max(prices_30) - 1) * 100
    drawdown_7 = (current_price / max(prices_7) - 1) * 100

    volumes = [
        float(point.volume or 0)
        for point in history[index - 29:index + 1]
        if float(point.volume or 0) > 0
    ]
    if len(volumes) >= 2:
        volume_mean = statistics.mean(volumes)
        volume_deviation = statistics.stdev(volumes)
        volume_zscore = (
            (float(history[index].volume or volume_mean) - volume_mean) / volume_deviation
            if volume_deviation > 0 else 0.0
        )
    else:
        volume_zscore = 0.0

    moving_average_20 = statistics.mean(
        point.price for point in history[index - 19:index + 1]
    )
    ma20_distance = (current_price / moving_average_20 - 1) * 100
    latest_change = current_price - history[index - 1].price
    streak_direction = 1 if latest_change > 0 else -1 if latest_change < 0 else 0
    streak = 0
    if streak_direction:
        for cursor in range(index, max(0, index - 10), -1):
            change = history[cursor].price - history[cursor - 1].price
            if change * streak_direction <= 0:
                break
            streak += streak_direction

    return [
        momentum(7),
        momentum(30),
        momentum(90),
        volatility_7,
        volatility_ratio,
        drawdown_30,
        drawdown_7,
        volume_zscore,
        ma20_distance,
        float(streak),
    ]


def _fit_logistic_regression(
    rows: list[list[float]],
    labels: list[int],
    *,
    iterations: int = 160,
    learning_rate: float = 0.12,
    l2_penalty: float = 0.015,
) -> tuple[list[float], float, list[float], list[float]]:
    if not rows or len(rows) != len(labels):
        raise ValueError("Training rows and labels must be non-empty and aligned")
    feature_count = len(rows[0])
    means = [statistics.mean(row[column] for row in rows) for column in range(feature_count)]
    scales = []
    for column in range(feature_count):
        values = [row[column] for row in rows]
        deviation = statistics.pstdev(values)
        scales.append(deviation if deviation > 1e-9 else 1.0)
    normalized_rows = [
        [(row[column] - means[column]) / scales[column] for column in range(feature_count)]
        for row in rows
    ]
    weights = [0.0] * feature_count
    positive_rate = min(0.999, max(0.001, statistics.mean(labels)))
    intercept = math.log(positive_rate / (1 - positive_rate))
    sample_count = len(rows)

    for _ in range(iterations):
        weight_gradients = [0.0] * feature_count
        intercept_gradient = 0.0
        for row, label in zip(normalized_rows, labels):
            linear = intercept + sum(weight * value for weight, value in zip(weights, row))
            probability = 1 / (1 + math.exp(-max(-30.0, min(30.0, linear))))
            error = probability - label
            intercept_gradient += error
            for column, value in enumerate(row):
                weight_gradients[column] += error * value
        intercept_update = learning_rate * intercept_gradient / sample_count
        intercept -= intercept_update
        largest_update = abs(intercept_update)
        for column in range(feature_count):
            gradient = weight_gradients[column] / sample_count + l2_penalty * weights[column]
            update = learning_rate * gradient
            weights[column] -= update
            largest_update = max(largest_update, abs(update))
        if largest_update < 1e-5:
            break
    return weights, intercept, means, scales


def _predict_probability(
    row: list[float],
    weights: list[float],
    intercept: float,
    means: list[float],
    scales: list[float],
) -> float:
    normalized = [
        (value - means[column]) / scales[column]
        for column, value in enumerate(row)
    ]
    linear = intercept + sum(weight * value for weight, value in zip(weights, normalized))
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, linear))))


def _probability_crossings(
    probabilities: list[tuple[int, float]],
    threshold: float,
) -> list[tuple[int, float]]:
    crossings: list[tuple[int, float]] = []
    previous_probability: float | None = None
    for index, probability in probabilities:
        if (
            previous_probability is not None
            and previous_probability < threshold <= probability
        ):
            crossings.append((index, probability))
        previous_probability = probability
    return crossings


def _feature_model_validation(
    history: list[HistoryPoint],
    *,
    last_signal_index: int,
    horizon_days: int,
    hit_threshold_percent: float,
    fold_count: int = 3,
) -> RiskFeatureModelResult:
    model_name = "v0.4 标准化逻辑回归实验"
    target = f"未来{horizon_days}日最大跌幅 ≥ {hit_threshold_percent:g}%"
    samples = [
        (index, _risk_feature_vector(history, index))
        for index in range(90, last_signal_index + 1)
    ]
    if len(samples) < 180:
        return RiskFeatureModelResult(
            status="insufficient_data",
            model_name=model_name,
            target=target,
            horizon_days=horizon_days,
            lookback_days=90,
            embargo_days=horizon_days,
            total_holdout_points=0,
            event_days=0,
            signal_count=0,
            baseline_hit_rate_percent=0.0,
            accuracy_percent=0.0,
            precision_percent=0.0,
            recall_percent=0.0,
            miss_rate_percent=0.0,
            lift=0.0,
            promoted=False,
            verdict="历史样本不足，至少需要约 270 天数据完成滚动训练与验证。",
            feature_importance=[],
            folds=[],
        )

    probability_thresholds = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
    initial_training_points = len(samples) // 2
    remaining_points = len(samples) - initial_training_points
    fold_size = max(1, remaining_points // fold_count)
    folds: list[RiskFeatureModelFold] = []
    aggregate_scores: list[tuple[int, float]] = []
    aggregate_signals: list[tuple[int, float]] = []
    fold_weights: list[list[float]] = []

    for fold_index in range(fold_count):
        holdout_start_position = initial_training_points + fold_index * fold_size
        holdout_end_position = (
            len(samples)
            if fold_index == fold_count - 1
            else min(len(samples), holdout_start_position + fold_size)
        )
        if holdout_start_position >= holdout_end_position:
            continue
        calibration_end = max(1, holdout_start_position - horizon_days)
        training_samples = samples[:calibration_end]
        training_rows = [row for _, row in training_samples]
        training_labels = [
            int(_future_max_drawdown(history, index, horizon_days) >= hit_threshold_percent)
            for index, _ in training_samples
        ]
        weights, intercept, means, scales = _fit_logistic_regression(
            training_rows,
            training_labels,
        )
        fold_weights.append(weights)
        training_probabilities = [
            (index, _predict_probability(row, weights, intercept, means, scales))
            for index, row in training_samples
        ]
        minimum_training_signals = max(5, round(len(training_samples) / 100))
        candidates: list[tuple[tuple[float, float, int, float], float]] = []
        for threshold in probability_thresholds:
            training_signals = _probability_crossings(training_probabilities, threshold)
            quality = _classification_quality(
                history,
                training_probabilities,
                training_signals,
                horizon_days=horizon_days,
                hit_threshold_percent=hit_threshold_percent,
            )
            if quality.signal_count < minimum_training_signals:
                continue
            candidates.append((
                (
                    quality.lift,
                    quality.precision_percent,
                    quality.signal_count,
                    -abs(threshold - 0.5),
                ),
                threshold,
            ))
        selected_threshold = max(candidates)[1] if candidates else 0.5

        prediction_samples = samples[holdout_start_position - 1:holdout_end_position]
        prediction_probabilities = [
            (index, _predict_probability(row, weights, intercept, means, scales))
            for index, row in prediction_samples
        ]
        holdout_samples = samples[holdout_start_position:holdout_end_position]
        holdout_indexes = {index for index, _ in holdout_samples}
        holdout_probabilities = [
            point for point in prediction_probabilities if point[0] in holdout_indexes
        ]
        holdout_signals = [
            point
            for point in _probability_crossings(prediction_probabilities, selected_threshold)
            if point[0] in holdout_indexes
        ]
        quality = _classification_quality(
            history,
            holdout_probabilities,
            holdout_signals,
            horizon_days=horizon_days,
            hit_threshold_percent=hit_threshold_percent,
        )
        folds.append(RiskFeatureModelFold(
            fold=fold_index + 1,
            probability_threshold_percent=round(selected_threshold * 100, 1),
            training_points=len(training_samples),
            holdout_points=len(holdout_samples),
            holdout_start=history[holdout_samples[0][0]].timestamp,
            holdout_end=history[holdout_samples[-1][0]].timestamp,
            holdout_event_count=quality.event_days,
            holdout_signal_count=quality.signal_count,
            baseline_hit_rate_percent=quality.baseline_hit_rate_percent,
            precision_percent=quality.precision_percent,
            recall_percent=quality.recall_percent,
            lift=quality.lift,
        ))
        aggregate_scores.extend(holdout_probabilities)
        aggregate_signals.extend(holdout_signals)

    aggregate_quality = _classification_quality(
        history,
        aggregate_scores,
        aggregate_signals,
        horizon_days=horizon_days,
        hit_threshold_percent=hit_threshold_percent,
    )
    average_weights = [
        statistics.mean(weights[column] for weights in fold_weights)
        for column in range(len(_FEATURE_SPECS))
    ]
    feature_importance = sorted(
        [
            RiskFeatureImportance(
                key=key,
                label=label,
                coefficient=round(coefficient, 3),
                direction="raises_risk" if coefficient >= 0 else "lowers_risk",
            )
            for (key, label), coefficient in zip(_FEATURE_SPECS, average_weights)
        ],
        key=lambda item: abs(item.coefficient),
        reverse=True,
    )
    successful_folds = sum(fold.lift > 1 for fold in folds)
    promoted = (
        aggregate_quality.lift > 1
        and aggregate_quality.precision_percent > aggregate_quality.baseline_hit_rate_percent
        and successful_folds >= 2
        and aggregate_quality.signal_count >= 5
    )
    verdict = (
        "通过晋级门槛：留出期相对市场基准有稳定增益，可进入影子运行。"
        if promoted
        else "未通过晋级门槛：保留为实验模型，不替换当前线上风险分。"
    )
    return RiskFeatureModelResult(
        status="validated",
        model_name=model_name,
        target=target,
        horizon_days=horizon_days,
        lookback_days=90,
        embargo_days=horizon_days,
        total_holdout_points=aggregate_quality.evaluated_days,
        event_days=aggregate_quality.event_days,
        signal_count=aggregate_quality.signal_count,
        baseline_hit_rate_percent=aggregate_quality.baseline_hit_rate_percent,
        accuracy_percent=aggregate_quality.accuracy_percent,
        precision_percent=aggregate_quality.precision_percent,
        recall_percent=aggregate_quality.recall_percent,
        miss_rate_percent=aggregate_quality.miss_rate_percent,
        lift=aggregate_quality.lift,
        promoted=promoted,
        verdict=verdict,
        feature_importance=feature_importance,
        folds=folds,
    )


def _market_regime(
    history: list[HistoryPoint],
    index: int,
    *,
    lookback_days: int = 90,
    trend_threshold_percent: float = 10.0,
) -> str:
    """Classify a signal using only prices known at the signal timestamp."""
    start_index = max(0, index - lookback_days)
    if index - start_index < 30:
        return "sideways"
    trailing_return = (
        history[index].price / history[start_index].price - 1
    ) * 100
    if trailing_return >= trend_threshold_percent:
        return "bull"
    if trailing_return <= -trend_threshold_percent:
        return "bear"
    return "sideways"


def backtest_risk(
    coin_id: str,
    symbol: str,
    history: list[HistoryPoint],
    *,
    window_days: int = 30,
    risk_threshold: int = 60,
    hit_threshold_percent: float = 3.0,
    horizons: tuple[int, ...] = (1, 3, 7),
) -> RiskBacktestResult:
    if window_days < 2:
        raise ValueError("Backtest window must contain at least two days")
    if not horizons or min(horizons) < 1:
        raise ValueError("Backtest horizons must be positive")
    if not 0 <= risk_threshold <= 100:
        raise ValueError("Risk threshold must be between 0 and 100")
    if hit_threshold_percent <= 0:
        raise ValueError("Hit threshold must be positive")

    clean_by_timestamp = {
        point.timestamp: point
        for point in history
        if point.price > 0
    }
    clean_history = [clean_by_timestamp[key] for key in sorted(clean_by_timestamp)]
    maximum_horizon = max(horizons)
    required_points = window_days + maximum_horizon + 1
    if len(clean_history) < required_points:
        raise ValueError(f"At least {required_points} history points are required for backtesting")

    last_signal_index = len(clean_history) - maximum_horizon - 1
    score_series = _backtest_score_series(
        coin_id,
        symbol,
        clean_history,
        window_days,
        last_signal_index,
    )
    signal_points = _threshold_crossings(score_series, risk_threshold)
    signals: list[RiskBacktestSignal] = []
    drawdowns_by_horizon: dict[int, list[float]] = {days: [] for days in horizons}
    signal_drawdowns: dict[int, dict[int, float]] = {}

    for index, score in signal_points:
        signal_price = clean_history[index].price
        future_drawdowns: dict[str, float] = {}
        signal_drawdowns[index] = {}
        for horizon_days in horizons:
            drawdown = _future_max_drawdown(clean_history, index, horizon_days)
            drawdowns_by_horizon[horizon_days].append(drawdown)
            signal_drawdowns[index][horizon_days] = drawdown
            future_drawdowns[str(horizon_days)] = drawdown

        signals.append(RiskBacktestSignal(
            timestamp=clean_history[index].timestamp,
            score=score,
            price=round(signal_price, 8),
            future_drawdowns=future_drawdowns,
        ))

    horizon_results: list[RiskBacktestHorizon] = []
    for horizon_days in horizons:
        values = drawdowns_by_horizon[horizon_days]
        hit_count = sum(value >= hit_threshold_percent for value in values)
        horizon_results.append(RiskBacktestHorizon(
            horizon_days=horizon_days,
            samples=len(values),
            hit_count=hit_count,
            hit_rate_percent=round(hit_count / len(values) * 100, 1) if values else 0.0,
            average_max_drawdown_percent=(
                round(statistics.mean(values), 2) if values else 0.0
            ),
            worst_max_drawdown_percent=round(max(values), 2) if values else 0.0,
        ))

    comparison_horizon = maximum_horizon
    regime_labels = {
        "bull": "上涨阶段",
        "bear": "下跌阶段",
        "sideways": "震荡阶段",
    }
    regime_values: dict[str, list[float]] = {
        "bull": [],
        "bear": [],
        "sideways": [],
    }
    for index, _ in signal_points:
        regime = _market_regime(clean_history, index)
        regime_values[regime].append(signal_drawdowns[index][comparison_horizon])
    regimes = []
    for regime in ("bull", "bear", "sideways"):
        values = regime_values[regime]
        hit_count = sum(value >= hit_threshold_percent for value in values)
        regimes.append(RiskBacktestRegime(
            regime=regime,
            label=regime_labels[regime],
            signal_count=len(values),
            hit_count=hit_count,
            hit_rate_percent=_hit_rate(values, hit_threshold_percent),
            average_max_drawdown_percent=(
                round(statistics.mean(values), 2) if values else 0.0
            ),
        ))

    split_position = max(1, min(len(score_series) - 1, round(len(score_series) * 0.7)))
    first_holdout_index = score_series[split_position][0]
    training_drawdowns = [
        signal_drawdowns[index][comparison_horizon]
        for index, _ in signal_points
        if index < first_holdout_index
    ]
    holdout_drawdowns = [
        signal_drawdowns[index][comparison_horizon]
        for index, _ in signal_points
        if index >= first_holdout_index
    ]
    validation = RiskBacktestValidation(
        horizon_days=comparison_horizon,
        split_timestamp=clean_history[first_holdout_index].timestamp,
        training_points=split_position,
        holdout_points=len(score_series) - split_position,
        training_signal_count=len(training_drawdowns),
        holdout_signal_count=len(holdout_drawdowns),
        training_hit_rate_percent=_hit_rate(training_drawdowns, hit_threshold_percent),
        holdout_hit_rate_percent=_hit_rate(holdout_drawdowns, hit_threshold_percent),
    )

    sensitivity = []
    sensitivity_thresholds = sorted({
        max(0, risk_threshold - 10),
        risk_threshold,
        min(100, risk_threshold + 10),
    })
    for threshold in sensitivity_thresholds:
        threshold_signals = _threshold_crossings(score_series, threshold)
        values = [
            _future_max_drawdown(clean_history, index, comparison_horizon)
            for index, _ in threshold_signals
        ]
        sensitivity.append(RiskBacktestSensitivity(
            threshold=threshold,
            horizon_days=comparison_horizon,
            signal_count=len(values),
            hit_rate_percent=_hit_rate(values, hit_threshold_percent),
            average_max_drawdown_percent=(
                round(statistics.mean(values), 2) if values else 0.0
            ),
        ))

    quality = _classification_quality(
        clean_history,
        score_series,
        signal_points,
        horizon_days=comparison_horizon,
        hit_threshold_percent=hit_threshold_percent,
    )
    walk_forward = _walk_forward_validation(
        clean_history,
        score_series,
        risk_threshold=risk_threshold,
        horizon_days=comparison_horizon,
        hit_threshold_percent=hit_threshold_percent,
    )
    feature_model = _feature_model_validation(
        clean_history,
        last_signal_index=last_signal_index,
        horizon_days=comparison_horizon,
        hit_threshold_percent=hit_threshold_percent,
    )

    return RiskBacktestResult(
        coin_id=coin_id,
        symbol=symbol,
        model_version="基础价格模型 v0.3 · 基准与滚动验证",
        history_days=len(clean_history),
        window_days=window_days,
        risk_threshold=risk_threshold,
        hit_threshold_percent=hit_threshold_percent,
        evaluated_points=len(score_series),
        signal_count=len(signals),
        sample_start=clean_history[0].timestamp,
        sample_end=clean_history[-1].timestamp,
        horizons=horizon_results,
        regimes=regimes,
        validation=validation,
        sensitivity=sensitivity,
        quality=quality,
        walk_forward=walk_forward,
        feature_model=feature_model,
        recent_signals=signals[-5:][::-1],
        methodology=(
            f"使用{window_days}日滚动基础风险分；仅记录风险分首次上穿阈值的日期。"
            "命中表示信号后指定窗口内，相对信号日收盘价的最大跌幅达到设定标准；"
            "市场阶段仅使用信号日前90日价格判定；Lift比较信号命中率与任意评估日的自然跌幅概率。"
            "Walk-forward每轮只用此前数据选择阈值，并剔除紧邻留出期的预测窗口，防止标签穿越。"
            "v0.4特征模型仅在留出期通过晋级门槛后才允许替代现有规则模型。"
        ),
        calculated_at=datetime.now(UTC).isoformat(),
    )
