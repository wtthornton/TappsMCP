"""Tech-stack detection - languages, libraries, frameworks, and domains.

Adapted from TappsCodingAgents ``core/detectors/tech_stack_detector.py``.
Uses stdlib ``tomllib`` (Python 3.12+) instead of ``tomli``.
"""

from __future__ import annotations

import ast
import json
import re
import tomllib
from collections import Counter
from pathlib import Path  # noqa: TC003

import structlog

from tapps_mcp.project.models import TechStack

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".swift": "swift",
    ".sh": "shell",
    ".bash": "shell",
    ".sql": "sql",
}

_FRAMEWORK_PATTERNS: dict[str, str] = {
    "flask": "flask",
    "django": "django",
    "fastapi": "fastapi",
    "starlette": "fastapi",
    "pyramid": "pyramid",
    "tornado": "tornado",
    "sanic": "sanic",
    "aiohttp": "aiohttp",
    "bottle": "bottle",
    "cherrypy": "cherrypy",
    "react": "react",
    "vue": "vue",
    "angular": "angular",
    "express": "express",
    "next": "next.js",
    "nuxt": "nuxt.js",
    "svelte": "svelte",
    "nest": "nestjs",
    "pytest": "pytest",
    "unittest": "unittest",
    "jest": "jest",
    "mocha": "mocha",
    "jasmine": "jasmine",
    "spring": "spring",
    "rails": "rails",
    "laravel": "laravel",
}

_DOMAIN_PATTERNS: dict[str, list[str]] = {
    "web": ["flask", "django", "fastapi", "express", "react", "vue", "angular", "next.js"],
    "api": ["fastapi", "flask", "express", "django", "aiohttp"],
    "data": ["pandas", "numpy", "polars", "dask", "spark"],
    "ml": ["tensorflow", "pytorch", "scikit-learn", "keras", "transformers"],
    "database": ["sqlalchemy", "psycopg2", "pymongo", "redis", "elasticsearch"],
    "cloud": ["boto3", "google-cloud", "azure", "kubernetes"],
    "testing": ["pytest", "unittest", "jest", "mocha", "selenium"],
    "devops": ["docker", "kubernetes", "terraform", "ansible"],
}

_MIN_LANGUAGE_FILE_COUNT = 3

_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".tox",
        ".eggs",
        "htmlcov",
        ".mypy_cache",
        ".tapps-agents",
        ".tapps-mcp-cache",
        "site-packages",
    }
)


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class TechStackDetector:
    """Detect languages, libraries, frameworks, and domains from a project."""

    def __init__(self, project_root: Path, *, max_files: int = 1000) -> None:
        self.project_root = project_root
        self.max_files = max_files
        self._languages: set[str] = set()
        self._libraries: set[str] = set()
        self._frameworks: set[str] = set()
        self._domains: set[str] = set()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def detect_all(self) -> TechStack:
        """Run all detectors and return a :class:`TechStack`."""
        self.detect_languages()
        self.detect_libraries()
        self.detect_frameworks()
        self.detect_domains()
        priority = self._context7_priority()
        return TechStack(
            languages=sorted(self._languages),
            libraries=sorted(self._libraries),
            frameworks=sorted(self._frameworks),
            domains=sorted(self._domains),
            context7_priority=priority,
        )

    def detect_languages(self) -> list[str]:
        counts: Counter[str] = Counter()
        scanned = 0
        for ext, lang in _LANGUAGE_EXTENSIONS.items():
            for fp in self.project_root.glob(f"**/*{ext}"):
                if _should_skip(fp):
                    continue
                counts[lang] += 1
                scanned += 1
                if scanned >= self.max_files:
                    break
            if scanned >= self.max_files:
                break
        self._languages = {lang for lang, n in counts.items() if n >= _MIN_LANGUAGE_FILE_COUNT}
        return sorted(self._languages)

    def detect_libraries(self) -> list[str]:
        self._parse_requirements(self.project_root / "requirements.txt")
        self._parse_pyproject(self.project_root / "pyproject.toml")
        self._parse_setup_py(self.project_root / "setup.py")
        self._parse_package_json(self.project_root / "package.json")
        return sorted(self._libraries)

    def detect_frameworks(self) -> list[str]:
        n = 0
        for py in self.project_root.glob("**/*.py"):
            if _should_skip(py):
                continue
            self._python_imports(py)
            n += 1
            if n >= self.max_files:
                break
        for ext in (".js", ".ts", ".jsx", ".tsx"):
            for js in self.project_root.glob(f"**/*{ext}"):
                if _should_skip(js):
                    continue
                self._js_imports(js)
                n += 1
                if n >= self.max_files:
                    break
            if n >= self.max_files:
                break
        return sorted(self._frameworks)

    def detect_domains(self) -> list[str]:
        all_tech = self._libraries | self._frameworks
        for domain, indicators in _DOMAIN_PATTERNS.items():
            for ind in indicators:
                if any(ind in t.lower() for t in all_tech):
                    self._domains.add(domain)
                    break
        if (self.project_root / "tests").exists() or (self.project_root / "test").exists():
            self._domains.add("testing")
        if (self.project_root / "Dockerfile").exists():
            self._domains.add("devops")
        return sorted(self._domains)

    # ------------------------------------------------------------------
    # Private parsers
    # ------------------------------------------------------------------

    def _parse_requirements(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                m = re.match(r"^([a-zA-Z0-9\-_]+)", stripped)
                if m:
                    self._libraries.add(m.group(1).lower())
        except OSError:
            pass

    def _parse_pyproject(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            for dep in data.get("project", {}).get("dependencies", []):
                m = re.match(r"^([a-zA-Z0-9\-_]+)", dep)
                if m:
                    self._libraries.add(m.group(1).lower())
            poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            for dep in poetry_deps:
                if dep != "python":
                    self._libraries.add(dep.lower())
        except (OSError, tomllib.TOMLDecodeError):
            pass

    def _parse_setup_py(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            content = path.read_text(encoding="utf-8")
            m = re.search(r"install_requires\s*=\s*\[(.*?)]", content, re.DOTALL)
            if m:
                for pkg in re.findall(r'["\']([a-zA-Z0-9\-_]+)', m.group(1)):
                    self._libraries.add(pkg.lower())
        except OSError:
            pass

    def _parse_package_json(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for section in ("dependencies", "devDependencies"):
                for pkg in data.get(section, {}):
                    self._libraries.add(pkg.lower())
        except (OSError, json.JSONDecodeError):
            pass

    def _python_imports(self, path: Path) -> None:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self._match_framework(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self._match_framework(node.module.split(".")[0])
        except (SyntaxError, UnicodeDecodeError, OSError):
            pass

    def _js_imports(self, path: Path) -> None:
        try:
            content = path.read_text(encoding="utf-8")
            for pkg in re.findall(r"""import\s+.*?\s+from\s+['"]([^'"]+)['"]""", content):
                name = pkg.split("/")[0]
                if not name.startswith("."):
                    self._match_framework(name)
            for pkg in re.findall(r"""require\(['"]([^'"]+)['"]\)""", content):
                name = pkg.split("/")[0]
                if not name.startswith("."):
                    self._match_framework(name)
        except (OSError, UnicodeDecodeError):
            pass

    def _match_framework(self, module: str) -> None:
        low = module.lower()
        for pattern, fw in _FRAMEWORK_PATTERNS.items():
            if pattern in low:
                self._frameworks.add(fw)

    def _context7_priority(self) -> list[str]:
        result = sorted(self._frameworks)
        others = sorted(self._libraries - self._frameworks)
        result.extend(others[:20])
        return result


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def _should_skip(path: Path) -> bool:
    return any(part in _SKIP_DIRS for part in path.parts)
