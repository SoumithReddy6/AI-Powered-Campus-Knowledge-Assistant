#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/Users/soumith/Documents/AI-Powered Campus Knowledge Assistant Using Institutional Data"
REPO_URL="https://github.com/SoumithReddy6/AI-Powered-Campus-Knowledge-Assistant.git"
BRANCH="main"
COMMIT_MSG="Campus assistant with protected Data Studio and domain assistant integration"

cd "$PROJECT_DIR"

# Initialize repo if needed
if [ ! -d ".git" ]; then
  git init
fi

# Ensure correct branch
git checkout -B "$BRANCH"

# Set or update remote
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO_URL"
else
  git remote add origin "$REPO_URL"
fi

# Stage everything except what .gitignore blocks
git add -A

# Commit only if something changed
if git diff --cached --quiet; then
  echo "No changes to commit."
  exit 0
fi

git commit -m "$COMMIT_MSG"

# Push (handle first push or rebase case)
if ! git push -u origin "$BRANCH"; then
  echo "Push failed. Trying rebase..."
  git pull --rebase origin "$BRANCH" || true
  git push -u origin "$BRANCH"
fi

echo "Done! Successfully pushed to GitHub."
