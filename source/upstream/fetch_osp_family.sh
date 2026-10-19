#!/usr/bin/env bash
# Install the Open Source Physics family (OSP@Singapore / EJSS lineage) as read-only
# upstream checkouts under source/upstream/. Shallow clones: we only need the files.
# Logs one line per repo to osp-family-log.tsv: name<TAB>commit<TAB>bytes<TAB>status
set -u
cd "$(dirname "$0")"
OUT=osp-family-log.tsv
: > "$OUT"

# name|url  (order = value for EduForge: browser runtime first, then Java core, then model libs)
REPOS="
webejs|https://github.com/OpenSourcePhysics/webejs.git
resources|https://github.com/OpenSourcePhysics/resources.git
csm|https://github.com/OpenSourcePhysics/csm.git
osp_ejs|https://github.com/OpenSourcePhysics/osp_ejs.git
osp|https://github.com/OpenSourcePhysics/osp.git
STP|https://github.com/OpenSourcePhysics/STP.git
"

for entry in $REPOS; do
  name="${entry%%|*}"
  url="${entry#*|}"
  if [ -d "$name/.git" ]; then
    sha=$(git -C "$name" rev-parse HEAD)
    size=$(du -sk "$name" 2>/dev/null | cut -f1)
    printf '%s\t%s\t%s\t%s\n' "$name" "$sha" "$size" "already_installed" >> "$OUT"
    echo "[skip] $name ($sha)"
    continue
  fi
  echo "[clone] $name <- $url"
  if git clone --depth 1 --single-branch "$url" "$name" > "clone-$name.log" 2>&1; then
    sha=$(git -C "$name" rev-parse HEAD)
    size=$(du -sk "$name" 2>/dev/null | cut -f1)
    printf '%s\t%s\t%s\t%s\n' "$name" "$sha" "$size" "ok" >> "$OUT"
    echo "[ok]   $name $sha ${size}KB"
  else
    printf '%s\t\t\tfail\n' "$name" >> "$OUT"
    echo "[FAIL] $name -- see clone-$name.log"
    tail -3 "clone-$name.log"
  fi
done
echo "done"
