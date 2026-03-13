# OWASP Top 10 Security Risks (2025)

## Overview

The OWASP Top 10 is a standard awareness document for developers and web application security. It represents a broad consensus about the most critical security risks to web applications. The 2025 edition is based on analysis of 175,000+ CVE records covering 248 CWEs within the 10 categories. It reflects a major methodology shift toward identifying root causes rather than symptoms, and incorporates feedback from security professionals worldwide.

## A01:2025 - Broken Access Control

### Description
Access control enforces policy such that users cannot act outside of their intended permissions. Failures typically lead to unauthorized information disclosure, modification, or destruction of all data or performing a business function outside the user's limits. Remains the #1 risk, with 3.73% of applications tested showing this vulnerability across 40 mapped CWEs. SSRF has been partially merged into this category.

### Common Vulnerabilities
- Bypassing access control checks by modifying the URL, internal application state, or the HTML page
- Allowing the primary key to be changed to another user's record
- Elevation of privilege
- Metadata manipulation, such as replaying or tampering with a JWT access control token
- Server-side request forgery (SSRF) enabling unauthorized access to internal resources

### Prevention
- Implement proper access control checks on every request
- Use deny-by-default access control policies
- Enforce record ownership rather than accepting user input
- Disable web server directory listing
- Log access control failures and alert administrators

## A02:2025 - Security Misconfiguration

### Description
Moved up from #5 in 2021 to #2 in 2025, with 3.00% of applications tested and 16 mapped CWEs. Security misconfiguration is the most commonly seen issue. This is commonly a result of insecure default configurations, incomplete or ad hoc configurations, open cloud storage, misconfigured HTTP headers, and verbose error messages containing sensitive information.

### Common Misconfigurations
- Default accounts and passwords still enabled
- Unnecessary features enabled or installed
- Insecure default configurations
- Missing security headers
- Verbose error messages revealing stack traces
- Unpatched systems

### Prevention
- Implement a secure configuration process
- Review and update configurations regularly
- Implement a minimal platform without unnecessary features
- Use security headers (HSTS, CSP, X-Frame-Options, etc.)
- Use automated tools to verify configurations
- Keep all software and dependencies up to date

## A03:2025 - Injection

### Description
Injection flaws occur when untrusted data is sent to an interpreter as part of a command or query. The attacker's hostile data can trick the interpreter into executing unintended commands or accessing data without proper authorization. Includes SQL injection, XSS, and command injection.

### Common Types
- SQL Injection
- NoSQL Injection
- Cross-Site Scripting (XSS)
- Command Injection
- LDAP Injection
- XPath Injection
- XML Injection

### Prevention
- Use parameterized queries (prepared statements) for all database access
- Use ORM/ODM frameworks that handle parameterization
- Validate and sanitize all user input
- Use least privilege principle for database accounts
- Escape special characters in output
- Use safe APIs that avoid the interpreter entirely

## A04:2025 - Insecure Design

### Description
Insecure design is a broad category representing different weaknesses, expressed as "missing or ineffective control design." This is different from insecure implementation. Focuses on the need for threat modeling and secure design patterns from the start.

### Common Issues
- Missing security controls
- Insecure default configurations
- Weak authentication mechanisms
- Insufficient threat modeling
- Lack of security architecture review

### Prevention
- Establish and use a secure development lifecycle
- Establish and use a library of secure design patterns
- Use threat modeling for authentication, access control, business logic, and cryptography
- Integrate security language and controls into user stories
- Integrate plausibility checks at each tier of your application

## A05:2025 - Cryptographic Failures

### Description
Moved down from #2 in 2021 to #5 in 2025. Previously known as "Sensitive Data Exposure," this category focuses on failures related to cryptography which often lead to exposure of sensitive data, including weak crypto and plaintext data storage.

### Common Vulnerabilities
- Transmitting sensitive data in clear text
- Using weak or deprecated cryptographic algorithms
- Using default or weak cryptographic keys
- Not encrypting sensitive data at rest
- Improper certificate validation

### Prevention
- Encrypt all sensitive data at rest and in transit
- Use strong, up-to-date cryptographic algorithms (AES-256, RSA-2048+)
- Never store passwords in plain text; use strong, adaptive hashing (bcrypt, Argon2)
- Disable caching for responses that contain sensitive data
- Use secure protocols (TLS 1.3 recommended, TLS 1.2 minimum) with proper certificate validation

## A06:2025 - Software Supply Chain Failures

### Description
Evolved from "Vulnerable and Outdated Components" to encompass the broader scope of software supply chain risks. Now covers unknown vulnerabilities introduced through third-party code, not just known CVEs. Includes risks from transitive dependencies, compromised build pipelines, and malicious packages.

### Common Issues
- Using outdated libraries and frameworks
- Not monitoring for security advisories
- Not updating dependencies regularly
- Using components with known vulnerabilities
- Trusting third-party code without verification
- Unvetted transitive dependencies introducing unknown vulnerabilities
- Dependency confusion and typosquatting attacks

### Prevention
- Remove unused dependencies, unnecessary features, components, and files
- Continuously inventory the versions of both client-side and server-side components
- Monitor for security vulnerabilities in components
- Only obtain components from official sources over secure links
- Use dependency management tools (npm audit, pip-audit, etc.)
- Apply security patches in a timely fashion
- Verify package integrity using checksums and signatures
- Use lockfiles and pin dependency versions
- Audit transitive dependencies, not just direct ones

## A07:2025 - Identification and Authentication Failures

### Description
Previously "Broken Authentication," this category includes failures related to identification and authentication. Attackers can exploit authentication weaknesses to gain access to user accounts.

### Common Vulnerabilities
- Permitting automated attacks (credential stuffing, brute force)
- Using weak or well-known passwords
- Missing or ineffective multi-factor authentication
- Exposing session identifier in the URL
- Not properly invalidating session IDs after logout

### Prevention
- Implement multi-factor authentication
- Do not ship with default credentials
- Implement weak-password checks
- Limit failed login attempts
- Use secure session management
- Generate strong session IDs and invalidate them properly
- Use password hashing with strong algorithms (bcrypt, Argon2)

## A08:2025 - Software and Data Integrity Failures

### Description
Previously "Insecure Deserialization," this category focuses on making assumptions about software updates, critical data, and CI/CD pipelines without verifying integrity. Includes CI/CD pipeline attacks and unsigned updates.

### Common Issues
- Using components from untrusted sources
- Not verifying software updates
- Insecure deserialization
- Not verifying data integrity
- Compromised CI/CD pipelines
- Unsigned or unverified build artifacts

### Prevention
- Use digital signatures or similar mechanisms to verify software or data integrity
- Ensure libraries and dependencies are from trusted sources
- Implement secure CI/CD pipelines with integrity verification at each stage
- Ensure integrity checks in the software update process
- Avoid deserializing untrusted data
- Implement integrity checks or digital signatures on serialized objects

## A09:2025 - Security Logging and Monitoring Failures

### Description
Previously "Insufficient Logging & Monitoring," this category includes failures to log security-relevant events or monitor for suspicious activities.

### Common Issues
- Not logging security-relevant events
- Logging insufficient detail
- Not monitoring logs for suspicious activity
- Not alerting on security events

### Prevention
- Log all authentication attempts (successful and failed)
- Log all access control failures
- Log all input validation failures
- Log all security-relevant events
- Ensure logs are tamper-proof
- Implement real-time monitoring and alerting
- Use centralized logging
- Establish incident response procedures

## A10:2025 - Server-Side Request Forgery (SSRF)

### Description
SSRF flaws occur whenever a web application is fetching a remote resource without validating the user-supplied URL. It allows an attacker to coerce the application to send a crafted request to an unexpected destination. Note: SSRF risks are also partially addressed under A01:2025 Broken Access Control.

### Common Vulnerabilities
- Fetching URLs without validation
- Using user input directly in URL construction
- Not restricting allowed protocols
- Not restricting allowed hosts/IPs

### Prevention
- Sanitize and validate all user-supplied input
- Use allowlists for URLs and IP addresses
- Do not send raw responses to clients
- Disable HTTP redirections
- Use network segmentation to reduce SSRF impact
- Validate and sanitize URLs before making requests

## References

- [OWASP Top 10 2025](https://owasp.org/Top10/2025/)
- [OWASP Foundation](https://owasp.org/)
- [OWASP Top 10 Project](https://owasp.org/www-project-top-ten/)
