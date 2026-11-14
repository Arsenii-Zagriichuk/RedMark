#!/usr/bin/env bash
# Git session guard (P1-15): one agent per checkout, and files are staged by name.
#
# PreToolUse on Bash: the first agent session to run a command in a checkout claims it,
# and every later command of that session renews the claim. Another session's git
# commands are blocked while the claim is fresh, so two agents never commit to each
# other's branch. Bulk staging (git add -A / --all / . and git commit -a) is blocked.
# SessionEnd: the session lets go of its claim.
#
# The claim lives in the checkout's own git dir, so each worktree has its own.
set -euo pipefail

STALE_MINUTES=30
CLAIM_NAME="redmark-agent-session"

if ! command -v jq &>/dev/null; then
  echo "git-session-guard: jq is missing; install it (brew install jq / apt install jq)." >&2
  exit 2
fi

input=$(cat)
event=$(jq -r '.hook_event_name // ""' <<<"$input")
session=$(jq -r '.session_id // ""' <<<"$input")
cwd=$(jq -r '.cwd // ""' <<<"$input")
command=$(jq -r '.tool_input.command // ""' <<<"$input")

git_dir=$(git -C "${cwd:-.}" rev-parse --absolute-git-dir 2>/dev/null) || exit 0
claim="$git_dir/$CLAIM_NAME"
claimed_by=$(cat "$claim" 2>/dev/null || true)

if [[ "$event" == "SessionEnd" ]]; then
  [[ -n "$session" && "$claimed_by" == "$session" ]] && rm -f "$claim"
  exit 0
fi

runs_git='(^|[;&|({`[:space:]])git[[:space:]]'
if [[ "$command" =~ $runs_git ]]; then
  bulk_add='git[[:space:]]+add([[:space:]]+[^;&|]*)?[[:space:]](-A|--all|\.|:/)([[:space:];&|)]|$)'
  commit_all='git[[:space:]]+commit([[:space:]]+[^;&|]*)?[[:space:]](-[a-zA-Z]*a[a-zA-Z]*|--all)([[:space:];&|)]|$)'
  if [[ "$command" =~ $bulk_add || "$command" =~ $commit_all ]]; then
    echo "Stage files by name (git add path/to/file ...), not with git add -A, --all, . or git commit -a (AGENTS.md rule 1)." >&2
    exit 2
  fi
fi

claim_is_fresh=$(find "$claim" -mmin "-$STALE_MINUTES" 2>/dev/null || true)
if [[ -n "$claimed_by" && "$claimed_by" != "$session" && -n "$claim_is_fresh" ]]; then
  if [[ "$command" =~ $runs_git ]]; then
    echo "Another agent session ($claimed_by) is working in this checkout. Use your own worktree: git worktree add ../redmark-<ticket> -b <type>/<ticket>-<slug> origin/main (AGENTS.md rule 1). If that session has ended, ask the person to delete $claim." >&2
    exit 2
  fi
  exit 0
fi

[[ -n "$session" ]] && printf '%s' "$session" >"$claim"
exit 0
