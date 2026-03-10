"""RuleForge - Generate AI assistant rules from codebase analysis."""

__version__ = "0.1.0"

from ruleforge.analyzer import analyze_project
from ruleforge.generator import generate_rules

__all__ = ["analyze_project", "generate_rules"]
