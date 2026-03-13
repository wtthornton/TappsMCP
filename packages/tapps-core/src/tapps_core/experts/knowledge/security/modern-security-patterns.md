# Modern Security Patterns

## Overview

This guide covers modern security patterns including zero-trust architecture, passkeys/FIDO2 authentication, supply chain security with SBOM, and container security. These patterns reflect 2025-2026 best practices.

## Zero-Trust Architecture

### Principles

**Never trust, always verify:**
- No implicit trust based on network location
- Verify every request regardless of source
- Enforce least-privilege access
- Assume breach and minimize blast radius

### Implementation Patterns

**Per-Request Authentication and Authorization:**
```python
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def verify_request(
    request: Request,
    token: str = Depends(security),
) -> AuthContext:
    # 1. Verify identity (authn)
    claims = await verify_jwt(token.credentials)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid token")

    # 2. Verify authorization (authz) - per request, not per session
    resource = extract_resource(request)
    if not await policy_engine.authorize(claims, resource, request.method):
        raise HTTPException(status_code=403, detail="Access denied")

    # 3. Log access decision
    await audit_log.record(claims["sub"], resource, request.method, "allowed")

    return AuthContext(user_id=claims["sub"], roles=claims["roles"])
```

**Service-to-Service mTLS:**
```python
import ssl
import httpx

def create_mtls_client(
    cert_path: str,
    key_path: str,
    ca_path: str,
) -> httpx.AsyncClient:
    """Create HTTP client with mutual TLS for service-to-service calls."""
    ssl_context = ssl.create_default_context(cafile=ca_path)
    ssl_context.load_cert_chain(cert_path, key_path)
    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3

    return httpx.AsyncClient(verify=ssl_context)
```

**Network Microsegmentation:**
```yaml
# Kubernetes NetworkPolicy - zero-trust pod communication
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-server-policy
spec:
  podSelector:
    matchLabels:
      app: api-server
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: api-gateway
      ports:
        - port: 8080
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: database
      ports:
        - port: 5432
```

### Policy Engines

**Open Policy Agent (OPA) integration:**
```python
import httpx

class OPAClient:
    def __init__(self, opa_url: str = "http://localhost:8181"):
        self.opa_url = opa_url
        self.client = httpx.AsyncClient()

    async def authorize(
        self,
        user: dict,
        resource: str,
        action: str,
    ) -> bool:
        response = await self.client.post(
            f"{self.opa_url}/v1/data/authz/allow",
            json={
                "input": {
                    "user": user,
                    "resource": resource,
                    "action": action,
                }
            },
        )
        result = response.json()
        return result.get("result", False)
```

## Passkeys and FIDO2/WebAuthn

### Overview

Passkeys replace passwords with cryptographic key pairs. They are:
- **Phishing-resistant**: Bound to the origin (domain)
- **No shared secrets**: Private key never leaves the device
- **Multi-device**: Synced via platform (Apple, Google, Microsoft)
- **Passwordless**: No password to remember, leak, or phish

### Registration Flow

```python
from webauthn import (
    generate_registration_options,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

# Step 1: Generate registration options
def get_registration_options(user_id: str, user_name: str):
    options = generate_registration_options(
        rp_id="example.com",
        rp_name="My App",
        user_id=user_id.encode(),
        user_name=user_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    # Store challenge for verification
    store_challenge(user_id, options.challenge)
    return options

# Step 2: Verify registration response from browser
def complete_registration(user_id: str, credential):
    expected_challenge = get_stored_challenge(user_id)

    verification = verify_registration_response(
        credential=credential,
        expected_challenge=expected_challenge,
        expected_origin="https://example.com",
        expected_rp_id="example.com",
    )

    # Store credential for future authentication
    store_credential(
        user_id=user_id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
    )
```

### Authentication Flow

```python
from webauthn import (
    generate_authentication_options,
    verify_authentication_response,
)

# Step 1: Generate authentication options
def get_auth_options(user_id: str | None = None):
    # If user_id is None, allow discoverable credentials (passkeys)
    options = generate_authentication_options(
        rp_id="example.com",
        allow_credentials=get_user_credentials(user_id) if user_id else [],
    )
    store_challenge(options.challenge)
    return options

# Step 2: Verify authentication response
def verify_auth(credential):
    stored_cred = get_credential(credential.id)
    expected_challenge = get_stored_challenge()

    verification = verify_authentication_response(
        credential=credential,
        expected_challenge=expected_challenge,
        expected_origin="https://example.com",
        expected_rp_id="example.com",
        credential_public_key=stored_cred.public_key,
        credential_current_sign_count=stored_cred.sign_count,
    )

    # Update sign count to prevent replay attacks
    update_sign_count(credential.id, verification.new_sign_count)
    return stored_cred.user_id
```

### Best Practices

1. **Always offer passkeys first**: Fall back to TOTP/SMS only if needed
2. **Support discoverable credentials**: Allow login without typing a username
3. **Store multiple credentials per user**: Users may have multiple devices
4. **Track sign counts**: Detect cloned authenticators
5. **Set `userVerification: required`**: Ensure biometric/PIN check on device

## Supply Chain Security

### Software Bill of Materials (SBOM)

SBOM generation is now a regulatory and compliance requirement:
- **SPDX 3.0** released (ISO/IEC 5962:2024) - unified format for software, AI/ML, and datasets
- **CycloneDX 1.6** released - adds support for attestations, cryptographic assets, and ML/AI BOMs
- **EU Cyber Resilience Act (CRA)**: Mandates SBOMs for all products with digital elements sold in the EU market (enforcement begins 2027)
- **U.S. CISA 2025**: Expanded required SBOM metadata fields including end-of-life dates, known-unknowns declaration, and component relationships

**Generate SBOM with Syft (recommended) or CycloneDX:**
```bash
# Syft (Anchore) - multi-format, multi-ecosystem
syft packages dir:. -o cyclonedx-json=sbom.cdx.json
syft packages dir:. -o spdx-json=sbom.spdx.json

# Python-specific
pip install cyclonedx-bom
cyclonedx-py environment -o sbom.json --format json

# Or from requirements
cyclonedx-py requirements requirements.txt -o sbom.json

# Node.js
npx @cyclonedx/cyclonedx-npm --output-file sbom.json
```

**SBOM in CI/CD pipeline:**
```yaml
# GitHub Actions - generate and attest
- name: Generate SBOM
  uses: anchore/sbom-action@v0
  with:
    format: cyclonedx-json
    output-file: sbom.json

- name: Upload SBOM
  uses: actions/upload-artifact@v4
  with:
    name: sbom
    path: sbom.json
```

**Validate and query SBOMs with GUAC:**
```bash
# GUAC (Graph for Understanding Artifact Composition)
# Ingests SBOMs, SLSA attestations, and vulnerability data into a unified graph
guacone collect files sbom.cdx.json
guacone query known package "pkg:pypi/requests"
```

### Dependency Scanning

**Automated vulnerability detection:**
```yaml
# GitHub Actions
- name: Audit Python dependencies
  run: pip-audit --format json --output audit.json

- name: Audit npm dependencies
  run: npm audit --json > npm-audit.json

# Trivy for containers + dependencies
- name: Trivy scan
  uses: aquasecurity/trivy-action@master
  with:
    scan-type: fs
    format: json
    output: trivy-results.json
```

**Pin dependencies with hashes:**
```bash
# Generate locked requirements with hashes
pip-compile --generate-hashes requirements.in -o requirements.txt
```

```
# requirements.txt (with hash verification)
requests==2.31.0 \
    --hash=sha256:942c5a758f98d790eaed1a29cb6eefc7f0edf3fcb0fce8aea3fbd5951d33bc74 \
    --hash=sha256:58cd2187c01e70e6e26505bca751777aa9f2ee0b7f4300988b709f44e013003eb
```

### Container Image Signing

**Sign with cosign (Sigstore) - keyless signing is the default:**

Sigstore keyless signing via OIDC is now mature and widely adopted. cosign uses
ephemeral keys backed by certificate transparency logs (Rekor), eliminating the
need to manage long-lived signing keys.

```bash
# Keyless signing (recommended - uses OIDC identity from CI or interactive login)
cosign sign ghcr.io/org/app:v1.0.0
cosign verify \
  --certificate-identity user@example.com \
  --certificate-oidc-issuer https://accounts.google.com \
  ghcr.io/org/app:v1.0.0

# GitHub Actions OIDC keyless signing (zero secrets needed)
cosign sign \
  --certificate-identity https://github.com/org/repo/.github/workflows/release.yml@refs/tags/v1.0.0 \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/org/app:v1.0.0

# Key-based signing (legacy, still supported)
cosign sign --key cosign.key ghcr.io/org/app:v1.0.0
cosign verify --key cosign.pub ghcr.io/org/app:v1.0.0
```

**Enforce image signatures with Kyverno:**
```yaml
# Kubernetes admission policy - reject unsigned images
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-image-signature
spec:
  validationFailureAction: Enforce
  rules:
    - name: verify-cosign-signature
      match:
        any:
          - resources:
              kinds: ["Pod"]
      verifyImages:
        - imageReferences: ["ghcr.io/org/*"]
          attestors:
            - entries:
                - keyless:
                    subject: "https://github.com/org/*"
                    issuer: "https://token.actions.githubusercontent.com"
```

### SLSA (Supply-chain Levels for Software Artifacts)

**SLSA v1.0 specification** was released by the Linux Foundation (late 2025, building
on the v1.0 RC published in 2023). Key changes from the draft levels:

- Levels simplified to **Build L0-L3** (build provenance) and **Source L0-L3** (source integrity) tracks
- BuildKit now generates provenance in **SLSA v1.0 format by default**
- SLSA v1.0 provenance uses the `in-toto` attestation framework

**Generate SLSA provenance in CI:**
```yaml
# GitHub Actions with SLSA generator
- uses: slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@v2.1.0
  with:
    base64-subjects: ${{ needs.build.outputs.digest }}
```

**SLSA Build Levels (v1.0):**
- **Build L0**: No provenance guarantees
- **Build L1**: Provenance exists, showing how the package was built
- **Build L2**: Hosted build platform, signed provenance
- **Build L3**: Hardened build platform, non-falsifiable provenance

**SLSA Source Levels (v1.0):**
- **Source L0**: No source guarantees
- **Source L1**: Version controlled with verified history retention
- **Source L2**: Tamper-proof change history (branch protection, verified commits)
- **Source L3**: Two-person review of all changes

## Container Security

### Distroless Images

**Minimal attack surface:**
```dockerfile
# Build stage
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/deps -r requirements.txt
COPY src/ ./src/

# Runtime stage - distroless
FROM gcr.io/distroless/python3-debian12
COPY --from=builder /deps /deps
COPY --from=builder /app/src /app/src
ENV PYTHONPATH=/deps
WORKDIR /app
USER nonroot
ENTRYPOINT ["python", "-m", "src.main"]
```

### Image Scanning

**Scan for vulnerabilities before deploy:**
```bash
# Trivy
trivy image --severity HIGH,CRITICAL myapp:latest

# Grype
grype myapp:latest --fail-on high
```

### Runtime Security

**Read-only filesystem:**
```yaml
# Kubernetes SecurityContext
securityContext:
  readOnlyRootFilesystem: true
  runAsNonRoot: true
  runAsUser: 65534
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

## Secret Management

### Vault Integration

```python
import hvac

def get_secret(path: str) -> dict:
    client = hvac.Client(url="https://vault.example.com:8200")
    client.auth.approle.login(
        role_id=os.environ["VAULT_ROLE_ID"],
        secret_id=os.environ["VAULT_SECRET_ID"],
    )
    secret = client.secrets.kv.v2.read_secret_version(path=path)
    return secret["data"]["data"]
```

### Sealed Secrets (Kubernetes)

```bash
# Encrypt secret for GitOps
kubeseal --format yaml < secret.yaml > sealed-secret.yaml

# Only the cluster can decrypt
kubectl apply -f sealed-secret.yaml
```

## Security Headers (2026 Recommendations)

```python
SECURITY_HEADERS = {
    # Prevent MIME type sniffing
    "X-Content-Type-Options": "nosniff",
    # Prevent clickjacking
    "X-Frame-Options": "DENY",
    # HSTS with preload (2 years)
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    # Content Security Policy
    "Content-Security-Policy": "default-src 'self'; script-src 'self'",
    # Permissions Policy (replaces Feature-Policy)
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    # Cross-Origin policies
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
}
```

## Best Practices Summary

1. **Zero trust**: Verify every request, enforce least privilege, assume breach
2. **Passkeys over passwords**: FIDO2/WebAuthn is phishing-resistant by design
3. **SBOM for every release**: Required by EU CRA and U.S. CISA - use Syft or CycloneDX
4. **Sign artifacts**: Use Sigstore/cosign keyless signing (OIDC-based, no key management)
5. **SLSA provenance**: Generate build provenance at L2+ for all release artifacts
6. **Enforce signatures**: Use Kyverno or other admission controllers to reject unsigned images
7. **Distroless containers**: Minimize attack surface in production
8. **mTLS for services**: Encrypt and authenticate all internal communication
9. **Rotate secrets automatically**: Use Vault or cloud secret managers
10. **Scan early and often**: Shift security left with CI/CD integration

## References

- [NIST Zero Trust Architecture (SP 800-207)](https://csrc.nist.gov/publications/detail/sp/800-207/final)
- [WebAuthn Specification (W3C)](https://www.w3.org/TR/webauthn-3/)
- [SLSA Framework v1.0](https://slsa.dev/)
- [SPDX 3.0 Specification](https://spdx.dev/)
- [CycloneDX 1.6 SBOM Standard](https://cyclonedx.org/)
- [Sigstore / cosign](https://docs.sigstore.dev/)
- [GUAC - Graph for Understanding Artifact Composition](https://guac.sh/)
- [Kyverno Policy Engine](https://kyverno.io/)
- [EU Cyber Resilience Act](https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act)
- [py-webauthn Library](https://github.com/duo-labs/py_webauthn)
