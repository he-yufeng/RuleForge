"""Analyze a project directory to extract coding patterns, stack info, and conventions."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any


@dataclass
class ProjectProfile:
    """Everything we know about a project after scanning it."""

    root: Path
    languages: dict[str, int] = field(default_factory=dict)  # lang -> file count
    frameworks: list[str] = field(default_factory=list)
    package_manager: str | None = None
    test_framework: str | None = None
    linter: str | None = None
    formatter: str | None = None
    has_ci: bool = False
    ci_system: str | None = None
    has_docker: bool = False
    has_makefile: bool = False
    git_ignore_patterns: list[str] = field(default_factory=list)
    source_dirs: list[str] = field(default_factory=list)
    conventions: list[str] = field(default_factory=list)  # human-readable
    dependencies: list[str] = field(default_factory=list)
    python_version: str | None = None
    node_version: str | None = None
    entry_points: list[str] = field(default_factory=list)
    monorepo: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


# map file extensions to language names
_EXT_LANG = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C",
    ".hpp": "C++",
    ".swift": "Swift",
    ".lua": "Lua",
    ".r": "R",
    ".R": "R",
    ".scala": "Scala",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".zig": "Zig",
    ".vue": "Vue",
    ".svelte": "Svelte",
}

# dirs to always skip
_SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "target",
    "vendor",
    ".next",
    ".nuxt",
    "coverage",
    ".cache",
    "egg-info",
}


def _should_skip(name: str) -> bool:
    return name in _SKIP_DIRS or name.startswith(".")


def _read_gitignore_patterns(root: Path) -> list[str]:
    gi = root / ".gitignore"
    if not gi.exists():
        return []
    try:
        lines = gi.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def _matches_gitignore(rel_path: str, is_dir: bool, raw_pattern: str) -> bool:
    pattern = raw_pattern.strip().replace("\\", "/")
    if not pattern or pattern.startswith("!"):
        return False

    directory_only = pattern.endswith("/")
    anchored = pattern.startswith("/")
    pattern = pattern.strip("/")
    if not pattern:
        return False

    if directory_only:
        return rel_path == pattern or rel_path.startswith(pattern + "/") or (
            not anchored and ("/" + pattern + "/") in ("/" + rel_path + "/")
        )

    if anchored or "/" in pattern:
        return fnmatch(rel_path, pattern) or (not anchored and fnmatch(rel_path, f"*/{pattern}"))

    parts = rel_path.split("/")
    if is_dir:
        return any(fnmatch(part, pattern) for part in parts)
    return fnmatch(parts[-1], pattern) or any(fnmatch(part, pattern) for part in parts[:-1])


def _is_gitignored(root: Path, path: Path, is_dir: bool, patterns: list[str]) -> bool:
    try:
        rel_path = path.relative_to(root).as_posix()
    except ValueError:
        return False

    ignored = False
    for raw in patterns:
        negated = raw.startswith("!")
        pattern = raw[1:] if negated else raw
        if _matches_gitignore(rel_path, is_dir, pattern):
            ignored = not negated
    return ignored


def _count_languages(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    gitignore_patterns = _read_gitignore_patterns(root)
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [
            d
            for d in dirnames
            if not _should_skip(d)
            and not _is_gitignored(root, current / d, is_dir=True, patterns=gitignore_patterns)
        ]
        for f in filenames:
            if _is_gitignored(root, current / f, is_dir=False, patterns=gitignore_patterns):
                continue
            ext = Path(f).suffix.lower()
            lang = _EXT_LANG.get(ext)
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def _detect_python_details(root: Path, profile: ProjectProfile) -> None:
    """Detect Python-specific tooling and conventions."""
    pyproject = root / "pyproject.toml"
    setup_py = root / "setup.py"
    setup_cfg = root / "setup.cfg"
    requirements = root / "requirements.txt"
    pipfile = root / "Pipfile"
    poetry_lock = root / "poetry.lock"

    if pyproject.exists():
        try:
            data = _load_toml(pyproject)
        except Exception:
            data = {}

        # build system
        build_backend = data.get("build-system", {}).get("build-backend", "")
        if "poetry" in build_backend:
            profile.package_manager = "poetry"
        elif "hatchling" in build_backend:
            profile.package_manager = "hatch"
        elif "flit" in build_backend:
            profile.package_manager = "flit"
        elif "setuptools" in build_backend:
            profile.package_manager = "setuptools"

        # python version
        py_req = data.get("project", {}).get("requires-python", "")
        if py_req:
            profile.python_version = py_req

        # ruff / black / isort
        if "tool" in data:
            tools = data["tool"]
            if "ruff" in tools:
                profile.linter = "ruff"
                profile.formatter = "ruff"
            if "black" in tools:
                profile.formatter = "black"
            if "isort" in tools and not profile.formatter:
                profile.conventions.append("isort for import sorting")
            if "mypy" in tools:
                profile.conventions.append("mypy for type checking")
            if "pytest" in tools:
                profile.test_framework = "pytest"

        # deps
        deps = data.get("project", {}).get("dependencies", [])
        profile.dependencies.extend(deps[:30])

    elif poetry_lock.exists():
        profile.package_manager = "poetry"
    elif pipfile.exists():
        profile.package_manager = "pipenv"
    elif requirements.exists():
        profile.package_manager = "pip"
    elif setup_py.exists() or setup_cfg.exists():
        profile.package_manager = "setuptools"

    # detect test framework from imports if not already set
    if not profile.test_framework:
        test_dirs = ["tests", "test"]
        for td in test_dirs:
            tp = root / td
            if tp.is_dir():
                profile.source_dirs.append(td)
                # just peek at a few files
                for tf in list(tp.rglob("*.py"))[:5]:
                    try:
                        content = tf.read_text(encoding="utf-8", errors="replace")[:2000]
                    except OSError:
                        continue
                    if "import pytest" in content or "from pytest" in content:
                        profile.test_framework = "pytest"
                        break
                    if "import unittest" in content:
                        profile.test_framework = "unittest"
                        break

    # linter fallback
    if not profile.linter:
        if (root / ".flake8").exists() or (root / "setup.cfg").exists():
            profile.linter = "flake8"
        elif (root / ".pylintrc").exists():
            profile.linter = "pylint"

    # detect frameworks from deps
    all_deps = " ".join(profile.dependencies).lower()
    _fw_map = {
        "fastapi": "FastAPI",
        "flask": "Flask",
        "django": "Django",
        "streamlit": "Streamlit",
        "gradio": "Gradio",
        "typer": "Typer",
        "click": "Click",
        "pytorch": "PyTorch",
        "torch": "PyTorch",
        "tensorflow": "TensorFlow",
        "langchain": "LangChain",
        "openai": "OpenAI SDK",
        "anthropic": "Anthropic SDK",
        "transformers": "HuggingFace Transformers",
        "pydantic": "Pydantic",
        "sqlalchemy": "SQLAlchemy",
        "celery": "Celery",
    }
    for key, name in _fw_map.items():
        if key in all_deps and name not in profile.frameworks:
            profile.frameworks.append(name)


def _detect_node_details(root: Path, profile: ProjectProfile) -> None:
    """Detect Node.js/TypeScript tooling."""
    pkg_json = root / "package.json"
    if not pkg_json.exists():
        return

    try:
        import json

        data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return

    # package manager
    if (root / "pnpm-lock.yaml").exists():
        profile.package_manager = profile.package_manager or "pnpm"
    elif (root / "yarn.lock").exists():
        profile.package_manager = profile.package_manager or "yarn"
    elif (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        profile.package_manager = profile.package_manager or "bun"
    elif (root / "package-lock.json").exists():
        profile.package_manager = profile.package_manager or "npm"

    # node version
    engines = data.get("engines", {})
    if "node" in engines:
        profile.node_version = engines["node"]

    all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

    # test framework
    if not profile.test_framework:
        if "vitest" in all_deps:
            profile.test_framework = "vitest"
        elif "jest" in all_deps:
            profile.test_framework = "jest"
        elif "mocha" in all_deps:
            profile.test_framework = "mocha"

    # linter/formatter
    if "eslint" in all_deps:
        profile.linter = profile.linter or "eslint"
    if "prettier" in all_deps:
        profile.formatter = profile.formatter or "prettier"
    if "biome" in all_deps or "@biomejs/biome" in all_deps:
        profile.linter = profile.linter or "biome"
        profile.formatter = profile.formatter or "biome"

    # frameworks
    _fw_map = {
        "next": "Next.js",
        "nuxt": "Nuxt",
        "react": "React",
        "vue": "Vue",
        "svelte": "Svelte",
        "@sveltejs/kit": "SvelteKit",
        "express": "Express",
        "fastify": "Fastify",
        "hono": "Hono",
        "nestjs": "NestJS",
        "@nestjs/core": "NestJS",
        "tailwindcss": "Tailwind CSS",
        "prisma": "Prisma",
        "drizzle-orm": "Drizzle ORM",
        "@trpc/server": "tRPC",
    }
    for key, name in _fw_map.items():
        if key in all_deps and name not in profile.frameworks:
            profile.frameworks.append(name)

    # scripts hint at conventions
    scripts = data.get("scripts", {})
    if "lint" in scripts:
        profile.conventions.append(f"lint script: `{scripts['lint']}`")
    if "test" in scripts:
        profile.conventions.append(f"test script: `{scripts['test']}`")


def _detect_go_details(root: Path, profile: ProjectProfile) -> None:
    go_mod = root / "go.mod"
    if not go_mod.exists():
        return
    try:
        content = go_mod.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    # go version
    m = re.search(r"^go\s+(\d+\.\d+)", content, re.MULTILINE)
    if m:
        profile.extra["go_version"] = m.group(1)
    # common deps
    if "github.com/gin-gonic/gin" in content:
        profile.frameworks.append("Gin")
    if "github.com/gofiber/fiber" in content:
        profile.frameworks.append("Fiber")
    if "google.golang.org/grpc" in content:
        profile.frameworks.append("gRPC")


def _detect_rust_details(root: Path, profile: ProjectProfile) -> None:
    cargo = root / "Cargo.toml"
    if not cargo.exists():
        return
    try:
        data = _load_toml(cargo)
    except Exception:
        return
    edition = data.get("package", {}).get("edition")
    if edition:
        profile.extra["rust_edition"] = edition
    deps = data.get("dependencies", {})
    if "tokio" in deps:
        profile.frameworks.append("Tokio")
    if "actix-web" in deps:
        profile.frameworks.append("Actix Web")
    if "axum" in deps:
        profile.frameworks.append("Axum")
    if "serde" in deps:
        profile.conventions.append("serde for serialization")


def _detect_ci(root: Path, profile: ProjectProfile) -> None:
    if (root / ".github" / "workflows").is_dir():
        profile.has_ci = True
        profile.ci_system = "GitHub Actions"
    elif (root / ".gitlab-ci.yml").exists():
        profile.has_ci = True
        profile.ci_system = "GitLab CI"
    elif (root / ".circleci").is_dir():
        profile.has_ci = True
        profile.ci_system = "CircleCI"
    elif (root / "Jenkinsfile").exists():
        profile.has_ci = True
        profile.ci_system = "Jenkins"


def _detect_misc(root: Path, profile: ProjectProfile) -> None:
    if (root / "Dockerfile").exists() or (root / "docker-compose.yml").exists():
        profile.has_docker = True
    if (root / "Makefile").exists():
        profile.has_makefile = True

    # monorepo indicators
    if (root / "lerna.json").exists() or (root / "pnpm-workspace.yaml").exists():
        profile.monorepo = True
    if (root / "packages").is_dir() or (root / "apps").is_dir():
        profile.monorepo = True

    # gitignore patterns (useful context for rules)
    profile.git_ignore_patterns = _read_gitignore_patterns(root)[:20]

    # source directory detection
    common_src = ["src", "lib", "app", "pkg", "cmd", "internal"]
    for d in common_src:
        if (root / d).is_dir():
            profile.source_dirs.append(d)

    # entry points
    for ep in ["main.py", "app.py", "index.ts", "index.js", "main.go", "main.rs"]:
        if (root / ep).exists() or (root / "src" / ep).exists():
            profile.entry_points.append(ep)


def _detect_existing_rules(root: Path, profile: ProjectProfile) -> None:
    """Check if there are already AI assistant rule files."""
    rule_files = [
        "CLAUDE.md",
        ".cursorrules",
        ".cursor/rules",
        ".github/copilot-instructions.md",
    ]
    existing = []
    for rf in rule_files:
        if (root / rf).exists():
            existing.append(rf)
    if existing:
        profile.extra["existing_rules"] = existing


def analyze_project(project_dir: str | Path) -> ProjectProfile:
    """Scan a project directory and return a profile of its tech stack and conventions.

    Args:
        project_dir: Path to the project root.

    Returns:
        A ProjectProfile with detected languages, frameworks, tooling, etc.
    """
    root = Path(project_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    profile = ProjectProfile(root=root)

    # language counts
    profile.languages = _count_languages(root)

    # language-specific details
    if "Python" in profile.languages:
        _detect_python_details(root, profile)
    if "TypeScript" in profile.languages or "JavaScript" in profile.languages:
        _detect_node_details(root, profile)
    if "Go" in profile.languages:
        _detect_go_details(root, profile)
    if "Rust" in profile.languages:
        _detect_rust_details(root, profile)

    _detect_ci(root, profile)
    _detect_misc(root, profile)
    _detect_existing_rules(root, profile)

    return profile


def _load_toml(path: Path) -> dict[str, Any]:
    if sys.version_info >= (3, 11):
        import tomllib

        return tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))

    import toml

    return toml.loads(path.read_text(encoding="utf-8", errors="replace"))
