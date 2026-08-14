"""Small HTML/CSS visual components not available as native Streamlit widgets."""
from __future__ import annotations

import streamlit as st

import db


def percentage_bar(breakdown: dict[str, float], colors: dict[str, str] | None = None) -> None:
    """A single horizontal bar split into colored, labeled segments sized by share of total."""
    colors = colors or db.GROUP_COLORS
    total = sum(v for v in breakdown.values() if v > 0)
    segments_html = ""
    legend_html = ""
    if total <= 0:
        st.caption("No data yet.")
        return
    for name, value in breakdown.items():
        if value <= 0:
            continue
        pct = value / total * 100
        color = colors.get(name, "#94a3b8")
        segments_html += (
            f'<div title="{name}: ${value:,.2f} ({pct:.0f}%)" '
            f'style="width:{pct:.3f}%;background:{color};height:100%;'
            f'display:flex;align-items:center;justify-content:center;overflow:hidden;">'
            f'<span style="color:white;font-size:12px;font-weight:600;white-space:nowrap;">'
            f'{pct:.0f}%</span></div>'
        )
        legend_html += (
            f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:16px;'
            f'font-size:13px;">'
            f'<span style="width:10px;height:10px;border-radius:2px;background:{color};'
            f'display:inline-block;"></span>{name}: ${value:,.2f}</span>'
        )
    st.markdown(
        f'<div style="display:flex;width:100%;height:28px;border-radius:6px;overflow:hidden;">'
        f'{segments_html}</div>'
        f'<div style="margin-top:8px;">{legend_html}</div>',
        unsafe_allow_html=True,
    )


def colored_progress(pct: float, label: str = "") -> None:
    """A progress bar that turns amber near 100% and red past it (budgets going over)."""
    pct_clamped = max(0.0, min(pct, 1.5))  # cap the visual fill at 150%
    color = "#16a34a" if pct < 0.8 else ("#f59e0b" if pct < 1.0 else "#dc2626")
    width = min(pct_clamped / 1.5 * 100, 100)
    st.markdown(
        f'<div style="background:#e2e8f0;border-radius:6px;height:14px;width:100%;overflow:hidden;">'
        f'<div style="background:{color};width:{width:.2f}%;height:100%;"></div></div>',
        unsafe_allow_html=True,
    )


def status_badge(pct: float) -> str:
    if pct >= 1.0:
        return "🔴 Over"
    if pct >= 0.8:
        return "🟡 Near limit"
    return "🟢 OK"
