# AGENTS.md

RuleForge is a small Python CLI that scans a repository and generates assistant rule files such as `CLAUDE.md`, `.cursorrules`, and `.github/copilot-instructions.md`.

## Commands

- Install locally with `pip install -e ".[dev]"`
- Run tests with `python -m pytest -q`
- Run lint with `python -m ruff check .`
- Build packages with `python -m build`
- Smoke-test the CLI with `python -m ruleforge.cli scan .` and `python -m ruleforge.cli audit .`

## Boundaries

- Keep generated rule text concise and project-specific. Generic agent advice is not useful here.
- Do not commit `dist/`, cache directories, virtualenvs, or local test databases.
- Do not add secrets, tokens, `.env` values, or machine-specific paths to docs or tests.
- Keep CLI behavior scriptable. New commands should have a plain output path or JSON mode when practical.

## Style

- Prefer small, readable helpers over large templates with hidden behavior.
- Add tests for detection, generation, and CLI output when changing user-facing behavior.
- Keep README examples aligned with the actual CLI.
