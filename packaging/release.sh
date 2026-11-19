#!/bin/sh
# Makes a GitHub release out of the archives the build workflow kept for a
# green run, without building again:
#   packaging/release.sh v1.0.0 [run id]        (needs the gh command, logged in)
set -e
cd "$(dirname "$0")/.."
TAG="$1"; [ -n "$TAG" ] || { echo "usage: packaging/release.sh vX.Y.Z [run id]"; exit 1; }
RUN="${2:-$(gh run list --workflow build.yml --branch main --status success --limit 1 --json databaseId --jq '.[0].databaseId')}"
[ -n "$RUN" ] || { echo "no green run of the build workflow found"; exit 1; }
OUT="$(mktemp -d)"
gh run download "$RUN" --dir "$OUT" --pattern "sondugrande-*"
gh release create "$TAG" "$OUT"/*/sondugrande-* --title "sondugrande ${TAG#v}" \
  --notes "Sondugrande ${TAG#v} and SoundGrain 6.1.0 for macOS (Apple silicon), Windows (64-bit) and Linux (x86-64). See the README and the manual."
echo "released $TAG from run $RUN"
