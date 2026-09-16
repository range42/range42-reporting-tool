"""Shared HTML-sanitization allowlist (single source of truth, backend side).

Mirrored in ``frontend/src/services/sanitize.ts``; the two MUST stay in sync. This module only
declares *what* is allowed — the sanitizer wiring is nh3 on the backend, DOMPurify on the
frontend.

Covers headings, lists, tables, inline/block code, images, and links.
"""

ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        # headings
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        # text + structure
        "p",
        "br",
        "hr",
        "span",
        "div",
        "blockquote",
        "strong",
        "em",
        "b",
        "i",
        "u",
        "s",
        "sub",
        "sup",
        # lists
        "ul",
        "ol",
        "li",
        # tables
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "caption",
        # code
        "code",
        "pre",
        # media + links
        "img",
        "a",
    }
)

# Per-tag attribute allowlist. The empty-string key holds attributes allowed on
# every tag (e.g. class for styling hooks).
ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "": frozenset({"class"}),
    "a": frozenset({"href", "title", "rel", "target"}),
    "img": frozenset({"src", "alt", "title", "width", "height"}),
    "td": frozenset({"colspan", "rowspan"}),
    "th": frozenset({"colspan", "rowspan", "scope"}),
    "code": frozenset({"class"}),
}
