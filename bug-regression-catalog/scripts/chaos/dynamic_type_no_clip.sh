#!/usr/bin/env bash
# Chaos runner for BUG-2026-05-29-A.
#
# Static enforcement — runs without a simulator. We grep the K1 screens for
# the anti-pattern (.copy(fontSize = N.sp) on any K1Type.* style) that caused
# the UP NEXT row's time to clip at Dynamic Type. If anything matches outside
# the design-system file itself (KlikOneKit.kt), the regression has returned.
#
# Visual verification (Accessibility XXXL × K1FontSizeState steps) is still
# owed on TestFlight build — flagged as MANUAL at the end.
set -uo pipefail

REPO_ROOT="${REPO_ROOT:-/Users/wilsonxu/Klik_backup/Klik/Klik_one}"
TARGET_DIR="$REPO_ROOT/liquid/samples/composeApp/src/commonMain/kotlin/io/github/fletchmckee/liquid/samples/app/ui/klikone"

if [ ! -d "$TARGET_DIR" ]; then
  echo "  SKIP — $TARGET_DIR not found (run from a checkout of minervacap2022/Klik_one)"
  exit 0
fi

# Anti-pattern #1: fontSize override on a K1Type style outside KlikOneKit.kt.
PATTERN1='K1Type\.[a-zA-Z]+\.copy\([^)]*fontSize *= *[0-9]+\.sp'
MATCHES1=$(grep -rnE --include='*.kt' --exclude='KlikOneKit.kt' "$PATTERN1" "$TARGET_DIR" || true)

# Anti-pattern #2: fixed-DP Column wrapper around m.time.
PATTERN2='Column\(\s*Modifier\.width\(\s*[0-9]+\.dp\s*\)\s*\)\s*\{[^}]*m\.time'
MATCHES2=$(grep -rPnz --include='*.kt' "$PATTERN2" "$TARGET_DIR" 2>/dev/null || true)

# Anti-pattern #3: TextOverflow.Ellipsis paired with a meeting time field.
PATTERN3='m\.time'
HAS_TIME_AND_ELLIPSIS=$(grep -rln --include='*.kt' "TextOverflow.Ellipsis" "$TARGET_DIR" | xargs grep -ln "$PATTERN3" 2>/dev/null || true)

FAIL=0
if [ -n "$MATCHES1" ]; then
  echo "  FAIL — K1Type.X.copy(fontSize = N.sp) override detected:"
  echo "$MATCHES1" | sed 's/^/    /'
  echo "    → pick the right K1Type variant or add one; never pin .fontSize"
  FAIL=1
fi
if [ -n "$MATCHES2" ]; then
  echo "  FAIL — fixed-DP Column around m.time detected (clips at Dynamic Type):"
  echo "$MATCHES2" | sed 's/^/    /'
  FAIL=1
fi
if [ -n "$HAS_TIME_AND_ELLIPSIS" ]; then
  echo "  WARN — TextOverflow.Ellipsis in same file as m.time:"
  for f in $HAS_TIME_AND_ELLIPSIS; do
    grep -n "TextOverflow.Ellipsis" "$f" | sed "s|^|    $f:|"
  done
  echo "    → confirm the ellipsis is not masking a layout that clips m.time"
fi

if [ "$FAIL" -ne 0 ]; then
  exit 1
fi

echo "  OK — static pattern check clean."
echo "  MANUAL — Visual verification owed on TestFlight build:"
echo "    1. iOS Settings → Accessibility → Display & Text Size → Larger Text → max."
echo "    2. Open Klik → Today → UP NEXT section."
echo "    3. Confirm m.time renders the full string (e.g. \"12:32 AM - 12:32 AM\"),"
echo "       wrapped to a second line if necessary, but NEVER clipped to \"... - 12:...\"."
echo "    4. Repeat at K1FontSizeState 0.8, 1.0, 1.2, 1.5, 2.0 from the You screen."
exit 0
