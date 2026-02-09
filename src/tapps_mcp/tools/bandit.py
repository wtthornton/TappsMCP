"""Bandit security scanner wrapper."""

from __future__ import annotations

import json

import structlog

from tapps_mcp.scoring.models import SecurityIssue
from tapps_mcp.tools.subprocess_runner import run_command, run_command_async

logger = structlog.get_logger(__name__)

# OWASP Top 10 2021 mapping for common Bandit rules
_OWASP_MAP: dict[str, str] = {
    "B101": "A05:2021-Security Misconfiguration",  # assert
    "B102": "A03:2021-Injection",  # exec
    "B103": "A05:2021-Security Misconfiguration",  # set_bad_file_permissions
    "B104": "A05:2021-Security Misconfiguration",  # hardcoded_bind_all_interfaces
    "B105": "A07:2021-Identification and Authentication Failures",  # hardcoded_password_string
    "B106": "A07:2021-Identification and Authentication Failures",  # hardcoded_password_funcarg
    "B107": "A07:2021-Identification and Authentication Failures",  # hardcoded_password_default
    "B108": "A01:2021-Broken Access Control",  # hardcoded_tmp_directory
    "B110": "A05:2021-Security Misconfiguration",  # try_except_pass
    "B112": "A05:2021-Security Misconfiguration",  # try_except_continue
    "B201": "A03:2021-Injection",  # flask_debug_true
    "B301": "A08:2021-Software and Data Integrity Failures",  # pickle
    "B302": "A08:2021-Software and Data Integrity Failures",  # marshal
    "B303": "A02:2021-Cryptographic Failures",  # md5/sha1
    "B304": "A02:2021-Cryptographic Failures",  # insecure cipher
    "B305": "A02:2021-Cryptographic Failures",  # insecure cipher mode
    "B306": "A05:2021-Security Misconfiguration",  # mktemp_q
    "B307": "A03:2021-Injection",  # eval
    "B308": "A03:2021-Injection",  # mark_safe
    "B310": "A10:2021-Server-Side Request Forgery",  # urllib_urlopen
    "B311": "A02:2021-Cryptographic Failures",  # random
    "B312": "A05:2021-Security Misconfiguration",  # telnetlib
    "B320": "A03:2021-Injection",  # xml
    "B321": "A05:2021-Security Misconfiguration",  # ftp
    "B323": "A02:2021-Cryptographic Failures",  # unverified_context
    "B324": "A02:2021-Cryptographic Failures",  # hashlib insecure
    "B501": "A02:2021-Cryptographic Failures",  # request_with_no_cert_validation
    "B502": "A02:2021-Cryptographic Failures",  # ssl_with_bad_version
    "B503": "A02:2021-Cryptographic Failures",  # ssl_with_bad_defaults
    "B506": "A04:2021-Insecure Design",  # yaml_load
    "B507": "A02:2021-Cryptographic Failures",  # ssh_no_host_key_verification
    "B601": "A03:2021-Injection",  # paramiko_calls
    "B602": "A03:2021-Injection",  # subprocess_popen_with_shell_equals_true
    "B603": "A03:2021-Injection",  # subprocess_without_shell_equals_true
    "B604": "A03:2021-Injection",  # any_other_function_with_shell_equals_true
    "B605": "A03:2021-Injection",  # start_process_with_a_shell
    "B606": "A03:2021-Injection",  # start_process_with_no_shell
    "B607": "A03:2021-Injection",  # start_process_with_partial_path
    "B608": "A03:2021-Injection",  # hardcoded_sql_expressions
    "B609": "A03:2021-Injection",  # linux_commands_wildcard_injection
    "B610": "A03:2021-Injection",  # django_extra_used
    "B611": "A03:2021-Injection",  # django_rawsql_used
    "B701": "A03:2021-Injection",  # jinja2_autoescape_false
    "B702": "A03:2021-Injection",  # use_of_mako_templates
    "B703": "A03:2021-Injection",  # django_mark_safe
}


def _map_owasp(code: str) -> str | None:
    """Map a bandit rule code to an OWASP category."""
    return _OWASP_MAP.get(code)


def parse_bandit_json(raw: str) -> list[SecurityIssue]:
    """Parse bandit ``-f json`` output into ``SecurityIssue`` models."""
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    results = data.get("results", [])
    issues: list[SecurityIssue] = []
    for r in results:
        code = r.get("test_id", "unknown")
        issues.append(
            SecurityIssue(
                code=code,
                message=r.get("issue_text", ""),
                file=r.get("filename", ""),
                line=r.get("line_number", 0),
                severity=r.get("issue_severity", "MEDIUM").lower(),
                confidence=r.get("issue_confidence", "MEDIUM").lower(),
                owasp=_map_owasp(code),
            )
        )
    return issues


def calculate_security_score(issues: list[SecurityIssue]) -> float:
    """Convert bandit issues into a 0-10 security score."""
    from tapps_mcp.scoring.constants import clamp_individual

    high = sum(1 for i in issues if i.severity in ("high", "critical"))
    medium = sum(1 for i in issues if i.severity == "medium")
    score = 10.0 - (high * 3.0 + medium * 1.0)
    return clamp_individual(score)


_BANDIT_ARGS: list[str] = [
    "bandit",
    "-f",
    "json",
    "--quiet",
]


def run_bandit_check(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[SecurityIssue]:
    """Run bandit on a single file synchronously."""
    result = run_command(
        [*_BANDIT_ARGS, file_path],
        cwd=cwd,
        timeout=timeout,
    )
    # bandit exits non-zero when issues found — that's expected
    return parse_bandit_json(result.stdout)


async def run_bandit_check_async(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[SecurityIssue]:
    """Run bandit on a single file asynchronously."""
    result = await run_command_async(
        [*_BANDIT_ARGS, file_path],
        cwd=cwd,
        timeout=timeout,
    )
    return parse_bandit_json(result.stdout)
