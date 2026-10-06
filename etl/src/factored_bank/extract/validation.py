"""Structural CSV acceptance only: no typing, repairs or business filtering."""

import csv
import re
import threading
from pathlib import Path

from .contracts import HEADERS
from .errors import ExtractError

_FIELD_LIMIT_LOCK = threading.Lock()
_TOKENS = re.compile(r'[^",\r\n]+|\r\n|[",\r\n]')
DEFAULT_FIELD_LIMIT = 16 * 1024 * 1024


def _strict_lines(stream):
    """Reject bare quotes and bare CR that csv.reader(strict=True) tolerates."""
    state = "start"
    for line in stream:
        for match in _TOKENS.finditer(line):
            token = match.group()
            if state == "quoted":
                if token == '"':
                    state = "closed"
                continue
            if state == "closed":
                if token == '"':
                    state = "quoted"
                elif token == ",":
                    state = "start"
                elif token in ("\n", "\r\n"):
                    state = "start"
                else:
                    raise ExtractError("csv_malformed")
            elif token == '"':
                if state != "start":
                    raise ExtractError("csv_malformed")
                state = "quoted"
            elif token in (",", "\n", "\r\n"):
                state = "start"
            elif token == "\r":
                raise ExtractError("csv_record_ending")
            else:
                state = "unquoted"
        yield line


def validate_csv(path: Path, table: str, field_limit: int = DEFAULT_FIELD_LIMIT) -> dict:
    """Return aggregate structural evidence; errors never contain source row values."""
    if table not in HEADERS or type(field_limit) is not int or field_limit < 1:
        raise ExtractError("invalid_csv_configuration", exit_code=2)
    try:
        with path.open("rb") as raw:
            bom = raw.read(3) == b"\xef\xbb\xbf"
        # csv.field_size_limit is process-global. Protect mutation and parsing together.
        with _FIELD_LIMIT_LOCK:
            previous = csv.field_size_limit()
            try:
                csv.field_size_limit(field_limit)
                with path.open("r", encoding="utf-8-sig", errors="strict", newline="") as stream:
                    reader = csv.reader(
                        _strict_lines(stream),
                        delimiter=",",
                        quotechar='"',
                        doublequote=True,
                        escapechar=None,
                        strict=True,
                    )
                    header = next(reader, None)
                    if header is None or header == []:
                        raise ExtractError("csv_missing_header")
                    if header != HEADERS[table]:
                        # An unexpected header can itself contain private values.
                        raise ExtractError("schema_changed", exit_code=3)
                    count = 0
                    for row in reader:
                        if not row:
                            raise ExtractError("csv_blank_record")
                        if len(row) != len(header):
                            raise ExtractError("csv_row_shape")
                        # The CSV parser limits characters; the contract limits UTF-8 bytes.
                        # Short fields cannot exceed the byte limit (at most 4 bytes/character).
                        if any(
                            len(value) > field_limit // 4
                            and len(value.encode("utf-8")) > field_limit
                            for value in row
                        ):
                            raise ExtractError("csv_field_limit")
                        count += 1
            finally:
                csv.field_size_limit(previous)
    except UnicodeDecodeError:
        raise ExtractError("csv_encoding") from None
    except csv.Error as exc:
        code = "csv_field_limit" if "field larger than field limit" in str(exc) else "csv_malformed"
        raise ExtractError(code) from None
    except (OSError, OverflowError):
        raise ExtractError("csv_read_failed") from None
    return {
        "row_count": count,
        "header": header,
        "encoding": "utf-8",
        "bom": bom,
        "dialect": {
            "delimiter": ",",
            "quotechar": '"',
            "doublequote": True,
            "escapechar": None,
            "record_endings": ["LF", "CRLF"],
        },
    }
