#!/usr/bin/env bash
# 大仓与特殊安装路径的实测脚本：CircuitJS1 浅克隆、three.js 稀疏克隆、Webots 分阶段体积实测。
# 每一步都把体积与结论写进 fetch-large-log.tsv，供 upstream.lock.json 誊写。
set -u
cd "$(dirname "$0")"
LOG=fetch-large-log.tsv
[ -f "$LOG" ] || printf 'step\tstatus\tsize_kb\tfiles\tcommit\tnote\tts\n' > "$LOG"

rec() { # step status size_kb files commit note
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" "$6" "$(date +%FT%T%:z)" >> "$LOG"
  echo "[$2] $1 | kb=$3 files=$4 | $6"
}

size_of() { du -sk "$1" 2>/dev/null | cut -f1; }
file_count() { find "$1" -path "$1/.git" -prune -o -type f -print 2>/dev/null | wc -l; }

# --- 1. CircuitJS1（官方在 pfalstad/circuitjs1，不在 falstad/）
if [ ! -d circuitjs1/.git ]; then
  if git clone --depth 1 --single-branch --branch master https://github.com/pfalstad/circuitjs1.git circuitjs1 >/dev/null 2>&1; then
    rec circuitjs1 OK "$(size_of circuitjs1)" "$(file_count circuitjs1)" "$(git -C circuitjs1 rev-parse HEAD)" "pfalstad/circuitjs1 master 浅克隆"
  else
    rec circuitjs1 FAIL "" "" "" "git clone 失败"
  fi
else
  rec circuitjs1 SKIP "$(size_of circuitjs1)" "$(file_count circuitjs1)" "$(git -C circuitjs1 rev-parse HEAD)" "已存在"
fi

# --- 2. three.js：整仓 1.7G，改用 blob:none + sparse（src / examples/jsm / build）
if [ ! -d three/.git ]; then
  if git clone --depth 1 --filter=blob:none --sparse --single-branch --branch dev https://github.com/mrdoob/three.js.git three >/dev/null 2>&1; then
    git -C three sparse-checkout set src examples/jsm build >/dev/null 2>&1
    rec three-sparse OK "$(size_of three)" "$(file_count three)" "$(git -C three rev-parse HEAD)" "filter=blob:none + sparse(src,examples/jsm,build)"
  else
    rec three-sparse FAIL "" "" "" "git clone 失败"
  fi
else
  rec three-sparse SKIP "$(size_of three)" "$(file_count three)" "$(git -C three rev-parse HEAD)" "已存在"
fi

# --- 3. Webots：整仓 4.2G。先只取树（--no-checkout），再按目录实测体积决定装到哪一层
if [ ! -d webots/.git ]; then
  if git clone --depth 1 --filter=blob:none --no-checkout --single-branch --branch master https://github.com/cyberbotics/webots.git webots >/dev/null 2>&1; then
    rec webots-trees OK "$(size_of webots)" 0 "$(git -C webots rev-parse HEAD)" "只取 commit+trees，未检出工作区"
    git -C webots sparse-checkout init --cone >/dev/null 2>&1
    git -C webots sparse-checkout set resources/projects/protos >/dev/null 2>&1
    rec webots-protos OK "$(size_of webots)" "$(file_count webots)" "" "sparse=resources/projects/protos"
    git -C webots sparse-checkout set resources/projects/protos resources/projects/worlds resources/projects/lidar >/dev/null 2>&1
    rec webots-worlds OK "$(size_of webots)" "$(file_count webots)" "" "sparse+=worlds,lidar"
  else
    rec webots-trees FAIL "" "" "" "git clone 失败"
  fi
else
  rec webots SKIP "$(size_of webots)" "$(file_count webots)" "$(git -C webots rev-parse HEAD)" "已存在"
fi
echo "LARGE DONE"
