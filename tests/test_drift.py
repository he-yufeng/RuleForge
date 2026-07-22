"""Tests for drift detection (ruleforge check)."""

import textwrap

from click.testing import CliRunner

from ruleforge.cli import main
from ruleforge.drift import check_drift


def _write_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [build-system]
            requires = ["hatchling"]
            build-backend = "hatchling.build"

            [project]
            name = "sample"
            version = "0.1.0"

            [tool.ruff]

            [tool.pytest.ini_options]
            """
        )
    )
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "app.py").write_text("print('hi')\n")


_CLEAN_RULES = (
    "# sample\n\nPython project. Install with hatch, run pytest and ruff before committing.\n"
)


def test_check_clean_rules_have_no_findings(tmp_path):
    _write_pyproject(tmp_path)
    (tmp_path / "AGENTS.md").write_text(_CLEAN_RULES)
    report = check_drift(tmp_path)
    assert report.findings == []
    assert not report.drifted


def test_check_flags_missing_test_framework_and_pm(tmp_path):
    _write_pyproject(tmp_path)
    (tmp_path / "AGENTS.md").write_text("# sample\n\nA Python project.\n")
    report = check_drift(tmp_path)

    rule_ids = {f.rule_id for f in report.findings}
    assert "test-framework-drift" in rule_ids
    assert "package-manager-drift" in rule_ids
    assert "linter-drift" in rule_ids
    assert report.drifted


def test_check_reports_missing_rule_file(tmp_path):
    _write_pyproject(tmp_path)
    report = check_drift(tmp_path)

    assert [f.rule_id for f in report.findings] == ["missing-rules"]
    assert report.drifted


def test_check_explicit_file_option(tmp_path):
    _write_pyproject(tmp_path)
    custom = tmp_path / "TEAM.md"
    custom.write_text("Python, hatch, pytest, ruff.\n")
    report = check_drift(tmp_path, rule_file=custom)

    assert report.findings == []
    assert report.rule_file == custom


def test_cli_check_exit_codes(tmp_path):
    _write_pyproject(tmp_path)
    (tmp_path / "AGENTS.md").write_text("# sample\n\nA Python project.\n")

    result = CliRunner().invoke(main, ["check", str(tmp_path)])
    assert result.exit_code == 1
    assert "test-framework-drift" in result.output

    (tmp_path / "AGENTS.md").write_text(_CLEAN_RULES)
    result = CliRunner().invoke(main, ["check", str(tmp_path)])
    assert result.exit_code == 0
    assert "up to date" in result.output


def test_cli_check_json_output(tmp_path):
    import json

    _write_pyproject(tmp_path)
    (tmp_path / "AGENTS.md").write_text("# sample\n\nA Python project.\n")

    result = CliRunner().invoke(main, ["check", str(tmp_path), "--format", "json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["drifted"] is True
    assert any(f["rule_id"] == "test-framework-drift" for f in payload["findings"])
