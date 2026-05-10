"""Audit existing AI assistant rule files."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruleforge.analyzer import ProjectProfile, analyze_project

RULE_FILE_NAMES = (
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
    ".github/copilot-instructions.md",
)


@dataclass
class RuleFile:
    path: Path
    content: str


@dataclass
class AuditCheck:
    name: str
    weight: int
    passed: bool
    detail: str


@dataclass
class RuleAuditReport:
    root: Path
    files: list[Path]
    checks: list[AuditCheck] = field(default_factory=list)

    @property
    def max_score(self) -> int:
        return sum(check.weight for check in self.checks)

    @property
    def score(self) -> int:
        return sum(check.weight for check in self.checks if check.passed)

    @property
    def percentage(self) -> int:
        if self.max_score == 0:
            return 0
        return round(self.score * 100 / self.max_score)

    @property
    def missing(self) -> list[AuditCheck]:
        return [check for check in self.checks if not check.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "files": [str(path.relative_to(self.root)) for path in self.files],
            "score": self.score,
            "max_score": self.max_score,
            "percentage": self.percentage,
            "checks": [
                {
                    "name": check.name,
                    "weight": check.weight,
                    "passed": check.passed,
                    "detail": check.detail,
                }
                for check in self.checks
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def audit_project(project_dir: str | Path) -> RuleAuditReport:
    """Audit AI assistant rules for a project."""
    profile = analyze_project(project_dir)
    rule_files = find_rule_files(profile.root)
    text = "\n\n".join(rule.content for rule in rule_files)
    checks = build_checks(profile, rule_files, text)
    return RuleAuditReport(
        root=profile.root,
        files=[rule.path for rule in rule_files],
        checks=checks,
    )


def find_rule_files(root: Path) -> list[RuleFile]:
    """Find common rule files without walking the whole repository."""
    files: list[RuleFile] = []
    for name in RULE_FILE_NAMES:
        path = root / name
        if path.is_file():
            files.append(_read_rule_file(path))

    cursor_rules = root / ".cursor" / "rules"
    if cursor_rules.is_dir():
        for path in sorted(cursor_rules.rglob("*.md")):
            if path.is_file():
                files.append(_read_rule_file(path))

    return files


def build_checks(
    profile: ProjectProfile,
    rule_files: list[RuleFile],
    text: str,
) -> list[AuditCheck]:
    """Build the weighted audit checklist."""
    lowered = text.lower()
    checks: list[AuditCheck] = []

    checks.append(
        AuditCheck(
            "Rule file exists",
            10,
            bool(rule_files),
            "Found at least one assistant rule file."
            if rule_files
            else "No AGENTS.md, CLAUDE.md, .cursorrules, or Copilot instructions found.",
        )
    )
    checks.append(
        AuditCheck(
            "Project context",
            10,
            _mentions_project_context(profile, lowered),
            "Mentions project identity, purpose, or codebase context."
            if _mentions_project_context(profile, lowered)
            else "Add a short project overview so the assistant knows what it is editing.",
        )
    )
    checks.append(
        AuditCheck(
            "Detected stack coverage",
            15,
            _mentions_detected_stack(profile, lowered),
            "Mentions detected languages, frameworks, or package manager."
            if _mentions_detected_stack(profile, lowered)
            else "Mention the main languages, frameworks, and package manager from this repo.",
        )
    )
    checks.append(
        AuditCheck(
            "Verification commands",
            20,
            _mentions_verification(profile, lowered),
            "Includes concrete test, lint, typecheck, or build commands."
            if _mentions_verification(profile, lowered)
            else (
                "Add concrete validation commands such as pytest, npm test, ruff, "
                "build, or CI checks."
            ),
        )
    )
    checks.append(
        AuditCheck(
            "Editing boundaries",
            10,
            _mentions_editing_boundaries(lowered),
            "Describes files or changes the assistant should avoid."
            if _mentions_editing_boundaries(lowered)
            else (
                "State the files, generated artifacts, or refactors that should "
                "not be touched casually."
            ),
        )
    )
    checks.append(
        AuditCheck(
            "Safety and secrets",
            15,
            _mentions_safety(lowered),
            "Covers secrets, tokens, credentials, or destructive operations."
            if _mentions_safety(lowered)
            else "Add explicit rules for secrets, tokens, .env files, and destructive commands.",
        )
    )
    checks.append(
        AuditCheck(
            "Git and review workflow",
            10,
            _mentions_git_workflow(lowered),
            "Mentions commits, PRs, branches, CI, or review workflow."
            if _mentions_git_workflow(lowered)
            else "Add repository workflow expectations around branches, commits, PRs, and CI.",
        )
    )
    checks.append(
        AuditCheck(
            "Agent behavior",
            10,
            _mentions_agent_behavior(lowered),
            "Sets expectations for autonomy, questions, style, or communication."
            if _mentions_agent_behavior(lowered)
            else "Explain when the assistant should act, ask, or report progress.",
        )
    )
    return checks


def _read_rule_file(path: Path) -> RuleFile:
    return RuleFile(
        path=path.resolve(),
        content=path.read_text(encoding="utf-8", errors="replace"),
    )


def _mentions_project_context(profile: ProjectProfile, text: str) -> bool:
    candidates = {profile.root.name.lower(), "project", "repo", "repository", "codebase"}
    return any(candidate and candidate in text for candidate in candidates)


def _mentions_detected_stack(profile: ProjectProfile, text: str) -> bool:
    candidates = set()
    candidates.update(lang.lower() for lang in profile.languages)
    candidates.update(framework.lower() for framework in profile.frameworks)
    if profile.package_manager:
        candidates.add(profile.package_manager.lower())
    return any(candidate in text for candidate in candidates)


def _mentions_verification(profile: ProjectProfile, text: str) -> bool:
    terms = {
        "test",
        "tests",
        "pytest",
        "unittest",
        "jest",
        "vitest",
        "lint",
        "ruff",
        "eslint",
        "typecheck",
        "mypy",
        "build",
        "ci",
    }
    if profile.test_framework:
        terms.add(profile.test_framework.lower())
    if profile.linter:
        terms.add(profile.linter.lower())
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in terms)


def _mentions_editing_boundaries(text: str) -> bool:
    terms = (
        "do not modify",
        "do not edit",
        "do not touch",
        "avoid",
        "generated",
        "lock file",
        "lockfile",
        "do not change",
        "never",
    )
    return any(term in text for term in terms)


def _mentions_safety(text: str) -> bool:
    terms = (
        "secret",
        "token",
        "credential",
        "password",
        ".env",
        "api key",
        "destructive",
        "delete",
        "remove",
        "reset --hard",
    )
    return any(term in text for term in terms)


def _mentions_git_workflow(text: str) -> bool:
    terms = ("git", "commit", "branch", "pull request", " pr ", "review", "ci", "actions")
    padded = f" {text} "
    return any(term in padded for term in terms)


def _mentions_agent_behavior(text: str) -> bool:
    terms = (
        "assistant",
        "agent",
        "ask",
        "question",
        "autonomy",
        "communicat",
        "progress",
        "style",
    )
    return any(term in text for term in terms)
