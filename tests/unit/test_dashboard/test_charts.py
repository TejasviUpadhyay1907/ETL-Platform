"""
Tests for dashboard/utils/charts.py

Verifies that chart builder functions return valid Plotly Figure objects
without raising, using minimal synthetic data.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import pytest

from dashboard.utils.charts import (
    pipeline_status_donut,
    pipeline_runs_over_time,
    stage_duration_bar,
    quality_gauge,
    quality_dimensions_bar,
    records_funnel,
    load_metrics_bar,
    stage_timeline,
    violations_pie,
)


class TestPipelineStatusDonut:
    def test_returns_figure(self):
        fig = pipeline_status_donut({"completed": 10, "failed": 2, "running": 1})
        assert isinstance(fig, go.Figure)

    def test_empty_dict(self):
        fig = pipeline_status_donut({})
        assert isinstance(fig, go.Figure)

    def test_single_status(self):
        fig = pipeline_status_donut({"completed": 100})
        assert isinstance(fig, go.Figure)


class TestPipelineRunsOverTime:
    def test_returns_figure(self):
        df = pd.DataFrame({"date": ["2024-01-01", "2024-01-02"], "count": [5, 8]})
        fig = pipeline_runs_over_time(df)
        assert isinstance(fig, go.Figure)


class TestStageDurationBar:
    def test_returns_figure(self):
        fig = stage_duration_bar({"ingestion": 1000, "validation": 2500, "loading": 800})
        assert isinstance(fig, go.Figure)

    def test_empty_dict(self):
        fig = stage_duration_bar({})
        assert isinstance(fig, go.Figure)


class TestQualityGauge:
    def test_high_score(self):
        fig = quality_gauge(95.0)
        assert isinstance(fig, go.Figure)

    def test_medium_score(self):
        fig = quality_gauge(75.0)
        assert isinstance(fig, go.Figure)

    def test_low_score(self):
        fig = quality_gauge(30.0)
        assert isinstance(fig, go.Figure)

    def test_zero(self):
        fig = quality_gauge(0.0)
        assert isinstance(fig, go.Figure)


class TestQualityDimensionsBar:
    def test_all_dimensions(self):
        dims = {
            "Completeness": 95.0, "Validity": 88.0, "Consistency": 91.0,
            "Uniqueness": 99.0, "Integrity": 85.0, "Timeliness": 70.0,
        }
        fig = quality_dimensions_bar(dims)
        assert isinstance(fig, go.Figure)

    def test_empty(self):
        fig = quality_dimensions_bar({})
        assert isinstance(fig, go.Figure)


class TestRecordsFunnel:
    def test_normal_funnel(self):
        fig = records_funnel(1000, 950, 940, 930)
        assert isinstance(fig, go.Figure)

    def test_zeros(self):
        fig = records_funnel(0, 0, 0, 0)
        assert isinstance(fig, go.Figure)


class TestLoadMetricsBar:
    def test_full_metrics(self):
        metrics = {"rows_inserted": 100, "rows_updated": 20, "rows_skipped": 5, "rows_failed": 1}
        fig = load_metrics_bar(metrics)
        assert isinstance(fig, go.Figure)

    def test_empty_metrics(self):
        fig = load_metrics_bar({})
        assert isinstance(fig, go.Figure)


class TestStageTimeline:
    def test_with_stages(self):
        stages = [
            {"stage_name": "ingestion",     "started_at": "2024-01-01T10:00:00", "completed_at": "2024-01-01T10:01:00", "status": "completed"},
            {"stage_name": "validation",    "started_at": "2024-01-01T10:01:00", "completed_at": "2024-01-01T10:02:00", "status": "completed"},
            {"stage_name": "transformation","started_at": "2024-01-01T10:02:00", "completed_at": "2024-01-01T10:03:00", "status": "failed"},
        ]
        fig = stage_timeline(stages)
        assert isinstance(fig, go.Figure)

    def test_empty_stages(self):
        fig = stage_timeline([])
        assert isinstance(fig, go.Figure)

    def test_missing_timestamps(self):
        stages = [{"stage_name": "ingestion", "status": "completed"}]
        fig = stage_timeline(stages)
        assert isinstance(fig, go.Figure)


class TestViolationsPie:
    def test_normal(self):
        fig = violations_pie(10, 5, 2)
        assert isinstance(fig, go.Figure)

    def test_zeros(self):
        fig = violations_pie(0, 0, 0)
        assert isinstance(fig, go.Figure)
