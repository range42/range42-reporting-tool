"""Magic-byte content-type sniffing for attachment uploads (WP3 S9).

The client-declared MIME type is never trusted (guardrail: spoofed types must
be rejected). ``sniff`` derives the content type from the leading bytes against
a deliberate, closed allowlist — png/jpeg/gif/webp images plus PDF. SVG is
excluded on purpose (embedded-script risk), as is everything else: an upload
whose bytes match no signature is rejected by the route layer with 415.

Hand-rolled rather than libmagic/filetype: the allowlist is the security
boundary, and seven fixed prefixes are simpler to audit than a dependency that
recognises hundreds of formats we would then have to filter back down.
"""


def _is_webp(data: bytes) -> bool:
    # RIFF container: "RIFF" <4-byte size> "WEBP"
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
)

IMAGE_TYPES: frozenset[str] = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
ALLOWED_TYPES: frozenset[str] = IMAGE_TYPES | {"application/pdf"}


def sniff(data: bytes) -> str | None:
    """Return the allowlisted MIME type matching ``data``'s magic bytes, else ``None``."""
    for prefix, mime in _PREFIXES:
        if data.startswith(prefix):
            return mime
    if _is_webp(data):
        return "image/webp"
    return None
