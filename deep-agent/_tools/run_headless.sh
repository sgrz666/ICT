#!/usr/bin/env bash
# Run one DeepSeek Harness headless task against the disposable smoke workspace.
# Usage: run_headless.sh <log-stem> <task-file> [--session-id <id>]
# - task text is read from a file so prompts stay out of shell quoting
# - stdout JSON events -> _logs/<stem>.jsonl, stderr diagnostics -> _logs/<stem>.err
set -u

STEM="$1"
TASKFILE="$2"
shift 2

HARNESS='D:/codeplus/ICT/deep-agent/deepseek-harness'
WORKSPACE="${WORKSPACE_DIR:-D:/codeplus/ICT/deep-agent/harness-smoke-workspace}"
LOGDIR='D:/codeplus/ICT/deep-agent/_logs'

export COREPACK_HOME='D:\codeplus\ICT\deep-agent\_corepack'
export DSH_HOME='D:\codeplus\ICT\deep-agent\.dsh-home'
export TSX_TSCONFIG_PATH="$HARNESS/tsconfig.json"
# Credentials come from the gitignored repo .env; never echoed.
set -a; . "$HARNESS/.env"; set +a

TSX='file:///D:/codeplus/ICT/deep-agent/deepseek-harness/node_modules/.pnpm/tsx@4.23.13/node_modules/tsx/dist/esm/index.mjs'
BIN="$HARNESS/apps/cli/src/bin.ts"

# Read the prompt before changing directory so relative task paths keep working.
TASK=$(cat "$TASKFILE") || exit 2

cd "$WORKSPACE" || exit 2
START=$(date -Is)
T0=$(date +%s)

node --import "$TSX" "$BIN" --profile headless --json "$@" "$TASK" \
  > "$LOGDIR/$STEM.jsonl" 2> "$LOGDIR/$STEM.err"
RC=$?
T1=$(date +%s)

{
  echo "stem=$STEM"
  echo "start=$START"
  echo "exit=$RC"
  echo "elapsed_seconds=$((T1 - T0))"
} > "$LOGDIR/$STEM.meta"
node "$LOGDIR/../_tools/summarize_events.mjs" "$LOGDIR/$STEM.jsonl" "$LOGDIR/$STEM.meta"
exit $RC
