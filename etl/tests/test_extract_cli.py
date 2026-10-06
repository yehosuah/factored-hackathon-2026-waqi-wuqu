"""Operator contract and credential-free offline verification."""

import json

from factored_bank.extract import cli


def test_verify_never_constructs_s3_client(tmp_path, monkeypatch, capsys):
    def forbidden(**kwargs):
        raise AssertionError("offline verification attempted S3")

    monkeypatch.setattr(cli, "S3Source", forbidden)
    code = cli.main(
        ["verify", "--raw-root", str(tmp_path / "raw"), "--output-root", str(tmp_path / "outputs")]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 4
    assert result["status"] == "unavailable"
    assert result["error_code"] == "release_unavailable"


def test_invalid_limits_return_structured_failure(tmp_path, capsys):
    code = cli.main(
        [
            "verify",
            "--workers",
            "0",
            "--raw-root",
            str(tmp_path / "raw"),
            "--output-root",
            str(tmp_path / "outputs"),
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 2
    assert result["error_code"] == "invalid_limits"


def test_invalid_action_combination_does_not_construct_source(monkeypatch, capsys):
    def forbidden(**kwargs):
        raise AssertionError("source not needed for invalid invocation")

    monkeypatch.setattr(cli, "S3Source", forbidden)
    assert cli.main(["plan", "--release-id", "abc"]) == 2
    assert json.loads(capsys.readouterr().out)["error_code"] == "invalid_argument_combination"


def test_invalid_argument_returns_sanitized_json_without_echoing_its_value(monkeypatch, capsys):
    sensitive_sentinel = "invented-team-sensitive-sentinel-not-a-real-secret"

    def forbidden(**kwargs):
        raise AssertionError("Invalid arguments must not construct an S3 client")

    monkeypatch.setattr(cli, "S3Source", forbidden)
    code = cli.main(["run", "--workers", sensitive_sentinel])
    captured = capsys.readouterr()
    assert sensitive_sentinel not in captured.out + captured.err
    result = json.loads(captured.out)
    assert code == 2
    assert result["exit_code"] == 2
    assert result["error_code"] == "invalid_arguments"
