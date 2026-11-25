#!/bin/bash
# Commit the given paths on top of the latest main and push, retrying on races.
# The procurement workflow is the only writer of its paths (runs are serialized by
# its concurrency group), so this run's files are authoritative: instead of
# rebasing (which can stop on a conflict and wedge every later attempt) it moves
# onto origin/main and re-stages only its own paths.
# usage: scripts/git_publish.sh "commit message" path [path...]
set -u
msg=$1; shift
# Leave any interrupted rebase or merge without touching the working tree (it holds this run's files).
gitdir=$(git rev-parse --git-dir)
rm -rf "$gitdir/rebase-merge" "$gitdir/rebase-apply" "$gitdir/MERGE_HEAD"
for i in 1 2 3 4 5; do
  if git fetch -q origin main; then
    git reset -q --mixed origin/main
    git add -A -- "$@"
    if git diff --cached --quiet; then echo "Nothing to publish"; exit 0; fi
    git commit -q -m "$msg" && git push -q origin HEAD:main && { echo "Published: $msg"; exit 0; }
  fi
  sleep $((i * 10))
done
echo "Could not publish after 5 attempts" >&2
exit 1
