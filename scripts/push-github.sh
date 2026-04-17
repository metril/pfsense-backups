#!/usr/bin/env bash
#
# push-github.sh — mirror this repo to GitHub under a different author identity.
#
# Usage:
#   scripts/push-github.sh                  # mirrors current branch
#   scripts/push-github.sh <branch>         # mirrors the named branch
#   scripts/push-github.sh --all            # mirrors every local branch + tags
#
# Requirements:
#   - git-filter-repo on PATH (install: `uv tool install git-filter-repo`)
#   - scripts/github-mailmap.txt exists (copy from scripts/github-mailmap.txt.example
#     and substitute your local git identity on the right-hand side)
#   - 'github' remote or GITHUB_URL env var set to the GitHub repo SSH URL
#
# How it works:
#   Operates on an ephemeral clone of this repo so the primary working tree is
#   never touched. git-filter-repo --mailmap rewrites author+committer identities,
#   then force-push-with-lease to GitHub. Deterministic: same inputs → same SHAs.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
MAILMAP="${REPO_ROOT}/scripts/github-mailmap.txt"
GITHUB_URL="${GITHUB_URL:-git@github.com:metril/pfsense-backup.git}"

if [[ ! -f "${MAILMAP}" ]]; then
  echo "error: ${MAILMAP} not found." >&2
  echo "       copy scripts/github-mailmap.txt.example to scripts/github-mailmap.txt" >&2
  echo "       and fill in your local git identity on the right-hand side." >&2
  exit 1
fi

if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "error: git-filter-repo not on PATH." >&2
  echo "       install with: uv tool install git-filter-repo" >&2
  exit 1
fi

MODE="branch"
REF="${1:-}"
if [[ "${REF}" == "--all" ]]; then
  MODE="all"
elif [[ -z "${REF}" ]]; then
  REF="$(git -C "${REPO_ROOT}" branch --show-current)"
  if [[ -z "${REF}" ]]; then
    echo "error: no branch argument and not on a branch." >&2
    exit 1
  fi
fi

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

echo ">>> cloning into ${TMP}"
git clone --no-local "${REPO_ROOT}" "${TMP}" >/dev/null

pushd "${TMP}" >/dev/null

echo ">>> rewriting author identities via ${MAILMAP}"
git filter-repo --mailmap "${MAILMAP}" --force

git remote add github "${GITHUB_URL}"

if [[ "${MODE}" == "all" ]]; then
  echo ">>> pushing all branches + tags to ${GITHUB_URL}"
  git push github --all --force-with-lease
  git push github --tags --force
else
  echo ">>> pushing ${REF} to ${GITHUB_URL}"
  git push github "${REF}:refs/heads/${REF}" --force-with-lease
  # Tags are cheap; push them too so tagged releases land on GitHub.
  git push github --tags --force
fi

popd >/dev/null
echo ">>> done"
