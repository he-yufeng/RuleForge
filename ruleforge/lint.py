"""Lint existing AI assistant rule files for quality problems.

Where ``audit`` measures how much guidance a rule file covers, ``lint`` looks for
guidance that is actively wrong or unusable: leftover template placeholders,
contradictory tool directives, and advice that no longer matches the repository.
These are the failures that quietly send an AI agent down the wrong path.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruleforge.analyzer import analyze_project
from ruleforge.audit import RuleFile, find_rule_files

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

# Groups of tools that are mutually exclusive in practice: a project picks one.
# Recommending two of them in the same rule file gives the agent conflicting orders.
_PACKAGE_MANAGER_GROUPS: tuple[tuple[str, ...], ...] = (
    ("npm", "yarn", "pnpm", "bun"),
    ("poetry", "pipenv", "pdm"),
)
_TEST_FRAMEWORK_GROUPS: tuple[tuple[str, ...], ...] = (
    ("pytest", "unittest", "nose"),
    ("jest", "vitest", "mocha", "jasmine", "ava"),
)
# Linters that compete within one language ecosystem: a project standardizes on
# one, so rules that still name the old one after a switch (e.g. flake8 -> ruff)
# point the assistant at a tool the repo no longer runs.
_LINTER_GROUPS: tuple[tuple[str, ...], ...] = (
    ("ruff", "flake8", "pylint", "pycodestyle"),
    ("eslint", "biome"),
)
# Formatters that compete within one ecosystem. ``ruff`` and ``biome`` appear in
# both their linter and formatter groups because each tool fills both roles.
_FORMATTER_GROUPS: tuple[tuple[str, ...], ...] = (
    ("black", "ruff", "autopep8", "yapf"),
    ("prettier", "biome"),
)
# Frameworks that compete within one category — a project picks one web or one
# core frontend framework, so rules naming a different one in the same category
# point the assistant at a stack the repo does not use. Meta-frameworks layered
# on top (Next.js, SvelteKit, Express) are intentionally excluded: they coexist
# with their base framework, so flagging them would be a false positive.
_FRAMEWORK_GROUPS: tuple[tuple[str, ...], ...] = (
    ("django", "flask", "fastapi"),
    ("react", "vue", "svelte", "angular"),
)

# Placeholder markers that mean a template was never filled in.
_PLACEHOLDER_WORDS = re.compile(r"\b(TODO|FIXME|XXX|HACK|TBD)\b")
_PLACEHOLDER_MUSTACHE = re.compile(r"\{\{[^}]+\}\}")
# Lowercase multi-word angle placeholders such as ``<your project name>``.
# Single-word angle content (``<details>``, ``<T>``) is left alone so real HTML
# and generics do not trip the check.
_PLACEHOLDER_ANGLE = re.compile(r"<[a-z][a-z0-9 _/-]*\s[a-z0-9 _/-]+>")


@dataclass
class LintFinding:
    rule_id: str
    severity: str
    message: str
    file: str | None = None
    line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
        }
        if self.file is not None:
            data["file"] = self.file
        if self.line is not None:
            data["line"] = self.line
        return data


@dataclass
class RuleLintReport:
    root: Path
    files: list[Path]
    findings: list[LintFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity == SEVERITY_WARNING]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "files": [path.name for path in self.files],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [finding.to_dict() for finding in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def lint_rules(project_dir: str | Path) -> RuleLintReport:
    """Lint AI assistant rule files for a project."""
    profile = analyze_project(project_dir)
    rule_files = find_rule_files(profile.root)

    findings: list[LintFinding] = []
    findings.extend(_check_placeholders(profile.root, rule_files))

    text = "\n\n".join(rule.content for rule in rule_files)
    lowered = text.lower()
    findings.extend(
        _check_tool_groups(
            category="package manager",
            rule_id="package-manager",
            groups=_PACKAGE_MANAGER_GROUPS,
            detected=profile.package_manager,
            lowered=lowered,
        )
    )
    findings.extend(
        _check_tool_groups(
            category="test framework",
            rule_id="test-framework",
            groups=_TEST_FRAMEWORK_GROUPS,
            detected=profile.test_framework,
            lowered=lowered,
        )
    )
    findings.extend(
        _check_tool_groups(
            category="linter",
            rule_id="linter",
            groups=_LINTER_GROUPS,
            detected=profile.linter,
            lowered=lowered,
        )
    )
    findings.extend(
        _check_tool_groups(
            category="formatter",
            rule_id="formatter",
            groups=_FORMATTER_GROUPS,
            detected=profile.formatter,
            lowered=lowered,
        )
    )
    findings.extend(
        _check_framework_groups(
            rule_id="framework",
            groups=_FRAMEWORK_GROUPS,
            detected=profile.frameworks,
            lowered=lowered,
        )
    )

    return RuleLintReport(
        root=profile.root,
        files=[rf.path for rf in rule_files],
        findings=findings,
    )


def _check_placeholders(root: Path, rule_files: list[RuleFile]) -> list[LintFinding]:
    findings: list[LintFinding] = []
    for rule in rule_files:
        try:
            name = rule.path.relative_to(root).as_posix()
        except ValueError:
            name = rule.path.name
        for lineno, line in enumerate(rule.content.splitlines(), start=1):
            marker = _find_placeholder(line)
            if marker is None:
                continue
            findings.append(
                LintFinding(
                    rule_id="placeholder",
                    severity=SEVERITY_ERROR,
                    message=(
                        f"Unfilled template placeholder {marker!r} in {name}:{lineno}. "
                        "Replace it with real project guidance or remove the line."
                    ),
                    file=name,
                    line=lineno,
                )
            )
    return findings


def _find_placeholder(line: str) -> str | None:
    for pattern in (_PLACEHOLDER_WORDS, _PLACEHOLDER_MUSTACHE, _PLACEHOLDER_ANGLE):
        match = pattern.search(line)
        if match:
            return match.group(0)
    return None


def _check_tool_groups(
    category: str,
    rule_id: str,
    groups: tuple[tuple[str, ...], ...],
    detected: str | None,
    lowered: str,
) -> list[LintFinding]:
    findings: list[LintFinding] = []
    detected_lower = detected.lower() if detected else None

    for group in groups:
        mentioned = [tool for tool in group if _mentions_word(lowered, tool)]
        if len(mentioned) > 1:
            findings.append(
                LintFinding(
                    rule_id=f"{rule_id}-conflict",
                    severity=SEVERITY_WARNING,
                    message=(
                        f"Rules recommend multiple competing {category}s: "
                        f"{', '.join(mentioned)}. Pick one so the assistant is not "
                        "given conflicting instructions."
                    ),
                )
            )

        if detected_lower and detected_lower in group:
            stale = [tool for tool in mentioned if tool != detected_lower]
            if stale and detected_lower not in mentioned:
                findings.append(
                    LintFinding(
                        rule_id=f"{rule_id}-stale",
                        severity=SEVERITY_WARNING,
                        message=(
                            f"Rules mention the {category} {', '.join(stale)}, but this repo "
                            f"uses {detected}. Update the rules to match the detected stack."
                        ),
                    )
                )

    return findings


def _check_framework_groups(
    rule_id: str,
    groups: tuple[tuple[str, ...], ...],
    detected: list[str],
    lowered: str,
) -> list[LintFinding]:
    """Flag rules that name a framework the repo does not use.

    Unlike the single-tool checks, a project can legitimately use several
    frameworks (a frontend plus a backend), so we only flag within a group of
    mutually-exclusive frameworks: if the repo uses one from the group and the
    rules mention a *different* one from the same group, that mention is stale.
    """
    findings: list[LintFinding] = []
    for group in groups:
        present = [fw for fw in detected if fw.lower() in group]
        if not present:
            continue  # repo uses nothing from this category -> nothing to compare
        present_lower = {fw.lower() for fw in present}
        stale = [fw for fw in group if fw not in present_lower and _mentions_word(lowered, fw)]
        if stale:
            findings.append(
                LintFinding(
                    rule_id=f"{rule_id}-stale",
                    severity=SEVERITY_WARNING,
                    message=(
                        f"Rules mention the framework {', '.join(stale)}, but this repo "
                        f"uses {', '.join(present)}. Update the rules to match the detected stack."
                    ),
                )
            )
    return findings


def _mentions_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None
