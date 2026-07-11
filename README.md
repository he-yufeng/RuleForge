<div align="center">

<img src="docs/banner.png" alt="RuleForge — auto-generate AI assistant rules from your codebase" width="100%">

[![PyPI version](https://img.shields.io/pypi/v/ruleforge-ai)](https://pypi.org/project/ruleforge-ai/)
[![CI](https://github.com/he-yufeng/RuleForge/actions/workflows/ci.yml/badge.svg)](https://github.com/he-yufeng/RuleForge/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[**Quick Start**](#quick-start) · [**What It Detects**](#what-it-detects) · [**Formats**](#supported-output-formats) · [中文](README.zh-CN.md)

</div>

<p align="center"><img src="docs/demo.png" alt="ruleforge generate ." width="660"></p>

RuleForge scans your project — languages, frameworks, linters, test setup, CI config — and generates ready-to-use rule files for **Claude Code** (`CLAUDE.md`), **Cursor** (`.cursorrules`), **GitHub Copilot** (`.github/copilot-instructions.md`), the tool-agnostic **`AGENTS.md`** convention, **Windsurf** (`.windsurfrules`), **Cline** (`.clinerules`), **Gemini CLI** (`GEMINI.md`), **Zed** (`.rules`), and **Aider** (`CONVENTIONS.md`).

Stop writing these files by hand. Let your codebase speak for itself.

## Why?

Every AI coding assistant works better with project-specific context. But most developers either:

- Skip writing rules entirely (leaving performance on the table)
- Copy-paste generic templates that don't match their actual stack
- Spend 30+ minutes hand-crafting rules that go stale

RuleForge generates accurate, stack-aware rules in seconds by actually reading your project config.

## What It Detects

| Category | Examples |
|----------|---------|
| **Languages** | Python, TypeScript, JavaScript, Go, Rust, Java, C++, and 20+ more |
| **Frameworks** | FastAPI, Flask, Django, React, Next.js, Vue, Svelte, Express, Gin, Axum... |
| **Package Managers** | pip, poetry, hatch, pnpm, yarn, bun, npm, cargo |
| **Linters & Formatters** | ruff, black, eslint, prettier, biome, clippy, go fmt |
| **Test Frameworks** | pytest, unittest, vitest, jest, mocha |
| **CI Systems** | GitHub Actions, GitLab CI, CircleCI, Jenkins |
| **Project Commands** | package scripts, Python CLI entry points, and the real verification commands used by GitHub Actions |
| **Other** | Docker, Makefile, monorepo structure, entry points, .gitignore patterns |

Language counts respect `.gitignore`, so generated bundles and local artifacts do not skew the detected stack.

## Installation

```bash
pip install ruleforge-ai
```

## Quick Start

```bash
# Scan your project to see what's detected
ruleforge scan .

# Generate all rule files (CLAUDE.md, .cursorrules, copilot-instructions)
ruleforge generate .

# Generate only CLAUDE.md
ruleforge generate . -f claude

# Preview without writing anything
ruleforge preview .

# Audit existing assistant rules for missing guidance
ruleforge audit .

# Fail CI if the rules are too thin
ruleforge audit . --min-score 80

# Lint existing rules for placeholders, conflicts, and stale advice
ruleforge lint .

# Overwrite existing files
ruleforge generate . --overwrite

# Output to a different directory
ruleforge generate . -o /tmp/rules
```

## Example Output

Running `ruleforge generate` on a FastAPI project produces a `CLAUDE.md` like:

```markdown
# my-api

This is a Python project.
Key frameworks: FastAPI, Pydantic, SQLAlchemy.

## Project Structure

Source directories: `src/`, `tests/`
Entry points: `main.py`
Package manager: poetry

## Coding Conventions

- Linter: ruff
- Formatter: ruff
- Testing: pytest
- Python: >=3.11
- CI: GitHub Actions

## Project Commands

- `npm run test`: `vitest run`
- `npm run lint`: `eslint .`

## Guidelines

- Use type hints for function signatures.
- Run `ruff check` and `ruff format` before committing.
- Write tests with pytest. Put test files in the `tests/` directory.
- Use Pydantic models for request/response schemas.
- The project uses Docker. Keep Dockerfile up to date with dependencies.

## Do NOT

- Do not modify generated files or lock files manually.
- Do not add dependencies without mentioning it.
- Do not change the project structure without asking first.
- Do not skip CI checks or disable linting rules.
- Do not commit files matching gitignore patterns.
```

## Supported Output Formats

| Format | File | Used By |
|--------|------|---------|
| `claude` | `CLAUDE.md` | Claude Code, Claude Desktop |
| `cursor` | `.cursorrules` | Cursor IDE |
| `copilot` | `.github/copilot-instructions.md` | GitHub Copilot |
| `agents` | `AGENTS.md` | Tool-agnostic agents that read `AGENTS.md` |
| `windsurf` | `.windsurfrules` | Windsurf / Codeium |
| `cline` | `.clinerules` | Cline |
| `gemini` | `GEMINI.md` | Gemini CLI |
| `zed` | `.rules` | Zed (reads a project `.rules` file) |
| `aider` | `CONVENTIONS.md` | Aider (`read: CONVENTIONS.md` in `.aider.conf.yml`) |

`ruleforge generate --format all` writes all nine; pass `--format` repeatedly (e.g. `--format agents --format cursor`) to pick a subset.

## Rule Audits

RuleForge can also check rule files you already wrote. It looks for the parts that usually make AI coding agents useful in a real repository:

- project context and detected stack
- concrete test, lint, typecheck, or build commands
- verification commands extracted from GitHub Actions `run` steps (secret-bearing lines are skipped)
- editing boundaries and generated-file warnings
- secret / token / `.env` handling
- git, PR, CI, and review workflow
- assistant behavior expectations

```bash
ruleforge audit .
ruleforge audit . --format json
ruleforge audit . --format sarif > ruleforge.sarif
ruleforge audit . --min-score 80
```

This is useful for CI or for checking whether a hand-written `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, or Copilot instructions file is specific enough to trust. SARIF output turns missing guidance into GitHub Code Scanning findings. When RuleForge generates new rules, it now also points out existing assistant rule files so the generated draft does not accidentally replace stricter local guidance.

## Rule Lint

Where `audit` measures how much a rule file covers, `lint` looks for guidance that is wrong or unusable, the kind of thing that quietly sends an agent down the wrong path:

- leftover template placeholders (`TODO`, `FIXME`, `{{ ... }}`, `<your project name>`)
- conflicting directives, like recommending both `npm` and `pnpm`, `pytest` and `unittest`, or `black` and `ruff`
- stale advice, like telling the agent to use `yarn` when the repo has a `pnpm-lock.yaml`, or to format with `black` when the project has switched to `ruff`

```bash
ruleforge lint .
ruleforge lint . --format json
ruleforge lint . --strict   # treat warnings as errors too
```

Placeholders are reported as errors and competing or stale tool directives as warnings. Conflict and staleness checks cover package managers, test frameworks, linters, and formatters. The command exits non-zero when there are errors (or any warning under `--strict`), so it drops straight into a CI step. Stale and conflict checks only compare tools within the same ecosystem, so a polyglot repo that genuinely runs both `pytest` and `jest`, or `ruff` and `eslint`, is left alone.

## Python API

```python
from ruleforge import analyze_project, generate_rules
from ruleforge.generator import write_rules

# Analyze
profile = analyze_project("./my-project")
print(profile.languages)    # {'Python': 42, 'TypeScript': 15}
print(profile.frameworks)   # ['FastAPI', 'React']

# Generate
rules = generate_rules(profile, formats=["claude", "cursor"])
for rule in rules:
    print(rule.filename, len(rule.content))

# Write to disk
write_rules(rules, "./my-project")
```

## Limitations

- Detection is based on config files and file extensions — it doesn't analyze code semantics
- Generated rules are a solid starting point, not a finished product. You should review and customize them for your project's specific conventions
- Framework detection depends on dependency declarations (pyproject.toml, package.json, etc.)

## Roadmap

The detection-and-generate core is stable. The next steps mostly chip away at the limitations above:

- **Light code-semantic detection** — sample a few representative source files for naming and layout conventions, instead of inferring everything from config files and extensions.
- **More assistant formats** — emit rules for Windsurf, Cline, and Zed alongside CLAUDE.md / `.cursorrules` / Copilot; the generator already separates content from format, so each new target is mostly a template.
- **Drift detection** — a `ruleforge check` that flags when committed rules have fallen behind the project (new commands, moved structure), so the files don't quietly go stale.
- **Per-package rules in a monorepo** — detect workspaces and emit scoped rule files per package, not just one set at the repo root.

## Contributing

Contributions welcome! Especially for:

- New language/framework detection (see `analyzer.py`)
- Better rule templates (see `generator.py`)
- Support for more AI assistant formats

```bash
git clone https://github.com/he-yufeng/RuleForge.git
cd RuleForge
pip install -e ".[dev]"
pytest
```

## Related Projects

RuleForge came out of juggling a lot of repos at once. A few other tools from the same work:

- **[CoreCoder](https://github.com/he-yufeng/CoreCoder)** — want to understand how a coding agent really works? Read the whole ~1k-line engine end to end, not a black box.
- **[RepoWiki](https://github.com/he-yufeng/RepoWiki)** — dropped into an unfamiliar codebase? It gives you a guided wiki and a where-to-start reading path, a self-hostable DeepWiki alternative.
- **[GitSense](https://github.com/he-yufeng/GitSense)** — want to contribute to open source? It finds issues worth your time and gauges whether your PR will get merged.
- **[CodeABC](https://github.com/he-yufeng/CodeABC)** — understand any codebase even if you don't code, built for non-programmers.

## License

MIT
