# Epic 6: Supply Chain Security

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P2 - Medium
**Estimated LOE:** ~3-4 days (1 developer)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that container images are scanned for vulnerabilities, signed for provenance, and have generated SBOMs for auditability.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Deploy Trivy for vulnerability scanning, Syft for SBOM generation, and Cosign for image signing. Pin all image digests in Compose files.

**Tech Stack:** docs-mcp, Python >=3.12

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

No image scanning, no SBOMs, no image signing, and images use mutable tags. A compromised upstream image or dependency would go undetected.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Trivy scans all running container images with no critical CVEs unresolved
- [ ] Syft generates SPDX SBOMs for all built images
- [ ] Cosign signs all locally-built images
- [ ] All Compose files use pinned image digests not tags

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 6.1 -- Deploy Trivy Image Scanning

**Points:** 2

Install Trivy. Scan all running images. Set up cron job for periodic scanning. Create MCP tool for on-demand scanning.

**Tasks:**
- [ ] Implement deploy trivy image scanning
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Deploy Trivy Image Scanning is implemented, tests pass, and documentation is updated.

---

### 6.2 -- Generate SBOMs with Syft

**Points:** 2

Install Syft. Generate SPDX SBOMs for all container images. Attach as Cosign attestations.

**Tasks:**
- [ ] Implement generate sboms with syft
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Generate SBOMs with Syft is implemented, tests pass, and documentation is updated.

---

### 6.3 -- Sign Images with Cosign

**Points:** 2

Install Cosign. Generate keypair. Sign all locally-built images. Attach SBOMs as attestations.

**Tasks:**
- [ ] Implement sign images with cosign
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Sign Images with Cosign is implemented, tests pass, and documentation is updated.

---

### 6.4 -- Pin Image Digests in Compose Files

**Points:** 1

Replace all mutable tags with pinned sha256 digests in Docker Compose files. Document digest update workflow.

**Tasks:**
- [ ] Implement pin image digests in compose files
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Pin Image Digests in Compose Files is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Trivy is single binary covering OS pkgs + lang deps + IaC + secrets
- Cosign key-pair mode is simpler than keyless for home lab
- Renovate can auto-update pinned digests
- See docs/recommendations-2026-server-hardening.md Section 8

**Project Structure:** 7 packages, 73 modules, 279 public APIs

**Key Dependencies:** tapps-core>=1.0.0, mcp[cli]>=1.26.0,<2, click>=8.3.1,<9, jinja2>=3.1.6,<4, gitpython>=3.1.44,<4, pydantic>=2.12.5,<3, structlog>=25.5.0,<26, pyyaml>=6.0.3,<7

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Define what is explicitly out of scope for **Supply Chain Security**. Consider: Penetration testing

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All 4 acceptance criteria met | 0/4 | 4/4 | Checklist review |
| All 4 stories completed | 0/4 | 4/4 | Sprint board |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 6.1: Deploy Trivy Image Scanning
2. Story 6.2: Generate SBOMs with Syft
3. Story 6.3: Sign Images with Cosign
4. Story 6.4: Pin Image Digests in Compose Files

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Authentication bypass if token validation incomplete | Medium | High | Warning: Mitigation required - no automated recommendation available |
| Deployment downtime if blue-green not configured | Medium | High | Warning: Mitigation required - no automated recommendation available |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| Files will be determined during story refinement | - | - |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:performance-targets -->
## Performance Targets

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Test coverage | baseline | >= 80% | pytest --cov |
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->
