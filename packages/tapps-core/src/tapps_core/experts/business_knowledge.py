"""Business expert knowledge directory utilities.

Validates and scaffolds knowledge directories for user-defined
business experts under {project_root}/.tapps-mcp/knowledge/.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import structlog

from tapps_core.experts.business_templates import (
    generate_readme_template,
    generate_starter_knowledge,
)
from tapps_core.experts.domain_utils import sanitize_domain_for_path
from tapps_core.experts.models import ExpertConfig

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)  # type: ignore[assignment]


@dataclass
class KnowledgeValidationResult:
    """Result of validating knowledge directories for business experts."""

    valid: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def get_business_knowledge_path(project_root: Path, expert: ExpertConfig) -> Path:
    """Return the knowledge directory path for a business expert.

    Args:
        project_root: Project root directory.
        expert: Expert configuration.

    Returns:
        Path to the knowledge directory under .tapps-mcp/knowledge/.
    """
    dir_name = (
        expert.knowledge_dir
        if expert.knowledge_dir
        else sanitize_domain_for_path(expert.primary_domain)
    )
    return project_root / ".tapps-mcp" / "knowledge" / dir_name


def validate_business_knowledge(
    project_root: Path, experts: list[ExpertConfig]
) -> KnowledgeValidationResult:
    """Validate knowledge directories for a list of business experts.

    Checks that each expert's knowledge directory exists and contains
    at least one ``.md`` file.  Does not raise on missing directories;
    instead populates ``missing`` / ``empty`` lists with warnings.

    Args:
        project_root: Project root directory.
        experts: List of expert configurations to validate.

    Returns:
        Validation result with valid, missing, empty, and warnings lists.
    """
    result = KnowledgeValidationResult()

    for expert in experts:
        knowledge_path = get_business_knowledge_path(project_root, expert)
        domain = expert.primary_domain

        if not knowledge_path.exists():
            result.missing.append(domain)
            result.warnings.append(
                f"Knowledge directory missing for '{domain}': {knowledge_path}"
            )
            logger.warning(
                "knowledge_dir_missing",
                domain=domain,
                path=str(knowledge_path),
            )
            continue

        md_files = list(knowledge_path.glob("*.md"))
        if not md_files:
            result.empty.append(domain)
            result.warnings.append(
                f"Knowledge directory empty (no .md files) for '{domain}': {knowledge_path}"
            )
            logger.warning(
                "knowledge_dir_empty",
                domain=domain,
                path=str(knowledge_path),
            )
            continue

        result.valid.append(domain)
        logger.debug(
            "knowledge_dir_valid",
            domain=domain,
            path=str(knowledge_path),
            file_count=len(md_files),
        )

    return result


def scaffold_knowledge_directory(project_root: Path, expert: ExpertConfig) -> Path:
    """Create a knowledge directory with a README template for a business expert.

    Creates the directory if it does not exist and writes a ``README.md``
    explaining the knowledge file format.  Idempotent: re-running does not
    overwrite an existing ``README.md``.

    Args:
        project_root: Project root directory.
        expert: Expert configuration.

    Returns:
        Path to the created (or existing) knowledge directory.
    """
    knowledge_path = get_business_knowledge_path(project_root, expert)
    knowledge_path.mkdir(parents=True, exist_ok=True)

    readme_path = knowledge_path / "README.md"
    if not readme_path.exists():
        readme_content = _build_readme_template(expert)
        readme_path.write_text(readme_content, encoding="utf-8")
        logger.info(
            "knowledge_dir_scaffolded",
            domain=expert.primary_domain,
            path=str(knowledge_path),
        )
    else:
        logger.debug(
            "knowledge_dir_readme_exists",
            domain=expert.primary_domain,
            path=str(readme_path),
        )

    overview_path = knowledge_path / "overview.md"
    if not overview_path.exists():
        overview_content = generate_starter_knowledge(
            expert_name=expert.expert_name,
            primary_domain=expert.primary_domain,
            description=expert.description,
        )
        overview_path.write_text(overview_content, encoding="utf-8")
        logger.info(
            "knowledge_overview_created",
            domain=expert.primary_domain,
            path=str(overview_path),
        )

    return knowledge_path


def _build_readme_template(expert: ExpertConfig) -> str:
    """Build the README.md content for a scaffolded knowledge directory.

    Delegates to :func:`generate_readme_template` from
    :mod:`tapps_core.experts.business_templates`.
    """
    return generate_readme_template(
        expert_name=expert.expert_name,
        primary_domain=expert.primary_domain,
        description=expert.description,
    )
