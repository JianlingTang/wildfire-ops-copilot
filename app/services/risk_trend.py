from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from app.models.schemas import ChatRequest, RunRecord
from app.services.firestore_store import store


def build_risk_trend_response(request: ChatRequest, run: RunRecord | None, *, mode: str) -> dict[str, Any]:
    trend = _risk_trend_payload(request, run)
    points = trend["points"]
    latest = points[-1] if points else None
    answer = (
        f"Risk trend uses {len(points)} daily points across the default -5/+5 day analysis window. "
        f"{trend['note']}"
    )
    if latest:
        answer += f" Latest point: {latest['risk_level']} at {latest['risk_score']}/100."
    return _response("RISK_TREND", answer, trend, mode)


def build_risk_prediction_response(request: ChatRequest, run: RunRecord | None, *, mode: str) -> dict[str, Any]:
    trend = _risk_trend_payload(request, run)
    future = [point for point in trend["points"] if point["type"] == "forecast"]
    peak = max(future or trend["points"], key=lambda point: point["risk_score"], default=None)
    answer = "Prediction uses the current AOI analysis and deterministic +5 day forecast window."
    if peak:
        answer += f" Highest predicted risk is {peak['risk_level']} at {peak['risk_score']}/100 on {peak['date']}."
    trend["prediction"] = {
        "forecast_points": future,
        "peak": peak,
        "caveat": "This is an explainable demo forecast, not an official meteorological forecast.",
    }
    return _response("RISK_PREDICTION", answer, trend, mode)


def _response(intent: str, answer: str, trend: dict[str, Any], mode: str) -> dict[str, Any]:
    return {
        "status": "success",
        "mode": mode,
        "answer": answer,
        "risk_trend": trend,
        "tool_trace": [
            {
                "called": "Risk Timeseries Tool",
                "did": "Built risk timeseries and rendered PNG chart.",
                "output": f"{len(trend['points'])} points with downloadable PNG.",
                "mode": mode,
                "status": "completed",
            }
        ],
        "intent": intent,
    }


def _risk_trend_payload(request: ChatRequest, run: RunRecord | None) -> dict[str, Any]:
    run = run or _latest_completed_run(request)
    region_name = run.region_name if run else request.region_name or request.region_id
    points = _points_from_run(run) if run else []
    note = (
        "Historical/current/forecast points come from the latest analysis artifact."
        if len(points) >= 11
        else "Run analysis first to generate the full -5/+5 day trend window."
    )
    chart = _render_chart(points, region_name)
    return {
        "points": points,
        "note": note,
        "region_name": region_name,
        "preview": chart,
        "downloads": {
            "png_filename": f"{_safe_filename(region_name)}-risk-trend.png",
        },
    }


def _points_from_run(run: RunRecord | None) -> list[dict[str, Any]]:
    if not run:
        return []
    timeseries = run.evidence.get("risk_timeseries", {})
    points = timeseries.get("points") if isinstance(timeseries, dict) else None
    if isinstance(points, list) and points:
        return points
    if run.risk_score is None or run.risk_level is None:
        return []
    date = (run.completed_at or run.created_at).date().isoformat()
    return [
        {
            "date": date,
            "risk_score": run.risk_score,
            "risk_level": run.risk_level,
            "type": "current",
        }
    ]


def _render_chart(points: list[dict[str, Any]], region_name: str) -> dict[str, Any]:
    fig, ax = plt.subplots(figsize=(8.4, 4.6), dpi=160)
    dates = [mdates.datestr2num(str(point["date"])) for point in points]
    scores = [int(point["risk_score"]) for point in points]
    colors = {"historical": "#64748b", "current": "#b45309", "forecast": "#0f766e"}

    if dates:
        ax.plot(dates, scores, "-", color="#334155", linewidth=2.2)
        for point, date, score in zip(points, dates, scores, strict=False):
            ax.scatter(date, score, s=52, color=colors.get(str(point.get("type")), "#334155"), zorder=3)
    ax.set_title(f"Risk trend for {region_name}")
    ax.set_xlabel("Date")
    ax.set_ylabel("Risk Score")
    ax.set_ylim(0, 100)
    ax.grid(True, linestyle="--", alpha=0.28)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.autofmt_xdate(rotation=30)
    fig.tight_layout()
    buffer = BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "format": "image/png",
        "encoding": "base64",
        "data_url": f"data:image/png;base64,{encoded}",
        "alt": f"Risk trend chart for {region_name} with Date x-axis and Risk Score y-axis.",
    }


def _latest_completed_run(request: ChatRequest) -> RunRecord | None:
    run = store.runs.get(request.run_id) if request.run_id else store.get_latest_run(request.region_id)
    return run if run and run.status == "completed" else None


def _safe_filename(value: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "-" for character in value)
    return "-".join(part for part in cleaned.split("-") if part) or "aoi"
