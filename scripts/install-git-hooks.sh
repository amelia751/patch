#!/usr/bin/env bash
# Install local git hooks that strip tooling attribution from commit messages.
# Hooks live in .git/hooks (not committed). Re-run after a fresh clone.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK_DIR="$ROOT/.git/hooks"
mkdir -p "$HOOK_DIR"

cat > "$HOOK_DIR/commit-msg" <<'HOOK'
#!/bin/sh
msg_file="$1"
tmp="$(mktemp)"
grep -viE '^(Co-authored-by:|Made-with:|Generated-with:|Generated with)' "$msg_file" > "$tmp" || true
awk 'NF{p=1} p{print}' < "$tmp" | awk '
  { lines[NR]=$0 }
  END {
    end=NR
    while (end>0 && lines[end] ~ /^[[:space:]]*$/) end--
    for (i=1; i<=end; i++) print lines[i]
  }
' > "$msg_file"
rm -f "$tmp"
HOOK

cp "$HOOK_DIR/commit-msg" "$HOOK_DIR/prepare-commit-msg"
chmod +x "$HOOK_DIR/commit-msg" "$HOOK_DIR/prepare-commit-msg"
printf 'installed commit-msg hooks in %s\n' "$HOOK_DIR"
