"""Analyze a project directory to extract coding patterns, stack info, and conventions."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml


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
    workspaces: list[WorkspacePackage] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkspacePackage:
    """One detected package inside a monorepo workspace."""

    path: str  # relative to the repo root, e.g. "packages/web"
    name: str  # manifest name when readable, else the directory name
    languages: dict[str, int] = field(default_factory=dict)
    commands: dict[str, str] = field(default_factory=dict)  # e.g. {"test": "npm test"}


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
        return (
            rel_path == pattern
            or rel_path.startswith(pattern + "/")
            or (not anchored and ("/" + pattern + "/") in ("/" + rel_path + "/"))
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


def _setup_cfg_configures_flake8(root: Path) -> bool:
    """True only when setup.cfg actually has a ``[flake8]`` section.

    setup.cfg is a generic setuptools / mypy / coverage config file, so its mere
    presence says nothing about linting — only a ``[flake8]`` section means the
    project really uses flake8.
    """
    cfg = root / "setup.cfg"
    if not cfg.exists():
        return False
    try:
        return "[flake8]" in cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


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

        scripts = data.get("project", {}).get("scripts", {})
        if scripts:
            profile.extra["python_entry_points"] = dict(list(scripts.items())[:20])

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
                # Both "tests" and "test" can exist; record each as a source
                # dir, but let the first framework we detect stand — without
                # this, a later dir would override an already-correct guess.
                if profile.test_framework:
                    continue
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
        if (root / ".flake8").exists() or _setup_cfg_configures_flake8(root):
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

    # scripts hint at conventions and are useful concrete commands for generated rules
    scripts = data.get("scripts", {})
    if scripts:
        profile.extra["package_scripts"] = {
            name: command
            for name, command in scripts.items()
            if name in {"dev", "build", "test", "lint", "format", "typecheck", "check"}
            or name.startswith(("test:", "lint:", "check:"))
        }
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
        profile.extra["ci_commands"] = _detect_github_actions_commands(root)
    elif (root / ".gitlab-ci.yml").exists():
        profile.has_ci = True
        profile.ci_system = "GitLab CI"
    elif (root / ".circleci").is_dir():
        profile.has_ci = True
        profile.ci_system = "CircleCI"
    elif (root / "Jenkinsfile").exists():
        profile.has_ci = True
        profile.ci_system = "Jenkins"


def _detect_github_actions_commands(root: Path) -> list[str]:
    commands: list[str] = []
    workflows = root / ".github" / "workflows"
    for path in sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")]):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
        except (OSError, yaml.YAMLError):
            continue
        for job in (data.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                run = step.get("run") if isinstance(step, dict) else None
                if not isinstance(run, str):
                    continue
                for line in run.splitlines():
                    command = line.strip()
                    if (
                        not command
                        or command.startswith("#")
                        or "${{ secrets." in command
                        or command in {"set -e", "set -eux", "set -euo pipefail"}
                    ):
                        continue
                    if len(command) <= 200 and command not in commands:
                        commands.append(command)
                    if len(commands) >= 20:
                        return commands
    return commands


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

    _detect_workspaces(root, profile)


def _workspace_patterns(root: Path) -> list[str]:
    """Collect workspace member globs from the usual monorepo manifests."""
    patterns: list[str] = []
    pnpm = root / "pnpm-workspace.yaml"
    if pnpm.exists():
        try:
            data = yaml.safe_load(pnpm.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, dict) and isinstance(data.get("packages"), list):
                patterns.extend(str(p) for p in data["packages"])
        except yaml.YAMLError:
            pass
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            ws = data.get("workspaces")
            if isinstance(ws, list):
                patterns.extend(str(p) for p in ws)
            elif isinstance(ws, dict) and isinstance(ws.get("packages"), list):
                patterns.extend(str(p) for p in ws["packages"])
        except json.JSONDecodeError:
            pass
    cargo = root / "Cargo.toml"
    if cargo.exists():
        try:
            members = _load_toml(cargo).get("workspace", {}).get("members")
            if isinstance(members, list):
                patterns.extend(str(m) for m in members)
        except Exception:
            pass
    return patterns


def _workspace_glob_dirs(root: Path, patterns: list[str]) -> list[Path]:
    """Expand the common single-star workspace globs ("packages/*") to dirs."""
    dirs: list[Path] = []
    for pat in patterns:
        pat = pat.strip().strip("\"'")
        if not pat or pat.startswith("!"):
            continue
        if "*" not in pat:
            candidate = root / pat
            if candidate.is_dir():
                dirs.append(candidate)
            continue
        # recursive or multi-star globs stay unexpanded; they are rare and
        # guessing their intent is worse than skipping them.
        if pat.count("*") != 1 or not pat.endswith("/*"):
            continue
        base = root / pat[:-2]
        if base.is_dir():
            dirs.extend(sorted(p for p in base.iterdir() if p.is_dir()))
    return dirs


def _package_manifest_name(pkg_dir: Path) -> str | None:
    pkg_json = pkg_dir / "package.json"
    if pkg_json.exists():
        try:
            name = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace")).get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        except json.JSONDecodeError:
            pass
    for manifest in ("pyproject.toml", "Cargo.toml"):
        mpath = pkg_dir / manifest
        if mpath.exists():
            try:
                data = _load_toml(mpath)
                name = data.get("project", {}).get("name") or data.get("package", {}).get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
            except Exception:
                pass
    return None


def _package_commands(pkg_dir: Path) -> dict[str, str]:
    """Best-effort per-package commands, read from its own manifest only."""
    commands: dict[str, str] = {}
    pkg_json = pkg_dir / "package.json"
    if pkg_json.exists():
        try:
            scripts = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace")).get(
                "scripts"
            )
            if isinstance(scripts, dict):
                if "test" in scripts:
                    commands["test"] = "npm test"
                if "lint" in scripts:
                    commands["lint"] = "npm run lint"
                if "build" in scripts:
                    commands["build"] = "npm run build"
        except json.JSONDecodeError:
            pass
    if (pkg_dir / "tests").is_dir() or list(pkg_dir.glob("test_*.py")):
        commands.setdefault("test", "pytest")
    return commands


def _detect_workspaces(root: Path, profile: ProjectProfile) -> None:
    patterns = _workspace_patterns(root)
    if not patterns:
        return
    seen: set[str] = set()
    for pkg_dir in _workspace_glob_dirs(root, patterns):
        rel = pkg_dir.relative_to(root).as_posix()
        if rel in seen:
            continue
        if _package_manifest_name(pkg_dir) is None:
            continue  # a dir without its own manifest is not a package
        seen.add(rel)
        profile.workspaces.append(
            WorkspacePackage(
                path=rel,
                name=_package_manifest_name(pkg_dir) or pkg_dir.name,
                languages=_count_languages(pkg_dir),
                commands=_package_commands(pkg_dir),
            )
        )
    if profile.workspaces:
        profile.monorepo = True


def _detect_existing_rules(root: Path, profile: ProjectProfile) -> None:
    """Check if there are already AI assistant rule files."""
    rule_files = [
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
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



_NAME_OK_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PY_DEF_RE = re.compile(r"^def ([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)
_PY_CLASS_RE = re.compile(r"^class ([A-Za-z_][A-Za-z0-9_]*)\b", re.MULTILINE)
_JS_FUNC_RE = re.compile(r"\bfunction\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")
_JS_ARROW_RE = re.compile(r"\bconst\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\(")
_JS_TEST_RE = re.compile(r"\.(?:test|spec)\.[jt]sx?$")
_PY_TEST_RE = re.compile(r"^(test_.*|.*_test)\.py$")


def _name_style(name: str) -> str | None:
    """Classify an identifier as snake / camel / pascal, ignoring dunders and
    leading-underscore privacy marks."""
    name = name.strip("_")
    if not name:
        return None
    if "_" in name:
        return "snake"
    if name[0].islower():
        return "camel"
    if name[0].isupper():
        return "pascal"
    return None


def _style_majority(names: list[str], style: str) -> bool:
    """A naming convention is only reported when the evidence is decisive."""
    return len(names) >= 8 and names.count(style) / len(names) >= 0.7


def _source_files(root: Path, extensions: tuple[str, ...], limit: int) -> list[Path]:
    """A bounded sample of source files, skipping vendor and hidden dirs."""
    picked: list[Path] = []
    skip_dirs = {"node_modules", ".git", "dist", "build", "venv", ".venv", "__pycache__", "vendor"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        for name in sorted(filenames):
            if name.endswith(extensions):
                picked.append(Path(dirpath) / name)
                if len(picked) >= limit:
                    return picked
    return picked


def _read_head(path: Path, limit: int = 12_000) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def _sample_code_conventions(root: Path, profile: ProjectProfile) -> None:
    """Infer naming and test-layout conventions from a light sample of sources.

    Findings land in ``profile.conventions`` only when the sampled majority is
    decisive (>= 8 identifiers, >= 70% one style); mixed evidence stays silent
    rather than assert a convention the project does not have.
    """
    if "Python" in profile.languages:
        func_names: list[str] = []
        class_names: list[str] = []
        test_in_dir = 0
        test_colocated = 0
        for path in _source_files(root, (".py",), 20):
            rel_parts = path.relative_to(root).parts
            is_test = _PY_TEST_RE.match(path.name) is not None
            if is_test:
                if any(part in ("tests", "test") for part in rel_parts[:-1]):
                    test_in_dir += 1
                else:
                    test_colocated += 1
                continue
            text = _read_head(path)
            func_names.extend(_PY_DEF_RE.findall(text))
            class_names.extend(_PY_CLASS_RE.findall(text))

        func_styles = [s for s in (_name_style(n) for n in func_names) if s]
        if _style_majority(func_styles, "snake"):
            profile.conventions.append("snake_case for functions and variables")
        elif _style_majority(func_styles, "camel"):
            profile.conventions.append("camelCase for functions and variables")
        class_styles = [s for s in (_name_style(n) for n in class_names) if s]
        if _style_majority(class_styles, "pascal"):
            profile.conventions.append("PascalCase for classes")

        if test_in_dir and not test_colocated:
            profile.conventions.append("tests live in tests/ directories")
        elif test_colocated and not test_in_dir:
            profile.conventions.append("tests are co-located with sources")

    if "TypeScript" in profile.languages or "JavaScript" in profile.languages:
        names: list[str] = []
        test_colocated = 0
        test_in_dir = 0
        for path in _source_files(root, (".ts", ".js"), 20):
            rel_parts = path.relative_to(root).parts
            if _JS_TEST_RE.search(path.name):
                if any(part in ("__tests__", "tests", "test") for part in rel_parts[:-1]):
                    test_in_dir += 1
                else:
                    test_colocated += 1
                continue
            text = _read_head(path)
            names.extend(_JS_FUNC_RE.findall(text))
            names.extend(_JS_ARROW_RE.findall(text))

        styles = [s for s in (_name_style(n) for n in names) if s]
        if _style_majority(styles, "camel"):
            profile.conventions.append("camelCase for functions and variables")
        elif _style_majority(styles, "snake"):
            profile.conventions.append("snake_case for functions and variables")

        if test_in_dir and not test_colocated:
            profile.conventions.append("tests live in __tests__ or tests/ directories")
        elif test_colocated and not test_in_dir:
            profile.conventions.append("tests are co-located with sources")


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
    _sample_code_conventions(root, profile)

    return profile


def _load_toml(path: Path) -> dict[str, Any]:
    if sys.version_info >= (3, 11):
        import tomllib

        return tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))

    import toml

    return toml.loads(path.read_text(encoding="utf-8", errors="replace"))
