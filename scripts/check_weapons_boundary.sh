#!/usr/bin/env bash
# Automated merge gate for CLAUDE.md §1 / COMPLIANCE.md's hard invariant:
# this codebase never builds or stubs targeting/fire-control/weaponeering/
# kill-chain logic, at any version. Run manually (BRIEF v1.5 Phase 0) and as
# a required CI check (.github/workflows/ci.yml's security-scan job,
# BRIEF v1.5 Phase 1) — same script both places so there's exactly one
# definition of "passing" to keep in sync.
#
# Scoped to APPLICATION CODE only (*.py/*.ts/*.tsx/*.rs) — deliberately not
# *.md/*.sh/*.yml. Documentation (COMPLIANCE.md, CLAUDE.md, every
# RECONCILIATION_REPORT.md-style debrief, this script's own header) is
# *supposed* to name the forbidden things in order to forbid them; gating
# prose the same way as code would explode on every future report that
# discusses this boundary (which is every report — that's the point of
# having one). What actually matters is that no CODE implements the
# forbidden functionality. The one legitimate exception — a source-code
# comment that documents compliance rather than describing a violation —
# is allowlisted explicitly below, by exact file:line, so a genuinely new
# hit anywhere else still fails loudly.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PATTERN='targeting|fire.?control|weaponeer|kill.?chain|weapon(ize|ization)?|lethal|strike\b|munition'

# Exact file:line matches that are known-safe negations/compliance comments
# *inside application code*. Extend only with a reviewed reason.
ALLOWLIST=$(cat <<'EOF'
apps/web/src/components/MapCanvas.tsx:19
EOF
)

HITS=$(grep -rniE "$PATTERN" \
  --include="*.py" --include="*.ts" --include="*.tsx" --include="*.rs" \
  . 2>/dev/null \
  | grep -v -E "node_modules|/target/|\.venv/|__pycache__" \
  | sed 's|^\./||' \
  || true)

if [ -z "$HITS" ]; then
  echo "PASS: zero weapons-boundary hits in application code."
  exit 0
fi

UNEXPECTED=""
while IFS= read -r hit; do
  file_line=$(echo "$hit" | cut -d: -f1,2)
  if ! grep -qxF "$file_line" <<< "$ALLOWLIST"; then
    UNEXPECTED="$UNEXPECTED$hit"$'\n'
  fi
done <<< "$HITS"

if [ -n "$UNEXPECTED" ]; then
  echo "FAIL: found weapons-boundary term(s) in application code, not on the reviewed allowlist:" >&2
  echo "$UNEXPECTED" >&2
  echo "" >&2
  echo "If this is a genuine new negation/compliance comment, review it and add its file:line to ALLOWLIST in scripts/check_weapons_boundary.sh. If it's a real violation, fix the code — this boundary never becomes in scope (see CLAUDE.md §1)." >&2
  exit 1
fi

echo "PASS: all weapons-boundary term hit(s) in application code matched the reviewed allowlist exactly."
exit 0
