"""GitHub Issue forms, PR templates, and Dependabot configuration generators.

Epic 19: Generate structured GitHub Issue form templates, PR templates,
and Dependabot configuration as part of ``tapps_init``. Makes repositories
machine-parseable for AI agents and establishes consistent contribution
patterns.

Called from ``pipeline.init._setup_platform`` to create ``.github/``
configuration artifacts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Issue Form Templates (YAML-defined structured forms)
# ---------------------------------------------------------------------------

_BUG_REPORT_FORM = """\
name: Bug Report
description: Report a bug or unexpected behavior
type: Bug
labels: ["bug", "triage"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for reporting a bug! Please fill out the sections below
        so we can reproduce and fix the issue.

  - type: input
    id: version
    attributes:
      label: Version
      description: What version are you using?
      placeholder: e.g. 1.2.3
    validations:
      required: true

  - type: dropdown
    id: environment
    attributes:
      label: Environment
      description: Where does the issue occur?
      options:
        - Local development
        - CI/CD pipeline
        - Docker container
        - Production
    validations:
      required: true

  - type: textarea
    id: description
    attributes:
      label: Description
      description: A clear description of the bug
      placeholder: What happened? What did you expect to happen?
    validations:
      required: true

  - type: textarea
    id: reproduction
    attributes:
      label: Steps to Reproduce
      description: Minimal steps to reproduce the behavior
      placeholder: |
        1. Run '...'
        2. Edit '...'
        3. See error
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: Expected Behavior
      description: What should have happened instead?
    validations:
      required: true

  - type: textarea
    id: logs
    attributes:
      label: Logs / Error Output
      description: Paste any relevant logs or error output
      render: shell

  - type: dropdown
    id: severity
    attributes:
      label: Severity
      options:
        - Low — cosmetic or minor inconvenience
        - Medium — workaround available
        - High — blocks workflow
        - Critical — data loss or security issue
    validations:
      required: true

  - type: checkboxes
    id: checklist
    attributes:
      label: Pre-submission checklist
      options:
        - label: I searched existing issues and this is not a duplicate
          required: true
        - label: I can reproduce this on the latest version
          required: false
"""

_FEATURE_REQUEST_FORM = """\
name: Feature Request
description: Suggest a new feature or enhancement
type: Feature
labels: ["enhancement"]
body:
  - type: markdown
    attributes:
      value: |
        Have an idea for a new feature? Describe it below.

  - type: textarea
    id: problem
    attributes:
      label: Problem Statement
      description: What problem does this feature solve?
      placeholder: I'm always frustrated when...
    validations:
      required: true

  - type: textarea
    id: solution
    attributes:
      label: Proposed Solution
      description: Describe your ideal solution
    validations:
      required: true

  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives Considered
      description: What other approaches did you consider?

  - type: dropdown
    id: scope
    attributes:
      label: Scope
      options:
        - Small — single file or function change
        - Medium — multiple files, backward compatible
        - Large — new module or breaking change
    validations:
      required: true

  - type: checkboxes
    id: checklist
    attributes:
      label: Pre-submission checklist
      options:
        - label: I searched existing issues and this is not a duplicate
          required: true
        - label: I am willing to contribute a PR for this feature
          required: false
"""

_TASK_FORM = """\
name: Task
description: Track a development task or chore
type: Task
labels: ["task"]
body:
  - type: textarea
    id: description
    attributes:
      label: Task Description
      description: What needs to be done?
    validations:
      required: true

  - type: textarea
    id: acceptance
    attributes:
      label: Acceptance Criteria
      description: How do we know this task is complete?
      placeholder: |
        - [ ] Criterion 1
        - [ ] Criterion 2
    validations:
      required: true

  - type: dropdown
    id: priority
    attributes:
      label: Priority
      options:
        - P0 — Critical path
        - P1 — High
        - P2 — Medium
        - P3 — Low / nice-to-have
    validations:
      required: true

  - type: input
    id: estimate
    attributes:
      label: Estimated Effort
      description: Rough estimate of effort
      placeholder: e.g. 2 hours, 1 day, 1 week
"""

# ---------------------------------------------------------------------------
# Issue Template Config (disables blank issues)
# ---------------------------------------------------------------------------

_ISSUE_CONFIG = """\
blank_issues_enabled: false
contact_links:
  - name: Documentation
    url: https://github.com/{owner}/{repo}#readme
    about: Read the project documentation before opening an issue
"""

# ---------------------------------------------------------------------------
# PR Template
# ---------------------------------------------------------------------------

_PR_TEMPLATE = """\
## Summary

<!-- 1-3 bullet points describing what this PR does -->

-

## Changes

<!-- List the key changes made -->

-

## Test Plan

<!-- How was this tested? Include commands, screenshots, or test output -->

- [ ] Tests pass locally (`uv run pytest tests/ -v`)
- [ ] Linting passes (`uv run ruff check src/`)
- [ ] Type checking passes (`uv run mypy --strict src/`)

## Breaking Changes

<!-- List any breaking changes, or write "None" -->

None

## Checklist

- [ ] Code follows project style guidelines
- [ ] Self-review of code completed
- [ ] Tests added for new functionality
- [ ] Documentation updated if needed
"""

# ---------------------------------------------------------------------------
# Dependabot Configuration
# ---------------------------------------------------------------------------

_DEPENDABOT_CONFIG = """\
# Dependabot configuration — generated by TappsMCP tapps_init
# See: https://docs.github.com/en/code-security/dependabot/dependabot-version-updates
version: 2
updates:
  # Python dependencies (pip ecosystem covers uv/pip/pyproject.toml)
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 10
    labels:
      - "dependencies"
      - "automated"
    groups:
      # Group all minor/patch security updates into a single PR
      security-updates:
        applies-to: security-updates
        patterns:
          - "*"
      # Group minor/patch version updates to reduce PR noise
      minor-and-patch:
        applies-to: version-updates
        update-types:
          - "minor"
          - "patch"

  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "ci"
    groups:
      actions-updates:
        patterns:
          - "*"
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_issue_templates(project_root: Path) -> dict[str, Any]:
    """Generate GitHub Issue form templates in ``.github/ISSUE_TEMPLATE/``.

    Creates structured YAML issue forms for bug reports, feature requests,
    and tasks. Also writes ``config.yml`` to disable blank issues.

    Returns a summary dict with ``files`` and ``action``.
    """
    template_dir = project_root / ".github" / "ISSUE_TEMPLATE"
    template_dir.mkdir(parents=True, exist_ok=True)

    files_written: list[str] = []

    templates = {
        "bug-report.yml": _BUG_REPORT_FORM,
        "feature-request.yml": _FEATURE_REQUEST_FORM,
        "task.yml": _TASK_FORM,
        "config.yml": _ISSUE_CONFIG,
    }

    for filename, content in templates.items():
        target = template_dir / filename
        target.write_text(content, encoding="utf-8")
        files_written.append(str(target.relative_to(project_root)))

    return {"files": files_written, "action": "created", "count": len(files_written)}


def generate_pr_template(project_root: Path) -> dict[str, Any]:
    """Generate ``.github/PULL_REQUEST_TEMPLATE.md``.

    Returns a summary dict with ``file`` and ``action``.
    """
    github_dir = project_root / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)
    target = github_dir / "PULL_REQUEST_TEMPLATE.md"
    target.write_text(_PR_TEMPLATE, encoding="utf-8")
    return {"file": str(target.relative_to(project_root)), "action": "created"}


def generate_dependabot_config(project_root: Path) -> dict[str, Any]:
    """Generate ``.github/dependabot.yml`` with ecosystem auto-detection.

    Always includes ``pip`` and ``github-actions`` ecosystems. The pip
    ecosystem covers uv, pip, and pyproject.toml based projects.

    Returns a summary dict with ``file`` and ``action``.
    """
    github_dir = project_root / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)
    target = github_dir / "dependabot.yml"
    target.write_text(_DEPENDABOT_CONFIG, encoding="utf-8")
    return {"file": str(target.relative_to(project_root)), "action": "created"}


def generate_all_github_templates(project_root: Path) -> dict[str, Any]:
    """Generate all GitHub templates (issues, PR, Dependabot).

    Convenience function that calls all individual generators and
    aggregates results.

    Returns a summary dict with sub-results for each template type.
    """
    results: dict[str, Any] = {}
    results["issue_templates"] = generate_issue_templates(project_root)
    results["pr_template"] = generate_pr_template(project_root)
    results["dependabot"] = generate_dependabot_config(project_root)

    total_files = (
        results["issue_templates"]["count"]
        + 1  # PR template
        + 1  # dependabot.yml
    )
    results["total_files"] = total_files
    results["success"] = True
    return results
