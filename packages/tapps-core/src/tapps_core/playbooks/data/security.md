# Security playbook

## When to use

Auth changes, secrets handling, new endpoints, dependency upgrades, or pre-release audits.

## Workflow

1. Call `tapps_session_start()` if not already called.
2. Call `tapps_lookup_docs(library="python-security", topic="input validation")` for patterns.
3. Run `tapps_security_scan(file_path="...")` on every changed sensitive module.
4. Run `tapps_dependency_scan()` before release or when lockfiles change.
5. Close with `/tapps-finish-task` and `task_type=security`.

## Checklist

- [ ] No secrets, tokens, or credentials in source or logs.
- [ ] User input validated at trust boundaries.
- [ ] Dependencies scanned for known CVEs.
- [ ] Security gate findings triaged by severity before merge.

## Exit criteria

Security scan and quality gate pass on changed files; CVE scan run when dependencies changed.
