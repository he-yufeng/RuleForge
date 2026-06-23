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

        [project.scripts]
        myapp = "myapp.cli:main"

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


def test_generate_gemini_format(py_project):
    profile = analyze_project(py_project)
    rules = generate_rules(profile, ["gemini"])
    assert len(rules) == 1
    assert rules[0].format == "gemini"
    assert rules[0].filename == "GEMINI.md"
    # Gemini CLI uses the canonical project doc, same content as CLAUDE.md
    claude = generate_rules(profile, ["claude"])[0].content
    assert rules[0].content == claude
    assert rules[0].content.strip()


def test_generate_zed_format(py_project):
    profile = analyze_project(py_project)
    rules = generate_rules(profile, ["zed"])
    assert len(rules) == 1
    assert rules[0].format == "zed"
    # Zed reads a project-root ".rules" file.
    assert rules[0].filename == ".rules"
    # Plain rules document with a "Rules for ..." heading, like the other dotfiles.
    assert rules[0].content.startswith(f"# Rules for {profile.root.name}")
    assert rules[0].content.strip()


def test_generate_aider_format(py_project):
    profile = analyze_project(py_project)
    rules = generate_rules(profile, ["aider"])
    assert len(rules) == 1
    assert rules[0].format == "aider"
    # Aider reads a project CONVENTIONS.md.
    assert rules[0].filename == "CONVENTIONS.md"
    # Canonical project doc, same content as CLAUDE.md (tool-agnostic conventions).
    assert rules[0].content == generate_rules(profile, ["claude"])[0].content
    assert rules[0].content.strip()


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


def test_generated_rules_include_project_commands(py_project):
    (py_project / "package.json").write_text(
        '{"scripts": {"test": "vitest run", "lint": "eslint .", "dev": "vite"}}',
        encoding="utf-8",
    )
    (py_project / "package-lock.json").write_text("{}", encoding="utf-8")
    (py_project / "src" / "app.ts").write_text("export const answer = 42;\n", encoding="utf-8")

    profile = analyze_project(py_project)
    rules = generate_rules(profile, ["claude"])

    content = rules[0].content
    assert "Project Commands" in content
    assert "`npm run test`: `vitest run`" in content
    assert "`npm run lint`: `eslint .`" in content
    assert "`myapp` -> `myapp.cli:main`" in content


def test_generated_rules_include_ci_commands(py_project):
    (py_project / ".github" / "workflows" / "ci.yml").write_text(
        "jobs:\n  test:\n    steps:\n      - run: pytest -q\n",
        encoding="utf-8",
    )

    profile = analyze_project(py_project)
    content = generate_rules(profile, ["claude"])[0].content

    assert "Commands observed in CI" in content
    assert "`pytest -q`" in content


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


def test_generate_new_assistant_formats(py_project):
    profile = analyze_project(py_project)
    rules = generate_rules(profile, ["agents", "windsurf", "cline"])
    by_format = {r.format: r.filename for r in rules}
    assert by_format == {
        "agents": "AGENTS.md",
        "windsurf": ".windsurfrules",
        "cline": ".clinerules",
    }


def test_new_formats_carry_detected_stack(py_project):
    profile = analyze_project(py_project)
    for rule in generate_rules(profile, ["agents", "windsurf", "cline"]):
        assert "Flask" in rule.content
        assert "pytest" in rule.content.lower()


def test_agents_md_matches_neutral_document(py_project):
    profile = analyze_project(py_project)
    agents = generate_rules(profile, ["agents"])[0].content
    claude = generate_rules(profile, ["claude"])[0].content
    # AGENTS.md is the canonical tool-agnostic document.
    assert agents == claude


def test_windsurf_and_cline_use_rules_header(py_project):
    profile = analyze_project(py_project)
    rules = {r.format: r.content for r in generate_rules(profile, ["windsurf", "cline"])}
    assert rules["windsurf"].startswith("# Rules for ")
    assert rules["cline"].startswith("# Rules for ")
