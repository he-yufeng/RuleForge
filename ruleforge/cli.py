"""CLI interface for RuleForge."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ruleforge.analyzer import analyze_project
from ruleforge.generator import RuleFormat, generate_rules, write_rules

console = Console()

ALL_FORMATS: list[RuleFormat] = ["claude", "cursor", "copilot"]


@click.group()
@click.version_option()
def main():
    """RuleForge - Generate AI assistant rules from your codebase."""
    pass


@main.command()
@click.argument("project_dir", default=".", type=click.Path(exists=True, file_okay=False))
def scan(project_dir: str):
    """Analyze a project and show what was detected."""
    profile = analyze_project(project_dir)

    table = Table(title=f"Project: {profile.root.name}", show_lines=True)
    table.add_column("Property", style="bold cyan")
    table.add_column("Value")

    if profile.languages:
        lang_str = ", ".join(f"{k} ({v} files)" for k, v in profile.languages.items())
        table.add_row("Languages", lang_str)
    if profile.frameworks:
        table.add_row("Frameworks", ", ".join(profile.frameworks))
    if profile.package_manager:
        table.add_row("Package Manager", profile.package_manager)
    if profile.test_framework:
        table.add_row("Test Framework", profile.test_framework)
    if profile.linter:
        table.add_row("Linter", profile.linter)
    if profile.formatter:
        table.add_row("Formatter", profile.formatter)
    if profile.has_ci:
        table.add_row("CI", profile.ci_system or "Yes")
    if profile.has_docker:
        table.add_row("Docker", "Yes")
    if profile.source_dirs:
        table.add_row("Source Dirs", ", ".join(profile.source_dirs))
    if profile.entry_points:
        table.add_row("Entry Points", ", ".join(profile.entry_points))
    if profile.monorepo:
        table.add_row("Monorepo", "Yes")
    if profile.python_version:
        table.add_row("Python Version", profile.python_version)
    if profile.node_version:
        table.add_row("Node Version", profile.node_version)
    existing = profile.extra.get("existing_rules", [])
    if existing:
        table.add_row("Existing Rules", ", ".join(existing))

    console.print(table)


@main.command()
@click.argument("project_dir", default=".", type=click.Path(exists=True, file_okay=False))
@click.option(
    "-f",
    "--format",
    "formats",
    multiple=True,
    type=click.Choice(["claude", "cursor", "copilot", "all"]),
    default=["all"],
    help="Output format(s). Use 'all' for everything.",
)
@click.option("--overwrite", is_flag=True, help="Overwrite existing rule files.")
@click.option("--dry-run", is_flag=True, help="Preview without writing files.")
@click.option("-o", "--output", type=click.Path(), help="Output directory (default: project dir).")
def generate(
    project_dir: str,
    formats: tuple[str, ...],
    overwrite: bool,
    dry_run: bool,
    output: str | None,
):
    """Generate AI assistant rule files for a project."""
    profile = analyze_project(project_dir)

    # resolve formats
    fmt_list: list[RuleFormat] = []
    if "all" in formats:
        fmt_list = ALL_FORMATS[:]
    else:
        fmt_list = list(formats)  # type: ignore

    rules = generate_rules(profile, fmt_list)

    if not rules:
        console.print("[yellow]No rules generated.[/yellow]")
        return

    out_dir = Path(output) if output else profile.root

    if dry_run:
        for rule in rules:
            console.print(Panel(rule.content, title=rule.filename, border_style="green"))
        console.print(f"\n[dim]Dry run: {len(rules)} file(s) would be written to {out_dir}[/dim]")
        return

    written = write_rules(rules, out_dir, overwrite=overwrite)

    if written:
        console.print(f"[green]Wrote {len(written)} file(s):[/green]")
        for p in written:
            console.print(f"  {p}")
    else:
        skipped = [r.filename for r in rules if (out_dir / r.filename).exists()]
        if skipped:
            console.print(
                f"[yellow]Skipped {len(skipped)} existing file(s): {', '.join(skipped)}[/yellow]"
            )
            console.print("[dim]Use --overwrite to replace them.[/dim]")


@main.command()
@click.argument("project_dir", default=".", type=click.Path(exists=True, file_okay=False))
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(["claude", "cursor", "copilot"]),
    default="claude",
    help="Which format to preview.",
)
def preview(project_dir: str, fmt: str):
    """Preview generated rules without writing anything."""
    profile = analyze_project(project_dir)
    rules = generate_rules(profile, [fmt])  # type: ignore
    if rules:
        # just print raw so it's easy to pipe
        click.echo(rules[0].content)


if __name__ == "__main__":
    main()
