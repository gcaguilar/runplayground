"""Weekly briefing (M5).

The dashboard should answer "how am I and what should I do next?" before
showing any weekly metric. This module composes the existing performance,
diagnostics and snapshot data into a small, evidence-backed briefing:

* current 10K fitness anchor and its change over 4, 8 and 12 weeks;
* the four distance predictions with their goal gap;
* the six diagnostic dimensions as signals;
* one headline, one improvement, one limitation and one next action.

Nothing is persisted. The headline is a code plus parameters so the bilingual
UI can render it; the underlying numbers are returned next to the sentence.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PerformanceSnapshot
from app.schemas import (
    BriefingActionOut,
    BriefingDistanceOut,
    BriefingInsightOut,
    BriefingSignalOut,
    BriefingTrendOut,
    BriefingView,
)
from app.services.diagnostics import build_diagnostics
from app.services.performance import build_overview, ensure_efforts, store_snapshot
from app.utils import as_utc, utcnow

MODEL_VERSION = "m5.0"
TREND_WINDOWS = (28, 56, 84)
TREND_STABLE_PCT = 0.5


def _snapshot_fitness(snapshot: PerformanceSnapshot) -> float | None:
    for item in snapshot.predictions or []:
        if not isinstance(item, dict):
            continue
        if item.get("distance_key") == "10k" and item.get("planning_s") is not None:
            return float(item["planning_s"])
    return snapshot.fitness_anchor_s


def _trends(
    db: Session,
    current_s: float | None,
    today: date,
) -> list[BriefingTrendOut]:
    snapshots = db.scalars(
        select(PerformanceSnapshot)
        .where(
            PerformanceSnapshot.snapshot_date >= today - timedelta(days=TREND_WINDOWS[-1] + 14),
            PerformanceSnapshot.snapshot_date <= today,
        )
        .order_by(PerformanceSnapshot.snapshot_date)
    ).all()

    output: list[BriefingTrendOut] = []
    for window in TREND_WINDOWS:
        cutoff = today - timedelta(days=window)
        previous = next(
            (snapshot for snapshot in reversed(snapshots) if snapshot.snapshot_date <= cutoff),
            None,
        )
        previous_s = _snapshot_fitness(previous) if previous is not None else None
        if current_s is None or previous_s is None or previous_s <= 0:
            output.append(
                BriefingTrendOut(
                    window_days=window,
                    as_of=previous.snapshot_date if previous else None,
                    current_s=round(current_s, 1) if current_s is not None else None,
                    previous_s=round(previous_s, 1) if previous_s is not None else None,
                    status="unknown",
                )
            )
            continue
        change_s = current_s - previous_s
        change_pct = change_s / previous_s * 100.0
        if change_pct <= -TREND_STABLE_PCT:
            status = "improving"
        elif change_pct >= TREND_STABLE_PCT:
            status = "worsening"
        else:
            status = "stable"
        output.append(
            BriefingTrendOut(
                window_days=window,
                as_of=previous.snapshot_date,
                current_s=round(current_s, 1),
                previous_s=round(previous_s, 1),
                change_s=round(change_s, 1),
                change_pct=round(change_pct, 1),
                status=status,
            )
        )
    return output


def _distance_out(overview) -> list[BriefingDistanceOut]:
    output: list[BriefingDistanceOut] = []
    for item in overview.distances:
        goal_time = item.goal.target_time_s if item.goal is not None else None
        goal_gap = (
            round(goal_time - item.planning.time_s, 1)
            if goal_time is not None and item.planning is not None
            else None
        )
        output.append(
            BriefingDistanceOut(
                distance_key=item.distance_key,
                distance_m=item.distance_m,
                time_s=item.planning.time_s if item.planning else None,
                low_s=item.planning.low_s if item.planning else None,
                high_s=item.planning.high_s if item.planning else None,
                goal_time_s=round(goal_time, 1) if goal_time is not None else None,
                goal_gap_s=goal_gap,
                confidence=item.confidence,
            )
        )
    return output


def _headline(
    diagnostics,
    trend: BriefingTrendOut | None,
    limiter_key: str | None,
) -> tuple[str, dict[str, float | int | str | None]]:
    params: dict[str, float | int | str | None] = {}
    if diagnostics.status == "insufficient":
        return "insufficient_data", params
    if "no_activities" in diagnostics.warnings or "stale_data" in diagnostics.warnings:
        return "no_recent_training", params
    if trend is not None:
        params["change_pct"] = abs(trend.change_pct or 0.0)
        params["window_days"] = trend.window_days
    if limiter_key is not None:
        params["limiter"] = limiter_key
    if trend is None or trend.status == "unknown":
        return ("no_trend_with_limit" if limiter_key else "no_trend_balanced"), params
    if trend.status == "improving":
        return ("improving_with_limit" if limiter_key else "improving_balanced"), params
    if trend.status == "worsening":
        return ("worsening_with_limit" if limiter_key else "worsening_balanced"), params
    return ("stable_with_limit" if limiter_key else "stable_balanced"), params


def _improvement(diagnostics, trend: BriefingTrendOut | None) -> BriefingInsightOut | None:
    if trend is not None and trend.status == "improving" and trend.change_pct is not None:
        return BriefingInsightOut(
            key="fitness_trend",
            value=round(abs(trend.change_pct), 1),
            reasons=["fitness_anchor_improved"],
        )
    scored = [item for item in diagnostics.dimensions if item.score is not None]
    if scored:
        best = max(scored, key=lambda item: item.score or 0.0)
        if (best.score or 0.0) >= 70:
            return BriefingInsightOut(
                key="dimension_strength",
                dimension_key=best.key,
                value=best.score,
                reasons=best.reasons,
            )
    return None


def _limitation(diagnostics) -> BriefingInsightOut | None:
    if not diagnostics.limiters:
        return None
    limiter = diagnostics.limiters[0]
    return BriefingInsightOut(
        key="limiter",
        dimension_key=limiter.dimension_key,
        value=limiter.score,
        reasons=limiter.reasons,
    )


def _action(diagnostics) -> BriefingActionOut | None:
    if not diagnostics.limiters:
        return None
    limiter = diagnostics.limiters[0]
    return BriefingActionOut(
        dimension_key=limiter.dimension_key,
        score=limiter.score,
        reasons=limiter.reasons,
    )


def build_briefing(
    db: Session,
    tz_offset_minutes: int = 0,
    now: datetime | None = None,
) -> BriefingView:
    reference = now or utcnow()
    offset = timedelta(minutes=tz_offset_minutes)
    today = (as_utc(reference) + offset).date()

    ensure_efforts(db)
    overview = build_overview(db, reference)
    store_snapshot(db, overview)
    diagnostics = build_diagnostics(db, reference, tz_offset_minutes)

    anchor = overview.fitness_anchor
    trends = _trends(db, anchor.time_s if anchor else None, today)
    trend = next((item for item in trends if item.window_days == 28), None)
    if trend is None or trend.status == "unknown":
        trend = next((item for item in trends if item.status != "unknown"), None)

    limiter_key = diagnostics.limiters[0].dimension_key if diagnostics.limiters else None
    headline, headline_params = _headline(diagnostics, trend, limiter_key)
    signals = [
        BriefingSignalOut(
            key=item.key,
            score=item.score,
            status=item.status,
            confidence=item.confidence,
            reasons=item.reasons,
        )
        for item in diagnostics.dimensions
    ]
    distances = _distance_out(overview)

    warnings: list[str] = []
    for code in (
        "no_activities",
        "no_anchor",
        "no_goal",
        "short_history",
        "stale_data",
    ):
        if code in diagnostics.warnings:
            warnings.append(code)
    if not any(item.time_s is not None for item in distances):
        warnings.append("no_predictions")

    if anchor is None or not any(item.time_s is not None for item in distances):
        status = "insufficient"
    elif any(item.time_s is None for item in distances) or any(
        item.status == "unknown" for item in trends
    ):
        status = "partial"
    else:
        status = "ok"

    return BriefingView(
        generated_at=reference,
        model_version=MODEL_VERSION,
        status=status,
        as_of=today,
        confidence=diagnostics.confidence,
        confidence_score=diagnostics.confidence_score,
        fitness_anchor=anchor,
        trends=trends,
        distances=distances,
        signals=signals,
        headline=headline,
        headline_params=headline_params,
        improvement=_improvement(diagnostics, trend),
        limitation=_limitation(diagnostics),
        action=_action(diagnostics),
        warnings=warnings,
        notes=[
            "briefing_is_derived",
            "trend_uses_snapshots",
            "load_is_estimated",
            "not_medical_advice",
        ],
    )
