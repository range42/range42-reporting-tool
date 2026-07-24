"""Server-authoritative HTML sanitization + plain-text extraction (nh3).

The writer editor (TipTap StarterKit) produces a constrained HTML subset.
``sanitize_html`` is the trust boundary for stored ``report_section.content``;
``html_to_plain`` derives ``content_plain`` / ``char_count`` for char-limit
enforcement and search.

The allowlist is NOT redefined here — it is sourced from
``app.core.sanitize_policy`` (the single source of truth, mirrored in
``frontend/src/services/sanitize.ts``). This module only wires nh3 to it.
"""

import re

import nh3

from app.core.sanitize_policy import ALLOWED_ATTRS, ALLOWED_TAGS

# nh3 wants plain ``set`` values and uses the "*" key for attributes allowed on
# every tag; the policy expresses that same global bucket with the "" key.
TIPTAP_ALLOWED: set[str] = set(ALLOWED_TAGS)
_NH3_ATTRS: dict[str, set[str]] = {("*" if tag == "" else tag): set(attrs) for tag, attrs in ALLOWED_ATTRS.items()}
_WS = re.compile(r"\s+")

# Inline images may only reference this app's own attachment-download endpoint
# (root-relative, fixed shape, dot-free segments — so no external/data:/traversal
# URLs survive sanitization). Mirrored in ``frontend/src/services/sanitize.ts``.
_IMG_SRC = re.compile(r"^/api/v1/exercises/[\w-]+/reports/[\w-]+/attachments/[\w-]+/download$")


def _attr_filter(tag: str, attr: str, value: str) -> str | None:
    if tag == "img" and attr == "src" and not _IMG_SRC.fullmatch(value):
        return None  # drop the attribute
    return value


def sanitize_html(html: str) -> str:
    """Return ``html`` reduced to the policy's allowed tag/attr set; scripts and JS URLs removed."""
    # link_rel=None: the policy owns the `rel` attribute (it is in the `a`
    # allowlist), so nh3 must not also guard/auto-inject it.
    return nh3.clean(html, tags=TIPTAP_ALLOWED, attributes=_NH3_ATTRS, link_rel=None, attribute_filter=_attr_filter)


def html_to_plain(html: str) -> str:
    """Strip every tag, unescape entities, collapse whitespace, trim."""
    stripped = nh3.clean(html, tags=set(), attributes={})
    return _WS.sub(" ", stripped).strip()
