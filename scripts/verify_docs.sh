#!/usr/bin/env bash
# Verifies the documentation set: required docs exist and are non-empty, every
# top-level docs/*.md carries a Status: line, and every relative link resolves —
# including its #anchor against the target file's actual headings.
#
# Convention for anyone adding a doc: the first lines must contain a
# "**Status:** ..." line stating what is real versus designed.
set -euo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REQUIRED_DOCS="
docs/architecture.md
docs/threat-model.md
docs/data-model.md
docs/agent-contracts.md
docs/operations.md
"

failures=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  failures=$((failures + 1))
}

ok() {
  printf 'ok   %s\n' "$*"
}

# Strip fenced code blocks so headings and links inside examples are ignored.
strip_fences() {
  awk '/^[[:space:]]*```/ { fence = !fence; next } !fence { print }' "$1"
}

# GitHub-compatible heading slugs: lowercase, drop punctuation, spaces to dashes.
anchors_of() {
  strip_fences "$1" \
    | sed -n 's/^#\{1,6\}[[:space:]]\{1,\}//p' \
    | tr '[:upper:]' '[:lower:]' \
    | sed 's/[^a-z0-9 _-]//g' \
    | sed 's/ /-/g'
}

links_of() {
  strip_fences "$1" \
    | grep -o '](\([^)[:space:]]*\))' \
    | sed 's/^](//; s/)$//' \
    || true
}

# --- required docs present, non-empty, and marked with a status -------------

for doc in $REQUIRED_DOCS; do
  if [ ! -f "$doc" ]; then
    fail "$doc is missing"
    continue
  fi
  if [ ! -s "$doc" ]; then
    fail "$doc is empty"
    continue
  fi
  ok "$doc exists and is non-empty"
done

# --- every top-level doc carries a Status: line -----------------------------

doc_count=0
for doc in docs/*.md; do
  [ -e "$doc" ] || continue
  doc_count=$((doc_count + 1))
  if ! grep -Eq '^\**Status:' "$doc"; then
    fail "$doc has no 'Status:' line"
  fi
done

if [ "$doc_count" -eq 0 ]; then
  fail "no docs/*.md files found"
else
  ok "$doc_count doc(s) carry a Status: line (or were reported above)"
fi

# --- relative links resolve, anchors included -------------------------------

link_count=0
for doc in docs/*.md; do
  [ -e "$doc" ] || continue
  dir="$(dirname "$doc")"

  while IFS= read -r link; do
    [ -n "$link" ] || continue
    case "$link" in
      http://*|https://*|mailto:*|\#*) continue ;;
    esac

    target="${link%%#*}"
    anchor="${link#*#}"
    [ "$anchor" = "$link" ] && anchor=""
    [ -n "$target" ] || continue

    resolved="$dir/$target"
    if [ ! -e "$resolved" ]; then
      fail "$doc → broken link: $link (no such path: $resolved)"
      continue
    fi

    if [ -n "$anchor" ] && [ "${resolved##*.}" = "md" ]; then
      if ! anchors_of "$resolved" | grep -Fxq "$anchor"; then
        fail "$doc → link $link resolves to $resolved but has no heading '#$anchor'"
        continue
      fi
    fi

    link_count=$((link_count + 1))
  done <<EOF
$(links_of "$doc")
EOF
done

ok "$link_count relative link(s) resolved"

# ---------------------------------------------------------------------------

if [ "$failures" -ne 0 ]; then
  printf 'FAIL: verify_docs.sh — %d problem(s)\n' "$failures" >&2
  exit 1
fi

printf 'PASS: verify_docs.sh\n'
