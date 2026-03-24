# Story 89.4: Shell/Bash project type detection

<!-- docsmcp:start:metadata -->
**Epic:** [89 - Cross-Project Tool Parity](../EPIC-89-CROSS-PROJECT-TOOL-PARITY.md)
**Points:** 3
**Priority:** P3 - Low
**Status:** Proposed

<!-- docsmcp:end:metadata -->

## User Story

As an agent profiling a shell/bash-heavy project, I need `tapps_project_profile` to correctly detect it as a CLI tool project rather than "documentation", so that recommendations and scoring reflect the project's actual nature.

## Description

`type_detector.py`'s `cli-tool` type only checks Python CLI indicators:
- `_has_cli_entrypoint()`: checks for `cli.py`, `main.py`, `command.py`, `__main__.py`
- `_has_click_or_typer()`: checks for click/typer framework imports
- `_has_setup_py_cli()`: checks `setup.py` for CLI entry points

Shell/bash projects with `*.sh` scripts, `bin/` directories, shebangs, and `install.sh` are invisible to these checks. The Ralph-claude-code project (85% bash, `install.sh`, `bin/` directory, Makefile) was classified as "documentation" at 0.6 confidence because markdown files outweighed the unrecognized shell files.

## Tasks

- [ ] Add `_has_shell_scripts()` indicator: check for `*.sh` files (count > threshold, e.g., 3+)
- [ ] Add `_has_bin_directory()` indicator: check for `bin/` directory with executable files
- [ ] Add `_has_install_script()` indicator: check for `install.sh`, `setup.sh`, or `Makefile`
- [ ] Add shell indicators to `cli-tool` type in `TYPE_DEFINITIONS` dict
- [ ] Adjust weights: shell indicators should contribute meaningfully to `cli-tool` confidence
- [ ] Consider: should `.sh` file count reduce `documentation` confidence? (many .sh + many .md = CLI, not docs)
- [ ] Add tests:
  - Pure shell project (only .sh files) -> `cli-tool`
  - Mixed shell + python project -> `cli-tool`
  - Shell project with install.sh and bin/ -> `cli-tool` with high confidence
  - Project with 1-2 .sh helper scripts -> NOT classified as CLI (below threshold)
- [ ] Test that ralph-like structure gets >0.7 confidence as `cli-tool`

## Acceptance Criteria

- [ ] Shell-heavy projects (>3 .sh files or bin/ directory) detected as `cli-tool`
- [ ] Confidence for shell projects is >0.7 when indicators are strong
- [ ] Python CLI detection is not degraded (existing tests pass)
- [ ] Projects with a few helper .sh scripts are not misclassified

## Definition of Done

A project with 85% bash scripts, `install.sh`, and `bin/` directory is classified as `cli-tool` with >0.7 confidence, not "documentation".

## Technical Notes

- The `documentation` type likely won because it counts `.md` files, and ralph-claude-code has docs alongside scripts
- Consider a negative signal: if a project has `bin/` + `install.sh`, reduce `documentation` confidence
- Shebang detection (`#!/bin/bash`) is more reliable than extension matching but requires reading file contents
