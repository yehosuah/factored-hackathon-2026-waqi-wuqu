"""Read-only S3 transport with bounded retries and planned-identity reads."""

import base64
import hashlib
import os
import random
import time
import zlib
from datetime import UTC, datetime
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    FlexibleChecksumError,
    IncompleteReadError,
    ReadTimeoutError,
    ResponseStreamingError,
)

from .errors import ExtractError

DEFAULT_BUCKET = "factored-datathon-2026-s3-157725502942-us-east-2-an"
_TRANSIENT = (
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    IncompleteReadError,
    ReadTimeoutError,
    ResponseStreamingError,
)
_RETRY_CODES = {
    "SlowDown",
    "Throttling",
    "ThrottlingException",
    "RequestTimeout",
    "InternalError",
    "InternalFailure",
    "ServiceUnavailable",
}
_CHECKSUM_NAMES = ("SHA256", "SHA1", "CRC32", "CRC32C", "CRC64NVME")


def _iso(value) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def _failure(exc: Exception) -> tuple[ExtractError, bool]:
    if isinstance(exc, FlexibleChecksumError):
        return ExtractError("remote_checksum_mismatch"), False
    if isinstance(exc, ClientError):
        response = exc.response
        code = response.get("Error", {}).get("Code", "")
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        if code in {"PreconditionFailed", "NoSuchKey", "NotFound", "404", "412"}:
            return ExtractError("source_changed", exit_code=3), False
        if code in {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "ExpiredToken"}:
            return ExtractError("source_access_denied"), False
        if status >= 500 or status == 429 or code in _RETRY_CODES:
            return ExtractError("source_transient_failure"), True
        return ExtractError("source_request_failed"), False
    if isinstance(exc, _TRANSIENT):
        return ExtractError("source_transport_failed"), True
    if isinstance(exc, BotoCoreError):
        return ExtractError("source_configuration", exit_code=2), False
    return ExtractError("source_transport_failed"), False


class S3Source:
    """SDK retries are disabled; each application transport operation has three attempts."""

    def __init__(
        self,
        bucket=DEFAULT_BUCKET,
        prefix="data/",
        region="us-east-2",
        profile=None,
        client=None,
    ):
        if not all(isinstance(v, str) and v for v in (bucket, prefix, region)):
            raise ExtractError("invalid_source_configuration", exit_code=2)
        if not prefix.endswith("/"):
            raise ExtractError("invalid_source_configuration", exit_code=2)
        self.bucket, self.prefix, self.region = bucket, prefix, region
        if client is not None:
            self.client = client
        else:
            try:
                session = boto3.Session(profile_name=profile, region_name=region)
                self.client = session.client(
                    "s3",
                    config=Config(
                        connect_timeout=10,
                        read_timeout=60,
                        retries={"total_max_attempts": 1, "mode": "standard"},
                    ),
                )
            except BotoCoreError:
                raise ExtractError("source_configuration", exit_code=2) from None

    @property
    def descriptor(self):
        return {"kind": "s3", "bucket": self.bucket, "prefix": self.prefix, "region": self.region}

    @staticmethod
    def _backoff(attempt):
        time.sleep(random.uniform(0, min(20, 2**attempt)))

    def _request(self, method, **kwargs):
        for attempt in range(1, 4):
            try:
                return getattr(self.client, method)(**kwargs)
            except (BotoCoreError, ClientError) as exc:
                failure, retry = _failure(exc)
                if not retry or attempt == 3:
                    raise failure from None
                self._backoff(attempt)
        raise AssertionError("unreachable")

    def list_objects(self) -> list[dict]:
        objects, token, seen = [], None, set()
        while True:
            request = {"Bucket": self.bucket, "Prefix": self.prefix}
            if token is not None:
                request["ContinuationToken"] = token
            response = self._request("list_objects_v2", **request)
            for obj in response.get("Contents", []):
                objects.append(
                    {
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "etag": obj["ETag"],
                        "last_modified": _iso(obj["LastModified"]),
                    }
                )
            if not response.get("IsTruncated", False):
                return sorted(objects, key=lambda entry: entry["key"])
            token = response.get("NextContinuationToken")
            if not token or token in seen:
                raise ExtractError("source_invalid_pagination")
            seen.add(token)

    @staticmethod
    def _check_identity(response, obj):
        if (
            response.get("ContentLength") != obj["size"]
            or response.get("ETag") != obj["etag"]
            or _iso(response.get("LastModified")) != obj["last_modified"]
        ):
            raise ExtractError("source_changed", exit_code=3)

    def download(self, obj: dict, destination: Path) -> dict:
        """Stream exactly the planned object; retry interrupted streams from byte zero."""
        if not isinstance(obj.get("key"), str) or not obj["key"].startswith(self.prefix):
            raise ExtractError(
                "invalid_source_object",
                exit_code=2,
                details={"attempts": 0, "transferred_bytes": 0},
            )
        transferred_bytes = 0
        for attempt in range(1, 4):
            body = None
            try:
                head = self.client.head_object(
                    Bucket=self.bucket,
                    Key=obj["key"],
                    ChecksumMode="ENABLED",
                )
                self._check_identity(head, obj)
                response = self.client.get_object(
                    Bucket=self.bucket,
                    Key=obj["key"],
                    IfMatch=obj["etag"],
                    ChecksumMode="ENABLED",
                )
                body = response["Body"]
                self._check_identity(response, obj)
                if (
                    head.get("VersionId")
                    and response.get("VersionId")
                    and head["VersionId"] != response["VersionId"]
                ):
                    raise ExtractError("source_changed", exit_code=3)
                sha256, sha1, crc32, size = hashlib.sha256(), hashlib.sha1(), 0, 0
                flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
                fd = os.open(destination, flags, 0o600)
                with os.fdopen(fd, "wb") as output:
                    os.fchmod(output.fileno(), 0o600)
                    while chunk := body.read(1024 * 1024):
                        # Count received payload before writing, including failed attempts.
                        transferred_bytes += len(chunk)
                        output.write(chunk)
                        sha256.update(chunk)
                        sha1.update(chunk)
                        crc32 = zlib.crc32(chunk, crc32)
                        size += len(chunk)
                        if size > obj["size"]:
                            raise ExtractError("source_size_mismatch")
                    output.flush()
                    os.fsync(output.fileno())
                if size != obj["size"]:
                    raise ExtractError("source_size_mismatch")
                calculated = {
                    "SHA256": base64.b64encode(sha256.digest()).decode("ascii"),
                    "SHA1": base64.b64encode(sha1.digest()).decode("ascii"),
                    "CRC32": base64.b64encode(crc32.to_bytes(4, "big")).decode("ascii"),
                }
                checksum = _remote_checksum(head, response, calculated)
                return {
                    "sha256": sha256.hexdigest(),
                    "size": size,
                    "version_id": response.get("VersionId"),
                    "remote_checksum": checksum,
                    "attempts": attempt,
                    "transferred_bytes": transferred_bytes,
                }
            except ExtractError as exc:
                exc.details.update(attempts=attempt, transferred_bytes=transferred_bytes)
                raise
            except (BotoCoreError, ClientError) as exc:
                failure, retry = _failure(exc)
                if not retry or attempt == 3:
                    failure.details.update(attempts=attempt, transferred_bytes=transferred_bytes)
                    raise failure from None
                self._backoff(attempt)
            except OSError:
                raise ExtractError(
                    "download_storage_failed",
                    details={"attempts": attempt, "transferred_bytes": transferred_bytes},
                ) from None
            finally:
                if body is not None:
                    body.close()
        raise AssertionError("unreachable")


def _remote_checksum(head, response, calculated):
    if (
        head.get("ChecksumType") is not None
        and response.get("ChecksumType") is not None
        and head["ChecksumType"] != response["ChecksumType"]
    ):
        raise ExtractError("source_changed", exit_code=3)
    observed = {
        algorithm: response.get("Checksum" + algorithm, head.get("Checksum" + algorithm))
        for algorithm in _CHECKSUM_NAMES
        if response.get("Checksum" + algorithm, head.get("Checksum" + algorithm)) is not None
    }
    checksum_type = response.get("ChecksumType", head.get("ChecksumType"))
    validated, unsupported = [], []
    for algorithm, value in observed.items():
        if head.get("Checksum" + algorithm) not in (None, value):
            raise ExtractError("source_changed", exit_code=3)
        if checksum_type != "FULL_OBJECT" or algorithm not in calculated:
            unsupported.append(algorithm)
        elif calculated[algorithm] != value:
            raise ExtractError("remote_checksum_mismatch")
        else:
            validated.append(algorithm)
    return {
        "status": "validated" if validated else "unsupported" if observed else "unavailable",
        "type": checksum_type,
        "values": observed,
        "validated_algorithms": validated,
        "unsupported_algorithms": unsupported,
    }
