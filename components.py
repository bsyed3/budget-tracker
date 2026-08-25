"""Small HTML/CSS visual components not available as native Streamlit widgets."""
from __future__ import annotations

import streamlit as st

import db

_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def theme_text_color() -> str:
    """White in dark mode, black in light mode -- follows the app's active Streamlit theme
    (including "Use system setting"), not the specific background it's drawn on."""
    return "#ffffff" if st.context.theme.type == "dark" else "#000000"


def money(x: float) -> str:
    """Format a dollar amount for use inside st.write/markdown/caption/etc.

    Streamlit's markdown renderer treats a pair of "$" as inline LaTeX math, so two or more
    plain "${x:,.2f}" on the same line can silently render in a math font. Escaping the "$"
    keeps it literal. Not needed for st.metric, st.dataframe, or raw HTML (unsafe_allow_html).
    """
    return f"\\${x:,.2f}"


def signed_money(x: float) -> str:
    """Like money(), but with an explicit +/- sign -- for a change/delta rather than a plain amount."""
    sign = "+" if x >= 0 else "-"
    return f"{sign}\\${abs(x):,.2f}"


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
        text_color = theme_text_color()
        segments_html += (
            f'<div title="{name}: ${value:,.2f} ({pct:.0f}%)" '
            f'style="width:{pct:.3f}%;background:{color};height:100%;'
            f'display:flex;align-items:center;justify-content:center;overflow:hidden;">'
            f'<span style="color:{text_color};font-size:12px;font-weight:600;white-space:nowrap;'
            f'font-family:{_FONT};">{pct:.0f}%</span></div>'
        )
        legend_html += (
            f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:16px;'
            f'font-size:13px;font-family:{_FONT};">'
            f'<span style="width:10px;height:10px;border-radius:2px;background:{color};'
            f'display:inline-block;"></span>{name}: ${value:,.2f}</span>'
        )
    st.markdown(
        f'<div style="display:flex;width:100%;height:28px;border-radius:6px;overflow:hidden;">'
        f'{segments_html}</div>'
        f'<div style="margin-top:8px;">{legend_html}</div>',
        unsafe_allow_html=True,
    )


def colored_progress(pct: float) -> None:
    """A progress bar scaled to 100% — anything at or past 100% fills the bar completely.

    Turns amber near the limit and red at/past it (budgets going over).
    """
    color = "#16a34a" if pct < 0.8 else ("#f59e0b" if pct < 1.0 else "#dc2626")
    width = min(max(pct, 0.0), 1.0) * 100
    st.markdown(
        f'<div style="background:#e2e8f0;border-radius:6px;height:14px;width:100%;overflow:hidden;">'
        f'<div style="background:{color};width:{width:.2f}%;height:100%;"></div></div>',
        unsafe_allow_html=True,
    )


def status_pill(pct: float) -> str:
    """A small colored badge (HTML) — pass to st.markdown(..., unsafe_allow_html=True)."""
    if pct >= 1.0:
        bg, label = "#dc2626", "OVER"
    elif pct >= 0.8:
        bg, label = "#f59e0b", "NEAR"
    else:
        bg, label = "#16a34a", "OK"
    return tag(label, bg)


def tag(label: str, color: str) -> str:
    """A small colored badge (HTML) with an arbitrary label/color — same styling as status_pill."""
    text_color = theme_text_color()
    return (
        f'<span style="background:{color};color:{text_color};padding:3px 10px;border-radius:999px;'
        f'font-size:11px;font-weight:700;letter-spacing:.03em;font-family:{_FONT};'
        f'display:inline-block;white-space:nowrap;">{label}</span>'
    )
