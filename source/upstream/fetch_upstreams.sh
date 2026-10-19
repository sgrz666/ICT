#!/usr/bin/env bash
# 浅克隆上游实验引擎到 source/upstream/。幂等：已有 .git 的目录跳过。
# 事实（commit/体积/文件数）逐行写入 fetch-log.tsv，供 upstream.lock.json 誊写。
# 用法：bash source/upstream/fetch_upstreams.sh [engine_id ...]（不带参数=全部）
set -u
cd "$(dirname "$0")"
LOG=fetch-log.tsv

# id <TAB> url <TAB> branch <TAB> dest
CATALOG=$(cat <<'LIST'
myphysicslab	https://github.com/myPhysicsLab/myPhysicsLab.git	master	myphysicslab
matter-js	https://github.com/liabru/matter-js.git	master	matter-js
rapier-js	https://github.com/dimforge/rapier.js.git	master	rapier-js
stellarium-web-engine	https://github.com/Stellarium/stellarium-web-engine.git	master	stellarium-web-engine
phet-phet-core	https://github.com/phetsims/phet-core.git	main	phet/phet-core
phet-scenery	https://github.com/phetsims/scenery.git	main	phet/scenery
phet-scenery-phet	https://github.com/phetsims/scenery-phet.git	main	phet/scenery-phet
phet-dot	https://github.com/phetsims/dot.git	main	phet/dot
phet-axon	https://github.com/phetsims/axon.git	main	phet/axon
phet-joist	https://github.com/phetsims/joist.git	main	phet/joist
phet-kite	https://github.com/phetsims/kite.git	main	phet/kite
phet-sun	https://github.com/phetsims/sun.git	main	phet/sun
phet-assert	https://github.com/phetsims/assert.git	main	phet/assert
phet-mobius	https://github.com/phetsims/mobius.git	main	phet/mobius
phet-bending-light	https://github.com/phetsims/bending-light.git	main	phet/bending-light
phet-ohms-law	https://github.com/phetsims/ohms-law.git	main	phet/ohms-law
phet-circuit-construction-kit-common	https://github.com/phetsims/circuit-construction-kit-common.git	main	phet/circuit-construction-kit-common
phet-circuit-construction-kit-dc	https://github.com/phetsims/circuit-construction-kit-dc.git	main	phet/circuit-construction-kit-dc
phet-circuit-construction-kit-ac	https://github.com/phetsims/circuit-construction-kit-ac.git	main	phet/circuit-construction-kit-ac
phet-pendulum-lab	https://github.com/phetsims/pendulum-lab.git	main	phet/pendulum-lab
phet-masses-and-springs	https://github.com/phetsims/masses-and-springs.git	main	phet/masses-and-springs
phet-hookes-law	https://github.com/phetsims/hookes-law.git	main	phet/hookes-law
phet-projectile-motion	https://github.com/phetsims/projectile-motion.git	main	phet/projectile-motion
phet-collision-lab	https://github.com/phetsims/collision-lab.git	main	phet/collision-lab
phet-wave-on-a-string	https://github.com/phetsims/wave-on-a-string.git	main	phet/wave-on-a-string
phet-waves-intro	https://github.com/phetsims/waves-intro.git	main	phet/waves-intro
phet-wave-interference	https://github.com/phetsims/wave-interference.git	main	phet/wave-interference
phet-gas-properties	https://github.com/phetsims/gas-properties.git	main	phet/gas-properties
phet-gases-intro	https://github.com/phetsims/gases-intro.git	main	phet/gases-intro
phet-gravity-and-orbits	https://github.com/phetsims/gravity-and-orbits.git	main	phet/gravity-and-orbits
phet-charges-and-fields	https://github.com/phetsims/charges-and-fields.git	main	phet/charges-and-fields
phet-magnets-and-electromagnets	https://github.com/phetsims/magnets-and-electromagnets.git	main	phet/magnets-and-electromagnets
phet-energy-skate-park-basics	https://github.com/phetsims/energy-skate-park-basics.git	main	phet/energy-skate-park-basics
phet-forces-and-motion-basics	https://github.com/phetsims/forces-and-motion-basics.git	main	phet/forces-and-motion-basics
LIST
)

FILTER=("$@")
[ -f "$LOG" ] || printf 'id\tdest\turl\tbranch\tstatus\tcommit\tsize_kb\tfiles\tnote\tts\n' > "$LOG"

pick() {
  [ ${#FILTER[@]} -eq 0 ] && return 0
  for f in "${FILTER[@]}"; do [ "$f" = "$1" ] && return 0; done
  return 1
}

while IFS=$'\t' read -r id url branch dest; do
  [ -z "${id:-}" ] && continue
  pick "$id" || continue
  if [ -d "$dest/.git" ]; then
    printf '%s\t%s\t%s\t%s\tSKIP\t%s\t%s\t%s\talready present\t%s\n' \
      "$id" "$dest" "$url" "$branch" "$(git -C "$dest" rev-parse HEAD)" "$(du -sk "$dest" 2>/dev/null | cut -f1)" \
      "$(find "$dest" -path "$dest/.git" -prune -o -type f -print | wc -l)" "$(date +%FT%T%:z)" >> "$LOG"
    echo "[skip] $id"
    continue
  fi
  mkdir -p "$(dirname "$dest")"
  err=$(git clone --depth 1 --single-branch --branch "$branch" "$url" "$dest" 2>&1)
  rc=$?
  if [ $rc -ne 0 ]; then
    printf '%s\t%s\t%s\t%s\tFAIL\t\t\t\t%s\t%s\n' "$id" "$dest" "$url" "$branch" \
      "$(echo "$err" | tr '\t\n' '  ' | cut -c1-200)" "$(date +%FT%T%:z)" >> "$LOG"
    echo "[fail] $id: $(echo "$err" | tail -1)"
    continue
  fi
  printf '%s\t%s\t%s\t%s\tOK\t%s\t%s\t%s\t\t%s\n' "$id" "$dest" "$url" "$branch" \
    "$(git -C "$dest" rev-parse HEAD)" "$(du -sk "$dest" 2>/dev/null | cut -f1)" \
    "$(find "$dest" -path "$dest/.git" -prune -o -type f -print | wc -l)" "$(date +%FT%T%:z)" >> "$LOG"
  echo "[ok] $id -> $dest"
done <<< "$CATALOG"
echo "ALL DONE"
