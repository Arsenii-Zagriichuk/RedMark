#!/usr/bin/env bash
# Format on edit (P1-15): PostToolUse on file edits. Python files get ruff's import sort
# and formatter, the same rules CI checks. A file that doesn't parse yet is left alone.
set -uo pipefail

file=$(jq -r '.tool_input.file_path // ""' 2>/dev/null)
[[ "$file" == *.py && -f "$file" ]] || exit 0
root=$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null) || exit 0

uv run --quiet --directory "$root" ruff check --quiet --select I --fix "$file" &>/dev/null
uv run --quiet --directory "$root" ruff format --quiet "$file" &>/dev/null
exit 0
