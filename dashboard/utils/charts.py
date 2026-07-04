"""
Reusable Plotly chart builders for the ETL dashboard.

All functions accept plain Python dicts/lists and return plotly Figure objects.
No business logic — pure presentation.
"""
from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

# ---------------------------------------------------------------------------
# Colour palette (dark-theme friendly)
# ---------------------------------------------------------------------------

COLORS = {
    "success":  "#22C55E",
    "failed":   "#EF4444",
    "running":  "#3B82F6",
    "warning":  "#F59E0B",
    "skipped":  "#6B7280",
    "info":     "#60A5FA",
    "primary":  "#2563EB",
    "accent":   "#7C3AED",
}

STATUS_COLORS = {
    "completed": COLORS["success"],
    "succeeded": COLORS["success"],
    "running":   COLORS["running"],
    "failed":    COLORS["failed"],
    "cancelled": COLORS["skipped"],
    "retrying":  COLORS["warning"],
    "queued":    COLORS["info"],
    "pending":   COLORS["info"],
}

GRADE_COLORS = {
    "A+": "#22C55E", "A": "#4ADE80",
    "B":  "#86EFAC", "C": "#F59E0B",
    "D":  "#FB923C", "F": "#EF4444",
}

_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#F1F5F9", size=12),
    margin=dict(l=40, r=20, t=40, b=40),
)


def _apply_layout(fig: go.Figure, title: str = "", height: int = 350) -> go.Figure:
    fig.update_layout(**_LAYOUT, title=title, height=height)
    fig.update_xaxes(gridcolor="#1E293B", linecolor="#334155")
    fig.update_yaxes(gridcolor="#1E293B", linecolor="#334155")
    return fig


# ---------------------------------------------------------------------------
# Pipeline status pie / donut
# ---------------------------------------------------------------------------

def pipeline_status_donut(counts: dict[str, int], title: str = "Pipeline Status") -> go.Figure:
    labels = list(counts.keys())
    values = list(counts.values())
    colors = [STATUS_COLORS.get(s.lower(), COLORS["skipped"]) for s in labels]

    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.55,
        marker=dict(colors=colors, line=dict(color="#0F172A", width=2)),
        textinfo="label+percent",
        textfont=dict(size=11),
    ))
    return _apply_layout(fig, title, height=300)


# ---------------------------------------------------------------------------
# Pipeline runs over time (line / area)
# ---------------------------------------------------------------------------

def pipeline_runs_over_time(df: pd.DataFrame, date_col: str = "date", value_col: str = "count") -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=df[date_col], y=df[value_col],
        mode="lines+markers",
        fill="tozeroy",
        line=dict(color=COLORS["primary"], width=2),
        marker=dict(size=5),
    ))
    return _apply_layout(fig, "Pipeline Runs Over Time")


# ---------------------------------------------------------------------------
# Stage duration bar
# ---------------------------------------------------------------------------

def stage_duration_bar(stage_durations: dict[str, float]) -> go.Figure:
    stages = list(stage_durations.keys())
    durations = [round(v / 1000, 2) for v in stage_durations.values()]  # ms → s

    fig = go.Figure(go.Bar(
        x=stages, y=durations,
        marker_color=COLORS["primary"],
        text=[f"{d}s" for d in durations],
        textposition="outside",
    ))
    fig.update_layout(**_LAYOUT, title="Stage Durations (seconds)", height=300)
    fig.update_yaxes(title="Seconds", gridcolor="#1E293B")
    return fig


# ---------------------------------------------------------------------------
# Quality score gauge
# ---------------------------------------------------------------------------

def quality_gauge(score: float, title: str = "Quality Score") -> go.Figure:
    if score >= 90:
        color = COLORS["success"]
    elif score >= 70:
        color = COLORS["warning"]
    else:
        color = COLORS["failed"]

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": title, "font": {"color": "#F1F5F9"}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#F1F5F9"},
            "bar": {"color": color},
            "bgcolor": "#1E293B",
            "bordercolor": "#334155",
            "steps": [
                {"range": [0, 60],  "color": "#450a0a"},
                {"range": [60, 80], "color": "#422006"},
                {"range": [80, 100],"color": "#052e16"},
            ],
        },
        number={"suffix": "%", "font": {"color": "#F1F5F9"}},
    ))
    fig.update_layout(**_LAYOUT, height=250)
    return fig


# ---------------------------------------------------------------------------
# Quality dimensions radar / bar
# ---------------------------------------------------------------------------

def quality_dimensions_bar(dimensions: dict[str, float]) -> go.Figure:
    dims = list(dimensions.keys())
    vals = list(dimensions.values())
    colors = [COLORS["success"] if v >= 80 else COLORS["warning"] if v >= 60 else COLORS["failed"] for v in vals]

    fig = go.Figure(go.Bar(
        x=dims, y=vals,
        marker_color=colors,
        text=[f"{v:.1f}%" for v in vals],
        textposition="outside",
    ))
    fig.add_hline(y=80, line_dash="dash", line_color=COLORS["warning"], annotation_text="Warning threshold")
    fig.update_layout(**_LAYOUT, title="Quality Dimensions", height=300)
    fig.update_yaxes(range=[0, 110], title="Score %", gridcolor="#1E293B")
    return fig


# ---------------------------------------------------------------------------
# Records funnel
# ---------------------------------------------------------------------------

def records_funnel(
    total: int,
    valid: int,
    cleaned: int,
    loaded: int,
) -> go.Figure:
    fig = go.Figure(go.Funnel(
        y=["Ingested", "Validated", "Cleaned", "Loaded"],
        x=[total, valid, cleaned, loaded],
        textinfo="value+percent initial",
        marker=dict(color=[COLORS["info"], COLORS["success"], COLORS["warning"], COLORS["primary"]]),
    ))
    return _apply_layout(fig, "Records Pipeline Funnel", height=300)


# ---------------------------------------------------------------------------
# Heatmap — quality scores by dataset over time
# ---------------------------------------------------------------------------

def quality_heatmap(df: pd.DataFrame, x_col: str, y_col: str, z_col: str) -> go.Figure:
    pivot = df.pivot_table(index=y_col, columns=x_col, values=z_col, aggfunc="mean")
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=list(pivot.columns),
        y=list(pivot.index),
        colorscale="RdYlGn",
        zmin=0, zmax=100,
        text=[[f"{v:.1f}" for v in row] for row in pivot.values],
        texttemplate="%{text}",
    ))
    return _apply_layout(fig, "Quality Score Heatmap", height=350)


# ---------------------------------------------------------------------------
# Load metrics bar
# ---------------------------------------------------------------------------

def load_metrics_bar(metrics: dict[str, Any]) -> go.Figure:
    keys = ["rows_inserted", "rows_updated", "rows_skipped", "rows_failed"]
    labels = ["Inserted", "Updated", "Skipped", "Failed"]
    colors = [COLORS["success"], COLORS["info"], COLORS["warning"], COLORS["failed"]]
    vals = [metrics.get(k, 0) for k in keys]

    fig = go.Figure(go.Bar(
        x=labels, y=vals,
        marker_color=colors,
        text=vals,
        textposition="outside",
    ))
    return _apply_layout(fig, "Load Results", height=280)


# ---------------------------------------------------------------------------
# Timeline / Gantt for pipeline stages
# ---------------------------------------------------------------------------

def stage_timeline(stages: list[dict[str, Any]]) -> go.Figure:
    """stages: list of {stage_name, started_at, completed_at, status}"""
    if not stages:
        return _apply_layout(go.Figure(), "Stage Timeline")

    rows = []
    for s in stages:
        start = s.get("started_at", "")
        end = s.get("completed_at", start)
        rows.append({
            "Stage": s.get("stage_name", ""),
            "Start": start,
            "End": end,
            "Status": s.get("status", ""),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return _apply_layout(go.Figure(), "Stage Timeline")

    colors_map = {row["Stage"]: STATUS_COLORS.get(row["Status"], COLORS["info"]) for _, row in df.iterrows()}
    fig = px.timeline(df, x_start="Start", x_end="End", y="Stage", color="Stage",
                      color_discrete_map=colors_map)
    fig.update_yaxes(autorange="reversed")
    return _apply_layout(fig, "Stage Execution Timeline", height=300)


# ---------------------------------------------------------------------------
# Violation breakdown pie
# ---------------------------------------------------------------------------

def violations_pie(error_count: int, warning_count: int, info_count: int) -> go.Figure:
    labels = ["Errors", "Warnings", "Info"]
    values = [error_count, warning_count, info_count]
    colors = [COLORS["failed"], COLORS["warning"], COLORS["info"]]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors),
        hole=0.4,
        textinfo="label+value",
    ))
    return _apply_layout(fig, "Violations by Severity", height=280)
