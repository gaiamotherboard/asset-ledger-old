#!/bin/sh
# Copy this file into the asset-ledger directory and run it locally:
#   chmod +x push-ssh-local.sh
#   ./push-ssh-local.sh
set -e

echo "== Asset Ledger: Prepare and push via SSH =="

# 1) Security check for common secret filenames tracked by git
echo "== Security check =="
echo "Checking for secret files in tracked files..."
if git ls-files | grep -E "(google_sa\.json|pgpassfile|\.env$)" > /dev/null 2>&1; then
  echo "❌ STOP! Secret files detected. Do not push!"
  git ls-files | grep -E "(google_sa\.json|pgpassfile|\.env$)"
  exit 1
else
  echo "✅ No secrets detected among tracked files."
fi

# 2) Initialize git if not already a repository
if [ ! -d .git ]; then
  echo "No .git present — initializing repository..."
  git init
else
  echo "Git repository detected."
fi

# 3) Ensure SSH key exists (or generate one)
echo ""
if [ -f "$HOME/.ssh/id_ed25519.pub" ] || [ -f "$HOME/.ssh/id_rsa.pub" ]; then
  echo "✅ SSH public key found. Public key below:"
  cat "$HOME/.ssh/id_ed25519.pub" 2>/dev/null || cat "$HOME/.ssh/id_rsa.pub"
  echo ""
  read -p "Is this key already added to GitHub? (yes/no) " added
  if [ "$added" != "yes" ]; then
    echo "If not added, copy the public key above and add it at: https://github.com/settings/ssh/new"
    read -p "Press Enter after you've added the key to GitHub..."
  fi
else
  echo "No SSH public key found. Generating an ed25519 key (no passphrase)..."
  ssh-keygen -t ed25519 -C "gaiamotherboard@github" -f "$HOME/.ssh/id_ed25519" -N "" || \
    { echo "ed25519 keygen failed, trying RSA."; ssh-keygen -t rsa -b 4096 -C "gaiamotherboard@github" -f "$HOME/.ssh/id_rsa" -N ""; }
  echo ""
  echo "New SSH public key (add this to GitHub -> Settings -> SSH and GPG keys -> New SSH key):"
  cat "$HOME/.ssh/id_ed25519.pub" 2>/dev/null || cat "$HOME/.ssh/id_rsa.pub"
  echo ""
  echo "Suggested title: 'Asset Ledger Upload'"
  read -p "Press Enter after you've added the key to GitHub..."
fi

# 4) Configure git user.name and user.email (prompt if placeholders present)
GIT_NAME="YOUR_FULL_NAME"
GIT_EMAIL="YOUR_EMAIL"
# Prompt if user hasn't edited the placeholders
if [ "$GIT_NAME" = "YOUR_FULL_NAME" ]; then
  read -p "Enter git user.name (e.g. Your Name): " GIT_NAME_INPUT
  GIT_NAME="${GIT_NAME_INPUT:-$GIT_NAME}"
fi
if [ "$GIT_EMAIL" = "YOUR_EMAIL" ]; then
  read -p "Enter git user.email (e.g. you@example.com): " GIT_EMAIL_INPUT
  GIT_EMAIL="${GIT_EMAIL_INPUT:-$GIT_EMAIL}"
fi

git config user.name "$GIT_NAME"
git config user.email "$GIT_EMAIL"
echo "Configured git user.name='$GIT_NAME' user.email='$GIT_EMAIL'"

# 5) Stage and commit
git add .
# If no commits yet, create initial commit; otherwise create an update commit if needed
if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  git commit -m "Initial commit: Asset Ledger - Production-lean Django+Postgres IT asset tracking system"
else
  if git diff --cached --quiet && git diff --quiet; then
    echo "No changes to commit."
  else
    git commit -m "Prepare for GitHub upload"
  fi
fi

# 6) Add SSH remote and push
git remote remove origin 2>/dev/null || true
git remote add origin git@github.com:gaiamotherboard/asset-ledger.git
git branch -M main
echo "Pushing to git@github.com:gaiamotherboard/asset-ledger.git (branch: main)..."
git push -u origin main

echo ""
echo "Done. If the push succeeded, verify at: https://github.com/gaiamotherboard/asset-ledger"
echo "If you see authentication errors, ensure the public key you added to GitHub matches the key printed earlier and that your SSH agent has the private key loaded (try: ssh-add ~/.ssh/id_ed25519)."
