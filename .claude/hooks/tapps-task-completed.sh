#!/bin/bash
# TappsMCP TaskCompleted hook
# Reminds to run quality checks but does NOT block.
cat > /dev/null
echo "Reminder: run tapps_validate_changed to confirm quality."
exit 0
