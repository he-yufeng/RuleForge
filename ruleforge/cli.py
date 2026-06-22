"""CLI interface for RuleForge."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ruleforge.analyzer import analyze_project
from ruleforge.audit import audit_project
from ruleforge.generator import RuleFormat, generate_rules, write_rules
from ruleforge.lint import lint_rules

console = Console()

ALL_FORMATS: list[RuleFormat] = [
    "claude",
    "cursor",
    "copilot",
    "agents",
    "windsurf",
    "cline",
    "gemini",
    "zed",
]


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
    type=click.Choice(
        ["claude", "cursor", "copilot", "agents", "windsurf", "cline", "gemini", "zed", "all"]
    ),
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
    type=click.Choice(
        ["claude", "cursor", "copilot", "agents", "windsurf", "cline", "gemini", "zed"]
    ),
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


@main.command()
@click.argument("project_dir", default=".", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json", "sarif"]),
    default="table",
    help="Output format.",
)
@click.option(
    "--min-score",
    default=0,
    show_default=True,
    help="Exit with code 1 if the audit score is below this percentage.",
)
def audit(project_dir: str, output_format: str, min_score: int):
    """Audit existing assistant rules for missing project guidance."""
    report = audit_project(project_dir)

    if output_format == "json":
        click.echo(report.to_json())
    elif output_format == "sarif":
        click.echo(report.to_sarif())
    else:
        files = [str(path.relative_to(report.root)) for path in report.files]
        console.print(
            f"[bold]Rule audit:[/bold] {report.percentage}% ({report.score}/{report.max_score})"
        )
        console.print(f"[bold]Files:[/bold] {', '.join(files) if files else '-'}")
        console.print()

        table = Table(show_lines=True)
        table.add_column("Check", style="bold cyan")
        table.add_column("Weight", justify="right")
        table.add_column("Status")
        table.add_column("Detail")
        for check in report.checks:
            status = "[green]pass[/green]" if check.passed else "[red]missing[/red]"
            table.add_row(check.name, str(check.weight), status, check.detail)
        console.print(table)

    if min_score and report.percentage < min_score:
        raise click.ClickException(
            f"Rule audit score {report.percentage}% is below --min-score {min_score}%."
        )


@main.command()
@click.argument("project_dir", default=".", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format.",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Treat warnings as errors when setting the exit code.",
)
def lint(project_dir: str, output_format: str, strict: bool):
    """Lint existing assistant rules for placeholders, conflicts, and stale advice."""
    report = lint_rules(project_dir)

    if output_format == "json":
        click.echo(report.to_json())
    else:
        files = [path.name for path in report.files]
        console.print(f"[bold]Rule lint:[/bold] {', '.join(files) if files else 'no rule files'}")
        if not report.findings:
            console.print("[green]No problems found.[/green]")
        else:
            table = Table(show_lines=True)
            table.add_column("Severity")
            table.add_column("Rule", style="bold cyan")
            table.add_column("Message")
            for finding in report.findings:
                color = "red" if finding.severity == "error" else "yellow"
                table.add_row(
                    f"[{color}]{finding.severity}[/{color}]",
                    finding.rule_id,
                    finding.message,
                )
            console.print(table)
        console.print(
            f"\n[dim]{len(report.errors)} error(s), {len(report.warnings)} warning(s)[/dim]"
        )

    failed = report.errors or (strict and report.warnings)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
