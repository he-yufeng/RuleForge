import json
import textwrap

from click.testing import CliRunner

from ruleforge.audit import audit_project
from ruleforge.cli import main


def test_audit_reports_missing_rule_file(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [build-system]
            requires = ["hatchling"]
            build-backend = "hatchling.build"

            [project]
            name = "sample"
            version = "0.1.0"
            dependencies = ["fastapi"]
            """
        )
    )
    report = audit_project(tmp_path)
    assert report.files == []
    assert report.percentage < 100
    assert any(check.name == "Rule file exists" and not check.passed for check in report.checks)


def test_audit_scores_project_specific_rules(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [build-system]
            requires = ["hatchling"]
            build-backend = "hatchling.build"

            [project]
            name = "sample"
            version = "0.1.0"
            dependencies = ["fastapi"]

            [tool.ruff]
            line-length = 100

            [tool.pytest.ini_options]
            testpaths = ["tests"]
            """
        )
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("from fastapi import FastAPI\n")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: CI\n")
    (tmp_path / "AGENTS.md").write_text(
        textwrap.dedent(
            """\
            # sample

            This repository is a FastAPI Python project managed with hatch.
            Run pytest and ruff before commits. Keep CI green.
            Do not edit generated files, lock files, or secrets such as .env and API keys.
            Use normal git branches, commits, pull requests, and review workflow.
            The assistant should act autonomously but ask when a product decision is unclear.
            """
        )
    )

    report = audit_project(tmp_path)
    assert report.files
    assert report.percentage >= 80


def test_audit_json_cli(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Project rules. Run tests. Never commit secrets.\n")
    result = CliRunner().invoke(main, ["audit", str(tmp_path), "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["score"] <= data["max_score"]
    assert data["files"] == ["AGENTS.md"]


def test_audit_sarif_reports_only_missing_checks(tmp_path):
    (tmp_path / "AGENTS.md").write_text(
        "Project rules. Run tests. Never commit secrets.\n",
        encoding="utf-8",
    )

    report = audit_project(tmp_path)
    data = json.loads(report.to_sarif())
    run = data["runs"][0]

    assert data["version"] == "2.1.0"
    assert run["tool"]["driver"]["name"] == "RuleForge"
    assert len(run["results"]) == len(report.missing)
    assert {result["ruleId"] for result in run["results"]} == {
        rule["id"]
        for rule, check in zip(run["tool"]["driver"]["rules"], report.checks)
        if not check.passed
    }
    assert all(result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "AGENTS.md"
               for result in run["results"])


def test_audit_sarif_cli(tmp_path):
    result = CliRunner().invoke(main, ["audit", str(tmp_path), "--format", "sarif"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["runs"][0]["results"]
