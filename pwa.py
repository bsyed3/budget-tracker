"""Makes 'Add to Home Screen' on iOS behave like a real app: full-screen (no Safari chrome),
its own icon, and its own name under the icon.

st.markdown(unsafe_allow_html=True) can't reliably run <script> tags. This uses
st.components.v1.html instead, which renders a same-origin iframe -- script tags inside an
iframe's srcdoc *do* execute normally. From inside that iframe, window.parent.document is the
actual top-level app page (same-origin, so this is allowed), which is where the <meta>/<link>
tags actually need to live for iOS to see them.
"""
from __future__ import annotations

import streamlit.components.v1 as components

APP_NAME = "Budget Tracker"
THEME_COLOR = "#2563eb"  # matches the app's Needs/brand blue

# 180x180 PNG, blue gradient background with a white "$". Regenerate via Pillow if ever needed:
# a 180x180 image, vertical gradient #2563eb -> #1d4ed8, bold white "$" centered.
_ICON_B64 = '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'

_TEMPLATE = """
<script>
(function() {
    var doc = window.parent.document;
    if (doc.querySelector('link[rel="apple-touch-icon"]')) return;
    doc.head.insertAdjacentHTML('beforeend', `
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <meta name="apple-mobile-web-app-title" content="__APP_NAME__">
        <meta name="mobile-web-app-capable" content="yes">
        <meta name="theme-color" content="__THEME_COLOR__">
        <link rel="apple-touch-icon" href="data:image/png;base64,__ICON_B64__">
        <link rel="icon" href="data:image/png;base64,__ICON_B64__">
    `);
})();
</script>
"""


def inject() -> None:
    """Call once per page render (idempotent -- skips if the tags are already there)."""
    html = (
        _TEMPLATE
        .replace("__APP_NAME__", APP_NAME)
        .replace("__THEME_COLOR__", THEME_COLOR)
        .replace("__ICON_B64__", _ICON_B64)
    )
    components.html(html, height=0, width=0)


_NUMBER_INPUT_UX = """
<script>
(function() {
    var doc = window.parent.document;
    if (doc._numberInputUxBound) return;
    doc._numberInputUxBound = true;
    // Tapping/clicking into a number field selects its whole value, so typing immediately
    // replaces it instead of inserting alongside the existing "0.00". Event delegation on
    // the document (rather than binding each input) survives Streamlit re-rendering the
    // page on every rerun.
    doc.addEventListener("focusin", function(e) {
        var el = e.target;
        if (el && el.tagName === "INPUT" && el.type === "number") {
            // Deferred: a mouse click's own default action (placing the cursor where you
            // clicked) runs *after* the focus event, so calling select() immediately gets
            // silently undone by it. Pushing this to the next tick runs after that settles.
            setTimeout(function() { el.select(); }, 0);
        }
    });

    // Cap typed input at 2 decimal places in real time (not just on blur/rerun). These are
    // React-controlled inputs, so a plain `el.value = ...` wouldn't be seen by React -- using
    // the native setter plus a re-dispatched "input" event is the standard way to change a
    // controlled input's value from outside React and have it actually stick.
    var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    doc.addEventListener("input", function(e) {
        var el = e.target;
        if (!(el && el.tagName === "INPUT" && el.type === "number")) return;
        var v = el.value;
        var m = v.match(/^-?\\d*\\.?\\d{0,2}/);
        var trimmed = m ? m[0] : "";
        if (trimmed !== v) {
            nativeSetter.call(el, trimmed);
            el.dispatchEvent(new Event("input", { bubbles: true }));
        }
    });
})();
</script>
"""


def inject_number_input_ux() -> None:
    """Call once per page render. Auto-selects a number input's value on focus."""
    components.html(_NUMBER_INPUT_UX, height=0, width=0)
