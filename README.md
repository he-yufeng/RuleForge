[![中文版](https://img.shields.io/badge/lang-中文-red)](README.zh-CN.md)
[![PyPI version](https://img.shields.io/pypi/v/ruleforge)](https://pypi.org/project/ruleforge/)
[![CI](https://github.com/he-yufeng/RuleForge/actions/workflows/ci.yml/badge.svg)](https://github.com/he-yufeng/RuleForge/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

# RuleForge

**Auto-generate AI coding assistant rules from your codebase.**

RuleForge scans your project — languages, frameworks, linters, test setup, CI config — and generates ready-to-use rule files for **Claude Code** (`CLAUDE.md`), **Cursor** (`.cursorrules`), and **GitHub Copilot** (`.github/copilot-instructions.md`).

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
| **Other** | Docker, Makefile, monorepo structure, entry points, .gitignore patterns |

## Installation

```bash
pip install ruleforge
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

## Rule Audits

RuleForge can also check rule files you already wrote. It looks for the parts that usually make AI coding agents useful in a real repository:

- project context and detected stack
- concrete test, lint, typecheck, or build commands
- editing boundaries and generated-file warnings
- secret / token / `.env` handling
- git, PR, CI, and review workflow
- assistant behavior expectations

```bash
ruleforge audit .
ruleforge audit . --format json
ruleforge audit . --min-score 80
```

This is useful for CI or for checking whether a hand-written `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, or Copilot instructions file is specific enough to trust.

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

## License

MIT
