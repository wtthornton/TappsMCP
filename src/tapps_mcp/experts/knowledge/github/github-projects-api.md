# GitHub Projects API

## Projects v2

GitHub Projects v2 supports up to 50,000 items per project.

## REST API (GA September 2025)

```bash
# Create a project
gh project create --owner @me --title "Dev Board"

# List projects
gh api users/{username}/projects --jq '.[].title'

# Add issue to project
gh project item-add {project-number} --owner @me \
  --url https://github.com/{owner}/{repo}/issues/{number}
```

## Custom Fields

- **Text** — free-form text
- **Number** — numeric values (e.g., story points)
- **Date** — date fields
- **Single select** — dropdown with predefined options
- **Iteration** — sprint/iteration tracking

## Views

- **Table** — spreadsheet-like view with sorting and filtering
- **Board** — Kanban-style columns (e.g., Todo, In Progress, Done)
- **Roadmap** — timeline view with date fields

## Built-in Automations

- **Auto-status** — move items between columns based on PR state
- **Auto-add** — automatically add new issues matching a filter
- **Auto-archive** — archive items in "Done" after N days

## Webhooks

```
projects_v2_item.created
projects_v2_item.edited
projects_v2_item.deleted
```

## Issue Types REST API (GA March 2025)

```bash
# List org issue types
gh api orgs/{org}/issue-types

# Create issue type
gh api orgs/{org}/issue-types --method POST \
  -f name="Epic" \
  -f description="Large feature grouping" \
  -f color="blue"
```

Issue types enable structured classification at the organization level.
Issue form templates can auto-set the type via the `type:` YAML key.
