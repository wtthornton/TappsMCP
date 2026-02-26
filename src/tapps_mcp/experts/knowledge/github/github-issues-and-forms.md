# GitHub Issues and Issue Forms

## Issue Forms (YAML-Defined)

Issue forms replace freeform Markdown templates with structured YAML:

```yaml
name: Bug Report
description: Report a bug
type: Bug
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: "Thanks for reporting!"

  - type: input
    id: version
    attributes:
      label: Version
      placeholder: "e.g. 1.2.3"
    validations:
      required: true

  - type: textarea
    id: description
    attributes:
      label: Description
    validations:
      required: true

  - type: dropdown
    id: severity
    attributes:
      label: Severity
      options:
        - Critical
        - High
        - Medium
        - Low

  - type: checkboxes
    id: terms
    attributes:
      label: Acknowledgments
      options:
        - label: I searched for duplicates
          required: true
```

## Body Element Types

- `markdown` — static text, no id needed
- `input` — single-line text
- `textarea` — multi-line text, optional `render: shell` for code blocks
- `dropdown` — single or multi-select
- `checkboxes` — multiple checkboxes with required flag

## Issue Types (GA 2025)

Organization-level issue types: Bug, Feature, Task.

```bash
# List issue types
gh api orgs/{org}/issue-types

# Create issue type
gh api orgs/{org}/issue-types --method POST \
  -f name="Epic" -f description="Large feature grouping"
```

## Sub-Issues (GA 2025)

Enable parent-child hierarchies up to 8 levels deep:

```bash
# Add sub-issue
gh api repos/{owner}/{repo}/issues/{parent}/sub_issues --method POST \
  -f sub_issue_id={child_id}
```

Progress tracking via `subIssuesSummary` in the Issues API response.

## Template Configuration

`.github/ISSUE_TEMPLATE/config.yml`:

```yaml
blank_issues_enabled: false
contact_links:
  - name: Discussion Forum
    url: https://github.com/{owner}/{repo}/discussions
    about: Ask questions here
```

## Labels and Auto-Assignment

Issue forms can auto-assign labels via the `labels:` key in the template.
Projects can be linked via the `projects:` key (requires org/project-number).
