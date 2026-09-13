#!/system/bin/sh
# ──────────────────────────────────────────────────────────────
#  FileBase — module builder
#  Syncs the bundled server files from the repo root and packs the
#  flashable module into dist/filebase-<version>.zip
#  Usage: sh "Magisk Module/build.sh"
# ──────────────────────────────────────────────────────────────

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
DIST="$ROOT/dist"

# Keep the bundled copies in sync with the canonical sources in the repo root.
cp -f "$ROOT/server.py" "$DIR/common/server.py"
cp -f "$ROOT/launch.sh" "$DIR/common/launch.sh"
cp -f "$ROOT/stop.sh"   "$DIR/common/stop.sh"
chmod 755 "$DIR/common/server.py" "$DIR/common/launch.sh" "$DIR/common/stop.sh"
chmod 755 "$DIR/action.sh" "$DIR/customize.sh" "$DIR/uninstall.sh" 2>/dev/null || true

VER="$(sed -n 's/^version=//p' "$DIR/module.prop" 2>/dev/null | head -n 1 | tr -d '\r')"
[ -z "$VER" ] && VER="dev"

mkdir -p "$DIST"
OUT="$DIST/filebase-$VER.zip"
rm -f "$OUT"

if command -v zip >/dev/null 2>&1; then
    ( cd "$DIR" && zip -r "$OUT" . -x '*.git*' '*.DS_Store' 'build.sh' >/dev/null )
    echo "[+] Built with zip: $OUT"
else
    echo "[*] 'zip' not found, falling back to Python"
    python3 - "$DIR" "$OUT" <<'PY'
import os
import sys
import zipfile

src, out = sys.argv[1], sys.argv[2]
skip_files = {".DS_Store", "build.sh"}
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
    for base, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            if name in skip_files:
                continue
            path = os.path.join(base, name)
            archive.write(path, os.path.relpath(path, src))
print("[+] Built with python: " + out)
PY
fi

echo "[+] Done: $OUT"

# ── Standalone tarball (server + launchers + docs) ─────────────
TAR="$DIST/webserver.tar.gz"
rm -f "$TAR"
TMP="$(mktemp -d 2>/dev/null || echo "/tmp/filebase-build.$$")"
mkdir -p "$TMP"
cp -f "$ROOT/server.py" "$ROOT/launch.sh" "$ROOT/stop.sh" "$TMP/"
cp -f "$ROOT/README.md" "$ROOT/README_CN.md" "$TMP/" 2>/dev/null || true
chmod 755 "$TMP/server.py" "$TMP/launch.sh" "$TMP/stop.sh" 2>/dev/null || true
FILES="server.py launch.sh stop.sh"
if [ -f "$TMP/README.md" ]; then FILES="$FILES README.md"; fi
if [ -f "$TMP/README_CN.md" ]; then FILES="$FILES README_CN.md"; fi
( cd "$TMP" && tar -czf "$TAR" $FILES )
rm -rf "$TMP"
echo "[+] Built standalone: $TAR"
