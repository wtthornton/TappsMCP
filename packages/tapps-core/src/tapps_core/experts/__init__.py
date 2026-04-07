"""Expert domain mapping — tech-stack-to-domain helpers.

The full RAG-backed expert consultation system has been removed.
Only the tech-stack-to-domain mapping helpers remain, used by session start.
"""

from tapps_core.experts.rag_warming import (
    TECH_STACK_TO_EXPERT_DOMAINS as TECH_STACK_TO_EXPERT_DOMAINS,
)
from tapps_core.experts.rag_warming import (
    tech_stack_to_expert_domains as tech_stack_to_expert_domains,
)
