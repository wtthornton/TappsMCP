"""Domain-specific security anti-pattern library for tapps_security_scan (TAP-477).

Each domain entry maps to a list of SecurityPattern records covering the most
important FAIL/PASS examples for that attack surface.  Domain checks are additive
— the generic scan still runs regardless.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

SupportedDomain = Literal["auth", "payments", "uploads", "api", "data"]

SUPPORTED_DOMAINS: frozenset[str] = frozenset({"auth", "payments", "uploads", "api", "data"})


@dataclass(frozen=True)
class SecurityPattern:
    """A single domain-specific security anti-pattern."""

    name: str
    severity: Literal["critical", "high", "medium", "low"]
    description: str
    fail_example: str
    fix: str
    # Regex matched against file source; match = finding
    pattern: str


@dataclass
class DomainFinding:
    """A matched domain-specific security finding."""

    domain: str
    pattern: str
    severity: str
    description: str
    fail_example: str
    fix: str
    line: int = 0
    matched_text: str = ""


# ---------------------------------------------------------------------------
# Pattern library (~5 patterns per domain)
# ---------------------------------------------------------------------------

_AUTH_PATTERNS: list[SecurityPattern] = [
    SecurityPattern(
        name="hardcoded_secret_key",
        severity="critical",
        description="Hardcoded SECRET_KEY or JWT secret in source",
        fail_example='SECRET_KEY = "my-hard-coded-secret"',
        fix="Load from environment: SECRET_KEY = os.environ['SECRET_KEY']",
        pattern=r'(?i)(secret_key|jwt_secret|signing_key)\s*=\s*["\'][^"\']{8,}["\']',
    ),
    SecurityPattern(
        name="weak_password_hashing",
        severity="high",
        description="Weak or missing password hashing (md5/sha1 for passwords)",
        fail_example="hashed = hashlib.md5(password.encode()).hexdigest()",
        fix="Use bcrypt, argon2, or passlib: hashed = bcrypt.hash(password)",
        pattern=r"hashlib\.(md5|sha1|sha256)\s*\(\s*password",
    ),
    SecurityPattern(
        name="timing_attack_comparison",
        severity="high",
        description="Direct string comparison of tokens/secrets (timing attack)",
        fail_example="if token == expected_token:",
        fix="Use hmac.compare_digest(token, expected_token)",
        pattern=r"if\s+\w*token\w*\s*==\s*\w",
    ),
    SecurityPattern(
        name="debug_auth_bypass",
        severity="critical",
        description="Auth bypass via debug/dev flag",
        fail_example="if DEBUG: return True  # skip auth in dev",
        fix="Never bypass auth based on DEBUG flag; use test credentials instead",
        pattern=r"(?i)if\s+(debug|dev_mode|testing)\s*[:=].*#.*auth",
    ),
    SecurityPattern(
        name="insecure_cookie",
        severity="medium",
        description="Session cookie without Secure or HttpOnly flags",
        fail_example='response.set_cookie("session", token)',
        fix='response.set_cookie("session", token, secure=True, httponly=True, samesite="lax")',
        pattern=r'set_cookie\s*\([^)]*\)(?!.*secure\s*=\s*True)',
    ),
]

_PAYMENTS_PATTERNS: list[SecurityPattern] = [
    SecurityPattern(
        name="raw_card_number_logged",
        severity="critical",
        description="Card number or CVV logged or printed",
        fail_example='logger.info(f"Processing card: {card_number}")',
        fix="Never log card data; log only last 4 digits after masking",
        pattern=r"(?i)(log|print)\s*\(.*card[_\s]?(number|num|no|cvv|cvc)",
    ),
    SecurityPattern(
        name="amount_client_side",
        severity="high",
        description="Payment amount taken directly from user input without server-side validation",
        fail_example="amount = request.json['amount']",
        fix="Always compute amount server-side from the order record; never trust client",
        pattern=r"amount\s*=\s*request\.(json|data|form|args)\[",
    ),
    SecurityPattern(
        name="stripe_key_hardcoded",
        severity="critical",
        description="Hardcoded Stripe or payment API key",
        fail_example='stripe.api_key = "sk_live_..."',
        fix="Load from environment: stripe.api_key = os.environ['STRIPE_SECRET_KEY']",
        pattern=r'(?i)(stripe\.api_key|payment_secret)\s*=\s*["\'](?:sk_live|pk_live)',
    ),
    SecurityPattern(
        name="idempotency_missing",
        severity="medium",
        description="Charge/transfer call missing idempotency key",
        fail_example="stripe.PaymentIntent.create(amount=amount, currency='usd')",
        fix="Pass idempotency_key= to prevent duplicate charges on retry",
        pattern=r"PaymentIntent\.create\([^)]*\)(?!.*idempotency_key)",
    ),
    SecurityPattern(
        name="webhook_signature_skipped",
        severity="high",
        description="Stripe/PayPal webhook not verifying signature",
        fail_example="payload = request.data  # no signature check",
        fix="Use stripe.Webhook.construct_event(payload, sig_header, secret)",
        pattern=r"(?i)webhook.*payload\s*=\s*request\.(data|body)(?!.*construct_event)",
    ),
]

_UPLOADS_PATTERNS: list[SecurityPattern] = [
    SecurityPattern(
        name="no_mime_check",
        severity="high",
        description="File upload without MIME type validation",
        fail_example="file = request.files['upload']; file.save(destination)",
        fix="Check MIME with python-magic and allow-list safe types only",
        pattern=r"\.save\s*\(.*\)(?!.*mime|.*content_type|.*allowed_extensions)",
    ),
    SecurityPattern(
        name="path_traversal",
        severity="critical",
        description="Upload destination uses unsanitised filename (path traversal)",
        fail_example="dest = upload_dir / filename",
        fix="Use secure_filename() and resolve() to confine to upload dir",
        pattern=r"(?i)(upload_dir|save_path)\s*/\s*filename(?!.*secure_filename)",
    ),
    SecurityPattern(
        name="no_size_limit",
        severity="medium",
        description="No file size limit on upload (DoS risk)",
        fail_example="file.save(path)  # unlimited size",
        fix="Check len(file.read()) or use MAX_CONTENT_LENGTH in Flask",
        pattern=r"file\.save\(|shutil\.copyfileobj\(",
    ),
    SecurityPattern(
        name="execute_uploaded_file",
        severity="critical",
        description="Uploaded file path passed to exec/subprocess",
        fail_example="subprocess.run([uploaded_path])",
        fix="Never execute uploaded files; serve from static storage only",
        pattern=r"subprocess\.(run|Popen|call)\s*\(\s*\[?\s*upload",
    ),
    SecurityPattern(
        name="serve_from_user_controlled_path",
        severity="high",
        description="send_file called with user-supplied path",
        fail_example="send_file(request.args['path'])",
        fix="Map user input to an allow-listed set of paths; never pass raw user input",
        pattern=r"send_file\s*\(\s*request\.(args|json|form)",
    ),
]

_API_PATTERNS: list[SecurityPattern] = [
    SecurityPattern(
        name="no_rate_limiting",
        severity="medium",
        description="API endpoint with no rate-limiting decorator or middleware reference",
        fail_example="@app.route('/api/login', methods=['POST'])\ndef login(): ...",
        fix="Apply rate limiting: @limiter.limit('5/minute') before sensitive endpoints",
        pattern=r"@(app|router)\.(route|post|get)\s*\(['\"][^'\"]*(?:login|signup|reset)['\"]",
    ),
    SecurityPattern(
        name="cors_wildcard",
        severity="high",
        description="CORS configured with wildcard origin",
        fail_example='CORS(app, origins="*")',
        fix='Restrict to known origins: CORS(app, origins=["https://app.example.com"])',
        pattern=r'(?i)cors\s*\([^)]*origins\s*=\s*["\'][*]["\']',
    ),
    SecurityPattern(
        name="sql_string_format",
        severity="critical",
        description="SQL query built with string formatting (SQL injection)",
        fail_example='cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")',
        fix='Use parameterized queries: cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))',
        pattern=r"(?i)execute\s*\(\s*f[\"'].*(?:SELECT|INSERT|UPDATE|DELETE)",
    ),
    SecurityPattern(
        name="debug_endpoint_exposed",
        severity="high",
        description="Debug or internal endpoint exposed without auth check",
        fail_example="@app.route('/debug/env')\ndef show_env(): return dict(os.environ)",
        fix="Remove debug endpoints from production; protect with auth if needed",
        pattern=r"@.*route\s*\(['\"][^'\"]*(?:debug|internal|admin)['\"]",
    ),
    SecurityPattern(
        name="unvalidated_redirect",
        severity="medium",
        description="Redirect URL taken from user input without validation",
        fail_example="return redirect(request.args['next'])",
        fix="Validate redirect URL against an allow-list of safe paths",
        pattern=r"redirect\s*\(\s*request\.(args|json|form)",
    ),
]

_DATA_PATTERNS: list[SecurityPattern] = [
    SecurityPattern(
        name="pickle_untrusted",
        severity="critical",
        description="Deserialising untrusted data with pickle",
        fail_example="obj = pickle.loads(request.data)",
        fix="Use JSON or a safe serialiser; never pickle untrusted input",
        pattern=r"pickle\.loads?\s*\(\s*request\.",
    ),
    SecurityPattern(
        name="yaml_unsafe_load",
        severity="high",
        description="yaml.load without Loader (executes arbitrary Python)",
        fail_example="data = yaml.load(stream)",
        fix="Use yaml.safe_load(stream) always",
        pattern=r"yaml\.load\s*\([^)]*\)(?!.*safe_load)",
    ),
    SecurityPattern(
        name="pii_logged",
        severity="high",
        description="PII fields (email/ssn/dob) included in log output",
        fail_example='logger.info("User: %s %s", user.email, user.ssn)',
        fix="Mask PII before logging: logger.info('User: %s', mask(user.email))",
        pattern=r"(?i)(log|print)\s*\(.*\b(email|ssn|dob|date_of_birth|phone)\b",
    ),
    SecurityPattern(
        name="raw_query_from_input",
        severity="critical",
        description="Database query built from unsanitised user input",
        fail_example='db.execute("SELECT * FROM " + table_name)',
        fix="Use ORM or parameterized queries; validate table/column names against allow-list",
        pattern=r'(?i)execute\s*\(\s*["\'][^"\']*["\'\s]*\+\s*\w',
    ),
    SecurityPattern(
        name="insecure_deserialization",
        severity="high",
        description="eval() or exec() called on external data",
        fail_example="result = eval(request.json['expr'])",
        fix="Never eval/exec user input; use ast.literal_eval for safe literals only",
        pattern=r"\b(eval|exec)\s*\(\s*(?:request\.|input\()",
    ),
]

_DOMAIN_PATTERNS: dict[str, list[SecurityPattern]] = {
    "auth": _AUTH_PATTERNS,
    "payments": _PAYMENTS_PATTERNS,
    "uploads": _UPLOADS_PATTERNS,
    "api": _API_PATTERNS,
    "data": _DATA_PATTERNS,
}

# ---------------------------------------------------------------------------
# Auto-detection heuristics
# ---------------------------------------------------------------------------

_DOMAIN_HINTS: dict[str, list[str]] = {
    "auth": ["auth", "login", "token", "session", "jwt", "oauth", "password", "credential"],
    "payments": ["payment", "billing", "charge", "stripe", "invoice", "checkout", "order"],
    "uploads": ["upload", "file", "attachment", "media", "storage", "s3", "blob"],
    "api": ["api", "route", "endpoint", "handler", "view", "controller", "webhook"],
    "data": ["model", "schema", "serializer", "data", "db", "database", "repository"],
}


def detect_domain(file_path: Path, source: str = "") -> str | None:
    """Infer the security domain from file path and optional source text."""
    stem = file_path.stem.lower()
    path_str = str(file_path).lower()

    for domain, hints in _DOMAIN_HINTS.items():
        if any(h in stem or h in path_str for h in hints):
            return domain

    # Fall back to source content scanning (first 2000 chars)
    sample = source[:2000].lower()
    scores: dict[str, int] = {d: 0 for d in _DOMAIN_HINTS}
    for domain, hints in _DOMAIN_HINTS.items():
        for h in hints:
            scores[domain] += sample.count(h)

    best_domain, best_score = max(scores.items(), key=lambda x: x[1])
    return best_domain if best_score >= 3 else None


# ---------------------------------------------------------------------------
# Domain scan runner
# ---------------------------------------------------------------------------

def run_domain_scan(
    file_path: Path,
    source: str,
    domain: str,
) -> list[DomainFinding]:
    """Run domain-specific anti-pattern checks against *source* text.

    Returns a list of DomainFinding for matched patterns.  Empty list = clean.
    """
    patterns = _DOMAIN_PATTERNS.get(domain, [])
    findings: list[DomainFinding] = []
    lines = source.splitlines()

    for sp in patterns:
        try:
            regex = re.compile(sp.pattern, re.IGNORECASE | re.MULTILINE)
        except re.error:
            continue

        for lineno, line in enumerate(lines, start=1):
            if regex.search(line):
                findings.append(
                    DomainFinding(
                        domain=domain,
                        pattern=sp.name,
                        severity=sp.severity,
                        description=sp.description,
                        fail_example=sp.fail_example,
                        fix=sp.fix,
                        line=lineno,
                        matched_text=line.strip()[:120],
                    )
                )
                break  # one finding per pattern per file

    return findings
