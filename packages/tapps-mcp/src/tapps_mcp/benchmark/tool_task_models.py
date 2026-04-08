"""MCPMark-inspired tool evaluation task definitions.

Defines deterministic tasks that measure the effectiveness of individual
MCP tools. Each task includes setup files with known issues, expected
tool calls, and verification criteria.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "BUILTIN_TASKS",
    "ToolTask",
    "ToolTaskResult",
    "ToolTaskVerification",
]


# ---------------------------------------------------------------------------
# Verification model
# ---------------------------------------------------------------------------


class ToolTaskVerification(BaseModel):
    """Verification criteria for a tool task."""

    model_config = ConfigDict(frozen=True)

    check_type: str = Field(
        description=(
            "Type of verification check: 'file_content', 'score_threshold', "
            "'test_pass', or 'no_security_issues'."
        ),
    )
    expected_file: str | None = Field(
        default=None,
        description="File path to check for content verification.",
    )
    expected_content_patterns: list[str] | None = Field(
        default=None,
        description="Regex patterns that the output file must match.",
    )
    min_quality_score: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Minimum quality score threshold (0-100).",
    )
    custom_verify: str | None = Field(
        default=None,
        description="Custom verification expression or description.",
    )


# ---------------------------------------------------------------------------
# Task model
# ---------------------------------------------------------------------------


class ToolTask(BaseModel):
    """A single tool evaluation task with setup and verification."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(description="Unique identifier for this task.")
    category: str = Field(
        description=(
            "Task category: 'quality', 'security', 'architecture', 'debugging', or 'refactoring'."
        ),
    )
    description: str = Field(description="Human-readable task description.")
    setup_files: dict[str, str] = Field(
        description="Mapping of filename to file content for task setup.",
    )
    expected_tools: list[str] = Field(
        description="List of MCP tools an ideal agent would call.",
    )
    verification: ToolTaskVerification = Field(
        description="Criteria for verifying task completion.",
    )
    difficulty: str = Field(
        description="Task difficulty: 'easy', 'medium', or 'hard'.",
    )


# ---------------------------------------------------------------------------
# Task result model
# ---------------------------------------------------------------------------


class ToolTaskResult(BaseModel):
    """Result from running a single tool task under specific conditions."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(description="Task that was evaluated.")
    condition: str = Field(
        description=(
            "Evaluation condition: 'all_tools', 'no_tools', 'single_tool', or 'all_minus_one'."
        ),
    )
    tool_name: str | None = Field(
        default=None,
        description="Tool name relevant to the condition (e.g. removed or isolated tool).",
    )
    resolved: bool = Field(description="Whether the task was resolved successfully.")
    tools_called: list[str] = Field(
        default_factory=list,
        description="Tools that were actually called during evaluation.",
    )
    call_count: int = Field(
        default=0,
        ge=0,
        description="Total number of tool calls made.",
    )
    token_usage: int = Field(
        default=0,
        ge=0,
        description="Total tokens consumed during evaluation.",
    )
    duration_ms: int = Field(
        default=0,
        ge=0,
        description="Wall-clock duration in milliseconds.",
    )


# ---------------------------------------------------------------------------
# Built-in tasks (20+ deterministic tasks)
# ---------------------------------------------------------------------------


def _build_builtin_tasks() -> list[ToolTask]:
    """Construct the full set of built-in benchmark tasks."""
    tasks: list[ToolTask] = []

    # -----------------------------------------------------------------------
    # Quality tasks (5)
    # -----------------------------------------------------------------------

    tasks.append(
        ToolTask(
            task_id="quality-unused-import",
            category="quality",
            description="Fix unused import in a Python file.",
            setup_files={
                "app.py": (
                    "import os\nimport sys\nimport json\n\n"
                    "def main() -> None:\n"
                    "    print(os.getcwd())\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_quick_check"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="app.py",
                expected_content_patterns=[
                    r"^import os$",
                    r"(?!.*import sys)",
                    r"(?!.*import json)",
                ],
            ),
            difficulty="easy",
        )
    )

    tasks.append(
        ToolTask(
            task_id="quality-reduce-complexity",
            category="quality",
            description="Reduce function cyclomatic complexity by extracting helpers.",
            setup_files={
                "processor.py": (
                    "def process(data: dict) -> str:\n"
                    "    result = ''\n"
                    "    if data.get('type') == 'a':\n"
                    "        if data.get('status') == 'active':\n"
                    "            if data.get('priority') > 5:\n"
                    "                result = 'high-a'\n"
                    "            else:\n"
                    "                result = 'low-a'\n"
                    "        else:\n"
                    "            result = 'inactive-a'\n"
                    "    elif data.get('type') == 'b':\n"
                    "        if data.get('status') == 'active':\n"
                    "            if data.get('priority') > 5:\n"
                    "                result = 'high-b'\n"
                    "            else:\n"
                    "                result = 'low-b'\n"
                    "        else:\n"
                    "            result = 'inactive-b'\n"
                    "    elif data.get('type') == 'c':\n"
                    "        if data.get('status') == 'active':\n"
                    "            result = 'active-c'\n"
                    "        else:\n"
                    "            result = 'inactive-c'\n"
                    "    else:\n"
                    "        result = 'unknown'\n"
                    "    return result\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_quick_check"],
            verification=ToolTaskVerification(
                check_type="score_threshold",
                min_quality_score=70.0,
            ),
            difficulty="medium",
        )
    )

    tasks.append(
        ToolTask(
            task_id="quality-add-type-annotations",
            category="quality",
            description="Add type annotations to untyped function signatures.",
            setup_files={
                "utils.py": (
                    "def calculate_total(items, tax_rate):\n"
                    "    subtotal = sum(item['price'] for item in items)\n"
                    "    return subtotal * (1 + tax_rate)\n"
                    "\n\n"
                    "def format_name(first, last, title=None):\n"
                    "    if title:\n"
                    "        return f'{title} {first} {last}'\n"
                    "    return f'{first} {last}'\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_quick_check"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="utils.py",
                expected_content_patterns=[
                    r"def calculate_total\(.*:.*\).*->",
                    r"def format_name\(.*:.*\).*->",
                ],
            ),
            difficulty="easy",
        )
    )

    tasks.append(
        ToolTask(
            task_id="quality-fix-line-length",
            category="quality",
            description="Fix lines exceeding 100-character limit.",
            setup_files={
                "config.py": (
                    "DEFAULT_CONFIGURATION_OPTIONS = {"
                    "'database_connection_string': "
                    "'postgresql://user:password@localhost:5432/mydb', "
                    "'cache_timeout_seconds': 3600, "
                    "'max_retry_attempts': 5}\n"
                    "\n\n"
                    "def get_configuration_value_from_environment"
                    "_or_default("
                    "key: str, default_value: str = '') -> str:\n"
                    "    import os\n"
                    "    return os.environ.get(key, default_value)\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_quick_check"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="config.py",
                custom_verify="No line exceeds 100 characters.",
            ),
            difficulty="easy",
        )
    )

    tasks.append(
        ToolTask(
            task_id="quality-improve-naming",
            category="quality",
            description="Improve variable and function naming for clarity.",
            setup_files={
                "calc.py": (
                    "def f(x, y, z):\n"
                    "    a = x * y\n"
                    "    b = a + z\n"
                    "    c = b / 100\n"
                    "    return c\n"
                    "\n\n"
                    "def g(d):\n"
                    "    e = []\n"
                    "    for i in d:\n"
                    "        if i > 0:\n"
                    "            e.append(i)\n"
                    "    return e\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_quick_check"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="calc.py",
                expected_content_patterns=[
                    r"def \w{4,}\(",
                ],
            ),
            difficulty="medium",
        )
    )

    # -----------------------------------------------------------------------
    # Security tasks (4)
    # -----------------------------------------------------------------------

    tasks.append(
        ToolTask(
            task_id="security-sql-injection",
            category="security",
            description="Fix SQL injection vulnerability by using parameterized queries.",
            setup_files={
                "db.py": (
                    "import sqlite3\n\n\n"
                    "def get_user(conn: sqlite3.Connection, username: str) -> dict:\n"
                    "    cursor = conn.execute(\n"
                    "        f\"SELECT * FROM users WHERE name = '{username}'\"\n"
                    "    )\n"
                    "    row = cursor.fetchone()\n"
                    "    return dict(row) if row else {}\n"
                ),
            },
            expected_tools=["tapps_security_scan", "tapps_score_file"],
            verification=ToolTaskVerification(
                check_type="no_security_issues",
                expected_file="db.py",
                expected_content_patterns=[
                    r"\?",
                ],
            ),
            difficulty="easy",
        )
    )

    tasks.append(
        ToolTask(
            task_id="security-hardcoded-secret",
            category="security",
            description="Remove hardcoded secret and use environment variable.",
            setup_files={
                "auth.py": (
                    "API_KEY = 'sk-proj-abc123def456ghi789'\n"
                    "DB_PASSWORD = 'SuperSecret123!'\n\n\n"
                    "def authenticate(token: str) -> bool:\n"
                    "    return token == API_KEY\n"
                ),
            },
            expected_tools=["tapps_security_scan", "tapps_score_file"],
            verification=ToolTaskVerification(
                check_type="no_security_issues",
                expected_file="auth.py",
                expected_content_patterns=[
                    r"os\.environ",
                ],
            ),
            difficulty="easy",
        )
    )

    tasks.append(
        ToolTask(
            task_id="security-path-traversal",
            category="security",
            description="Fix path traversal vulnerability in file serving.",
            setup_files={
                "server.py": (
                    "from pathlib import Path\n\n"
                    "UPLOAD_DIR = Path('/uploads')\n\n\n"
                    "def serve_file(filename: str) -> bytes:\n"
                    "    path = UPLOAD_DIR / filename\n"
                    "    return path.read_bytes()\n"
                ),
            },
            expected_tools=["tapps_security_scan", "tapps_score_file"],
            verification=ToolTaskVerification(
                check_type="no_security_issues",
                expected_file="server.py",
                expected_content_patterns=[
                    r"resolve\(\)|is_relative_to|\.\..*check",
                ],
            ),
            difficulty="medium",
        )
    )

    tasks.append(
        ToolTask(
            task_id="security-input-validation",
            category="security",
            description="Add input validation to a user registration function.",
            setup_files={
                "register.py": (
                    "def register_user(\n"
                    "    email: str, password: str, age: int\n"
                    ") -> dict:\n"
                    "    return {\n"
                    "        'email': email,\n"
                    "        'password': password,\n"
                    "        'age': age,\n"
                    "    }\n"
                ),
            },
            expected_tools=["tapps_security_scan", "tapps_score_file"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="register.py",
                expected_content_patterns=[
                    r"raise|ValueError|ValidationError",
                ],
            ),
            difficulty="medium",
        )
    )

    # -----------------------------------------------------------------------
    # Architecture tasks (4)
    # -----------------------------------------------------------------------

    tasks.append(
        ToolTask(
            task_id="arch-circular-import",
            category="architecture",
            description="Resolve circular import between two modules.",
            setup_files={
                "models.py": (
                    "from services import UserService\n\n\n"
                    "class User:\n"
                    "    name: str\n"
                    "    service: UserService\n"
                ),
                "services.py": (
                    "from models import User\n\n\n"
                    "class UserService:\n"
                    "    def get_user(self) -> User:\n"
                    "        return User()\n"
                ),
            },
            expected_tools=["tapps_dependency_graph", "tapps_impact_analysis"],
            verification=ToolTaskVerification(
                check_type="test_pass",
                custom_verify="No circular import error when importing either module.",
            ),
            difficulty="medium",
        )
    )

    tasks.append(
        ToolTask(
            task_id="arch-extract-shared",
            category="architecture",
            description="Extract duplicated logic into a shared module.",
            setup_files={
                "handler_a.py": (
                    "import json\nimport logging\n\n"
                    "logger = logging.getLogger(__name__)\n\n\n"
                    "def handle_a(data: str) -> dict:\n"
                    "    try:\n"
                    "        parsed = json.loads(data)\n"
                    "    except json.JSONDecodeError:\n"
                    "        logger.error('Invalid JSON')\n"
                    "        return {'error': 'invalid json'}\n"
                    "    return {'result': parsed.get('value', 0) * 2}\n"
                ),
                "handler_b.py": (
                    "import json\nimport logging\n\n"
                    "logger = logging.getLogger(__name__)\n\n\n"
                    "def handle_b(data: str) -> dict:\n"
                    "    try:\n"
                    "        parsed = json.loads(data)\n"
                    "    except json.JSONDecodeError:\n"
                    "        logger.error('Invalid JSON')\n"
                    "        return {'error': 'invalid json'}\n"
                    "    return {'result': parsed.get('value', 0) + 10}\n"
                ),
            },
            expected_tools=["tapps_dead_code", "tapps_impact_analysis"],
            verification=ToolTaskVerification(
                check_type="file_content",
                custom_verify="Shared JSON parsing logic extracted to a common module.",
            ),
            difficulty="medium",
        )
    )

    tasks.append(
        ToolTask(
            task_id="arch-implement-interface",
            category="architecture",
            description="Define a Protocol for loosely-coupled components.",
            setup_files={
                "storage.py": (
                    "class FileStorage:\n"
                    "    def save(self, key: str, data: bytes) -> None:\n"
                    "        with open(f'/tmp/{key}', 'wb') as f:\n"
                    "            f.write(data)\n"
                    "\n"
                    "    def load(self, key: str) -> bytes:\n"
                    "        with open(f'/tmp/{key}', 'rb') as f:\n"
                    "            return f.read()\n"
                    "\n\n"
                    "class S3Storage:\n"
                    "    def save(self, key: str, data: bytes) -> None:\n"
                    "        pass  # S3 upload\n"
                    "\n"
                    "    def load(self, key: str) -> bytes:\n"
                    "        return b''  # S3 download\n"
                ),
            },
            expected_tools=["tapps_lookup_docs", "tapps_score_file"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="storage.py",
                expected_content_patterns=[
                    r"Protocol|ABC|abstract",
                ],
            ),
            difficulty="hard",
        )
    )

    tasks.append(
        ToolTask(
            task_id="arch-add-error-handling",
            category="architecture",
            description="Add comprehensive error handling to a service function.",
            setup_files={
                "service.py": (
                    "import json\nfrom pathlib import Path\n\n\n"
                    "def load_config(path: str) -> dict:\n"
                    "    content = Path(path).read_text()\n"
                    "    config = json.loads(content)\n"
                    "    db_url = config['database']['url']\n"
                    "    return {'db_url': db_url}\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_lookup_docs"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="service.py",
                expected_content_patterns=[
                    r"try:",
                    r"except.*Error",
                ],
            ),
            difficulty="easy",
        )
    )

    # -----------------------------------------------------------------------
    # Debugging tasks (4)
    # -----------------------------------------------------------------------

    tasks.append(
        ToolTask(
            task_id="debug-off-by-one",
            category="debugging",
            description="Fix off-by-one error in range-based iteration.",
            setup_files={
                "pagination.py": (
                    "def paginate(items: list, page: int, per_page: int) -> list:\n"
                    "    start = page * per_page\n"
                    "    end = start + per_page - 1\n"
                    "    return items[start:end]\n"
                ),
                "test_pagination.py": (
                    "from pagination import paginate\n\n\n"
                    "def test_paginate_first_page() -> None:\n"
                    "    items = list(range(10))\n"
                    "    result = paginate(items, page=0, per_page=3)\n"
                    "    assert result == [0, 1, 2]\n"
                    "\n\n"
                    "def test_paginate_second_page() -> None:\n"
                    "    items = list(range(10))\n"
                    "    result = paginate(items, page=1, per_page=3)\n"
                    "    assert result == [3, 4, 5]\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_quick_check"],
            verification=ToolTaskVerification(
                check_type="test_pass",
                custom_verify="Both pagination tests pass.",
            ),
            difficulty="easy",
        )
    )

    tasks.append(
        ToolTask(
            task_id="debug-type-error",
            category="debugging",
            description="Fix type error in string/integer concatenation.",
            setup_files={
                "formatter.py": (
                    "def format_summary(name: str, count: int, total: float) -> str:\n"
                    "    percentage = count / total * 100\n"
                    "    return name + ': ' + count + '/' + total + ' (' + percentage + '%)'\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_quick_check"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="formatter.py",
                expected_content_patterns=[
                    r"str\(|f['\"]|format\(",
                ],
            ),
            difficulty="easy",
        )
    )

    tasks.append(
        ToolTask(
            task_id="debug-missing-return",
            category="debugging",
            description="Fix function that silently returns None on some paths.",
            setup_files={
                "validator.py": (
                    "def validate_email(email: str) -> bool:\n"
                    "    if '@' not in email:\n"
                    "        return False\n"
                    "    parts = email.split('@')\n"
                    "    if len(parts) != 2:\n"
                    "        return False\n"
                    "    if '.' not in parts[1]:\n"
                    "        return False\n"
                    "    # Missing explicit return True\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_quick_check"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="validator.py",
                expected_content_patterns=[
                    r"return True",
                ],
            ),
            difficulty="easy",
        )
    )

    tasks.append(
        ToolTask(
            task_id="debug-wrong-comparison",
            category="debugging",
            description="Fix incorrect comparison operator (= vs ==, is vs ==).",
            setup_files={
                "checker.py": (
                    "def check_status(status: str | None) -> str:\n"
                    "    if status is 'active':\n"
                    "        return 'running'\n"
                    "    if status is 'paused':\n"
                    "        return 'suspended'\n"
                    "    if status is None:\n"
                    "        return 'unknown'\n"
                    "    return 'other'\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_quick_check"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="checker.py",
                expected_content_patterns=[
                    r"status == ['\"]active['\"]",
                    r"status == ['\"]paused['\"]",
                    r"status is None",
                ],
            ),
            difficulty="easy",
        )
    )

    # -----------------------------------------------------------------------
    # Refactoring tasks (4)
    # -----------------------------------------------------------------------

    tasks.append(
        ToolTask(
            task_id="refactor-extract-function",
            category="refactoring",
            description="Extract repeated logic into a reusable function.",
            setup_files={
                "reports.py": (
                    "def daily_report(transactions: list[dict]) -> dict:\n"
                    "    total = 0.0\n"
                    "    for t in transactions:\n"
                    "        if t['type'] == 'credit':\n"
                    "            total += t['amount']\n"
                    "        elif t['type'] == 'debit':\n"
                    "            total -= t['amount']\n"
                    "    return {'period': 'daily', 'total': total}\n"
                    "\n\n"
                    "def weekly_report(transactions: list[dict]) -> dict:\n"
                    "    total = 0.0\n"
                    "    for t in transactions:\n"
                    "        if t['type'] == 'credit':\n"
                    "            total += t['amount']\n"
                    "        elif t['type'] == 'debit':\n"
                    "            total -= t['amount']\n"
                    "    return {'period': 'weekly', 'total': total}\n"
                ),
            },
            expected_tools=["tapps_dead_code", "tapps_score_file"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="reports.py",
                custom_verify="Duplicated total calculation extracted to a shared function.",
            ),
            difficulty="medium",
        )
    )

    tasks.append(
        ToolTask(
            task_id="refactor-simplify-conditional",
            category="refactoring",
            description="Simplify deeply nested conditionals using early returns.",
            setup_files={
                "access.py": (
                    "def check_access(\n"
                    "    user: dict, resource: dict, action: str\n"
                    ") -> bool:\n"
                    "    if user is not None:\n"
                    "        if user.get('active'):\n"
                    "            if resource is not None:\n"
                    "                if action in resource.get('allowed_actions', []):\n"
                    "                    if user.get('role') in "
                    "resource.get('allowed_roles', []):\n"
                    "                        return True\n"
                    "                    else:\n"
                    "                        return False\n"
                    "                else:\n"
                    "                    return False\n"
                    "            else:\n"
                    "                return False\n"
                    "        else:\n"
                    "            return False\n"
                    "    else:\n"
                    "        return False\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_quick_check"],
            verification=ToolTaskVerification(
                check_type="score_threshold",
                min_quality_score=70.0,
            ),
            difficulty="medium",
        )
    )

    tasks.append(
        ToolTask(
            task_id="refactor-modernize-syntax",
            category="refactoring",
            description="Modernize legacy Python patterns to Python 3.12+ idioms.",
            setup_files={
                "legacy.py": (
                    "from typing import Dict, List, Optional, Tuple, Union\n\n\n"
                    "def process(\n"
                    "    items: List[Dict[str, Union[str, int]]],\n"
                    "    default: Optional[str] = None,\n"
                    ") -> Tuple[List[str], int]:\n"
                    "    results = list()\n"
                    "    count = 0\n"
                    "    for item in items:\n"
                    "        name = item.get('name', default)\n"
                    "        if name is not None:\n"
                    "            results.append(str(name))\n"
                    "            count = count + 1\n"
                    "    return (results, count)\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_quick_check"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="legacy.py",
                expected_content_patterns=[
                    r"list\[",
                    r"dict\[",
                    r"\| None",
                ],
            ),
            difficulty="easy",
        )
    )

    tasks.append(
        ToolTask(
            task_id="refactor-rename-consistently",
            category="refactoring",
            description="Rename inconsistent identifiers to follow PEP 8 conventions.",
            setup_files={
                "models.py": (
                    "class userAccount:\n"
                    "    def __init__(self, UserName: str, emailAddress: str) -> None:\n"
                    "        self.UserName = UserName\n"
                    "        self.emailAddress = emailAddress\n"
                    "\n"
                    "    def GetDisplayName(self) -> str:\n"
                    "        return f'{self.UserName} <{self.emailAddress}>'\n"
                    "\n"
                    "    def updateEmail(self, newEmail: str) -> None:\n"
                    "        self.emailAddress = newEmail\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_quick_check"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="models.py",
                expected_content_patterns=[
                    r"class [A-Z][a-z]",
                    r"def [a-z_]+\(",
                ],
            ),
            difficulty="medium",
        )
    )

    # -----------------------------------------------------------------------
    # Additional tasks to reach 21 total
    # -----------------------------------------------------------------------

    tasks.append(
        ToolTask(
            task_id="quality-docstring-coverage",
            category="quality",
            description="Add docstrings to all public functions and classes.",
            setup_files={
                "api.py": (
                    "class DataProcessor:\n"
                    "    def __init__(self, config: dict) -> None:\n"
                    "        self.config = config\n"
                    "\n"
                    "    def transform(self, raw: list[dict]) -> list[dict]:\n"
                    "        return [self._process_item(item) for item in raw]\n"
                    "\n"
                    "    def _process_item(self, item: dict) -> dict:\n"
                    "        return {k: str(v).strip() for k, v in item.items()}\n"
                    "\n\n"
                    "def load_data(path: str) -> list[dict]:\n"
                    "    import json\n"
                    "    with open(path) as f:\n"
                    "        return json.load(f)\n"
                ),
            },
            expected_tools=["tapps_score_file", "tapps_quick_check"],
            verification=ToolTaskVerification(
                check_type="file_content",
                expected_file="api.py",
                expected_content_patterns=[
                    r'""".*"""',
                ],
            ),
            difficulty="easy",
        )
    )

    return tasks


BUILTIN_TASKS: list[ToolTask] = _build_builtin_tasks()
