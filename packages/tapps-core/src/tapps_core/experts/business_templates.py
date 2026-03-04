"""Starter templates for business expert knowledge directories."""

from __future__ import annotations


def generate_readme_template(
    expert_name: str,
    primary_domain: str,
    description: str = "",
) -> str:
    """Generate a README.md for the knowledge directory.

    Args:
        expert_name: Human-readable expert name.
        primary_domain: Primary domain of authority.
        description: Short description (unused in README, reserved for future use).

    Returns:
        Markdown content for the README.md file.
    """
    _ = description  # reserved for future use
    return f"""# {expert_name} Knowledge Base

Domain: **{primary_domain}**

## Adding Knowledge Files

Place markdown (`.md`) files in this directory to provide domain-specific
knowledge for the **{expert_name}** expert. The RAG system indexes
these files and retrieves relevant chunks during consultations.

## File Format

- **Plain markdown** with optional YAML frontmatter.
- Use descriptive filenames (e.g., `deployment-checklist.md`, `error-codes.md`).

### Optional Frontmatter

```yaml
---
title: Deployment Checklist
tags: [deployment, ops]
updated: 2026-01-15
---
```

## Best Practices

- **One topic per file** - keeps retrieval focused and relevant.
- **Use headers for RAG chunking** - the system splits on `## ` headers.
- **Keep files under 50 KB** - large files reduce retrieval precision.
- **Update regularly** - stale knowledge degrades consultation quality.
"""


def generate_starter_knowledge(
    expert_name: str,
    primary_domain: str,
    description: str = "",
) -> str:
    """Generate a starter overview.md knowledge file.

    Creates an initial knowledge file with domain description, common topics
    placeholder, example Q&A format, and getting-started guidance.

    Args:
        expert_name: Human-readable expert name.
        primary_domain: Primary domain of authority.
        description: Short description of the expert's focus area.

    Returns:
        Markdown content for the overview.md starter file.
    """
    desc_line = description if description else f"Domain knowledge for {primary_domain}."
    return f"""# {expert_name} - Overview

{desc_line}

## Common Topics

<!-- Add topics relevant to your domain. Examples: -->
<!-- - Architecture patterns and best practices -->
<!-- - Common pitfalls and how to avoid them -->
<!-- - Decision frameworks and trade-offs -->
<!-- - Tool and technology recommendations -->

## Example Q&A

Below is an example of how knowledge is used during consultations.

**Q:** What are the key considerations for {primary_domain}?

**A:** When working with {primary_domain}, consider:
1. Start with clear requirements and constraints
2. Follow established patterns and conventions
3. Validate assumptions early with prototypes or tests
4. Document decisions for future reference

## Getting Started

To build a useful knowledge base for **{expert_name}**:

1. **Start with what you know** - document the most frequently asked questions
   and their answers.
2. **Add decision records** - capture important decisions with context and
   rationale (one per file).
3. **Include checklists** - create step-by-step guides for common workflows.
4. **Keep files focused** - one topic per file improves retrieval accuracy.
5. **Update regularly** - review and refresh content as your domain evolves.
"""
