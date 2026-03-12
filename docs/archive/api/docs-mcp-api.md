# `packages.docs-mcp.src.docs_mcp`

Docs MCP: Documentation MCP server for the Tapps platform.

---

*Documentation coverage: 0.0%*


---

# `packages.docs-mcp.src.docs_mcp.__main__`

Allow running DocsMCP as ``python -m docs_mcp``.

---

*Documentation coverage: 0.0%*


---

# `packages.docs-mcp.src.docs_mcp.analyzers`

Code analysis engines for DocsMCP.

---

*Documentation coverage: 0.0%*


---

# `packages.docs-mcp.src.docs_mcp.analyzers.api_surface`

Public API surface detector for source modules (Python + multi-language).

## Classes

### `APIFunction`(BaseModel)

Public function in the API surface.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `signature` | `str` |  |
| `line` | `int` |  |
| `docstring_present` | `bool` | `False` |
| `docstring_summary` | `str` | `''` |
| `is_async` | `bool` | `False` |
| `decorators` | `list[str]` | `[]` |
| `parameters` | `list[dict[str, str | None]]` | `[]` |
| `return_type` | `str | None` | `None` |

### `APIClass`(BaseModel)

Public class in the API surface.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `line` | `int` |  |
| `bases` | `list[str]` | `[]` |
| `docstring_present` | `bool` | `False` |
| `docstring_summary` | `str` | `''` |
| `method_count` | `int` | `0` |
| `public_methods` | `list[str]` | `[]` |
| `decorators` | `list[str]` | `[]` |

### `APIConstant`(BaseModel)

Public constant in the API surface.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `line` | `int` |  |
| `type` | `str | None` | `None` |
| `value` | `str | None` | `None` |

### `APISurface`(BaseModel)

Complete public API surface for a module.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `source_path` | `str` |  |
| `functions` | `list[APIFunction]` | `[]` |
| `classes` | `list[APIClass]` | `[]` |
| `constants` | `list[APIConstant]` | `[]` |
| `type_aliases` | `list[str]` | `[]` |
| `re_exports` | `list[str]` | `[]` |
| `all_exports` | `list[str] | None` | `None` |
| `coverage` | `float` | `0.0` |
| `missing_docs` | `list[str]` | `[]` |
| `total_public` | `int` | `0` |

### `APISurfaceAnalyzer`

Detects public API surface of source modules.

**Methods:**

#### `__init__`

```python
def __init__(self, extractor: Extractor | None = None) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `extractor` | `Extractor \| None` |  | None |

#### `analyze`

```python
def analyze(self, file_path: Path, *, project_root: Path | None = None, depth: str = 'public', include_types: bool = True) -> APISurface:
```

Analyze the public API surface of a source file.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` | Path to the source file. | *required* |
| `project_root` | `Path \| None` | Optional project root for relative paths. | None |
| `depth` | `str` | Visibility depth - "public", "protected", or "all". | 'public' |
| `include_types` | `bool` | Whether to include type alias detection. | True |

**Returns:** An APISurface describing the module's public API.

---

*Documentation coverage: 85.7%*


---

# `packages.docs-mcp.src.docs_mcp.analyzers.commit_parser`

Conventional commit parser and heuristic classifier for DocsMCP.

Parses commit messages that follow the Conventional Commits specification
(``type(scope): description``). For non-conventional messages, falls back
to keyword-based heuristic classification.

## Classes

### `ParsedCommit`(BaseModel)

Result of parsing/classifying a single commit message.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `type` | `str` | `''` |
| `scope` | `str` | `''` |
| `description` | `str` | `''` |
| `body` | `str` | `''` |
| `breaking` | `bool` | `False` |
| `raw` | `str` | `''` |
| `is_conventional` | `bool` | `False` |

## Functions

### `parse_conventional_commit`

```python
def parse_conventional_commit(message: str) -> ParsedCommit:
```

Parse a message as a conventional commit.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `message` | `str` |  | *required* |

### `classify_commit`

```python
def classify_commit(message: str) -> ParsedCommit:
```

Classify a commit message, preferring conventional parsing.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `message` | `str` |  | *required* |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.analyzers.dependency`

Import dependency graph builder for Python projects.

## Classes

### `ImportEdge`(BaseModel)

A single import relationship between two modules.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `source` | `str` |  |
| `target` | `str` |  |
| `import_type` | `str` | `'runtime'` |
| `line` | `int` | `0` |
| `names` | `list[str]` | `[]` |

### `ImportGraph`(BaseModel)

Directed graph of import relationships in a project.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `edges` | `list[ImportEdge]` | `[]` |
| `modules` | `list[str]` | `[]` |
| `external_imports` | `dict[str, list[str]]` | `{}` |
| `entry_points` | `list[str]` | `[]` |
| `most_imported` | `list[str]` | `[]` |
| `total_internal_imports` | `int` | `0` |
| `total_external_imports` | `int` | `0` |

### `ImportGraphBuilder`

Builds a directed import dependency graph for a Python project.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `SKIP_DIRS` | `ClassVar[frozenset[str]]` | `frozenset({'__pycache__', '.git', '.venv', 'venv', 'node_modules', '.tox', '.mypy_cache', '.pytest_cache', '.ruff_cache', 'dist', 'build', '.eggs'})` |
| `STDLIB_TOP_LEVEL` | `ClassVar[frozenset[str]]` | `frozenset({'abc', 'ast', 'asyncio', 'base64', 'collections', 'contextlib', 'copy', 'csv', 'dataclasses', 'datetime', 'enum', 'functools', 'glob', 'hashlib', 'html', 'http', 'importlib', 'inspect', 'io', 'itertools', 'json', 'logging', 'math', 'multiprocessing', 'operator', 'os', 'pathlib', 'pickle', 'platform', 'pprint', 'queue', 'random', 're', 'secrets', 'shlex', 'shutil', 'signal', 'socket', 'sqlite3', 'string', 'struct', 'subprocess', 'sys', 'tempfile', 'textwrap', 'threading', 'time', 'timeit', 'tomllib', 'traceback', 'types', 'typing', 'unittest', 'urllib', 'uuid', 'warnings', 'weakref', 'xml', 'zipfile', '__future__', 'typing_extensions'})` |

**Methods:**

#### `build`

```python
def build(self, project_root: Path, *, source_dirs: list[str] | None = None) -> ImportGraph:
```

Build the import graph for a project.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` |  | *required* |
| `source_dirs` | `list[str] \| None` |  | None |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger()` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.analyzers.git_history`

Git log parser for DocsMCP.

Wraps ``gitpython`` to extract commit history, tags, and per-file
last-modified timestamps. All methods return empty/degraded results
when the directory is not a Git repository.

## Classes

### `CommitInfo`(BaseModel)

Lightweight representation of a single Git commit.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `hash` | `str` |  |
| `short_hash` | `str` |  |
| `author` | `str` |  |
| `author_email` | `str` |  |
| `date` | `str` |  |
| `message` | `str` |  |
| `files_changed` | `int` | `0` |
| `insertions` | `int` | `0` |
| `deletions` | `int` | `0` |

### `TagInfo`(BaseModel)

A Git tag with optional semver metadata.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `commit_hash` | `str` |  |
| `date` | `str` |  |
| `is_semver` | `bool` | `False` |
| `version` | `str` | `''` |

### `GitHistoryAnalyzer`

Extracts commit history and tag information from a Git repository.

**Methods:**

#### `__init__`

```python
def __init__(self, repo_path: Path) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `repo_path` | `Path` |  | *required* |

#### `get_commits`

```python
def get_commits(self, *, limit: int = 100, since: str | None = None, until: str | None = None, path: str | None = None) -> list[CommitInfo]:
```

Return recent commits, newest first.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `limit` | `int` |  | 100 |
| `since` | `str \| None` |  | None |
| `until` | `str \| None` |  | None |
| `path` | `str \| None` |  | None |

#### `get_tags`

```python
def get_tags(self) -> list[TagInfo]:
```

Return all tags in the repository.

#### `get_file_last_modified`

```python
def get_file_last_modified(self, file_path: str) -> str | None:
```

Return the ISO 8601 date of the last commit touching *file_path*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `str` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 87.5%*


---

# `packages.docs-mcp.src.docs_mcp.analyzers.models`

Data models for code analysis results.

## Classes

### `ModuleNode`(BaseModel)

Hierarchical representation of a Python module/package.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `path` | `str` |  |
| `is_package` | `bool` | `False` |
| `submodules` | `list[ModuleNode]` | `[]` |
| `public_api_count` | `int` | `0` |
| `module_docstring` | `str | None` | `None` |
| `has_main` | `bool` | `False` |
| `all_exports` | `list[str] | None` | `None` |
| `size_bytes` | `int` | `0` |
| `function_count` | `int` | `0` |
| `class_count` | `int` | `0` |

### `ModuleMap`(BaseModel)

Complete module map of a project.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `project_root` | `str` |  |
| `project_name` | `str` |  |
| `module_tree` | `list[ModuleNode]` | `[]` |
| `entry_points` | `list[str]` | `[]` |
| `total_modules` | `int` | `0` |
| `total_packages` | `int` | `0` |
| `public_api_count` | `int` | `0` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.analyzers.module_map`

Module structure analyzer that builds a hierarchical map of a project.

Supports Python (AST-based) and multi-language files (TypeScript, Go,
Rust, Java) when tree-sitter is installed.

## Classes

### `ModuleMapAnalyzer`

Walks a project directory and builds a hierarchical module map.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `SKIP_DIRS` | `ClassVar[frozenset[str]]` | `frozenset({'__pycache__', '.git', '.venv', 'venv', 'node_modules', '.tox', '.mypy_cache', '.pytest_cache', '.ruff_cache', 'dist', 'build', '.eggs'})` |
| `SKIP_SUFFIXES` | `ClassVar[frozenset[str]]` | `frozenset({'.egg-info'})` |

**Methods:**

#### `__init__`

```python
def __init__(self, extractor: Extractor | None = None) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `extractor` | `Extractor \| None` |  | None |

#### `analyze`

```python
def analyze(self, project_root: Path, *, depth: int = 10, include_private: bool = False, source_dirs: list[str] | None = None) -> ModuleMap:
```

Build a complete module map of the project.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Root directory of the project. | *required* |
| `depth` | `int` | Maximum directory depth to traverse (0 = root only). | 10 |
| `include_private` | `bool` | Whether to include modules starting with ``_`` (``__init__.py`` is always included regardless). | False |
| `source_dirs` | `list[str] \| None` | Explicit source directories relative to project_root. When ``None``, auto-detects by looking for ``src/`` layout or directories containing Python files. | None |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger()` |

---

*Documentation coverage: 75.0%*


---

# `packages.docs-mcp.src.docs_mcp.analyzers.version_detector`

Tag/version boundary detection for DocsMCP.

Detects semver tags in a Git repository, groups commits between
version boundaries, and sorts by version number.

## Classes

### `VersionBoundary`(BaseModel)

Commits between two version tags.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `version` | `str` |  |
| `tag` | `str` |  |
| `date` | `str` |  |
| `commit_count` | `int` |  |
| `commits` | `list[CommitInfo]` | `[]` |

### `VersionDetector`

Detects version boundaries from Git tags.

**Methods:**

#### `detect_versions`

```python
def detect_versions(self, repo_path: Path, *, include_commits: bool = True) -> list[VersionBoundary]:
```

Return version boundaries sorted by semver (newest first).

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `repo_path` | `Path` |  | *required* |
| `include_commits` | `bool` |  | True |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.cli`

DocsMCP CLI - documentation MCP server management.

## Functions

### `cli`

```python
def cli() -> None:
```

DocsMCP: Documentation generation and maintenance MCP server.

### `serve`

```python
def serve(transport: str, host: str, port: int) -> None:
```

Start the DocsMCP MCP server.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `transport` | `str` |  | *required* |
| `host` | `str` |  | *required* |
| `port` | `int` |  | *required* |

**Examples:**

```python
def test_combined_server_name(combined) -> None:
    """Combined server is named TappsPlatform."""
    assert combined.name == "TappsPlatform"
```

### `doctor`

```python
def doctor() -> None:
```

Check DocsMCP configuration and dependencies.

### `generate`

```python
def generate() -> None:
```

Generate documentation (not yet implemented).

### `scan`

```python
def scan() -> None:
```

Scan project for documentation inventory.

### `version`

```python
def version() -> None:
```

Print DocsMCP version.

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.config`

DocsMCP configuration system.

---

*Documentation coverage: 0.0%*


---

# `packages.docs-mcp.src.docs_mcp.config.settings`

DocsMCP configuration system.

Precedence (highest to lowest):
    1. Environment variables (``DOCS_MCP_*``)
    2. Project-level ``.docsmcp.yaml``
    3. Built-in defaults

## Classes

### `DocsMCPSettings`(BaseSettings)

Root settings for DocsMCP server.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `model_config` |  | `SettingsConfigDict(env_prefix='DOCS_MCP_', env_nested_delimiter='__', extra='ignore')` |
| `project_root` | `Path` | `Field(default_factory=Path.cwd, description='Project root boundary - all file paths must be within this directory.')` |
| `log_level` | `str` | `Field(default='INFO', description='Logging level.')` |
| `log_json` | `bool` | `Field(default=False, description='Output JSON-formatted logs.')` |
| `output_dir` | `str` | `Field(default='docs', description='Directory where generated documentation is written.')` |
| `default_style` | `str` | `Field(default='standard', description='README style: minimal, standard, or comprehensive.')` |
| `default_format` | `Literal['markdown', 'rst', 'plain']` | `Field(default='markdown', description='Default output format for generated documentation.')` |
| `include_toc` | `bool` | `Field(default=True, description='Include table of contents in generated documents.')` |
| `include_badges` | `bool` | `Field(default=True, description='Include badges in generated README files.')` |
| `changelog_format` | `str` | `Field(default='keep-a-changelog', description='Changelog format: keep-a-changelog or conventional.')` |
| `adr_format` | `str` | `Field(default='madr', description='ADR template format: madr or nygard.')` |
| `diagram_format` | `str` | `Field(default='mermaid', description='Diagram output format: mermaid or plantuml.')` |
| `git_log_limit` | `int` | `Field(default=500, ge=1, description='Maximum number of git commits to analyze.')` |

## Functions

### `load_docs_settings`

```python
def load_docs_settings(project_root: Path | None = None) -> DocsMCPSettings:
```

Load settings with correct precedence.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path \| None` | Override for project root.  When ``None``, uses CWD. | None |

**Returns:** Fully resolved ``DocsMCPSettings``.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.extractors`

Code extraction engines for DocsMCP.

---

*Documentation coverage: 0.0%*


---

# `packages.docs-mcp.src.docs_mcp.extractors.base`

Base protocol for source code extractors.

## Classes

### `Extractor`(Protocol)

Protocol that all source code extractors must implement.

**Methods:**

#### `extract`

```python
def extract(self, file_path: Path, *, project_root: Path | None = None) -> ModuleInfo:
```

Extract structured information from a source file.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |
| `project_root` | `Path \| None` |  | None |

#### `can_handle`

```python
def can_handle(self, file_path: Path) -> bool:
```

Return True if this extractor can handle the given file type.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.extractors.dispatcher`

Extractor dispatcher -- selects the best extractor for a given file.

## Functions

### `get_extractor`

```python
def get_extractor(file_path: Path) -> Extractor:
```

Return the best available extractor for *file_path*.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger()` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.extractors.docstring_parser`

Docstring parser supporting Google, NumPy, and Sphinx styles.

Parses Python docstrings into structured data models without external
dependencies. Handles style auto-detection and graceful fallback for
malformed input.

## Classes

### `DocstringParam`(BaseModel)

A single parameter documented in a docstring.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `type` | `str | None` | `None` |
| `description` | `str` | `''` |

### `DocstringReturns`(BaseModel)

Return value documentation.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `type` | `str | None` | `None` |
| `description` | `str` | `''` |

### `DocstringRaises`(BaseModel)

A single exception documented in a docstring.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `exception` | `str` |  |
| `description` | `str` | `''` |

### `DocstringExample`(BaseModel)

A code example extracted from a docstring.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `code` | `str` |  |
| `description` | `str` | `''` |

### `ParsedDocstring`(BaseModel)

Fully parsed docstring with all extracted sections.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `summary` | `str` | `''` |
| `description` | `str` | `''` |
| `params` | `list[DocstringParam]` | `[]` |
| `returns` | `DocstringReturns | None` | `None` |
| `raises` | `list[DocstringRaises]` | `[]` |
| `examples` | `list[DocstringExample]` | `[]` |
| `notes` | `str` | `''` |
| `style` | `str` | `'unknown'` |
| `raw` | `str` | `''` |

## Functions

### `parse_docstring`

```python
def parse_docstring(docstring: str, style: str = 'auto') -> ParsedDocstring:
```

Parse a docstring into structured components.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `docstring` | `str` | The raw docstring text. | *required* |
| `style` | `str` | Parsing style - ``"auto"`` (default), ``"google"``, ``"numpy"``, ``"sphinx"``, or ``"unknown"``. | 'auto' |

**Returns:** A ``ParsedDocstring`` containing the extracted sections.

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.extractors.generic`

Regex-based fallback extractor for any text-based source file.

## Classes

### `LanguagePatterns`

Decorators: `@dataclass`

Regex patterns for extracting symbols from a specific language.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `function` | `re.Pattern[str] | None` | `None` |
| `class_def` | `re.Pattern[str] | None` | `None` |
| `import_stmt` | `re.Pattern[str] | None` | `None` |
| `constant` | `re.Pattern[str] | None` | `None` |
| `doc_comment_prefix` | `str | None` | `None` |
| `block_comment_start` | `str | None` | `None` |
| `block_comment_end` | `str | None` | `None` |

### `GenericExtractor`

Regex-based fallback extractor for any text-based source file.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `LANGUAGE_MAP` | `ClassVar[dict[str, str]]` | `{'.py': 'python', '.pyi': 'python', '.js': 'javascript', '.jsx': 'javascript', '.ts': 'typescript', '.tsx': 'typescript', '.mjs': 'javascript', '.cjs': 'javascript', '.go': 'go', '.rs': 'rust'}` |

**Methods:**

#### `can_handle`

```python
def can_handle(self, file_path: Path) -> bool:
```

Accept any file — this is the universal fallback.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |

#### `extract`

```python
def extract(self, file_path: Path, *, project_root: Path | None = None) -> ModuleInfo:
```

Extract symbols via regex. Never raises.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |
| `project_root` | `Path \| None` |  | None |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.extractors.models`

Data models for code extraction results.

## Classes

### `DecoratorInfo`(BaseModel)

Information about a decorator applied to a function or class.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `arguments` | `str | None` | `None` |
| `line` | `int` |  |

### `ParameterInfo`(BaseModel)

Information about a function parameter.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `annotation` | `str | None` | `None` |
| `default` | `str | None` | `None` |
| `kind` | `str` | `'POSITIONAL_OR_KEYWORD'` |

### `FunctionInfo`(BaseModel)

Information about a function or method.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `line` | `int` |  |
| `end_line` | `int | None` | `None` |
| `signature` | `str` |  |
| `parameters` | `list[ParameterInfo]` | `[]` |
| `return_annotation` | `str | None` | `None` |
| `decorators` | `list[DecoratorInfo]` | `[]` |
| `docstring` | `str | None` | `None` |
| `is_async` | `bool` | `False` |
| `is_property` | `bool` | `False` |
| `is_staticmethod` | `bool` | `False` |
| `is_classmethod` | `bool` | `False` |
| `is_abstractmethod` | `bool` | `False` |

### `ConstantInfo`(BaseModel)

Information about a module-level or class-level constant/variable.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `line` | `int` |  |
| `value` | `str | None` | `None` |
| `annotation` | `str | None` | `None` |

### `ClassInfo`(BaseModel)

Information about a class definition.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `line` | `int` |  |
| `end_line` | `int | None` | `None` |
| `bases` | `list[str]` | `[]` |
| `decorators` | `list[DecoratorInfo]` | `[]` |
| `docstring` | `str | None` | `None` |
| `methods` | `list[FunctionInfo]` | `[]` |
| `class_variables` | `list[ConstantInfo]` | `[]` |

### `ModuleInfo`(BaseModel)

Information about a Python module extracted from its AST.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `path` | `str` |  |
| `docstring` | `str | None` | `None` |
| `imports` | `list[str]` | `[]` |
| `functions` | `list[FunctionInfo]` | `[]` |
| `classes` | `list[ClassInfo]` | `[]` |
| `constants` | `list[ConstantInfo]` | `[]` |
| `has_main_block` | `bool` | `False` |
| `all_exports` | `list[str] | None` | `None` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.extractors.python`

Python AST-based source code extractor.

## Classes

### `PythonExtractor`

Extracts structured information from Python source files using the AST.

**Methods:**

#### `can_handle`

```python
def can_handle(self, file_path: Path) -> bool:
```

Return True for .py and .pyi files.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |

#### `extract`

```python
def extract(self, file_path: Path, *, project_root: Path | None = None) -> ModuleInfo:
```

Extract module information from a Python file.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |
| `project_root` | `Path \| None` |  | None |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger()` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.extractors.treesitter_base`

Base class for tree-sitter powered source code extractors.

## Classes

### `TreeSitterExtractor`(abc.ABC)

Base class for tree-sitter powered extractors.

**Methods:**

#### property `language_obj`

```python
def language_obj(self) -> Any:
```

Return the tree-sitter Language object for this extractor.

#### property `file_extensions`

```python
def file_extensions(self) -> frozenset[str]:
```

Return the set of file extensions this extractor handles.

#### `can_handle`

```python
def can_handle(self, file_path: Path) -> bool:
```

Return True if tree-sitter is available and extension matches.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |

#### `extract`

```python
def extract(self, file_path: Path, *, project_root: Path | None = None) -> ModuleInfo:
```

Parse with tree-sitter and delegate to subclass traversal. Never raises.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Path` |  | *required* |
| `project_root` | `Path \| None` |  | None |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger()` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.extractors.treesitter_go`

Tree-sitter based Go extractor.

## Classes

### `GoExtractor`(TreeSitterExtractor)

Extract symbols from Go source files using tree-sitter.

**Methods:**

#### property `file_extensions`

```python
def file_extensions(self) -> frozenset[str]:
```

#### property `language_obj`

```python
def language_obj(self) -> Any:
```

#### `can_handle`

```python
def can_handle(self, file_path: Any) -> bool:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Any` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger()` |

---

*Documentation coverage: 40.0%*


---

# `packages.docs-mcp.src.docs_mcp.extractors.treesitter_java`

Tree-sitter based Java extractor.

## Classes

### `JavaExtractor`(TreeSitterExtractor)

Extract symbols from Java source files using tree-sitter.

**Methods:**

#### property `file_extensions`

```python
def file_extensions(self) -> frozenset[str]:
```

#### property `language_obj`

```python
def language_obj(self) -> Any:
```

#### `can_handle`

```python
def can_handle(self, file_path: Any) -> bool:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Any` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger()` |

---

*Documentation coverage: 40.0%*


---

# `packages.docs-mcp.src.docs_mcp.extractors.treesitter_rust`

Tree-sitter based Rust extractor.

## Classes

### `RustExtractor`(TreeSitterExtractor)

Extract symbols from Rust source files using tree-sitter.

**Methods:**

#### property `file_extensions`

```python
def file_extensions(self) -> frozenset[str]:
```

#### property `language_obj`

```python
def language_obj(self) -> Any:
```

#### `can_handle`

```python
def can_handle(self, file_path: Any) -> bool:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Any` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger()` |

---

*Documentation coverage: 40.0%*


---

# `packages.docs-mcp.src.docs_mcp.extractors.treesitter_typescript`

Tree-sitter based TypeScript/TSX extractor.

## Classes

### `TypeScriptExtractor`(TreeSitterExtractor)

Extract symbols from TypeScript and TSX files using tree-sitter.

**Methods:**

#### property `file_extensions`

```python
def file_extensions(self) -> frozenset[str]:
```

#### property `language_obj`

```python
def language_obj(self) -> Any:
```

#### `can_handle`

```python
def can_handle(self, file_path: Any) -> bool:
```

Check availability and extension.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Any` |  | *required* |

#### `extract`

```python
def extract(self, file_path: Any, *, project_root: Any | None = None) -> ModuleInfo:
```

Override to select TSX parser for .tsx files.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `file_path` | `Any` |  | *required* |
| `project_root` | `Any \| None` |  | None |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger()` |

---

*Documentation coverage: 66.7%*


---

# `packages.docs-mcp.src.docs_mcp.extractors.type_annotations`

Type annotation extraction and resolution for Python AST nodes.

Resolves Python type annotations from AST nodes and string representations
into structured, human-readable TypeInfo objects with normalization to
modern Python typing conventions.

## Classes

### `TypeInfo`(BaseModel)

Structured representation of a Python type annotation.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `raw` | `str` |  |
| `resolved` | `str` |  |
| `is_optional` | `bool` | `False` |
| `base_type` | `str` | `''` |
| `type_args` | `list[str]` | `[]` |
| `is_generic` | `bool` | `False` |
| `is_callable` | `bool` | `False` |
| `is_literal` | `bool` | `False` |
| `is_union` | `bool` | `False` |

## Functions

### `resolve_annotation`

```python
def resolve_annotation(node: ast.expr | None) -> TypeInfo:
```

Resolve an AST annotation node into a structured TypeInfo.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `node` | `ast.expr \| None` | An AST expression node representing a type annotation, or None. | *required* |

**Returns:** A TypeInfo with resolved type information.

### `annotation_to_string`

```python
def annotation_to_string(node: ast.expr | None) -> str:
```

Convert an AST annotation node to its string representation.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `node` | `ast.expr \| None` | An AST expression node, or None. | *required* |

**Returns:** The string representation of the annotation, or empty string if None.

### `parse_annotation_string`

```python
def parse_annotation_string(annotation_str: str) -> TypeInfo:
```

Parse a string type annotation into a TypeInfo.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `annotation_str` | `str` | A string representation of a type annotation. | *required* |

**Returns:** A TypeInfo with resolved type information, or a degraded result
    if parsing fails.

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.generators`

DocsMCP generators - README generation, metadata extraction, and smart merge.

---

*Documentation coverage: 0.0%*


---

# `packages.docs-mcp.src.docs_mcp.generators.adr`

Architecture Decision Record (ADR) generation in MADR and Nygard formats.

## Classes

### `ADRRecord`(BaseModel)

An Architecture Decision Record.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `number` | `int` |  |
| `title` | `str` |  |
| `status` | `str` | `'proposed'` |
| `date` | `str` | `''` |
| `context` | `str` | `''` |
| `decision` | `str` | `''` |
| `consequences` | `str` | `''` |
| `supersedes` | `int | None` | `None` |

### `ADRGenerator`

Generates Architecture Decision Records in MADR or Nygard format.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `VALID_TEMPLATES` | `ClassVar[frozenset[str]]` | `frozenset({'madr', 'nygard'})` |
| `VALID_STATUSES` | `ClassVar[frozenset[str]]` | `frozenset({'proposed', 'accepted', 'deprecated', 'superseded'})` |

**Methods:**

#### `generate`

```python
def generate(self, title: str, *, template: str = 'madr', context: str = '', decision: str = '', consequences: str = '', status: str = 'proposed', adr_dir: Path | None = None, project_root: Path) -> tuple[str, str]:
```

Generate an ADR document and return (content, filename).

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `title` | `str` | The title of the decision. | *required* |
| `template` | `str` | Template format - "madr" or "nygard". | 'madr' |
| `context` | `str` | The problem context. | '' |
| `decision` | `str` | The decision made. | '' |
| `consequences` | `str` | The consequences of the decision. | '' |
| `status` | `str` | ADR status (proposed, accepted, deprecated, superseded). | 'proposed' |
| `adr_dir` | `Path \| None` | Directory for ADR files. Defaults to project_root/docs/decisions. | None |
| `project_root` | `Path` | Root directory of the project. | *required* |

**Returns:** A tuple of (rendered content, filename).

#### `generate_index`

```python
def generate_index(self, adr_dir: Path) -> str:
```

Generate a markdown index of all ADR files in a directory.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `adr_dir` | `Path` | Directory containing ADR files. | *required* |

**Returns:** Markdown index content. Returns an empty index table if no ADRs
    are found or the directory does not exist.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.generators.api_docs`

Per-module API reference documentation generator.

Generates structured API reference docs from Python source files using
the existing PythonExtractor and docstring parser infrastructure.
Supports markdown, mkdocs, and Sphinx RST output formats.

## Classes

### `APIDocParam`(BaseModel)

A documented parameter.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `type` | `str` | `''` |
| `description` | `str` | `''` |
| `default` | `str | None` | `None` |

### `APIDocFunction`(BaseModel)

A documented function or method.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `signature` | `str` |  |
| `description` | `str` | `''` |
| `params` | `list[APIDocParam]` | `[]` |
| `returns` | `str` | `''` |
| `raises` | `list[str]` | `[]` |
| `examples` | `list[str]` | `[]` |
| `decorators` | `list[str]` | `[]` |
| `is_async` | `bool` | `False` |
| `is_property` | `bool` | `False` |
| `is_classmethod` | `bool` | `False` |
| `is_staticmethod` | `bool` | `False` |
| `line` | `int` | `0` |

### `APIDocClass`(BaseModel)

A documented class.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `bases` | `list[str]` | `[]` |
| `description` | `str` | `''` |
| `methods` | `list[APIDocFunction]` | `[]` |
| `class_variables` | `list[APIDocParam]` | `[]` |
| `decorators` | `list[str]` | `[]` |
| `line` | `int` | `0` |

### `APIDocModule`(BaseModel)

A documented module.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `source_path` | `str` | `''` |
| `docstring` | `str` | `''` |
| `functions` | `list[APIDocFunction]` | `[]` |
| `classes` | `list[APIDocClass]` | `[]` |
| `constants` | `list[APIDocParam]` | `[]` |
| `coverage` | `float` | `0.0` |

### `APIDocGenerator`

Generates per-module API reference documentation from Python sources.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `VALID_FORMATS` | `ClassVar[frozenset[str]]` | `frozenset({'markdown', 'mkdocs', 'sphinx_rst'})` |
| `VALID_DEPTHS` | `ClassVar[frozenset[str]]` | `frozenset({'public', 'protected', 'all'})` |

**Methods:**

#### `generate`

```python
def generate(self, source_path: Path, *, project_root: Path, output_format: str = 'markdown', depth: str = 'public', include_examples: bool = True) -> str:
```

Generate API reference documentation for a file or directory.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `source_path` | `Path` | Path to a .py file or directory of .py files. | *required* |
| `project_root` | `Path` | Root directory of the project. | *required* |
| `output_format` | `str` | Output format - ``"markdown"``, ``"mkdocs"``, or ``"sphinx_rst"``. | 'markdown' |
| `depth` | `str` | Symbol visibility filter - ``"public"`` (no underscore prefix except __init__), ``"protected"`` (include single underscore), or ``"all"`` (everything). | 'public' |
| `include_examples` | `bool` | Whether to search tests for usage examples. | True |

**Returns:** The rendered API documentation as a string, or empty string
    on error.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.generators.changelog`

Changelog generation in Keep-a-Changelog and Conventional formats.

Generates structured changelogs from git version boundaries and commits.
Uses Jinja2 templates for rendering, with fallback to programmatic
generation if templates are unavailable.

## Classes

### `ChangelogEntry`(BaseModel)

A single entry in a changelog version section.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `type` | `str` |  |
| `description` | `str` |  |
| `scope` | `str` | `''` |
| `commit_hash` | `str` | `''` |
| `breaking` | `bool` | `False` |

### `ChangelogVersion`(BaseModel)

A version section in the changelog.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `version` | `str` |  |
| `date` | `str` |  |
| `entries` | `list[ChangelogEntry]` | `[]` |

### `ChangelogGenerator`

Generates changelogs from git version boundaries.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `TYPE_MAP` | `ClassVar[dict[str, str]]` | `{'feat': 'Added', 'fix': 'Fixed', 'docs': 'Changed', 'refactor': 'Changed', 'perf': 'Changed', 'test': 'Changed', 'chore': 'Changed', 'style': 'Changed', 'ci': 'Changed', 'build': 'Changed', 'revert': 'Removed', 'deprecate': 'Deprecated', 'security': 'Security'}` |
| `CONVENTIONAL_TYPE_MAP` | `ClassVar[dict[str, str]]` | `{'feat': 'Features', 'fix': 'Bug Fixes', 'docs': 'Documentation', 'refactor': 'Refactoring', 'perf': 'Performance', 'test': 'Tests', 'chore': 'Chores', 'style': 'Chores', 'ci': 'CI', 'build': 'Build', 'revert': 'Reverts', 'deprecate': 'Deprecated', 'security': 'Security'}` |

**Methods:**

#### `generate`

```python
def generate(self, versions: list[VersionBoundary], *, format: str = 'keep-a-changelog', include_unreleased: bool = True, unreleased_commits: list[Any] | None = None) -> str:
```

Generate a changelog string from version boundaries.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `versions` | `list[VersionBoundary]` |  | *required* |
| `format` | `str` |  | 'keep-a-changelog' |
| `include_unreleased` | `bool` |  | True |
| `unreleased_commits` | `list[Any] \| None` |  | None |

**Returns:** str - The rendered changelog markdown.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.generators.diagrams`

Diagram generation for Python project structures.

Generates Mermaid and PlantUML diagrams from project analysis results,
including dependency graphs, class hierarchies, module maps, and ER diagrams.

## Classes

### `DiagramResult`(BaseModel)

Result of diagram generation.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `diagram_type` | `str` |  |
| `format` | `str` |  |
| `content` | `str` |  |
| `node_count` | `int` | `0` |
| `edge_count` | `int` | `0` |

### `DiagramGenerator`

Generates visual diagrams from project analysis data.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `VALID_TYPES` | `ClassVar[frozenset[str]]` | `frozenset({'dependency', 'class_hierarchy', 'module_map', 'er_diagram'})` |
| `VALID_FORMATS` | `ClassVar[frozenset[str]]` | `frozenset({'mermaid', 'plantuml'})` |

**Methods:**

#### `generate`

```python
def generate(self, project_root: Path, *, diagram_type: str = 'dependency', output_format: str = 'mermaid', scope: str = 'project', depth: int = 2, direction: str = 'TD', show_external: bool = False) -> DiagramResult:
```

Generate a diagram for a project.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Root directory of the project. | *required* |
| `diagram_type` | `str` | One of ``dependency``, ``class_hierarchy``, ``module_map``, or ``er_diagram``. | 'dependency' |
| `output_format` | `str` | Output format -- ``mermaid`` or ``plantuml``. | 'mermaid' |
| `scope` | `str` | Scope of the diagram; ``project`` for the whole project or a file path for a single file (class/ER diagrams). | 'project' |
| `depth` | `int` | Depth limit for module map / dependency diagrams. | 2 |
| `direction` | `str` | Graph direction (``TD``, ``LR``, etc.). | 'TD' |
| `show_external` | `bool` | Whether to include external dependencies. | False |

**Returns:** A :class:`DiagramResult` with the rendered content.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `structlog.stdlib.BoundLogger` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.generators.guides`

Onboarding and contributing guide generation.

## Classes

### `OnboardingGuideGenerator`

Generates a getting-started / onboarding guide for a project.

**Methods:**

#### `generate`

```python
def generate(self, project_root: Path, *, metadata: ProjectMetadata | None = None) -> str:
```

Generate an onboarding guide for the project.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Root directory of the project. | *required* |
| `metadata` | `ProjectMetadata \| None` | Pre-extracted project metadata. If None, extracts automatically via MetadataExtractor. | None |

**Returns:** Rendered onboarding guide as a markdown string.
    Returns an empty string on unrecoverable errors.

### `ContributingGuideGenerator`

Generates a CONTRIBUTING.md guide for a project.

**Methods:**

#### `generate`

```python
def generate(self, project_root: Path, *, metadata: ProjectMetadata | None = None) -> str:
```

Generate a contributing guide for the project.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Root directory of the project. | *required* |
| `metadata` | `ProjectMetadata \| None` | Pre-extracted project metadata. If None, extracts automatically via MetadataExtractor. | None |

**Returns:** Rendered contributing guide as a markdown string.
    Returns an empty string on unrecoverable errors.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.generators.metadata`

Project metadata extraction from pyproject.toml, package.json, and Cargo.toml.

## Classes

### `ProjectMetadata`(BaseModel)

Extracted project metadata from configuration files.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` | `''` |
| `version` | `str` | `''` |
| `description` | `str` | `''` |
| `author` | `str` | `''` |
| `author_email` | `str` | `''` |
| `license` | `str` | `''` |
| `python_requires` | `str` | `''` |
| `homepage` | `str` | `''` |
| `repository` | `str` | `''` |
| `keywords` | `list[str]` | `[]` |
| `dependencies` | `list[str]` | `[]` |
| `dev_dependencies` | `list[str]` | `[]` |
| `entry_points` | `dict[str, str]` | `{}` |
| `source_file` | `str` | `''` |

### `MetadataExtractor`

Extracts project metadata from various configuration file formats.

**Methods:**

#### `extract`

```python
def extract(self, project_root: Path) -> ProjectMetadata:
```

Extract metadata from the project root directory.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` |  | *required* |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.generators.readme`

README generation with Jinja2 templates and section generators.

## Classes

### `ReadmeSection`(BaseModel)

A single section of a generated README.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `content` | `str` |  |
| `source` | `str` | `'generated'` |

### `ReadmeGenerator`

Generates README.md content from project metadata and analysis.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `VALID_STYLES` | `ClassVar[frozenset[str]]` | `frozenset({'minimal', 'standard', 'comprehensive'})` |

**Methods:**

#### `__init__`

```python
def __init__(self, style: str = 'standard') -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `style` | `str` |  | 'standard' |

#### property `style`

```python
def style(self) -> str:
```

Return the current generation style.

#### `generate`

```python
def generate(self, project_root: Path, *, metadata: ProjectMetadata | None = None) -> str:
```

Generate a complete README from project metadata and analysis.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Root directory of the project. | *required* |
| `metadata` | `ProjectMetadata \| None` | Pre-extracted metadata. If None, extracts automatically. | None |

**Returns:** The rendered README content as a string.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 83.3%*


---

# `packages.docs-mcp.src.docs_mcp.generators.release_notes`

Release notes generation for a specific version.

Extracts highlights, breaking changes, features, fixes, contributors,
and other changes from a version boundary's commits and renders
structured release notes as markdown.

## Classes

### `ReleaseNotes`(BaseModel)

Structured release notes for a single version.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `version` | `str` |  |
| `date` | `str` |  |
| `highlights` | `list[str]` | `[]` |
| `breaking_changes` | `list[str]` | `[]` |
| `features` | `list[str]` | `[]` |
| `fixes` | `list[str]` | `[]` |
| `other_changes` | `list[str]` | `[]` |
| `contributors` | `list[str]` | `[]` |

### `ReleaseNotesGenerator`

Generates release notes from a version boundary.

**Methods:**

#### `generate`

```python
def generate(self, version_boundary: VersionBoundary) -> ReleaseNotes:
```

Generate structured release notes from a version boundary.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `version_boundary` | `VersionBoundary` |  | *required* |

**Returns:** ReleaseNotes - Structured release notes with categorized changes.

#### `render_markdown`

```python
def render_markdown(self, notes: ReleaseNotes) -> str:
```

Render release notes as markdown.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `notes` | `ReleaseNotes` |  | *required* |

**Returns:** str - Markdown-formatted release notes.

#### `generate_from_versions`

```python
def generate_from_versions(self, versions: list[Any], version: str = '') -> ReleaseNotes | None:
```

Find and generate release notes for a specific version.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `versions` | `list[Any]` |  | *required* |
| `version` | `str` |  | '' |

**Returns:** ReleaseNotes | None - Release notes, or ``None`` if the version was not found.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.generators.smart_merge`

Smart merge engine for preserving human-written README sections.

## Classes

### `MergeResult`(BaseModel)

Result of merging existing and generated README content.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `content` | `str` |  |
| `sections_preserved` | `list[str]` | `[]` |
| `sections_updated` | `list[str]` | `[]` |
| `sections_added` | `list[str]` | `[]` |

### `SmartMerger`

Merges generated README content with existing human-written content.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `SECTION_MARKER_START` | `ClassVar[str]` | `'<!-- docsmcp:start:{section} -->'` |
| `SECTION_MARKER_END` | `ClassVar[str]` | `'<!-- docsmcp:end:{section} -->'` |

**Methods:**

#### `merge`

```python
def merge(self, existing: str, generated: str) -> MergeResult:
```

Merge existing and generated README content.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `existing` | `str` | The current README content (may be empty). | *required* |
| `generated` | `str` | The freshly generated README content. | *required* |

**Returns:** MergeResult with the merged content and tracking lists.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.generators.specs`

Product Requirements Document (PRD) generation with phased requirements.

## Classes

### `PRDPhase`(BaseModel)

A single phase in the phased requirements roadmap.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `description` | `str` | `''` |
| `requirements` | `list[str]` | `[]` |

### `PRDConfig`(BaseModel)

Configuration for PRD generation.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `title` | `str` |  |
| `problem` | `str` | `''` |
| `personas` | `list[str]` | `[]` |
| `phases` | `list[PRDPhase]` | `[]` |
| `constraints` | `list[str]` | `[]` |
| `non_goals` | `list[str]` | `[]` |
| `style` | `str` | `'standard'` |
| `existing_content` | `str` | `''` |

### `PRDGenerator`

Generates Product Requirements Documents with phased requirements.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `VALID_STYLES` | `ClassVar[frozenset[str]]` | `frozenset({'standard', 'comprehensive'})` |

**Methods:**

#### `generate`

```python
def generate(self, config: PRDConfig, *, project_root: Path | None = None, auto_populate: bool = False) -> str:
```

Generate a PRD document.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `config` | `PRDConfig` | PRD configuration with title, problem, phases, etc. | *required* |
| `project_root` | `Path \| None` | Project root for auto-populate analyzers. | None |
| `auto_populate` | `bool` | When True, enrich sections from project analyzers. | False |

**Returns:** Rendered markdown content with docsmcp markers.

#### staticmethod `parse_phases_json`

```python
def parse_phases_json(phases_json: str) -> list[PRDPhase]:
```

Parse a JSON string into a list of PRDPhase objects.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `phases_json` | `str` | JSON string representing phases. | *required* |

**Returns:** List of PRDPhase objects.

**Raises:**

- ValueError: If the JSON is malformed or not a list.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.integrations`

DocsMCP integrations - optional enrichment from external tools.

---

*Documentation coverage: 0.0%*


---

# `packages.docs-mcp.src.docs_mcp.integrations.tapps`

TappsMCP integration for optional quality enrichment in DocsMCP.

Reads shared file artifacts produced by TappsMCP to enrich documentation
with quality scores, project profiles, and dependency data. All methods
return safe defaults when TappsMCP data is unavailable - DocsMCP never
fails due to missing TappsMCP data.

## Classes

### `TappsQualityScore`(BaseModel)

Quality score data from TappsMCP.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `file_path` | `str` |  |
| `overall_score` | `float` |  |
| `category_scores` | `dict[str, float]` | `{}` |

### `TappsProjectProfile`(BaseModel)

Project profile data from TappsMCP.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `project_type` | `str` | `''` |
| `tech_stack` | `dict[str, Any]` | `{}` |
| `has_ci` | `bool` | `False` |
| `ci_systems` | `list[str]` | `[]` |
| `has_docker` | `bool` | `False` |
| `has_tests` | `bool` | `False` |
| `test_frameworks` | `list[str]` | `[]` |
| `package_managers` | `list[str]` | `[]` |

### `TappsDependencyData`(BaseModel)

Dependency graph data from TappsMCP.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `total_modules` | `int` | `0` |
| `total_edges` | `int` | `0` |
| `cycles` | `list[list[str]]` | `[]` |
| `coupling` | `list[dict[str, Any]]` | `[]` |

### `TappsEnrichment`(BaseModel)

Combined TappsMCP enrichment data for DocsMCP.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `available` | `bool` | `False` |
| `quality_scores` | `list[TappsQualityScore]` | `[]` |
| `project_profile` | `TappsProjectProfile | None` | `None` |
| `dependency_data` | `TappsDependencyData | None` | `None` |
| `overall_project_score` | `float | None` | `None` |

### `TappsIntegration`

Reads TappsMCP data from shared file artifacts for optional enrichment.

**Methods:**

#### `__init__`

```python
def __init__(self, project_root: Path) -> None:
```

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` |  | *required* |

#### property `is_available`

```python
def is_available(self) -> bool:
```

Return True when the .tapps-mcp directory exists.

#### `load_enrichment`

```python
def load_enrichment(self) -> TappsEnrichment:
```

Load combined enrichment data from the TappsMCP export file.

#### `load_project_profile`

```python
def load_project_profile(self) -> TappsProjectProfile | None:
```

Load project profile from the TappsMCP export file.

#### `load_quality_scores`

```python
def load_quality_scores(self) -> list[TappsQualityScore]:
```

Load quality scores from the TappsMCP export file.

#### staticmethod `generate_quality_badge`

```python
def generate_quality_badge(score: float) -> str:
```

Generate a shields.io quality score badge in Markdown.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `score` | `float` | The overall quality score (0-100). | *required* |

**Returns:** Markdown image string for the quality badge.

#### staticmethod `generate_gate_badge`

```python
def generate_gate_badge(passed: bool) -> str:
```

Generate a shields.io quality gate badge in Markdown.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `passed` | `bool` | Whether the quality gate passed. | *required* |

**Returns:** Markdown image string for the gate badge.

## Constants

| Name | Type | Value |
|------|------|-------|
| `log` | `structlog.stdlib.BoundLogger` | `structlog.get_logger()` |

---

*Documentation coverage: 92.3%*


---

# `packages.docs-mcp.src.docs_mcp.server`

DocsMCP MCP server entry point.

Creates the FastMCP server instance, registers tools, and provides
``run_server()`` for the CLI.

## Functions

### async `docs_session_start`

```python
async def docs_session_start(project_root: str = '') -> dict[str, Any]:
```

REQUIRED as the FIRST call in every session. Detects project type,

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `str` | Optional override for project root directory. | '' |

### async `docs_project_scan`

```python
async def docs_project_scan(project_root: str = '') -> dict[str, Any]:
```

Comprehensive documentation state audit. Inventories all documentation

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `str` | Optional override for project root directory. | '' |

### async `docs_config`

```python
async def docs_config(action: str = 'view', key: str = '', value: str = '') -> dict[str, Any]:
```

View or update DocsMCP configuration.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `action` | `str` | "view" to read config, "set" to update a config value. | 'view' |
| `key` | `str` | Config key to set (e.g. "default_style", "output_dir"). Required when action="set". | '' |
| `value` | `str` | Value to set. Required when action="set". | '' |

### `run_server`

```python
def run_server(transport: str = 'stdio', host: str = '127.0.0.1', port: int = 8000) -> None:
```

Start the DocsMCP MCP server.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `transport` | `str` |  | 'stdio' |
| `host` | `str` |  | '127.0.0.1' |
| `port` | `int` |  | 8000 |

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |
| `mcp` | `` | `FastMCP('DocsMCP')` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.server_analysis`

DocsMCP analysis tools — docs_module_map and docs_api_surface.

These tools register on the shared ``mcp`` FastMCP instance from
``server.py`` and provide code structure analysis capabilities.

## Functions

### async `docs_module_map`

```python
async def docs_module_map(depth: int = 10, include_private: bool = False, source_dirs: str = '', project_root: str = '') -> dict[str, Any]:
```

Build a hierarchical module map of a project.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `depth` | `int` | Maximum directory depth to traverse (default: 10). | 10 |
| `include_private` | `bool` | Whether to include modules starting with ``_`` (``__init__.py`` is always included). | False |
| `source_dirs` | `str` | Comma-separated source directories relative to project root. When empty, auto-detects ``src/`` layout or scans project root. | '' |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

### async `docs_api_surface`

```python
async def docs_api_surface(source_path: str, include_types: bool = True, depth: str = 'public', project_root: str = '') -> dict[str, Any]:
```

Analyze the public API surface of a source file.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `source_path` | `str` | Path to a source file (absolute or relative to project root). | *required* |
| `include_types` | `bool` | Whether to detect type alias definitions. | True |
| `depth` | `str` | Visibility depth — ``"public"``, ``"protected"``, or ``"all"``. | 'public' |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.server_gen_tools`

DocsMCP generation tools.

Registers generation tools on the shared ``mcp`` FastMCP instance from
``server.py``: README, changelog, release notes, API docs, ADR,
onboarding/contributing guides, and diagrams.

## Functions

### async `docs_generate_changelog`

```python
async def docs_generate_changelog(format: str = 'keep-a-changelog', include_unreleased: bool = True, output_path: str = '', project_root: str = '') -> dict[str, Any]:
```

Generate a CHANGELOG.md from git history.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `format` | `str` | Changelog format - "keep-a-changelog" or "conventional". | 'keep-a-changelog' |
| `include_unreleased` | `bool` | Whether to include unreleased changes section. | True |
| `output_path` | `str` | File path to write the changelog (relative to project root). When empty, returns the content without writing a file. | '' |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

### async `docs_generate_release_notes`

```python
async def docs_generate_release_notes(version: str = '', project_root: str = '') -> dict[str, Any]:
```

Generate release notes for a specific version.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `version` | `str` | Version string to generate notes for (e.g. "1.2.0"). When empty, generates for the latest version. | '' |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

### async `docs_generate_readme`

```python
async def docs_generate_readme(style: str = 'standard', output_path: str = '', merge: bool = True, project_root: str = '') -> dict[str, Any]:
```

Generate or update a README.md file for the project.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `style` | `str` | README style - "minimal", "standard", or "comprehensive". | 'standard' |
| `output_path` | `str` | Output file path (default: README.md in project root). | '' |
| `merge` | `bool` | Whether to merge with existing README (default: True). | True |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

### async `docs_generate_api`

```python
async def docs_generate_api(source_path: str = '', format: str = 'markdown', depth: str = 'public', include_examples: bool = True, output_path: str = '', project_root: str = '') -> dict[str, Any]:
```

Generate API reference documentation from Python source files.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `source_path` | `str` | File or directory to document (relative to project root). When empty, documents the entire project source. | '' |
| `format` | `str` | Output format - "markdown", "mkdocs", or "sphinx_rst". | 'markdown' |
| `depth` | `str` | Visibility depth - "public", "protected", or "all". | 'public' |
| `include_examples` | `bool` | Whether to extract usage examples from test files. | True |
| `output_path` | `str` | File path to write output (relative to project root). When empty, returns the content without writing a file. | '' |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

### async `docs_generate_adr`

```python
async def docs_generate_adr(title: str, template: str = 'madr', context: str = '', decision: str = '', consequences: str = '', status: str = 'proposed', adr_directory: str = '', output_path: str = '', project_root: str = '') -> dict[str, Any]:
```

Create an Architecture Decision Record (ADR).

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `title` | `str` | Title of the decision (e.g. "Use MCP protocol"). | *required* |
| `template` | `str` | ADR template format - "madr" or "nygard". | 'madr' |
| `context` | `str` | Context and problem statement. | '' |
| `decision` | `str` | The decision that was made. | '' |
| `consequences` | `str` | Consequences of this decision. | '' |
| `status` | `str` | Decision status - "proposed", "accepted", "deprecated", or "superseded". | 'proposed' |
| `adr_directory` | `str` | Directory for ADR files (default: docs/decisions/). | '' |
| `output_path` | `str` | Override output file path. When empty, auto-generates from title and number. | '' |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

### async `docs_generate_onboarding`

```python
async def docs_generate_onboarding(output_path: str = '', project_root: str = '') -> dict[str, Any]:
```

Generate a getting-started / onboarding guide for the project.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `output_path` | `str` | Output file path (default: docs/ONBOARDING.md). | '' |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

### async `docs_generate_contributing`

```python
async def docs_generate_contributing(output_path: str = '', project_root: str = '') -> dict[str, Any]:
```

Generate a CONTRIBUTING.md file for the project.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `output_path` | `str` | Output file path (default: CONTRIBUTING.md in project root). | '' |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

### async `docs_generate_prd`

```python
async def docs_generate_prd(title: str, problem: str = '', personas: str = '', phases: str = '', constraints: str = '', non_goals: str = '', style: str = 'standard', auto_populate: bool = False, existing_content: str = '', output_path: str = '', project_root: str = '') -> dict[str, Any]:
```

Generate a Product Requirements Document (PRD) with phased requirements.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `title` | `str` | Title for the PRD (e.g. "User Authentication System"). | *required* |
| `problem` | `str` | Problem statement text. | '' |
| `personas` | `str` | Comma-separated list of user personas. | '' |
| `phases` | `str` | JSON array of phase objects with keys: name, description, requirements. Example: [{"name": "MVP", "requirements": ["Login"]}] | '' |
| `constraints` | `str` | Comma-separated list of technical constraints. | '' |
| `non_goals` | `str` | Comma-separated list of non-goals / out-of-scope items. | '' |
| `style` | `str` | PRD style - "standard" or "comprehensive". | 'standard' |
| `auto_populate` | `bool` | Enrich from project analyzers (ModuleMap, Metadata, etc). | False |
| `existing_content` | `str` | Existing PRD markdown to merge with (preserves edits). | '' |
| `output_path` | `str` | File path to write the PRD (relative to project root). When empty, returns the content without writing a file. | '' |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

### async `docs_generate_diagram`

```python
async def docs_generate_diagram(diagram_type: str = 'dependency', scope: str = 'project', depth: int = 2, format: str = '', direction: str = 'TD', show_external: bool = False, project_root: str = '') -> dict[str, Any]:
```

Generate Mermaid or PlantUML diagrams from code analysis.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `diagram_type` | `str` | Type of diagram to generate. | 'dependency' |
| `scope` | `str` | "project" for full project, or a file path for single-file scope. | 'project' |
| `depth` | `int` | Max traversal depth for dependency/module diagrams (default: 2). | 2 |
| `format` | `str` | Output format - "mermaid" or "plantuml" (default: from config). | '' |
| `direction` | `str` | Graph direction - "TD" (top-down) or "LR" (left-right). | 'TD' |
| `show_external` | `bool` | Include external dependencies in dependency diagrams. | False |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.server_git_tools`

DocsMCP git analysis tools -- docs_git_summary.

This module registers on the shared ``mcp`` FastMCP instance from
``server.py`` and provides git history analysis for documentation generation.

## Functions

### async `docs_git_summary`

```python
async def docs_git_summary(limit: int = 50, since: str = '', path: str = '', include_versions: bool = True, project_root: str = '') -> dict[str, Any]:
```

Analyze git history for documentation generation.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `limit` | `int` | Maximum number of recent commits to return (default 50). | 50 |
| `since` | `str` | ISO date string -- only include commits after this date. | '' |
| `path` | `str` | If given, only commits touching this file/directory. | '' |
| `include_versions` | `bool` | Whether to detect version boundaries from tags. | True |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.server_helpers`

Helper functions for DocsMCP server — response builders and singleton caches.

## Functions

### `error_response`

```python
def error_response(tool_name: str, code: str, message: str) -> dict[str, Any]:
```

Build a standard error response envelope.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `tool_name` | `str` |  | *required* |
| `code` | `str` |  | *required* |
| `message` | `str` |  | *required* |

### `success_response`

```python
def success_response(tool_name: str, elapsed_ms: int, data: dict[str, Any], *, degraded: bool | object = _SENTINEL, next_steps: list[str] | None = None) -> dict[str, Any]:
```

Build a standard success response envelope.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `tool_name` | `str` |  | *required* |
| `elapsed_ms` | `int` |  | *required* |
| `data` | `dict[str, Any]` |  | *required* |
| `degraded` | `bool \| object` |  | _SENTINEL |
| `next_steps` | `list[str] \| None` |  | None |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.server_resources`

MCP resources and workflow prompts for DocsMCP.

Registers MCP resources (docs://status, docs://config, docs://coverage) and
workflow prompts (docs_workflow_overview, docs_workflow) on the shared ``mcp``
FastMCP instance from ``server.py``.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.server_val_tools`

DocsMCP validation tools -- docs_check_drift, docs_check_completeness,
docs_check_links, docs_check_freshness.

These tools register on the shared ``mcp`` FastMCP instance from
``server.py`` and provide documentation validation capabilities.

## Functions

### async `docs_check_drift`

```python
async def docs_check_drift(since: str = '', doc_dirs: str = '', project_root: str = '') -> dict[str, Any]:
```

Detect documentation drift -- code changes not reflected in docs.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `since` | `str` | Reserved for future use (git ref or date filter). | '' |
| `doc_dirs` | `str` | Comma-separated list of documentation directories to search. When empty, scans the entire project for doc files. | '' |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

### async `docs_check_completeness`

```python
async def docs_check_completeness(project_root: str = '') -> dict[str, Any]:
```

Check documentation completeness across multiple categories.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `str` | Override project root path (default: configured root). | '' |

### async `docs_check_links`

```python
async def docs_check_links(files: str = '', project_root: str = '') -> dict[str, Any]:
```

Validate internal links in documentation files.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `files` | `str` | Comma-separated list of specific files to check (relative or absolute paths). When empty, scans all documentation files. | '' |
| `project_root` | `str` | Override project root path (default: configured root). | '' |

### async `docs_check_freshness`

```python
async def docs_check_freshness(project_root: str = '') -> dict[str, Any]:
```

Score documentation freshness based on file modification times.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `str` | Override project root path (default: configured root). | '' |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.validators`

Documentation validation engine for DocsMCP.

Provides drift detection, completeness checking, link validation,
and freshness scoring for project documentation.

---

*Documentation coverage: 0.0%*


---

# `packages.docs-mcp.src.docs_mcp.validators.completeness`

Documentation completeness checker.

## Classes

### `CompletenessCategory`(BaseModel)

A single category in the completeness report.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `name` | `str` |  |
| `score` | `float` | `0.0` |
| `present` | `list[str]` | `[]` |
| `missing` | `list[str]` | `[]` |
| `weight` | `float` | `1.0` |

### `CompletenessReport`(BaseModel)

Aggregated completeness check results.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `overall_score` | `float` | `0.0` |
| `categories` | `list[CompletenessCategory]` | `[]` |
| `recommendations` | `list[str]` | `[]` |

### `CompletenessChecker`

Check documentation completeness across multiple categories.

**Methods:**

#### `check`

```python
def check(self, project_root: Path) -> CompletenessReport:
```

Run completeness check.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Root of the project to scan. | *required* |

**Returns:** A CompletenessReport with per-category scores and recommendations.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.validators.drift`

Drift detection: identify code changes not reflected in documentation.

## Classes

### `DriftItem`(BaseModel)

A single drift finding between code and documentation.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `file_path` | `str` |  |
| `drift_type` | `str` |  |
| `severity` | `str` | `'warning'` |
| `description` | `str` | `''` |
| `code_last_modified` | `str` | `''` |
| `doc_last_modified` | `str` | `''` |

### `DriftReport`(BaseModel)

Aggregated drift detection results.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `total_items` | `int` | `0` |
| `items` | `list[DriftItem]` | `[]` |
| `drift_score` | `float` | `0.0` |
| `checked_files` | `int` | `0` |

### `DriftDetector`

Detect documentation drift relative to code changes.

**Methods:**

#### `check`

```python
def check(self, project_root: Path, *, since: str | None = None, doc_dirs: list[str] | None = None) -> DriftReport:
```

Run drift detection.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Root of the project to scan. | *required* |
| `since` | `str \| None` | Unused for MVP (reserved for git ref/date filtering). | None |
| `doc_dirs` | `list[str] \| None` | Optional list of directories containing docs. | None |

**Returns:** A DriftReport with drift findings.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*


---

# `packages.docs-mcp.src.docs_mcp.validators.freshness`

Documentation freshness scoring based on file modification times.

## Classes

### `FreshnessItem`(BaseModel)

Freshness info for a single documentation file.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `file_path` | `str` |  |
| `last_modified` | `str` |  |
| `age_days` | `int` |  |
| `freshness` | `str` |  |

### `FreshnessReport`(BaseModel)

Aggregated freshness scoring results.

**Class Variables:**

| Name | Type | Default |
|------|------|---------|
| `items` | `list[FreshnessItem]` | `[]` |
| `average_age_days` | `float` | `0.0` |
| `freshness_score` | `float` | `0.0` |

### `FreshnessChecker`

Score documentation freshness based on file modification times.

**Methods:**

#### `check`

```python
def check(self, project_root: Path) -> FreshnessReport:
```

Run freshness check.

**Parameters:**

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `project_root` | `Path` | Root of the project to scan. | *required* |

**Returns:** A FreshnessReport with per-file freshness and overall score.

## Constants

| Name | Type | Value |
|------|------|-------|
| `logger` | `` | `structlog.get_logger(__name__)` |

---

*Documentation coverage: 100.0%*
