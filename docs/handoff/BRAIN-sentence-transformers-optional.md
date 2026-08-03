# Hand-back prompt: make `sentence-transformers` an optional extra in tapps-brain

**Repo:** `wtthornton/tapps-brain` (NOT tapps-mcp — filed from tapps-mcp per repo-boundaries rule)
**Observed:** 2026-08-03, against tapps-brain **3.28.1**
**Impact:** ~4.5 GB of unused GPU wheels in every tapps-mcp release venv

---

## Problem

`tapps-brain` declares `sentence-transformers` as a **base** (non-optional) dependency:

```
# tapps_brain-3.28.1.dist-info/METADATA
Requires-Dist: sentence-transformers<6,>=5.4.0
Requires-Dist: numpy<3,>=2.4.2
```

Because `tapps-core` depends on `tapps-brain>=3.28.0,<4` as a base dependency, this
cascades into **every** install of tapps-core / tapps-mcp / docs-mcp:

```
tapps-brain
  └── sentence-transformers
        └── transformers
              └── torch  ──┬── nvidia-* CUDA wheels   ~2.7 GB
                           ├── torch                  ~1.1 GB
                           └── triton                 ~689 MB
```

Measured in `~/.tapps-mcp/releases/3.12.59-679b9a61/lib/python3.13/site-packages/`:

1. `nvidia/` — 2.7 GB (`libcublasLt.so.13` alone is 517 MB; `cudnn/lib` 471 MB)
2. `torch/` — 1.1 GB
3. `triton/` — 689 MB

Total install is ~5.0 GB, of which **~4.5 GB is the GPU stack**.

## Why this is wrong

- **The deploy never asks for it.** `tapps-mcp deploy-local` installs
  `docs-mcp[treesitter]` and `tapps-mcp[treesitter]`. The `treesitter` extra contains
  only `tree-sitter*` parsers. `sentence-transformers` arrives purely transitively
  through `tapps-brain`'s base deps.
- **CUDA is dead weight on CPU hosts.** The primary dev host has no NVIDIA GPU
  (`nvidia-smi` is not installed). The CUDA wheels can never be exercised.
- **Every consumer pays.** Any repo installing tapps-core inherits ~4.5 GB it cannot use.
- **The optional-extra pattern already exists in this codebase.** Both `tapps-core` and
  `docs-mcp` already gate the same libraries behind extras:

  ```toml
  # packages/tapps-core/pyproject.toml
  [project.optional-dependencies]
  vector = [
      "faiss-cpu>=1.14.3,<2",
      "sentence-transformers>=5.5.1,<6",
      "numpy>=2.4.6,<3",
  ]
  ```

  ```toml
  # packages/docs-mcp/pyproject.toml
  agents = [
      "sentence-transformers>=5.5.1,<6",
  ]
  ```

  tapps-brain is the one place the dependency is unconditional.

## Requested change

1. Move `sentence-transformers` (and `numpy`, if it is only needed for embeddings) out of
   `[project.dependencies]` into a new optional extra, e.g.:

   ```toml
   [project.optional-dependencies]
   embeddings = [
       "sentence-transformers>=5.4.0,<6",
       "numpy>=2.4.2,<3",
   ]
   ```

2. Guard the import sites so a brain without the extra degrades cleanly rather than
   raising `ImportError` at startup. docs-mcp already models this — the import is
   function-local, not module-level:

   ```python
   # packages/docs-mcp/src/docs_mcp/agents/embeddings.py:87
   from sentence_transformers import SentenceTransformer
   ```

   Semantic search should report `degraded: true` when the extra is absent, consistent
   with the deterministic-tools contract in tapps-mcp ADR-0004 (missing checkers fall
   back and mark the result degraded).

3. Confirm which brain features actually require embeddings. If semantic
   `memory_search` is the only consumer, the extra is the correct boundary. If the KG or
   consolidation paths also need it, say so — that changes whether tapps-mcp should
   install `tapps-brain[embeddings]` by default.

## Verification after the change

```bash
# In tapps-mcp, after bumping the brain pin:
tapps-mcp deploy-local
ls ~/.tapps-mcp/releases/<new>/lib/python3.13/site-packages/ | grep -E '^(torch|nvidia|triton)'
# expect: no matches
du -sh ~/.tapps-mcp/releases/<new>    # expect ~400-500 MB, down from ~5.0 GB
```

Then confirm brain memory operations still work:

```bash
uv run tapps-mcp memory search --query "test"
```

## Open question for the brain maintainer

If embeddings are genuinely required for core brain operation, the alternative in-lane fix
on the tapps-mcp side is to pin the **CPU-only torch wheel** via a `pytorch-cpu` index +
`[tool.uv.sources]` override. That drops the ~2.7 GB of `nvidia/*` while keeping
`sentence-transformers` functional. It is strictly worse than making the dep optional —
it only fixes builds from the tapps-mcp checkout, not consumers installing tapps-brain
directly — so it is the fallback, not the preference.

## Related

- [tapps-mcp ADR-0033](../adr/0033-pin-tapps-brain-version-floor-at-3280.md) — current brain floor `>=3.28.0,<4`
- [tapps-mcp ADR-0004](../adr/0004-deterministic-tools-only-contract.md) — degraded-fallback contract
