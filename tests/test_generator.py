"""Tests for the rule generator."""

import textwrap

import pytest

from ruleforge.analyzer import analyze_project
from ruleforge.generator import generate_rules, write_rules


@pytest.fixture
def py_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent("""\
        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        [project]
        name = "myapp"
        version = "0.1.0"
        requires-python = ">=3.10"
        dependencies = ["flask", "sqlalchemy"]

        [tool.ruff]
        target-version = "py310"

        [tool.pytest.ini_options]
        testpaths = ["tests"]
        """)
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("from flask import Flask\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("import pytest\n")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("")
    (tmp_path / "Dockerfile").write_text("FROM python:3.10\n")
    return tmp_path


def test_generate_all_formats(py_project):
    profile = analyze_project(py_project)
    rules = generate_rules(profile)
    assert len(rules) == 3
    fmts = {r.format for r in rules}
    assert fmts == {"claude", "cursor", "copilot"}


def test_generate_single_format(py_project):
    profile = analyze_project(py_project)
    rules = generate_rules(profile, ["claude"])
    assert len(rules) == 1
    assert rules[0].format == "claude"
    assert rules[0].filename == "CLAUDE.md"


def test_claude_content(py_project):
    profile = analyze_project(py_project)
    rules = generate_rules(profile, ["claude"])
    content = rules[0].content
    assert "Flask" in content
    assert "ruff" in content.lower()
    assert "pytest" in content.lower()
    assert "Docker" in content


def test_generated_rules_reference_existing_rule_files(py_project):
    (py_project / "AGENTS.md").write_text("Repo rules\n", encoding="utf-8")
    profile = analyze_project(py_project)
    rules = generate_rules(profile, ["claude"])

    content = rules[0].content
    assert "Existing Assistant Rules" in content
    assert "`AGENTS.md`" in content
    assert "preserve stricter local instructions" in content


def test_cursor_has_rules_prefix(py_project):
    profile = analyze_project(py_project)
    rules = generate_rules(profile, ["cursor"])
    assert "Rules for" in rules[0].content


def test_copilot_has_instructions_prefix(py_project):
    profile = analyze_project(py_project)
    rules = generate_rules(profile, ["copilot"])
    assert "Copilot Instructions for" in rules[0].content


def test_write_rules_creates_files(py_project):
    profile = analyze_project(py_project)
    rules = generate_rules(profile)
    written = write_rules(rules, py_project, overwrite=True)
    assert len(written) == 3
    assert (py_project / "CLAUDE.md").exists()
    assert (py_project / ".cursorrules").exists()
    assert (py_project / ".github" / "copilot-instructions.md").exists()


def test_write_rules_no_overwrite(py_project):
    profile = analyze_project(py_project)
    rules = generate_rules(profile, ["claude"])

    # write once
    write_rules(rules, py_project)
    assert (py_project / "CLAUDE.md").exists()
    _ = (py_project / "CLAUDE.md").read_text()

    # write again without overwrite - should skip
    (py_project / "CLAUDE.md").write_text("custom stuff")
    write_rules(rules, py_project, overwrite=False)
    assert (py_project / "CLAUDE.md").read_text() == "custom stuff"
