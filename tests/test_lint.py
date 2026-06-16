import json
import textwrap

from click.testing import CliRunner

from ruleforge.cli import main
from ruleforge.lint import lint_rules


def _write_pyproject(tmp_path, build_backend="hatchling.build", extra=""):
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""\
            [build-system]
            requires = ["hatchling"]
            build-backend = "{build_backend}"

            [project]
            name = "sample"
            version = "0.1.0"
            {extra}
            """
        )
    )


def test_lint_clean_rules_have_no_findings(tmp_path):
    _write_pyproject(tmp_path)
    (tmp_path / "AGENTS.md").write_text(
        "# sample\n\nPython project. Run pytest and ruff before committing.\n"
    )
    report = lint_rules(tmp_path)
    assert report.findings == []
    assert report.errors == []


def test_lint_flags_placeholder_with_line_number(tmp_path):
    (tmp_path / "AGENTS.md").write_text(
        textwrap.dedent(
            """\
            # sample

            This project does TODO.
            Run the tests with `<your test command here>`.
            Deploy target: {{ environment }}.
            """
        )
    )
    report = lint_rules(tmp_path)
    placeholders = [f for f in report.findings if f.rule_id == "placeholder"]
    assert len(placeholders) == 3
    assert all(f.severity == "error" for f in placeholders)
    todo = next(f for f in placeholders if "TODO" in f.message)
    assert todo.line == 3
    assert todo.file == "AGENTS.md"


def test_lint_ignores_html_and_generics_in_angle_brackets(tmp_path):
    (tmp_path / "AGENTS.md").write_text(
        textwrap.dedent(
            """\
            # sample

            <details><summary>Notes</summary></details>
            Helpers return `Result<String>` values.
            """
        )
    )
    report = lint_rules(tmp_path)
    assert [f for f in report.findings if f.rule_id == "placeholder"] == []


def test_lint_detects_conflicting_package_managers(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "sample"}\n')
    (tmp_path / "index.js").write_text("console.log(1)\n")
    (tmp_path / "AGENTS.md").write_text(
        "# sample\n\nInstall deps with npm. Some scripts still use yarn.\n"
    )
    report = lint_rules(tmp_path)
    conflicts = [f for f in report.findings if f.rule_id == "package-manager-conflict"]
    assert len(conflicts) == 1
    assert conflicts[0].severity == "warning"
    assert "npm" in conflicts[0].message and "yarn" in conflicts[0].message


def test_lint_detects_stale_package_manager(tmp_path):
    # Lock file makes the detected package manager pnpm.
    (tmp_path / "package.json").write_text('{"name": "sample"}\n')
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    (tmp_path / "index.js").write_text("console.log(1)\n")
    (tmp_path / "AGENTS.md").write_text("# sample\n\nRun `yarn install` to set up.\n")
    report = lint_rules(tmp_path)
    stale = [f for f in report.findings if f.rule_id == "package-manager-stale"]
    assert len(stale) == 1
    assert "yarn" in stale[0].message
    assert "pnpm" in stale[0].message


def test_lint_detects_stale_test_framework(tmp_path):
    # pytest is detected from pyproject, but the rules still point at unittest.
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [build-system]
            requires = ["hatchling"]
            build-backend = "hatchling.build"

            [project]
            name = "sample"
            version = "0.1.0"

            [tool.pytest.ini_options]
            testpaths = ["tests"]
            """
        )
    )
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "AGENTS.md").write_text("# sample\n\nWrite tests with unittest.\n")
    report = lint_rules(tmp_path)
    stale = [f for f in report.findings if f.rule_id == "test-framework-stale"]
    assert len(stale) == 1
    assert "unittest" in stale[0].message
    assert "pytest" in stale[0].message


def test_lint_allows_cross_ecosystem_test_frameworks(tmp_path):
    # A polyglot repo may legitimately run both pytest and jest; do not flag that.
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [build-system]
            requires = ["hatchling"]
            build-backend = "hatchling.build"

            [project]
            name = "sample"
            version = "0.1.0"

            [tool.pytest.ini_options]
            testpaths = ["tests"]
            """
        )
    )
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "AGENTS.md").write_text(
        "# sample\n\nRun pytest for Python and jest for the web client.\n"
    )
    report = lint_rules(tmp_path)
    assert [f for f in report.findings if f.rule_id.startswith("test-framework")] == []


def test_lint_json_cli_and_exit_code(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# sample\n\nThis project does TODO.\n")
    result = CliRunner().invoke(main, ["lint", str(tmp_path), "--format", "json"])
    # A placeholder is an error, so the command exits non-zero.
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["error_count"] == 1
    assert data["findings"][0]["rule_id"] == "placeholder"


def test_lint_clean_cli_exits_zero(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# sample\n\nA tidy rule file with no problems.\n")
    result = CliRunner().invoke(main, ["lint", str(tmp_path)])
    assert result.exit_code == 0
    assert "No problems found." in result.output


def test_lint_strict_treats_warnings_as_errors(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "sample"}\n')
    (tmp_path / "index.js").write_text("console.log(1)\n")
    (tmp_path / "AGENTS.md").write_text("# sample\n\nUse npm or pnpm, your call.\n")
    runner = CliRunner()

    relaxed = runner.invoke(main, ["lint", str(tmp_path)])
    assert relaxed.exit_code == 0  # only a warning

    strict = runner.invoke(main, ["lint", str(tmp_path), "--strict"])
    assert strict.exit_code == 1
