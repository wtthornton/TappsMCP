#!/bin/bash
# TappsMCP SessionStart hook (compact)
# Re-injects TappsMCP context after context compaction.
cat > /dev/null
echo "[TappsMCP] Context was compacted - re-injecting TappsMCP awareness."
echo "Remember: use tapps_quick_check after editing Python files."
echo "Run tapps_validate_changed before declaring work complete."
exit 0
