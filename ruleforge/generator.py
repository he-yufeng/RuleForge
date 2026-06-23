"""Generate AI assistant rule files from a ProjectProfile."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ruleforge.analyzer import ProjectProfile

RuleFormat = Literal[
    "claude", "cursor", "copilot", "agents", "windsurf", "cline", "gemini", "zed", "aider"
]


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


def _build_project_commands_section(profile: ProjectProfile) -> str:
    package_scripts = profile.extra.get("package_scripts") or {}
    python_entry_points = profile.extra.get("python_entry_points") or {}
    ci_commands = profile.extra.get("ci_commands") or []
    if not package_scripts and not python_entry_points and not ci_commands:
        return ""

    lines = ["## Project Commands", ""]

    if package_scripts:
        runner = {
            "npm": "npm run",
            "pnpm": "pnpm",
            "yarn": "yarn",
            "bun": "bun run",
        }.get(profile.package_manager or "npm", "npm run")
        for name, command in package_scripts.items():
            lines.append(f"- `{runner} {name}`: `{command}`")

    if python_entry_points:
        lines.append("")
        lines.append("CLI entry points:")
        for name, target in python_entry_points.items():
            lines.append(f"- `{name}` -> `{target}`")

    if ci_commands:
        lines.append("")
        lines.append("Commands observed in CI:")
        for command in ci_commands:
            lines.append(f"- `{command}`")

    lines.append("")
    return "\n".join(lines)


def _build_existing_rules_section(profile: ProjectProfile) -> str:
    existing = profile.extra.get("existing_rules") or []
    if not existing:
        return ""

    files = ", ".join(f"`{path}`" for path in existing)
    return "\n".join(
        [
            "## Existing Assistant Rules",
            "",
            f"Existing rule files: {files}",
            "- Read these files before making changes; preserve stricter local instructions.",
            "",
        ]
    )


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
        _build_project_commands_section(profile),
        _build_existing_rules_section(profile),
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


def _generate_agents_md(profile: ProjectProfile) -> str:
    """Generate AGENTS.md format.

    AGENTS.md is the tool-agnostic convention a growing number of agents and
    editors read, so the canonical project-named document is used as-is.
    """
    return _generate_claude_md(profile)


def _generate_windsurfrules(profile: ProjectProfile) -> str:
    """Generate .windsurfrules format (Windsurf / Codeium)."""
    content = _generate_claude_md(profile)
    name = profile.root.name
    return content.replace(f"# {name}", f"# Rules for {name}", 1)


def _generate_clinerules(profile: ProjectProfile) -> str:
    """Generate .clinerules format (Cline)."""
    content = _generate_claude_md(profile)
    name = profile.root.name
    return content.replace(f"# {name}", f"# Rules for {name}", 1)


def _generate_gemini_md(profile: ProjectProfile) -> str:
    """Generate GEMINI.md format.

    Gemini CLI reads ``GEMINI.md`` as its project instruction file, the same
    role CLAUDE.md plays for Claude Code, so the canonical project-named
    document is used as-is.
    """
    return _generate_claude_md(profile)


def _generate_zed_rules(profile: ProjectProfile) -> str:
    """Generate Zed's ``.rules`` format.

    Zed's agent looks for a project ``.rules`` file first (ahead of
    ``.cursorrules`` / ``AGENTS.md`` / ``CLAUDE.md``), so it gets the same plain
    rules document with a "Rules for ..." heading like the other dotfile formats.
    """
    content = _generate_claude_md(profile)
    name = profile.root.name
    return content.replace(f"# {name}", f"# Rules for {name}", 1)


def _generate_aider_conventions(profile: ProjectProfile) -> str:
    """Generate Aider's ``CONVENTIONS.md`` format.

    Aider reads a project ``CONVENTIONS.md`` as its coding-guidelines file (added
    to the chat via ``read: CONVENTIONS.md`` in ``.aider.conf.yml``), so it gets
    the canonical project document as-is, like the other tool-agnostic formats.
    """
    return _generate_claude_md(profile)


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
        "agents": ("AGENTS.md", _generate_agents_md),
        "windsurf": (".windsurfrules", _generate_windsurfrules),
        "cline": (".clinerules", _generate_clinerules),
        "gemini": ("GEMINI.md", _generate_gemini_md),
        "zed": (".rules", _generate_zed_rules),
        "aider": ("CONVENTIONS.md", _generate_aider_conventions),
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
