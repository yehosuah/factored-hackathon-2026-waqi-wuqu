"""All records in these tests are deliberately synthetic team fixtures."""

import csv
import io
from concurrent.futures import ThreadPoolExecutor

import pytest

from factored_bank.extract.contracts import HEADERS
from factored_bank.extract.errors import ExtractError
from factored_bank.extract.validation import validate_csv


def fixture_bytes(rows=(), table="products", ending="\n"):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator=ending)
    writer.writerow(HEADERS[table])
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def check(tmp_path, content, **kwargs):
    path = tmp_path / "fixture.csv"
    path.write_bytes(content)
    return validate_csv(path, "products", **kwargs)


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
def test_original_bytes_multiline_empty_values_and_quotes(tmp_path, ending, bom):
    row = ["" for _ in HEADERS["products"]]
    row[0] = 'team fixture, says "hola"\nnext line'
    row[1] = "NULL"
    row[2] = "ñ"
    original = bom + fixture_bytes([row, row], ending=ending)
    result = check(tmp_path, original)
    assert result["row_count"] == 2
    assert result["bom"] is bool(bom)
    assert (tmp_path / "fixture.csv").read_bytes() == original


def test_header_only_valid(tmp_path):
    assert check(tmp_path, fixture_bytes())["row_count"] == 0


@pytest.mark.parametrize("mode", ["add", "remove", "reorder", "rename", "duplicate"])
def test_schema_changes_are_review_required(tmp_path, mode):
    header = HEADERS["products"].copy()
    if mode == "add":
        header.append("extra")
    elif mode == "remove":
        header.pop()
    elif mode == "reorder":
        header.reverse()
    elif mode == "rename":
        header[0] = "renamed"
    else:
        header[1] = header[0]
    with pytest.raises(ExtractError) as error:
        check(tmp_path, (",".join(header) + "\n").encode())
    assert error.value.code == "schema_changed"
    assert error.value.exit_code == 3


@pytest.mark.parametrize(
    ("suffix", "code"),
    [
        (b"\n", "csv_blank_record"),
        (b"x,y\n", "csv_row_shape"),
        (b'"never closed\n', "csv_malformed"),
        (b'"closed"tail\n', "csv_malformed"),
        (b'bare"quote\n', "csv_malformed"),
        (b"\xff\n", "csv_encoding"),
        (b"\r", "csv_record_ending"),
    ],
)
def test_structural_failures_sanitized(tmp_path, suffix, code):
    with pytest.raises(ExtractError) as error:
        check(tmp_path, fixture_bytes() + suffix)
    assert error.value.code == code
    assert "never closed" not in str(error.value)


def test_field_limit_is_named_and_restored(tmp_path):
    previous = csv.field_size_limit()
    row = ["x" * 100] + [""] * (len(HEADERS["products"]) - 1)
    with pytest.raises(ExtractError) as error:
        check(tmp_path, fixture_bytes([row]), field_limit=64)
    assert error.value.code == "csv_field_limit"
    assert csv.field_size_limit() == previous


def test_concurrent_distinct_field_limits(tmp_path):
    path = tmp_path / "fixture.csv"
    row = ["x" * 100] + [""] * (len(HEADERS["products"]) - 1)
    path.write_bytes(fixture_bytes([row]))

    def run(limit):
        try:
            return validate_csv(path, "products", field_limit=limit)["row_count"]
        except ExtractError as exc:
            return exc.code

    with ThreadPoolExecutor(4) as pool:
        assert list(pool.map(run, [64, 128] * 10)) == ["csv_field_limit", 1] * 10


def test_empty_file_rejected(tmp_path):
    with pytest.raises(ExtractError) as error:
        check(tmp_path, b"")
    assert error.value.code == "csv_missing_header"


def test_field_limit_counts_utf8_bytes_not_characters(tmp_path):
    field_limit = max(map(len, HEADERS["products"]))
    value = "ñ" * field_limit
    assert len(value) <= field_limit < len(value.encode("utf-8"))
    row = [value] + [""] * (len(HEADERS["products"]) - 1)
    with pytest.raises(ExtractError) as error:
        check(tmp_path, fixture_bytes([row]), field_limit=field_limit)
    assert error.value.code == "csv_field_limit"
