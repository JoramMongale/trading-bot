#!/usr/bin/env bash
# Build the zip you copy to the Windows trading machine.
#
#   ./scripts/make_windows_zip.sh
#
# Uses `git archive`, so the zip contains exactly the TRACKED files at a known
# commit. That is the point: .venv, output/, data/raw/ and every stray local
# file are excluded by construction rather than by an exclusion list somebody
# has to remember to update. The build is reproducible from its own commit id,
# which is stamped into the filename and into VERSION.txt inside the archive.
#
# It refuses to package a dirty tree, and that refusal is deliberate. An earlier
# version had a --dirty flag built on `git stash create`, which captures only
# TRACKED files -- so a brand-new untracked file was silently left out of the
# zip while the build reported success. A packaging tool that quietly omits your
# newest work is worse than no packaging tool. Commit first; then the commit id
# in VERSION.txt actually means something.

set -euo pipefail
cd "$(dirname "$0")/.."

if ! git diff-index --quiet HEAD -- || [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
  echo "REFUSING: the working tree is not clean."
  echo
  git status --short
  echo
  echo "Commit (or stash) everything first. The zip is meant to be reproducible"
  echo "from the commit id it carries -- packaging a dirty tree breaks that, and"
  echo "untracked files would be dropped without warning."
  exit 1
fi

SHA=$(git rev-parse --short HEAD)
OUT="dist/trading-bot-windows-${SHA}.zip"
mkdir -p dist

git archive --format=zip --prefix=trading-bot/ HEAD -o "$OUT"

# VERSION.txt travels with the code so the Windows machine can answer "which
# build is this?" without needing git installed over there.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/trading-bot"
{
  echo "commit    $(git rev-parse HEAD)"
  echo "short     $SHA"
  echo "built     $(date -u +%Y-%m-%dT%H:%MZ)"
  echo "branch    $(git rev-parse --abbrev-ref HEAD)"
} > "$TMP/trading-bot/VERSION.txt"
( cd "$TMP" && zip -q "$OLDPWD/$OUT" trading-bot/VERSION.txt )

echo "built  $OUT"
echo "size   $(du -h "$OUT" | cut -f1 | tr -d ' ')"
echo "files  $(unzip -l "$OUT" | tail -1 | awk '{print $2}')"
echo
echo "On the Windows machine:"
echo "  1. unzip it"
echo "  2. cd trading-bot"
echo "  3. scripts\\setup.bat"
echo
echo "data/raw/*.csv is gitignored and therefore NOT in the zip. For backtesting,"
echo "download the histdata M1 CSVs on that machine -- see the README."
