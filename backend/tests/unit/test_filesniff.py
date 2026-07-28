"""WP3 S9 (#80) — magic-byte content sniffing.

The client-supplied MIME type is never trusted: the stored ``content_type`` is
whatever ``sniff()`` derives from the first bytes, and uploads whose bytes match
no allowlisted signature are rejected upstream (415).
"""

import pytest

from app.core.filesniff import IMAGE_TYPES, sniff

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF87 = b"GIF87a" + b"\x00" * 16
GIF89 = b"GIF89a" + b"\x00" * 16
WEBP = b"RIFF\x24\x00\x00\x00WEBP" + b"\x00" * 16
PDF = b"%PDF-1.7\n" + b"\x00" * 16


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (PNG, "image/png"),
        (JPEG, "image/jpeg"),
        (GIF87, "image/gif"),
        (GIF89, "image/gif"),
        (WEBP, "image/webp"),
        (PDF, "application/pdf"),
    ],
)
def test_sniff_known_signatures(data: bytes, expected: str) -> None:
    assert sniff(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        b"",  # empty
        b"PK\x03\x04" + b"\x00" * 16,  # zip — not allowlisted
        b"<svg xmlns='http://www.w3.org/2000/svg'/>",  # svg — script risk, excluded
        b"MZ\x90\x00" + b"\x00" * 16,  # PE executable
        b"just some text",
        b"\x89PN",  # truncated png header
        b"RIFF\x24\x00\x00\x00WAVE",  # riff but not webp
    ],
)
def test_sniff_rejects_unknown_or_spoofed(data: bytes) -> None:
    assert sniff(data) is None


def test_image_types_cover_exactly_the_image_signatures() -> None:
    assert IMAGE_TYPES == frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
