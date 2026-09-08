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

# Served from ./static/icon.png (requires [server] enableStaticServing = true in
# .streamlit/config.toml -- see that file) as a real fetchable URL rather than a data: URI.
# iOS Safari has a known history of not reliably honoring a data: URI for apple-touch-icon --
# the Home Screen icon can silently fall back to a page screenshot even though the tag looks
# fine in dev tools. The same file is also passed straight to st.set_page_config(page_icon=...)
# in app.py for the desktop favicon, so there's exactly one <link rel="icon"> in the page
# rather than this file adding a second, competing one.
_ICON_URL = "/app/static/icon.png"

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
        <link rel="apple-touch-icon" href="__ICON_URL__">
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
        .replace("__ICON_URL__", _ICON_URL)
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


_TOOLTIP_CLAMP = """
<script>
(function() {
    var doc = window.parent.document;
    if (doc._tooltipClampBound) return;
    doc._tooltipClampBound = true;
    var win = window.parent;
    var MARGIN = 8;

    // Vega-Lite/vega-tooltip positions its hover tooltip a fixed offset from the cursor with no
    // viewport-boundary check. A tall multi-line tooltip (e.g. the Spending by Category Type
    // pie's per-category breakdown) hovered near the bottom of the window runs off the bottom
    // edge -- and since the tooltip is position: fixed, that part is simply unreachable (there's
    // no scrolling a fixed element into view). This nudges it back on-screen, vertically and
    // horizontally, every time vega-tooltip repositions it, so all of its content stays visible
    // no matter where on the page you're hovering.
    function clamp(el) {
        var rect = el.getBoundingClientRect();
        var top = rect.top;
        var left = rect.left;
        if (rect.bottom > win.innerHeight - MARGIN) {
            top = Math.max(MARGIN, win.innerHeight - MARGIN - rect.height);
        }
        if (rect.right > win.innerWidth - MARGIN) {
            left = Math.max(MARGIN, win.innerWidth - MARGIN - rect.width);
        }
        if (top !== rect.top) el.style.top = top + "px";
        if (left !== rect.left) el.style.left = left + "px";
    }

    function watch(el) {
        var observer = new MutationObserver(function() { clamp(el); });
        observer.observe(el, { attributes: true, attributeFilter: ["style"] });
    }

    // The tooltip element is created lazily by vega-tooltip on first hover anywhere on the
    // page, so watch for it to show up rather than assuming it already exists.
    var existing = doc.getElementById("vg-tooltip-element");
    if (existing) {
        watch(existing);
    } else {
        var bodyObserver = new MutationObserver(function() {
            var el = doc.getElementById("vg-tooltip-element");
            if (el) {
                watch(el);
                bodyObserver.disconnect();
            }
        });
        bodyObserver.observe(doc.body, { childList: true, subtree: true });
    }
})();
</script>
"""


def inject_tooltip_clamp() -> None:
    """Call once per page render. Keeps Vega-Lite hover tooltips fully on-screen."""
    components.html(_TOOLTIP_CLAMP, height=0, width=0)
