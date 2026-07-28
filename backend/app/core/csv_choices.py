"""CSV → choice-value parsing for template choice sections (WP3 S12, #82).

v1 resolves the G-4 doc gap by importing choice values from CSV only:
``choice_config.catalog_binding`` stays opaque metadata and is never
interpreted here. The expected shape is a UTF-8 CSV with a ``code,label``
header (case-insensitive; extra columns ignored). Every malformed input is
rejected with ``CsvChoiceError`` — the route maps it to a 422.
"""

import csv
import io

CSV_MAX_BYTES = 1024 * 1024  # 1 MiB — a value list, not a data lake

_REQUIRED_COLUMNS = ("code", "label")


class CsvChoiceError(ValueError):
    """Raised for any malformed choice-value CSV; message is user-facing."""


def parse_choice_csv(data: bytes) -> list[tuple[str, str]]:
    """Parse ``data`` into ordered ``(code, label)`` rows.

    An empty label falls back to the code so imports from bare code lists work.
    """
    if len(data) > CSV_MAX_BYTES:
        raise CsvChoiceError("CSV file too large")
    try:
        text = data.decode("utf-8-sig")  # tolerate a BOM from spreadsheet exports
    except UnicodeDecodeError as exc:
        raise CsvChoiceError("CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = [name.strip().lower() for name in (reader.fieldnames or [])]
    if any(col not in fieldnames for col in _REQUIRED_COLUMNS):
        raise CsvChoiceError("CSV header must contain 'code' and 'label' columns")

    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for record in reader:
        normalized = {(k or "").strip().lower(): (v or "").strip() for k, v in record.items() if k is not None}
        if not any(normalized.values()):
            continue  # blank line
        code = normalized.get("code", "")
        if not code:
            raise CsvChoiceError(f"empty code in row {reader.line_num}")
        if code in seen:
            raise CsvChoiceError(f"duplicate code {code!r} in row {reader.line_num}")
        seen.add(code)
        rows.append((code, normalized.get("label", "") or code))

    if not rows:
        raise CsvChoiceError("CSV contains no data rows")
    return rows
