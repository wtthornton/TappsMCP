#!/usr/bin/env python3
"""Use docs-mcp generators to build an epic and its story documents.

Run from repo root:
  uv run python scripts/build_epic_stories.py

Writes:
  - docs/planning/epics/EPIC-69-EXPERT-PERSONAS.md (epic with story stubs)
  - docs/planning/epics/EPIC-69/story-69.1-*.md, story-69.2-*.md, story-69.3-*.md

You can edit the EPIC_NUMBER, TITLE, and story list below to generate
a different epic. Requires docs-mcp and tapps-core (uv sync --all-packages).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root: parent of scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    """Generate the EPIC-69 epic markdown plus its child story stubs via docs-mcp."""
    # Epic 69: Expert Personas (from research: add optional persona/voice to experts)
    epic_number = 69
    epic_title = "Expert Personas"
    epic_goal = (
        "Add an optional persona (or voice) field to domain experts so that "
        "consultation responses have a consistent identity and scope. "
        "Experts today are name + domain + knowledge only; a short persona "
        "would clarify who is speaking and improve disambiguation when multiple "
        "domains could apply."
    )
    epic_motivation = (
        "Research showed experts are defined as ExpertConfig + Markdown knowledge; "
        "the answer is built from expert name, domain, and RAG context with no "
        "explicit persona. Adding an optional persona improves clarity and "
        "consistency of expert responses."
    )
    acceptance_criteria = [
        "ExpertConfig (and BusinessExpertEntry) support optional persona field",
        "_build_answer in engine prepends persona when set",
        "Built-in registry includes persona for at least 2 pilot experts",
        "Knowledge README documents how to write personas",
        "All existing tests pass; new tests cover persona in answer assembly",
    ]
    stories_json = [
        {"title": "Add persona field to ExpertConfig and business config", "points": 2},
        {"title": "Wire persona into consultation answer assembly", "points": 2},
        {"title": "Add pilot personas and docs", "points": 1},
    ]

    root = REPO_ROOT
    if not root.is_dir():
        print(f"Repo root not found: {root}", file=sys.stderr)
        return 1

    # --- Epic ---
    from docs_mcp.generators.epics import EpicConfig, EpicGenerator, EpicStoryStub

    story_list = [
        EpicStoryStub(
            title=s["title"],
            points=int(s.get("points", 0)),
            description=s.get("description", ""),
            tasks=s.get("tasks", []),
            ac_count=int(s.get("ac_count", 0)),
        )
        for s in stories_json
    ]
    epic_config = EpicConfig(
        title=epic_title,
        number=epic_number,
        goal=epic_goal,
        motivation=epic_motivation,
        status="Proposed",
        priority="P2",
        estimated_loe="~1 week (1 developer)",
        dependencies=[],
        blocks=[],
        acceptance_criteria=acceptance_criteria,
        stories=story_list,
        technical_notes=[
            "ExpertConfig in tapps_core/experts/models.py",
            "Engine._build_answer in tapps_core/experts/engine.py",
            "ExpertRegistry.BUILTIN_EXPERTS in registry.py",
        ],
        risks=[],
        non_goals=["Changing RAG or retrieval; persona is answer-assembly only"],
        style="standard",
    )
    epic_generator = EpicGenerator()
    epic_content = epic_generator.generate(
        epic_config,
        project_root=root,
        auto_populate=True,
    )
    epic_slug = epic_title.upper().replace(" ", "-")
    epic_path = root / "docs" / "planning" / "epics" / f"EPIC-{epic_number}-{epic_slug}.md"
    epic_path.parent.mkdir(parents=True, exist_ok=True)
    epic_path.write_text(epic_content, encoding="utf-8")
    print(f"Wrote epic: {epic_path.relative_to(root)}")

    # --- Stories (one doc per story) ---
    from docs_mcp.generators.stories import StoryConfig, StoryGenerator, StoryTask

    story_dir = root / "docs" / "planning" / "epics" / f"EPIC-{epic_number}"
    story_dir.mkdir(parents=True, exist_ok=True)
    story_generator = StoryGenerator()

    for i, stub in enumerate(story_list, 1):
        story_id = f"{epic_number}.{i}"
        title_slug = stub.title.lower().replace(" ", "-")[:40].rstrip("-")
        story_filename = f"story-{story_id}-{title_slug}.md"
        story_path = story_dir / story_filename

        story_config = StoryConfig(
            title=stub.title,
            epic_number=epic_number,
            story_number=i,
            role="maintainer",
            want=stub.title.lower(),
            so_that="the epic acceptance criteria for this story are met",
            description=stub.description or f"Implement: {stub.title}",
            points=stub.points,
            size="S" if stub.points <= 2 else "M",
            tasks=[StoryTask(description=t, file_path="") for t in stub.tasks]
            if stub.tasks
            else [
                StoryTask(description=f"Implement {stub.title}", file_path=""),
                StoryTask(description="Add or update unit tests", file_path=""),
                StoryTask(description="Update docs if needed", file_path=""),
            ],
            acceptance_criteria=[
                f"Story {story_id} scope completed and verified by tests",
                "No regressions in existing expert consultation behavior",
            ],
            dependencies=[],
            files=[],
            technical_notes=[],
            criteria_format="checkbox",
            style="standard",
            inherit_context=True,
            epic_path=f"../EPIC-{epic_number}-{epic_slug}.md",
        )
        story_content = story_generator.generate(
            story_config,
            project_root=root,
            auto_populate=False,
        )
        story_path.write_text(story_content, encoding="utf-8")
        print(f"Wrote story: {story_path.relative_to(root)}")

    print("Done. Review docs/planning/epics/ and edit as needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
