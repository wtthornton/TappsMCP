# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in TappsMCP, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please email security concerns to the repository maintainers via GitHub's private vulnerability reporting:

1. Go to the [Security tab](../../security) of this repository
2. Click "Report a vulnerability"
3. Fill in the details of the vulnerability

### What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response timeline

- **Acknowledgement**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Fix release**: Depends on severity (critical: ASAP, high: 1-2 weeks, medium/low: next release)

## Security Architecture

TappsMCP implements several security layers:

- **Path validation**: All file operations are validated against a project root boundary
- **Secret scanning**: Detects and redacts API keys, tokens, passwords, and PII
- **RAG safety**: Prompt injection detection on retrieved documentation
- **Governance layer**: Content filtering before tool responses
- **Subprocess sandboxing**: Timeouts and controlled environment for external tool execution

## Scope

The following are in scope for security reports:

- Path traversal or boundary escape
- Prompt injection bypass in RAG safety filters
- Secret/PII leakage through tool outputs
- Command injection via subprocess execution
- Authentication/authorization bypass (when using HTTP transport)

The following are out of scope:

- Denial of service via resource exhaustion (mitigated by timeouts and limits)
- Vulnerabilities in upstream dependencies (report to those projects directly)
- Issues requiring physical access to the host machine
