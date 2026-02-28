# GitHub Projects API

## Overview

GitHub Projects v2 is a flexible project management tool integrated with GitHub
issues and pull requests. It supports custom fields, multiple views, built-in
automations, and both GraphQL and REST APIs. Projects v2 supports up to 50,000
items per project.

## Projects v2 REST API (GA September 2025)

### Creating and Managing Projects

```bash
# Create a project
gh project create --owner @me --title "Dev Board"

# List projects for a user
gh api users/{username}/projects --jq '.[].title'

# List projects for an organization
gh api orgs/{org}/projects --jq '.[] | {title, number}'

# Get project details
gh project view {project-number} --owner @me --format json

# Edit project
gh project edit {project-number} --owner @me --title "New Title"

# Close project
gh project close {project-number} --owner @me

# Delete project
gh project delete {project-number} --owner @me
```

### Adding and Managing Items

```bash
# Add issue to project
gh project item-add {project-number} --owner @me \
  --url https://github.com/{owner}/{repo}/issues/{number}

# Add PR to project
gh project item-add {project-number} --owner @me \
  --url https://github.com/{owner}/{repo}/pull/{number}

# Add draft item (no linked issue)
gh project item-create {project-number} --owner @me \
  --title "Draft task" --body "Task description"

# List items
gh project item-list {project-number} --owner @me --format json

# Remove item
gh project item-delete {project-number} --owner @me --id {item-id}

# Archive item
gh project item-archive {project-number} --owner @me --id {item-id}
```

### Setting Field Values

```bash
# Set a single-select field
gh project item-edit --project-id {project-id} --id {item-id} \
  --field-id {field-id} --single-select-option-id {option-id}

# Set a text field
gh project item-edit --project-id {project-id} --id {item-id} \
  --field-id {field-id} --text "Value"

# Set a number field
gh project item-edit --project-id {project-id} --id {item-id} \
  --field-id {field-id} --number 5

# Set a date field
gh project item-edit --project-id {project-id} --id {item-id} \
  --field-id {field-id} --date "2026-03-15"
```

## Custom Fields

### Field Types

| Type | Description | Use Case |
|---|---|---|
| Text | Free-form text | Notes, descriptions |
| Number | Numeric values | Story points, priority |
| Date | Date picker | Due dates, milestones |
| Single select | Dropdown options | Status, category |
| Iteration | Sprint/iteration | Sprint planning |

### Managing Custom Fields

```bash
# List fields in a project
gh project field-list {project-number} --owner @me --format json

# Create a single-select field
gh project field-create {project-number} --owner @me \
  --name "Priority" --data-type SINGLE_SELECT

# Delete a field
gh project field-delete --id {field-id}
```

## Views

### View Types

- **Table** - spreadsheet-like view with sorting and filtering
- **Board** - Kanban-style columns (e.g., Todo, In Progress, Done)
- **Roadmap** - timeline view using date fields

### View Configuration via GraphQL

```graphql
mutation {
  updateProjectV2View(input: {
    projectId: "PVT_..."
    viewId: "PVTV_..."
    layout: BOARD_LAYOUT
    sortBy: {
      field: PRIORITY
      direction: ASC
    }
  }) {
    projectV2View {
      id
      name
    }
  }
}
```

### Filtering Items

```bash
# Filter by label in table view
gh project item-list {project-number} --owner @me \
  --format json | jq '[.items[] | select(.labels | contains(["bug"]))]'
```

## Built-in Automations

### Auto-Status

Move items between columns based on PR state:

- PR opened -> "In Progress"
- PR merged -> "Done"
- PR closed -> "Closed"

### Auto-Add

Automatically add new issues matching a filter:

```
# Auto-add all bugs
is:issue label:bug
```

### Auto-Archive

Archive items in "Done" after N days (configurable, default 14).

## Workflows and Actions Integration

### Syncing Project Status with CI

```yaml
# .github/workflows/project-sync.yml
name: Update Project Status
on:
  pull_request:
    types: [opened, closed, merged]

permissions:
  contents: read
  repository-projects: write

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - name: Move to In Progress
        if: github.event.action == 'opened'
        run: |
          gh project item-edit \
            --project-id $PROJECT_ID \
            --id $ITEM_ID \
            --field-id $STATUS_FIELD_ID \
            --single-select-option-id $IN_PROGRESS_ID
        env:
          GH_TOKEN: ${{ secrets.PROJECT_TOKEN }}
```

### Sprint Automation

```python
import subprocess
import json

def get_sprint_items(project_number: int, owner: str) -> list[dict]:
    """Get all items in the current sprint iteration."""
    result = subprocess.run(
        [
            "gh", "project", "item-list",
            str(project_number),
            "--owner", owner,
            "--format", "json",
        ],
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    return data.get("items", [])


def calculate_velocity(items: list[dict]) -> int:
    """Calculate sprint velocity from completed story points."""
    total = 0
    for item in items:
        if item.get("status") == "Done":
            total += item.get("story_points", 0)
    return total
```

## Webhooks

### Project Events

```
projects_v2_item.created    # Item added to project
projects_v2_item.edited     # Item field values changed
projects_v2_item.deleted    # Item removed from project
projects_v2_item.archived   # Item archived
projects_v2_item.restored   # Item unarchived
```

### Webhook Payload Processing

```python
import json
from dataclasses import dataclass

@dataclass
class ProjectEvent:
    action: str
    item_id: str
    project_id: str
    changes: dict

def parse_webhook(payload: str) -> ProjectEvent:
    """Parse a GitHub Projects webhook payload."""
    data = json.loads(payload)
    return ProjectEvent(
        action=data["action"],
        item_id=data["projects_v2_item"]["id"],
        project_id=data["projects_v2_item"]["project_node_id"],
        changes=data.get("changes", {}),
    )
```

## Issue Types REST API (GA March 2025)

### Managing Issue Types

```bash
# List organization issue types
gh api orgs/{org}/issue-types

# Create issue type
gh api orgs/{org}/issue-types --method POST \
  -f name="Epic" \
  -f description="Large feature grouping" \
  -f color="blue"

# Update issue type
gh api orgs/{org}/issue-types/{type-id} --method PATCH \
  -f name="Story" \
  -f description="User story"

# Delete issue type
gh api orgs/{org}/issue-types/{type-id} --method DELETE
```

### Issue Types in Templates

Issue form templates can auto-set the type via the `type:` YAML key:

```yaml
# .github/ISSUE_TEMPLATE/bug_report.yml
name: Bug Report
description: Report a bug
type: Bug
body:
  - type: textarea
    id: description
    attributes:
      label: Description
    validations:
      required: true
```

## Sub-Issues (GA 2025)

### Creating Sub-Issues

```bash
# Add sub-issue to parent
gh api repos/{owner}/{repo}/issues/{parent}/sub_issues --method POST \
  -f sub_issue_id={child-issue-id}

# List sub-issues
gh api repos/{owner}/{repo}/issues/{parent}/sub_issues

# Remove sub-issue
gh api repos/{owner}/{repo}/issues/{parent}/sub_issues/{child} --method DELETE
```

### Tracking Progress

Sub-issues enable hierarchical task tracking:

```
Epic: Implement Authentication (#100)
  Story: OAuth2 provider (#101)      [Done]
  Story: JWT token handling (#102)    [In Progress]
  Story: Session management (#103)    [Todo]
Progress: 1/3 (33%)
```

## Best Practices

1. **Use single-select for status** - avoid free-text status fields
2. **Set up auto-add rules** - reduce manual project maintenance
3. **Use iterations for sprints** - track velocity over time
4. **Link PRs to project items** - maintain traceability
5. **Use views for stakeholders** - board for developers, roadmap for managers
6. **Archive completed items** - keep active view clean
7. **Automate via Actions** - sync CI/CD status with project state

## Quick Reference

| Operation | Command |
|---|---|
| Create project | `gh project create --owner @me --title "Name"` |
| Add item | `gh project item-add {num} --owner @me --url {url}` |
| List items | `gh project item-list {num} --owner @me` |
| Edit field | `gh project item-edit --project-id {id} --id {id} ...` |
| List fields | `gh project field-list {num} --owner @me` |
