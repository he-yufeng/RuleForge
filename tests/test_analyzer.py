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


def test_detect_ci(tmp_project):
    profile = analyze_project(tmp_project)
    assert profile.has_ci
    assert profile.ci_system == "GitHub Actions"


def test_detect_source_dirs(tmp_project):
    profile = analyze_project(tmp_project)
    assert "src" in profile.source_dirs


def test_gitignore_patterns(tmp_project):
    profile = analyze_project(tmp_project)
    assert "__pycache__/" in profile.git_ignore_patterns


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
