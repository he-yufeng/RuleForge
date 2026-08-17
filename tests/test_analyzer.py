"""Tests for the project analyzer."""

import json
import textwrap

import pytest

from ruleforge.analyzer import analyze_project


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal Python project for testing."""
    # pyproject.toml
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent("""\
        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        [project]
        name = "sample"
        version = "0.1.0"
        requires-python = ">=3.9"
        dependencies = ["fastapi", "pydantic"]

        [tool.ruff]
        target-version = "py39"

        [tool.pytest.ini_options]
        testpaths = ["tests"]
        """)
    )

    # source files
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hello')\n")
    (src / "utils.py").write_text("def add(a, b): return a + b\n")

    # test dir
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("import pytest\ndef test_it(): pass\n")

    # CI
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n")

    # gitignore
    (tmp_path / ".gitignore").write_text("__pycache__/\n*.pyc\ndist/\n")

    return tmp_path


def test_detect_python(tmp_project):
    profile = analyze_project(tmp_project)
    assert "Python" in profile.languages
    assert profile.languages["Python"] >= 2


def test_detect_frameworks(tmp_project):
    profile = analyze_project(tmp_project)
    assert "FastAPI" in profile.frameworks
    assert "Pydantic" in profile.frameworks


def test_detect_tooling(tmp_project):
    profile = analyze_project(tmp_project)
    assert profile.linter == "ruff"
    assert profile.formatter == "ruff"
    assert profile.test_framework == "pytest"
    assert profile.package_manager == "hatch"
    assert profile.python_version == ">=3.9"


def test_setup_cfg_without_flake8_section_is_not_flake8(tmp_path):
    # setup.cfg is generic setuptools metadata here — no linter is configured.
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "setup.cfg").write_text("[metadata]\nname = demo\n", encoding="utf-8")
    profile = analyze_project(tmp_path)
    assert profile.linter is None


def test_setup_cfg_with_flake8_section_detects_flake8(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "setup.cfg").write_text("[flake8]\nmax-line-length = 100\n", encoding="utf-8")
    profile = analyze_project(tmp_path)
    assert profile.linter == "flake8"


def test_detect_ci(tmp_project):
    profile = analyze_project(tmp_project)
    assert profile.has_ci
    assert profile.ci_system == "GitHub Actions"


def test_detect_ci_commands(tmp_project):
    workflow = tmp_project / ".github" / "workflows" / "ci.yml"
    workflow.write_text(
        textwrap.dedent("""\
        name: CI
        jobs:
          test:
            runs-on: ubuntu-latest
            steps:
              - run: |
                  ruff check .
                  pytest -q
              - run: echo "${{ secrets.DEPLOY_TOKEN }}"
        """),
        encoding="utf-8",
    )

    profile = analyze_project(tmp_project)

    assert profile.extra["ci_commands"] == ["ruff check .", "pytest -q"]


def test_detect_source_dirs(tmp_project):
    profile = analyze_project(tmp_project)
    assert "src" in profile.source_dirs


def test_detect_existing_assistant_rules(tmp_project):
    (tmp_project / "AGENTS.md").write_text("Local rules\n", encoding="utf-8")
    (tmp_project / "GEMINI.md").write_text("Gemini rules\n", encoding="utf-8")

    profile = analyze_project(tmp_project)

    assert profile.extra["existing_rules"] == ["AGENTS.md", "GEMINI.md"]


def test_gitignore_patterns(tmp_project):
    profile = analyze_project(tmp_project)
    assert "__pycache__/" in profile.git_ignore_patterns


def test_language_count_respects_gitignore(tmp_project):
    generated = tmp_project / "generated"
    generated.mkdir()
    (generated / "bundle.ts").write_text("export const value = 1;\n")
    (tmp_project / "notes.generated.py").write_text("print('generated')\n")
    with (tmp_project / ".gitignore").open("a", encoding="utf-8") as f:
        f.write("generated/\n*.generated.py\n")

    profile = analyze_project(tmp_project)

    assert profile.languages["Python"] == 3
    assert "TypeScript" not in profile.languages


def test_nonexistent_dir():
    with pytest.raises(FileNotFoundError):
        analyze_project("/nonexistent/path/foo/bar")


@pytest.fixture
def node_project(tmp_path):
    """Create a minimal Node.js project."""
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "sample-app",
                "version": "1.0.0",
                "dependencies": {"next": "^14.0", "react": "^18.0"},
                "devDependencies": {"eslint": "^8.0", "prettier": "^3.0", "vitest": "^1.0"},
                "scripts": {"lint": "eslint .", "test": "vitest"},
            }
        )
    )
    (tmp_path / "pnpm-lock.yaml").write_text("")
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.ts").write_text("console.log('hi')\n")
    (src / "App.tsx").write_text("export default function App() { return <div/>; }\n")
    return tmp_path


def test_detect_node(node_project):
    profile = analyze_project(node_project)
    assert "TypeScript" in profile.languages
    assert profile.package_manager == "pnpm"
    assert profile.test_framework == "vitest"
    assert profile.linter == "eslint"
    assert profile.formatter == "prettier"
    assert "Next.js" in profile.frameworks
    assert "React" in profile.frameworks
    assert profile.extra["package_scripts"] == {
        "lint": "eslint .",
        "test": "vitest",
    }


def test_test_framework_detection_not_overridden_by_second_test_dir(tmp_path):
    # Both tests/ (pytest) and test/ (unittest) exist: the first framework
    # detected must stand, and both dirs are still recorded as source dirs.
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("import pytest\n\n\ndef test_a():\n    pass\n")
    (tmp_path / "test").mkdir()
    (tmp_path / "test" / "test_b.py").write_text("import unittest\n")

    profile = analyze_project(tmp_path)

    assert profile.test_framework == "pytest"
    assert "tests" in profile.source_dirs
    assert "test" in profile.source_dirs


def _make_js_pkg(root, rel, name, scripts=None):
    pkg = root / rel
    pkg.mkdir(parents=True)
    (pkg / "package.json").write_text(json.dumps({"name": name, "scripts": scripts or {}}))
    (pkg / "index.ts").write_text("export const x = 1\n")
    return pkg


def test_detect_pnpm_workspaces(tmp_path):
    (tmp_path / "pnpm-workspace.yaml").write_text('packages:\n  - "packages/*"\n')
    _make_js_pkg(tmp_path, "packages/web", "@app/web", {"test": "vitest", "build": "tsc"})
    _make_js_pkg(tmp_path, "packages/api", "@app/api")
    (tmp_path / "packages" / "README.md").mkdir(exist_ok=True)  # no manifest, not a package

    profile = analyze_project(tmp_path)

    assert profile.monorepo
    paths = [ws.path for ws in profile.workspaces]
    assert paths == ["packages/api", "packages/web"]
    web = next(ws for ws in profile.workspaces if ws.name == "@app/web")
    assert web.languages.get("TypeScript") == 1
    assert web.commands["test"] == "npm test"
    assert web.commands["build"] == "npm run build"
    api = next(ws for ws in profile.workspaces if ws.name == "@app/api")
    assert "test" not in api.commands


def test_detect_package_json_workspaces(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"name": "root", "workspaces": ["libs/*"]}))
    _make_js_pkg(tmp_path, "libs/util", "util")

    profile = analyze_project(tmp_path)

    assert [ws.name for ws in profile.workspaces] == ["util"]


def test_detect_cargo_workspace_members(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[workspace]\nmembers = ["crates/core"]\n')
    core = tmp_path / "crates" / "core"
    core.mkdir(parents=True)
    (core / "Cargo.toml").write_text('[package]\nname = "core"\n')

    profile = analyze_project(tmp_path)

    assert [ws.name for ws in profile.workspaces] == ["core"]


def test_no_workspace_manifests_no_packages(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"name": "plain"}))
    (tmp_path / "packages").mkdir()  # a bare packages/ dir is not a workspace claim

    profile = analyze_project(tmp_path)

    assert profile.workspaces == []
