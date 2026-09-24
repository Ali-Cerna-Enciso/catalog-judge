from __future__ import annotations

import json
from pathlib import Path

from catalog_judge.cli import main


def test_doctor_is_offline_and_does_not_print_key(capsys, monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "unit-test-secret")
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "unit-test-secret" not in output
    assert "typesafe_sdk" in output


def test_demo_uses_new_public_samples(capsys, tmp_path: Path) -> None:
    assert main(["demo", "--limit", "1", "--workers", "1", "--output", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert "política de código" in captured.err
    assert '"rows": 1' in captured.out
    assert (tmp_path / "retail.csv").exists()
    assert (tmp_path / "tickets.csv").exists()


def test_ticket_ambiguous_noul_cli_default_is_085() -> None:
    from catalog_judge.cli import build_parser
    from catalog_judge.routing import DEFAULT_THRESHOLDS

    args = build_parser().parse_args(["tickets", "--input", "tickets/data/tickets_100.csv"])
    assert args.ticket_ambiguous_noul == 0.85
    assert args.ticket_ambiguous_noul == DEFAULT_THRESHOLDS.ticket_ambiguous_noul


def test_retail_cli_mock(tmp_path: Path, retail_sample: Path, capsys) -> None:
    output = tmp_path / "retail.json"
    assert main(["retail", "--input", str(retail_sample), "--mode", "mock", "--limit", "2", "--workers", "2", "--output", str(output)]) == 0
    assert output.exists()
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["summary"]["valid_responses"] == 2
    assert payload["summary"]["contract_coverage"] == 1.0
