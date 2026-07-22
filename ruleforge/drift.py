"""Drift detection: have the committed rules fallen behind the project?

``lint`` flags guidance that is actively wrong; this module flags the quieter
failure — the project moved on (new test runner, new package manager, new
framework, CI added) and the rules never caught up. An assistant then follows
last year's stack: installs with pip when the repo is on poetry, runs unittest
when the suite is pytest. ``ruleforge check`` is the CI gate for that.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruleforge.analyzer import analyze_project
from ruleforge.audit import find_rule_files


@dataclass
class DriftFinding:
    """One detected stack item the rules do not mention."""

    rule_id: str
    severity: str  # "error" | "warning"
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "severity": self.severity, "message": self.message}


@dataclass
class DriftReport:
    root: Path
    rule_file: Path | None
    findings: list[DriftFinding] = field(default_factory=list)

    @property
    def drifted(self) -> bool:
        return any(f.severity == "error" for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "rule_file": str(self.rule_file) if self.rule_file else None,
            "drifted": self.drifted,
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _mentions_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def _mentions_item(text: str, name: str) -> bool:
    """Match a stack item against rule text, tolerating dash/space style."""
    lowered = name.lower()
    if _mentions_word(text, lowered):
        return True
    # "github-actions" -> "github actions", "package-lock" -> "package lock"
    spaced = re.sub(r"[-_]", " ", lowered)
    return spaced != lowered and _mentions_word(text, spaced)


def check_drift(project_dir: str | Path, rule_file: str | Path | None = None) -> DriftReport:
    """Compare the project's current stack against what the rules mention.

    Checks the items an assistant actually acts on: primary language, package
    manager, test framework, linter, formatter, frameworks, and CI. A missing
    mention is drift. Errors (language/package manager/test framework) fail
    the check; the rest are warnings.
    """
    profile = analyze_project(project_dir)

    if rule_file is not None:
        chosen = Path(rule_file)
    else:
        candidates = find_rule_files(profile.root)
        chosen = candidates[0].path if candidates else None  # type: ignore[assignment]

    report = DriftReport(root=profile.root, rule_file=chosen)
    if chosen is None or not chosen.is_file():
        report.findings.append(
            DriftFinding(
                rule_id="missing-rules",
                severity="error",
                message="No rule file found to check. Run `ruleforge generate` first.",
            )
        )
        return report

    text = chosen.read_text(encoding="utf-8", errors="replace").lower()

    def add(rule_id: str, severity: str, message: str) -> None:
        report.findings.append(DriftFinding(rule_id=rule_id, severity=severity, message=message))

    if profile.languages:
        language = max(profile.languages, key=profile.languages.get)
        if not _mentions_item(text, language):
            add(
                "language-drift",
                "error",
                f"This is primarily a {language} project, but the rules never say so.",
            )

    if profile.package_manager and not _mentions_item(text, profile.package_manager):
        add(
            "package-manager-drift",
            "error",
            f"Dependencies are managed with {profile.package_manager}, "
            "but the rules never mention it.",
        )

    if profile.test_framework and not _mentions_item(text, profile.test_framework):
        add(
            "test-framework-drift",
            "error",
            f"Tests run on {profile.test_framework}, but the rules never mention it.",
        )

    if profile.linter and not _mentions_item(text, profile.linter):
        add(
            "linter-drift",
            "warning",
            f"The project lints with {profile.linter}, but the rules never mention it.",
        )

    if profile.formatter and not _mentions_item(text, profile.formatter):
        add(
            "formatter-drift",
            "warning",
            f"The project formats with {profile.formatter}, but the rules never mention it.",
        )

    for framework in profile.frameworks:
        if not _mentions_item(text, framework):
            add(
                "framework-drift",
                "warning",
                f"The project uses {framework}, but the rules never mention it.",
            )

    if profile.has_ci and profile.ci_system and not _mentions_item(text, profile.ci_system):
        add(
            "ci-drift",
            "warning",
            f"CI runs on {profile.ci_system}, but the rules never mention it.",
        )

    return report
