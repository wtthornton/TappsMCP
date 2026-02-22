#!/usr/bin/env bash
# Validate the Cursor plugin bundle structure and manifest
set -euo pipefail

PLUGIN_DIR="${1:-plugin/cursor}"

echo "Validating Cursor plugin bundle at: $PLUGIN_DIR"

# Check required files
REQUIRED_FILES=(
  ".cursor-plugin/plugin.json"
  "marketplace.json"
  "mcp.json"
  "logo.png"
  "README.md"
  "CHANGELOG.md"
  "skills/tapps-score/SKILL.md"
  "skills/tapps-gate/SKILL.md"
  "skills/tapps-validate/SKILL.md"
)

FAIL=0
for f in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "$PLUGIN_DIR/$f" ]]; then
    echo "ERROR: Missing required file: $PLUGIN_DIR/$f" >&2
    FAIL=1
  fi
done

if [[ $FAIL -ne 0 ]]; then
  echo "Plugin validation FAILED — missing files" >&2
  exit 1
fi

# Validate plugin.json is valid JSON with required fields
python3 -c "
import json, sys
with open('$PLUGIN_DIR/.cursor-plugin/plugin.json') as f:
    p = json.load(f)
required = ['name', 'displayName', 'author', 'description',
            'keywords', 'license', 'version']
missing = [k for k in required if k not in p]
if missing:
    print(f'ERROR: plugin.json missing fields: {missing}',
          file=sys.stderr)
    sys.exit(1)
print('plugin.json: OK')
"

# Validate marketplace.json is valid JSON with required fields
python3 -c "
import json, sys
with open('$PLUGIN_DIR/marketplace.json') as f:
    m = json.load(f)
required = ['name', 'displayName', 'author', 'description',
            'keywords', 'license', 'version', 'repository',
            'homepage', 'category']
missing = [k for k in required if k not in m]
if missing:
    print(f'ERROR: marketplace.json missing fields: {missing}',
          file=sys.stderr)
    sys.exit(1)
print('marketplace.json: OK')
"

echo "Plugin validation PASSED."
