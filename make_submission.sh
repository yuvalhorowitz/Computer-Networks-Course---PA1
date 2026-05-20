#!/bin/bash
# make_submission.sh
#
# Assemble the PA1 submission zip per spec Section 5.
#   * Reads team IDs from students.json
#   * Names the zip PA1_<ID1>_<ID2>[_<ID3>...].zip
#   * Includes ONLY: server.c, client.c, Makefile, README.pdf
#   * Verifies a clean build from scratch before zipping
#
# Usage:
#   ./make_submission.sh             # build + create zip
#   ./make_submission.sh --dry-run   # verify only, don't create the zip
#
# Notes:
#   * README.pdf must exist (export from README.docx in Word, or print
#     README.html in your browser to PDF).

set -euo pipefail

STUDENTS_JSON=${STUDENTS_JSON:-students.json}
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run|-n) DRY_RUN=1 ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

# ───── Read student IDs ────────────────────────────────────────────────
if [ ! -f "$STUDENTS_JSON" ]; then
    echo "error: $STUDENTS_JSON not found" >&2
    exit 1
fi

IDS=$(python3 - "$STUDENTS_JSON" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
ids = []
for s in data.get('students', []):
    sid = s.get('id', '').strip()
    if sid and sid != '0' and sid != '000000000':
        ids.append(sid)
if not ids:
    sys.exit("no valid student IDs found in students.json")
print('_'.join(ids))
PY
)

ZIP_NAME="PA1_${IDS}.zip"

# ───── Pre-flight: required files exist ────────────────────────────────
REQUIRED=(server.c client.c Makefile README.pdf)
MISSING=()
for f in "${REQUIRED[@]}"; do
    [ -f "$f" ] || MISSING+=("$f")
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "error: required files missing:" >&2
    printf '  - %s\n' "${MISSING[@]}" >&2
    if printf '%s\n' "${MISSING[@]}" | grep -qx "README.pdf"; then
        cat >&2 <<'EOF'

How to produce README.pdf:
  Option A — from Word:
    open README.docx          # then File → Save As… → PDF
  Option B — from HTML:
    open README.html          # then in browser File → Print → Save as PDF
EOF
    fi
    exit 1
fi

# ───── Verify clean build ──────────────────────────────────────────────
echo ">>> Verifying clean build..."
make clean >/dev/null
make_log=$(mktemp)
trap 'rm -f "$make_log"' EXIT
if ! make 2>&1 | tee "$make_log"; then
    echo "error: build failed" >&2
    exit 1
fi
if grep -qE "warning:" "$make_log"; then
    echo "" >&2
    echo "warning: build produced warnings (see above) — fix before submitting" >&2
fi
echo ">>> Build OK (no errors)."

# ───── Show what's going in ────────────────────────────────────────────
echo ""
echo ">>> Submission contents (per spec Section 5):"
for f in "${REQUIRED[@]}"; do
    size=$(wc -c < "$f" | tr -d '[:space:]')
    printf "    %-12s  %8s bytes\n" "$f" "$size"
done
echo ""

# ───── Show what's NOT going in (sanity) ───────────────────────────────
EXTRA_IN_ROOT=$(find . -maxdepth 1 -type f \
    ! -name 'server.c' ! -name 'client.c' ! -name 'Makefile' ! -name 'README.pdf' \
    ! -name 'PA1_*.zip' \
    | sort)
if [ -n "$EXTRA_IN_ROOT" ]; then
    echo ">>> Files in project root that will NOT be included:"
    echo "$EXTRA_IN_ROOT" | sed 's/^/    /'
    echo ""
fi

# ───── Confirm or zip ──────────────────────────────────────────────────
if [ "$DRY_RUN" = "1" ]; then
    echo "(dry run) Would create: $ZIP_NAME"
    exit 0
fi

rm -f "$ZIP_NAME"
echo ">>> Creating $ZIP_NAME..."
zip -j "$ZIP_NAME" "${REQUIRED[@]}" >/dev/null

echo ""
echo ">>> Done. Submission archive:"
ls -la "$ZIP_NAME"
echo ""
echo ">>> Verify contents:"
unzip -l "$ZIP_NAME"
echo ""
echo "Upload $ZIP_NAME on Moodle."
