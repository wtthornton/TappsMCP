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

**Generate SBOM in CycloneDX format:**
```bash
# Python
pip install cyclonedx-bom
cyclonedx-py environment -o sbom.json --format json

# Or from requirements
cyclonedx-py requirements requirements.txt -o sbom.json

# Node.js
npx @cyclonedx/cyclonedx-npm --output-file sbom.json
```

**SBOM in CI/CD pipeline:**
```yaml
# GitHub Actions
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

**Sign with cosign (Sigstore):**
```bash
# Sign container image
cosign sign --key cosign.key ghcr.io/org/app:v1.0.0

# Verify signature
cosign verify --key cosign.pub ghcr.io/org/app:v1.0.0

# Keyless signing (uses OIDC identity)
cosign sign ghcr.io/org/app:v1.0.0
cosign verify \
  --certificate-identity user@example.com \
  --certificate-oidc-issuer https://accounts.google.com \
  ghcr.io/org/app:v1.0.0
```

### SLSA (Supply-chain Levels for Software Artifacts)

**Generate SLSA provenance in CI:**
```yaml
# GitHub Actions with SLSA generator
- uses: slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@v2.1.0
  with:
    base64-subjects: ${{ needs.build.outputs.digest }}
```

**SLSA Levels:**
- **Level 1**: Documentation of the build process
- **Level 2**: Tamper resistance of the build service
- **Level 3**: Hardened builds with non-falsifiable provenance
- **Level 4**: Two-person review of all changes

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
3. **SBOM for every release**: Know your dependency tree, scan continuously
4. **Sign artifacts**: Use Sigstore/cosign for container images and binaries
5. **Distroless containers**: Minimize attack surface in production
6. **mTLS for services**: Encrypt and authenticate all internal communication
7. **Rotate secrets automatically**: Use Vault or cloud secret managers
8. **Scan early and often**: Shift security left with CI/CD integration

## References

- [NIST Zero Trust Architecture (SP 800-207)](https://csrc.nist.gov/publications/detail/sp/800-207/final)
- [WebAuthn Specification (W3C)](https://www.w3.org/TR/webauthn-3/)
- [SLSA Framework](https://slsa.dev/)
- [CycloneDX SBOM Standard](https://cyclonedx.org/)
- [Sigstore / cosign](https://docs.sigstore.dev/)
- [py-webauthn Library](https://github.com/duo-labs/py_webauthn)
