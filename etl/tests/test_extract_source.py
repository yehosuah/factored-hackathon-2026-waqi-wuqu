"""Fake transport fixtures never contact AWS or use real credentials."""

import base64
import hashlib
import io
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, ResponseStreamingError

from factored_bank.extract.errors import ExtractError
from factored_bank.extract.source import S3Source

WHEN = datetime(2026, 1, 1, tzinfo=UTC)
BODY = b"team,fixture\noriginal,bytes\n"
OBJ = {
    "key": "data/products.csv",
    "size": len(BODY),
    "etag": '"opaque-etag"',
    "last_modified": WHEN.isoformat(),
}


def metadata(**extra):
    return {"ContentLength": len(BODY), "ETag": OBJ["etag"], "LastModified": WHEN, **extra}


def source(extra=None):
    client = Mock()
    client.head_object.return_value = metadata(**(extra or {}))
    client.get_object.side_effect = lambda **_: metadata(Body=io.BytesIO(BODY), **(extra or {}))
    result = S3Source(client=client)
    result._backoff = Mock()
    return result, client


def aws_error(code, status):
    return ClientError(
        {
            "Error": {"Code": code, "Message": "SECRET SHOULD NEVER APPEAR"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "FixtureOperation",
    )


def test_complete_pagination_and_prefix():
    s, client = source()
    entry = {"Key": OBJ["key"], "Size": OBJ["size"], "ETag": OBJ["etag"], "LastModified": WHEN}
    client.list_objects_v2.side_effect = [
        {"Contents": [], "IsTruncated": True, "NextContinuationToken": "page-2"},
        {"Contents": [entry], "IsTruncated": False},
    ]
    assert s.list_objects() == [OBJ]
    assert client.list_objects_v2.call_args.kwargs["ContinuationToken"] == "page-2"
    assert client.list_objects_v2.call_args.kwargs["Prefix"] == "data/"


def test_conditional_exact_byte_download_private_permissions(tmp_path):
    s, client = source()
    target = tmp_path / "download.part"
    result = s.download(OBJ, target)
    assert target.read_bytes() == BODY
    assert target.stat().st_mode & 0o777 == 0o600
    assert result["sha256"] == hashlib.sha256(BODY).hexdigest()
    assert result["remote_checksum"]["status"] == "unavailable"
    assert client.get_object.call_args.kwargs["IfMatch"] == OBJ["etag"]
    assert client.get_object.call_args.kwargs["ChecksumMode"] == "ENABLED"


def test_full_object_checksum_and_version(tmp_path):
    digest = base64.b64encode(hashlib.sha256(BODY).digest()).decode()
    s, _ = source({"ChecksumSHA256": digest, "ChecksumType": "FULL_OBJECT", "VersionId": "v1"})
    result = s.download(OBJ, tmp_path / "part")
    assert result["version_id"] == "v1"
    assert result["remote_checksum"]["validated_algorithms"] == ["SHA256"]


def test_checksum_mismatch(tmp_path):
    s, _ = source({"ChecksumSHA256": "wrong", "ChecksumType": "FULL_OBJECT"})
    with pytest.raises(ExtractError) as error:
        s.download(OBJ, tmp_path / "part")
    assert error.value.code == "remote_checksum_mismatch"


def test_composite_checksum_not_mistaken_for_whole_file(tmp_path):
    s, _ = source({"ChecksumSHA256": "composite-2", "ChecksumType": "COMPOSITE"})
    assert s.download(OBJ, tmp_path / "part")["remote_checksum"]["status"] == "unsupported"


@pytest.mark.parametrize(
    ("code", "status", "expected", "exit_code"),
    [
        ("AccessDenied", 403, "source_access_denied", 4),
        ("PreconditionFailed", 412, "source_changed", 3),
        ("NoSuchKey", 404, "source_changed", 3),
    ],
)
def test_terminal_failure_no_retry_or_secret(tmp_path, code, status, expected, exit_code):
    s, client = source()
    client.get_object.side_effect = aws_error(code, status)
    with pytest.raises(ExtractError) as error:
        s.download(OBJ, tmp_path / "part")
    assert error.value.code == expected
    assert error.value.exit_code == exit_code
    assert "SECRET" not in str(error.value)
    assert client.get_object.call_count == 1


def test_stream_retry_restarts_entire_file(tmp_path):
    s, client = source()
    broken = Mock()
    broken.read.side_effect = [BODY[:5], ResponseStreamingError(error="private data")]
    client.get_object.side_effect = [metadata(Body=broken), metadata(Body=io.BytesIO(BODY))]
    target = tmp_path / "part"
    result = s.download(OBJ, target)
    assert target.read_bytes() == BODY
    assert result["attempts"] == 2
    assert result["transferred_bytes"] == len(BODY) + 5
    assert broken.close.call_count == 1
    assert [c.kwargs["IfMatch"] for c in client.get_object.call_args_list] == [OBJ["etag"]] * 2


def test_three_attempt_limit(tmp_path):
    s, client = source()
    client.head_object.side_effect = aws_error("SlowDown", 503)
    with pytest.raises(ExtractError) as error:
        s.download(OBJ, tmp_path / "part")
    assert error.value.details == {"attempts": 3, "transferred_bytes": 0}
    assert client.head_object.call_count == 3
    assert s._backoff.call_count == 2


def test_metadata_conflict_holds_without_get(tmp_path):
    s, client = source()
    client.head_object.return_value = metadata(ETag='"changed"')
    with pytest.raises(ExtractError) as error:
        s.download(OBJ, tmp_path / "part")
    assert error.value.code == "source_changed"
    assert client.get_object.call_count == 0


def test_symlink_is_not_overwritten(tmp_path):
    s, _ = source()
    victim = tmp_path / "victim"
    victim.write_bytes(b"keep")
    target = tmp_path / "part"
    target.symlink_to(victim)
    with pytest.raises(ExtractError):
        s.download(OBJ, target)
    assert victim.read_bytes() == b"keep"


def test_repeated_pagination_token_is_rejected():
    s, client = source()
    client.list_objects_v2.return_value = {
        "IsTruncated": True,
        "NextContinuationToken": "same-token",
    }
    with pytest.raises(ExtractError) as error:
        s.list_objects()
    assert error.value.code == "source_invalid_pagination"
    assert client.list_objects_v2.call_count == 2


def test_get_metadata_conflict_does_not_leave_open_stream(tmp_path):
    s, client = source()
    stream = io.BytesIO(BODY)
    client.get_object.side_effect = None
    client.get_object.return_value = metadata(Body=stream, ETag='"new-identity"')
    with pytest.raises(ExtractError) as error:
        s.download(OBJ, tmp_path / "part")
    assert error.value.code == "source_changed"
    assert stream.closed
    assert not (tmp_path / "part").exists()


def test_crc32_checksum_supported(tmp_path):
    import zlib

    digest = base64.b64encode(zlib.crc32(BODY).to_bytes(4, "big")).decode()
    s, _ = source({"ChecksumCRC32": digest, "ChecksumType": "FULL_OBJECT"})
    assert s.download(OBJ, tmp_path / "part")["remote_checksum"]["status"] == "validated"


def test_failed_stream_accounts_for_received_payload_across_attempts(tmp_path):
    s, client = source()
    streams = []
    for _ in range(3):
        broken = Mock()
        broken.read.side_effect = [BODY[:5], ResponseStreamingError(error="private data")]
        streams.append(metadata(Body=broken))
    client.get_object.side_effect = streams
    with pytest.raises(ExtractError) as error:
        s.download(OBJ, tmp_path / "part")
    assert error.value.details == {"attempts": 3, "transferred_bytes": 15}
    assert "private data" not in str(error.value)


def test_checksum_failure_accounts_for_all_received_payload(tmp_path):
    s, _ = source({"ChecksumSHA256": "wrong", "ChecksumType": "FULL_OBJECT"})
    with pytest.raises(ExtractError) as error:
        s.download(OBJ, tmp_path / "part")
    assert error.value.details == {"attempts": 1, "transferred_bytes": len(BODY)}
