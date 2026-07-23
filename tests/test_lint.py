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


def test_lint_reads_cline_rules_file(tmp_path):
    # .clinerules is a generated format, so lint must discover and read it
    _write_pyproject(tmp_path)
    (tmp_path / ".clinerules").write_text("# sample\n\nPython project. Run pytest and ruff.\n")
    report = lint_rules(tmp_path)
    assert any(p.name == ".clinerules" for p in report.files)


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


def test_lint_detects_stale_formatter(tmp_path):
    # [tool.ruff] makes ruff the detected formatter, but the rules still tell the
    # assistant to format with black.
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
            line-length = 100
            """
        )
    )
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "AGENTS.md").write_text("# sample\n\nFormat code with black before committing.\n")
    report = lint_rules(tmp_path)
    stale = [f for f in report.findings if f.rule_id == "formatter-stale"]
    assert len(stale) == 1
    assert "black" in stale[0].message
    assert "ruff" in stale[0].message


def test_lint_detects_conflicting_linters(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "AGENTS.md").write_text(
        "# sample\n\nLint with ruff. Older docs still mention flake8.\n"
    )
    report = lint_rules(tmp_path)
    conflicts = [f for f in report.findings if f.rule_id == "linter-conflict"]
    assert len(conflicts) == 1
    assert "ruff" in conflicts[0].message and "flake8" in conflicts[0].message


def test_lint_allows_cross_ecosystem_linters(tmp_path):
    # Python ruff and JS eslint belong to different ecosystems; not a conflict.
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
            line-length = 100
            """
        )
    )
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "package.json").write_text('{"name": "sample"}\n')
    (tmp_path / "index.js").write_text("console.log(1)\n")
    (tmp_path / "AGENTS.md").write_text(
        "# sample\n\nLint Python with ruff and the web client with eslint.\n"
    )
    report = lint_rules(tmp_path)
    assert [f for f in report.findings if f.rule_id.startswith("linter")] == []


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


def test_lint_flags_framework_from_wrong_stack(tmp_path):
    # repo uses Flask; rules that still talk about Django are stale
    _write_pyproject(tmp_path, extra='dependencies = ["flask>=2.0"]')
    (tmp_path / "app.py").write_text("import flask\n\napp = flask.Flask(__name__)\n")
    (tmp_path / "AGENTS.md").write_text(
        "# sample\n\nBuild the Django models, then run pytest and ruff.\n"
    )
    report = lint_rules(tmp_path)
    stale = [f for f in report.findings if f.rule_id == "framework-stale"]
    assert len(stale) == 1
    assert "django" in stale[0].message.lower()
    assert "Flask" in stale[0].message


def test_lint_does_not_flag_framework_in_use(tmp_path):
    # rules mention the same framework the repo actually uses -> no false positive
    _write_pyproject(tmp_path, extra='dependencies = ["flask>=2.0"]')
    (tmp_path / "app.py").write_text("import flask\n\napp = flask.Flask(__name__)\n")
    (tmp_path / "AGENTS.md").write_text(
        "# sample\n\nFlask app. Run pytest and ruff before committing.\n"
    )
    report = lint_rules(tmp_path)
    assert [f for f in report.findings if f.rule_id == "framework-stale"] == []


def _write_package_json(tmp_path, scripts=None):
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "sample", "version": "1.0.0", "scripts": scripts or {}})
    )


def test_lint_flags_phantom_npm_script(tmp_path):
    _write_pyproject(tmp_path)
    _write_package_json(tmp_path, {"test": "vitest run", "build": "tsc"})
    (tmp_path / "AGENTS.md").write_text(
        "# sample\n\nRun `npm run buidl` to compile, then `npm run build`.\n"
    )
    report = lint_rules(tmp_path)
    phantom = [f for f in report.findings if f.rule_id == "phantom-command"]
    assert len(phantom) == 1
    assert "buidl" in phantom[0].message
    assert phantom[0].file == "AGENTS.md"


def test_lint_npm_builtins_and_declared_scripts_are_clean(tmp_path):
    _write_pyproject(tmp_path)
    _write_package_json(tmp_path, {"test": "vitest run", "build": "tsc"})
    (tmp_path / "AGENTS.md").write_text(
        "# sample\n\nUse `npm install`, `npm test`, and `npm run build`.\n"
    )
    report = lint_rules(tmp_path)
    assert [f for f in report.findings if f.rule_id == "phantom-command"] == []


def test_lint_flags_phantom_make_target(tmp_path):
    _write_pyproject(tmp_path)
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n\nbuild:\n\techo ok\n")
    (tmp_path / "AGENTS.md").write_text("# sample\n\nVerify with `make tes`.\n")
    report = lint_rules(tmp_path)
    phantom = [f for f in report.findings if f.rule_id == "phantom-command"]
    assert len(phantom) == 1
    assert "make tes" in phantom[0].message


def test_lint_make_declared_targets_are_clean(tmp_path):
    _write_pyproject(tmp_path)
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n")
    (tmp_path / "AGENTS.md").write_text("# sample\n\nVerify with `make test`.\n")
    report = lint_rules(tmp_path)
    assert [f for f in report.findings if f.rule_id == "phantom-command"] == []


def test_lint_phantom_check_skips_without_ground_truth(tmp_path):
    _write_pyproject(tmp_path)
    (tmp_path / "AGENTS.md").write_text("# sample\n\nRun `npm run buidl` then `make tes`.\n")
    report = lint_rules(tmp_path)
    assert [f for f in report.findings if f.rule_id == "phantom-command"] == []


def test_lint_monorepo_subpackage_script_counts(tmp_path):
    _write_pyproject(tmp_path)
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "package.json").write_text(
        json.dumps({"name": "web", "scripts": {"dev": "vite"}})
    )
    (tmp_path / "AGENTS.md").write_text("# sample\n\nStart with `npm run dev`.\n")
    report = lint_rules(tmp_path)
    assert [f for f in report.findings if f.rule_id == "phantom-command"] == []
