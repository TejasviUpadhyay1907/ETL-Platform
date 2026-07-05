import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
"""
Page 4 — Data Quality Dashboard

Quality scores, letter grades, violation breakdown, trends, dataset comparison.
"""
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Data Quality", page_icon="🎯", layout="wide")

from dashboard.utils.auth import init_session, require_auth, render_sidebar_user
from dashboard.utils import api_client as api
from dashboard.utils.formatting import (
    fmt_number, fmt_pct, grade_badge, status_badge, fmt_dt, extract_data, extract_list,
)
from dashboard.utils.charts import (
    quality_gauge, quality_dimensions_bar, violations_pie, quality_heatmap,
)

init_session()
require_auth()
render_sidebar_user()

st.title("🎯 Data Quality Dashboard")

# ── Fetch pipeline history to populate run selector ───────────────────────
history_resp = api.get_pipeline_history(page=1, page_size=50)
runs = extract_list(history_resp)

if not runs:
    st.info("No pipeline runs available. Run a pipeline first.")
    st.stop()

# ── Sidebar: run selector ──────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Select Run")
    filter_dataset = st.selectbox("Dataset", ["All", "orders", "customers", "products", "inventory", "suppliers", "payments"])
    filtered_runs = [r for r in runs if filter_dataset == "All" or r.get("dataset_type") == filter_dataset]
    run_options = {f"{r.get('run_number', 'N/A')} — {r.get('dataset_type', '')} ({r.get('status', '')})" : r.get("id") for r in filtered_runs if r.get("id")}

    if not run_options:
        st.warning("No runs for this dataset.")
        st.stop()

    selected_label = st.selectbox("Pipeline Run", list(run_options.keys()))
    selected_id = run_options[selected_label]

# ── Fetch quality data for selected run ───────────────────────────────────
quality_resp = api.get_quality_score(selected_id)
quality_data = extract_data(quality_resp)

summary_resp = api.get_quality_summary(selected_id)
summary_data = extract_data(summary_resp)

violations_resp = api.get_quality_report(selected_id, page=1, page_size=100)
violations = extract_list(violations_resp)

# ── Quality score KPIs ────────────────────────────────────────────────────
if quality_data:
    score = quality_data.get("overall_score", 0)
    grade = quality_data.get("letter_grade", "—")

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.metric("Overall Score", fmt_pct(score))
    with k2:
        st.metric("Letter Grade", grade_badge(grade))
    with k3:
        st.metric("Total Records", fmt_number(quality_data.get("total_records")))
    with k4:
        st.metric("Valid Records", fmt_number(quality_data.get("valid_records")))
    with k5:
        st.metric("Total Violations", fmt_number(quality_data.get("total_violations")))

    st.markdown("---")

    # ── Gauge + dimensions ─────────────────────────────────────────────────
    col_gauge, col_dims = st.columns(2)
    with col_gauge:
        st.plotly_chart(quality_gauge(score, f"Quality Score — {grade}"), use_container_width=True)

    with col_dims:
        dimensions = {
            "Completeness": quality_data.get("completeness", score),
            "Validity":     quality_data.get("validity",     score),
            "Consistency":  quality_data.get("consistency",  score),
            "Uniqueness":   quality_data.get("uniqueness",   score),
            "Integrity":    quality_data.get("integrity",    score),
            "Timeliness":   quality_data.get("timeliness",   score),
        }
        st.plotly_chart(quality_dimensions_bar(dimensions), use_container_width=True)

    # ── Violations summary ─────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Violations Summary")

    err_count  = quality_data.get("error_violations", 0) or 0
    warn_count = quality_data.get("warning_violations", 0) or 0
    info_count = max(0, (quality_data.get("total_violations", 0) or 0) - err_count - warn_count)

    viol_col, rules_col = st.columns(2)
    with viol_col:
        if (err_count + warn_count + info_count) > 0:
            st.plotly_chart(violations_pie(err_count, warn_count, info_count), use_container_width=True)
        else:
            st.success("✅ No violations found.")

    with rules_col:
        st.metric("Error Violations",   fmt_number(err_count))
        st.metric("Warning Violations", fmt_number(warn_count))
        st.metric("Rules Executed",     fmt_number(quality_data.get("total_rules_executed")))

else:
    if quality_resp.get("error"):
        st.warning(f"No quality score available for this run: {quality_resp.get('error')}")
    else:
        st.info("No quality data found for this run.")

# ── Violation details table ────────────────────────────────────────────────
if violations:
    st.markdown("---")
    st.subheader(f"Violation Details ({len(violations)} records)")

    search_v = st.text_input("Filter violations", placeholder="rule code, field name…")
    filtered_v = violations
    if search_v:
        sq = search_v.lower()
        filtered_v = [v for v in violations if sq in str(v).lower()]

    viol_rows = [
        {
            "Rule Code":    v.get("rule_code", "—"),
            "Severity":     v.get("severity", "—"),
            "Field":        v.get("field_name", "—"),
            "Row":          v.get("row_index", "—"),
            "Actual Value": str(v.get("actual_value", "—"))[:50],
            "Message":      str(v.get("message", "—"))[:80],
        }
        for v in filtered_v[:200]
    ]
    st.dataframe(pd.DataFrame(viol_rows), use_container_width=True, hide_index=True)

# ── Quality trend across all runs ─────────────────────────────────────────
if len(runs) >= 2:
    st.markdown("---")
    st.subheader("Quality Score Trend (recent runs)")

    trend_rows = [
        {
            "Run": r.get("run_number", "—"),
            "Dataset": r.get("dataset_type", "—"),
            "Score": r.get("quality_score") or 0,
            "Date": (r.get("started_at") or "")[:10],
        }
        for r in runs if r.get("quality_score") is not None
    ]
    if trend_rows:
        trend_df = pd.DataFrame(trend_rows).sort_values("Date")
        import plotly.express as px
        fig = px.line(
            trend_df, x="Run", y="Score", color="Dataset",
            title="Quality Score Trend by Run",
            markers=True,
        )
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#F1F5F9"), height=350)
        fig.add_hline(y=80, line_dash="dash", line_color="#F59E0B", annotation_text="Warning threshold")
        st.plotly_chart(fig, use_container_width=True)
