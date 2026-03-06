# `packages.tapps-mcp.src.tapps_mcp.server_scoring_tools`

Scoring and quality-gate tool handlers for TappsMCP.

**Supported Languages:** Python (full), TypeScript/JavaScript, Go, Rust (stub). Language is auto-detected from file extension. See `scoring/language_detector.py` for routing logic.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:[`register`](#register).

## Functions

### async `tapps_score_file`

```python
async def tapps_score_file(file_path: str, quick: bool = False, fix: bool = False, mode: str = 'auto') -> dict[str, Any]:
```

REQUIRED after editing any Python file. Scores quality across 7

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `str` | Path to the Python file to score. | *required* |
| `quick` | `bool` | If True, run ruff-only scoring (< 500 ms). | False |
| `fix` | `bool` | If True (requires quick=True), apply ruff auto-fixes first. | False |
| `mode` | `str` | Execution mode - "subprocess", "direct", or "auto" (default). "direct" uses radon as a library and sync subprocess in thread pool, avoiding async subprocess reliability issues. | 'auto' |

### async `tapps_quality_gate`

```python
async def tapps_quality_gate(file_path: str, preset: str = '', ctx: Context[Any, Any, Any] | None = None) -> dict[str, Any]:
```

BLOCKING REQUIREMENT before declaring work complete. Runs full scoring

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `str` | Path to the Python file to evaluate. | *required* |
| `preset` | `str` | Quality preset - "standard" (70+), "strict" (80+), or "framework" (75+). When empty, prompts the user to select via elicitation (if supported). | '' |
| `ctx` | `Context[Any, Any, Any] \| None` |  | None |

### async `tapps_quick_check`

```python
async def tapps_quick_check(file_path: str, preset: str = 'standard', fix: bool = False) -> dict[str, Any]:
```

REQUIRED at minimum after editing any Python file. Runs quick

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `str` | Path to the Python file to check. | *required* |
| `preset` | `str` | Quality gate preset - "standard", "strict", or "framework". | 'standard' |
| `fix` | `bool` | If True, apply ruff auto-fixes before scoring. | False |

### `ast_quick_complexity`

```python
def ast_quick_complexity(code: str) -> int | None:
```

Compute a lightweight AST-based max function cyclomatic complexity.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `code` | `str` |  | *required* |

### `register`

```python
def register(mcp_instance: FastMCP) -> None:
```

Register scoring/gate tools on the shared *mcp_instance*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `mcp_instance` | `FastMCP` |  | *required* |

---

*Documentation coverage: 100.0%*
