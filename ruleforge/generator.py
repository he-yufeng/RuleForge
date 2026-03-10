"""Generate AI assistant rule files from a ProjectProfile."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ruleforge.analyzer import ProjectProfile

RuleFormat = Literal["claude", "cursor", "copilot"]


@dataclass
class GeneratedRule:
    """A generated rule file ready to be written."""

    filename: str
    content: str
    format: RuleFormat


def _build_header(profile: ProjectProfile) -> str:
    """Project overview section."""
    name = profile.root.name
    langs = ", ".join(profile.languages.keys())
    lines = [f"# {name}", ""]

    if langs:
        lines.append(f"This is a {langs} project.")

    if profile.frameworks:
        lines.append(f"Key frameworks: {', '.join(profile.frameworks)}.")

    if profile.monorepo:
        lines.append("This is a monorepo with multiple packages.")

    lines.append("")
    return "\n".join(lines)


def _build_structure_section(profile: ProjectProfile) -> str:
    lines = ["## Project Structure", ""]

    if profile.source_dirs:
        dirs = ", ".join(f"`{d}/`" for d in profile.source_dirs)
        lines.append(f"Source directories: {dirs}")

    if profile.entry_points:
        eps = ", ".join(f"`{e}`" for e in profile.entry_points)
        lines.append(f"Entry points: {eps}")

    if profile.package_manager:
        lines.append(f"Package manager: {profile.package_manager}")

    lines.append("")
    return "\n".join(lines)


def _build_conventions_section(profile: ProjectProfile) -> str:
    lines = ["## Coding Conventions", ""]

    if profile.linter:
        lines.append(f"- Linter: {profile.linter}")
    if profile.formatter:
        lines.append(f"- Formatter: {profile.formatter}")
    if profile.test_framework:
        lines.append(f"- Testing: {profile.test_framework}")
    if profile.python_version:
        lines.append(f"- Python: {profile.python_version}")
    if profile.node_version:
        lines.append(f"- Node.js: {profile.node_version}")
    if profile.extra.get("go_version"):
        lines.append(f"- Go: {profile.extra['go_version']}")
    if profile.extra.get("rust_edition"):
        lines.append(f"- Rust edition: {profile.extra['rust_edition']}")
    if profile.has_ci:
        lines.append(f"- CI: {profile.ci_system}")

    for conv in profile.conventions:
        lines.append(f"- {conv}")

    lines.append("")
    return "\n".join(lines)


def _build_guidelines(profile: ProjectProfile) -> str:
    """Context-aware coding guidelines based on detected stack."""
    lines = ["## Guidelines", ""]

    # language-specific
    if "Python" in profile.languages:
        lines.append("- Use type hints for function signatures.")
        if profile.linter == "ruff":
            lines.append("- Run `ruff check` and `ruff format` before committing.")
        elif profile.formatter == "black":
            lines.append("- Run `black` for formatting before committing.")
        if profile.test_framework == "pytest":
            lines.append("- Write tests with pytest. Put test files in the `tests/` directory.")

    if "TypeScript" in profile.languages:
        lines.append("- Prefer TypeScript over JavaScript for new files.")
        if profile.linter == "eslint":
            lines.append("- Follow ESLint rules. Run linting before committing.")
        if profile.formatter == "prettier":
            lines.append("- Format code with Prettier.")
        if profile.formatter == "biome":
            lines.append("- Format and lint with Biome.")

    if "Go" in profile.languages:
        lines.append("- Follow standard Go conventions. Run `go fmt` and `go vet`.")
        lines.append("- Handle errors explicitly, don't ignore them.")

    if "Rust" in profile.languages:
        lines.append("- Run `cargo clippy` for linting and `cargo fmt` for formatting.")
        lines.append("- Prefer `Result` over `unwrap()` in library code.")

    # framework-specific
    if "React" in profile.frameworks or "Next.js" in profile.frameworks:
        lines.append("- Use functional components with hooks, not class components.")
    if "FastAPI" in profile.frameworks:
        lines.append("- Use Pydantic models for request/response schemas.")
    if "Django" in profile.frameworks:
        lines.append("- Follow Django's app-based project structure.")
    if "Pydantic" in profile.frameworks:
        lines.append("- Use Pydantic for data validation and settings management.")

    # general
    if profile.has_docker:
        lines.append("- The project uses Docker. Keep Dockerfile up to date with dependencies.")
    if profile.has_makefile:
        lines.append("- Check the Makefile for common development commands.")

    lines.append("")
    return "\n".join(lines)


def _build_dont_section(profile: ProjectProfile) -> str:
    """Things the AI should avoid."""
    lines = ["## Do NOT", ""]
    lines.append("- Do not modify generated files or lock files manually.")
    lines.append("- Do not add dependencies without mentioning it.")
    lines.append("- Do not change the project structure without asking first.")

    if profile.has_ci:
        lines.append("- Do not skip CI checks or disable linting rules.")
    if profile.git_ignore_patterns:
        lines.append("- Do not commit files matching gitignore patterns.")

    lines.append("")
    return "\n".join(lines)


def _generate_claude_md(profile: ProjectProfile) -> str:
    """Generate CLAUDE.md format."""
    sections = [
        _build_header(profile),
        _build_structure_section(profile),
        _build_conventions_section(profile),
        _build_guidelines(profile),
        _build_dont_section(profile),
    ]
    return "\n".join(s for s in sections if s.strip())


def _generate_cursorrules(profile: ProjectProfile) -> str:
    """Generate .cursorrules format (same content, slightly different header)."""
    # cursorrules is just a text file with instructions
    content = _generate_claude_md(profile)
    # replace the title style
    name = profile.root.name
    content = content.replace(f"# {name}", f"# Rules for {name}", 1)
    return content


def _generate_copilot_instructions(profile: ProjectProfile) -> str:
    """Generate .github/copilot-instructions.md format."""
    content = _generate_claude_md(profile)
    name = profile.root.name
    content = content.replace(f"# {name}", f"# Copilot Instructions for {name}", 1)
    return content


def generate_rules(
    profile: ProjectProfile,
    formats: list[RuleFormat] | None = None,
) -> list[GeneratedRule]:
    """Generate rule files for the specified formats.

    Args:
        profile: The analyzed project profile.
        formats: Which formats to generate. Defaults to all three.

    Returns:
        List of GeneratedRule objects ready to write.
    """
    if formats is None:
        formats = ["claude", "cursor", "copilot"]

    results = []

    generators = {
        "claude": ("CLAUDE.md", _generate_claude_md),
        "cursor": (".cursorrules", _generate_cursorrules),
        "copilot": (".github/copilot-instructions.md", _generate_copilot_instructions),
    }

    for fmt in formats:
        if fmt not in generators:
            continue
        filename, gen_fn = generators[fmt]
        content = gen_fn(profile)
        results.append(GeneratedRule(filename=filename, content=content, format=fmt))

    return results


def write_rules(
    rules: list[GeneratedRule],
    project_dir: str | Path,
    overwrite: bool = False,
) -> list[Path]:
    """Write generated rules to disk.

    Args:
        rules: The rules to write.
        project_dir: Where to write them.
        overwrite: If False, skip files that already exist.

    Returns:
        List of paths that were actually written.
    """
    root = Path(project_dir).resolve()
    written = []

    for rule in rules:
        target = root / rule.filename
        if target.exists() and not overwrite:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rule.content, encoding="utf-8")
        written.append(target)

    return written
