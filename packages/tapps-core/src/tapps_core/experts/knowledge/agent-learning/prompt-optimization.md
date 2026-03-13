# Prompt Optimization Best Practices

## Overview

Prompt optimization improves agent performance by systematically testing and refining prompts based on outcomes. This guide covers best practices for effective prompt optimization.

## A/B Testing Strategy

### Variant Creation

**Best Practice:** Create variants with specific, testable modifications.

```python
# Good: Specific modifications
variant1 = optimizer.create_variant(
    base_prompt="Write a function",
    modifications=[
        "add: Use type hints",
        "add: Add docstring",
        "add: Include error handling"
    ]
)

variant2 = optimizer.create_variant(
    base_prompt="Write a function",
    modifications=[
        "add: Use async/await",
        "add: Add logging",
        "add: Include validation"
    ]
)
```

**Best Practices:**
- One modification per variant (for clear attribution)
- Test modifications independently
- Use descriptive modification names

### Test Requirements

**Best Practice:** Test each variant at least 5 times before evaluation.

```python
# Minimum test count
min_tests = 5

# Test variant
for _ in range(min_tests):
    result = test_prompt(variant.prompt_template)
    optimizer.record_test_result(
        variant_id=variant.variant_id,
        success=result.success,
        quality_score=result.quality
    )

# Only evaluate after sufficient tests
best = optimizer.get_best_variant(min_tests=min_tests)
```

**Rationale:**
- Reduces statistical noise
- Provides reliable metrics
- Enables confident decisions

### Statistical Significance

**Best Practice:** Use statistical tests to compare variants.

```python
# Compare variants
variant1_quality = [0.8, 0.85, 0.82, 0.79, 0.83]
variant2_quality = [0.75, 0.78, 0.76, 0.77, 0.79]

# Calculate means
mean1 = sum(variant1_quality) / len(variant1_quality)
mean2 = sum(variant2_quality) / len(variant2_quality)

# Check if difference is significant
if abs(mean1 - mean2) > 0.05:  # 5% threshold
    # Difference is significant
    best_variant = variant1 if mean1 > mean2 else variant2
```

## Hardware-Aware Optimization

### NUC Optimization

**Best Practice:** Use shorter, essential-only prompts for NUC devices.

```python
# NUC: Compressed prompts
if hardware_profile == HardwareProfile.NUC:
    optimized = optimizer.optimize_for_hardware(prompt)
    # Result: Shorter, essential instructions only
    # Removes verbose explanations
    # Keeps core requirements
```

**Optimization Strategy:**
- Remove verbose instructions
- Keep essential requirements
- Limit examples to 1-2
- Use concise language

### Workstation Optimization

**Best Practice:** Use full detailed prompts for workstation devices.

```python
# Workstation: Full prompts
if hardware_profile == HardwareProfile.WORKSTATION:
    optimized = optimizer.optimize_for_hardware(prompt)
    # Result: Full detailed prompt
    # Includes examples
    # Includes best practices
    # Includes edge cases
```

**Optimization Strategy:**
- Include detailed instructions
- Provide multiple examples
- Include best practices
- Cover edge cases

## Context-Specific Optimization

### Task Type Optimization

**Best Practice:** Optimize prompts for specific task types.

```python
# Different prompts for different tasks
if task_type == "code_generation":
    prompt = get_code_generation_prompt(context)
elif task_type == "code_review":
    prompt = get_code_review_prompt(context)
elif task_type == "refactoring":
    prompt = get_refactoring_prompt(context)
```

### Domain-Specific Optimization

**Best Practice:** Optimize prompts based on domain context.

```python
# Domain-specific prompts
if domain == "e-commerce":
    prompt = add_ecommerce_context(base_prompt)
elif domain == "healthcare":
    prompt = add_healthcare_context(base_prompt)
```

## Prompt Components

### Clear Instructions

**Best Practice:** Use clear, actionable instructions.

```python
# Good: Clear instructions
prompt = """
Write a function that:
1. Takes a list of items as input
2. Calculates the total price
3. Returns the total as a float
4. Handles empty lists gracefully
"""

# Bad: Vague instructions
prompt = "Write a function to calculate something"
```

### Examples

**Best Practice:** Include relevant examples.

```python
# Good: Relevant examples
prompt = """
Write a function to calculate total price.

Example:
Input: [Item(price=10.0), Item(price=20.0)]
Output: 30.0
"""

# Examples should:
# - Match task context
# - Show expected behavior
# - Cover edge cases
```

### Constraints

**Best Practice:** Specify constraints clearly.

```python
# Good: Clear constraints
prompt = """
Write a function with:
- Type hints required
- Docstring required
- Maximum 50 lines
- No external dependencies
"""
```

## Optimization Metrics

### Quality Score

**Best Practice:** Use overall quality score as primary metric.

```python
# Track quality score
optimizer.record_test_result(
    variant_id=variant_id,
    success=True,
    quality_score=0.85  # Overall quality score
)
```

### Success Rate

**Best Practice:** Track success rate separately.

```python
# Track success
optimizer.record_test_result(
    variant_id=variant_id,
    success=True,  # Task succeeded
    quality_score=0.85
)

# Success rate calculated automatically
# variant.success_count / variant.test_count
```

### Multi-Metric Evaluation

**Best Practice:** Consider multiple metrics when evaluating variants.

```python
# Evaluate on multiple metrics
def evaluate_variant(variant):
    score = (
        variant.average_quality * 0.6 +  # Quality weight
        (variant.success_count / variant.test_count) * 0.4  # Success weight
    )
    return score
```

## Continuous Optimization

### Regular Review

**Best Practice:** Regularly review and update prompts.

```python
# Review prompts monthly
if should_review_prompts():
    # Get current best variant
    best = optimizer.get_best_variant()
    
    # Create new variants based on best
    new_variants = create_variants_from_best(best)
    
    # Test new variants
    for variant in new_variants:
        test_variant(variant)
```

### Incremental Improvement

**Best Practice:** Make incremental improvements, not radical changes.

```python
# Good: Incremental changes
modifications = [
    "add: Use type hints",  # Small change
    "add: Add docstring"   # Small change
]

# Bad: Radical changes
modifications = [
    "completely rewrite prompt"  # Too large
]
```

## Modern Prompt Engineering Patterns (2025-2026)

### Structured Output Prompting

**Best Practice:** Use structured output schemas to get deterministic, parseable responses.

```python
# Structured output via JSON schema constraints
# Models like Claude and GPT-4o support structured outputs natively

prompt = """
Analyze this code and return your assessment as JSON matching this schema:
{
  "quality_score": <float 0-100>,
  "issues": [{"severity": "high|medium|low", "description": "..."}],
  "suggestions": ["..."]
}
"""

# MCP tools return structured JSON by default - the schema is defined
# by the tool's type annotations and Pydantic models, not by the prompt.
# This eliminates parsing failures and hallucinated response formats.
```

### Tool-Use Prompting

**Best Practice:** Design prompts that guide models to use available tools effectively.

```python
# Instead of asking the model to "check code quality", prompt it to
# call specific tools in sequence:

system_prompt = """
When asked to validate code quality, follow this sequence:
1. Call tapps_quick_check(file_path) for each changed file
2. If any file scores below 70, call tapps_consult_expert(question)
   with the specific quality issue
3. Call tapps_checklist(task_type="feature") before declaring done

Never skip steps. Each tool returns next_steps - follow them.
"""

# Tool-use prompting reduces hallucination because the model delegates
# factual queries to deterministic tools rather than generating answers.
```

### Chain-of-Thought with Verification

**Best Practice:** Combine chain-of-thought reasoning with tool-based verification.

```python
# Modern pattern: think-then-verify
# The model reasons about the approach, then verifies with tools

prompt = """
Before implementing, reason through your approach:
1. What patterns does this codebase use? (check tapps_memory)
2. What does the library API look like? (check tapps_lookup_docs)
3. What security considerations apply? (check tapps_consult_expert)

After implementing, verify:
1. Run tapps_quick_check on every changed file
2. Run tapps_validate_changed before declaring complete
"""

# This pattern reduces iterations by front-loading research
# and catching issues immediately rather than in review.
```

### Engagement-Level Prompting

**Best Practice:** Adjust prompt verbosity based on context and user preferences.

```python
# High engagement: detailed guidance, strict validation
high_engagement = """
You MUST call tapps_session_start first.
You MUST call tapps_lookup_docs before using any library.
You MUST call tapps_quick_check after every file edit.
"""

# Low engagement: minimal overhead, trust the developer
low_engagement = """
Use tapps_quick_check when you want quality feedback.
Other tools available on request.
"""
```

## Anti-Patterns

### ❌ Testing Too Few Times

**Problem:** Insufficient tests lead to unreliable results.

**Solution:** Test at least 5 times per variant.

### ❌ Ignoring Hardware Profile

**Problem:** Same prompt on all hardware wastes resources.

**Solution:** Use hardware-aware optimization.

### ❌ No Context Consideration

**Problem:** Generic prompts don't perform well.

**Solution:** Optimize prompts for specific contexts.

### ❌ Radical Changes

**Problem:** Large changes make it hard to identify what works.

**Solution:** Make incremental improvements.

## References

- [Agent Learning Guide](../../../docs/AGENT_LEARNING_GUIDE.md)
- [PromptOptimizer](../../../tapps_agents/core/agent_learning.py)

