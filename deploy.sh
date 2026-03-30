#!/bin/bash
# deploy.sh — ONE correct way to deploy andremacedo.com to production
# Production branch is "main". NOT "production". Period.
set -euo pipefail
cd "$(dirname "$0")"
export CLOUDFLARE_ACCOUNT_ID="98a1dcdbeec2aa3aac24e49c22c652d2"
wrangler pages deploy . --project-name andremacedo-com --branch main --commit-dirty=true
echo "✓ Deployed to PRODUCTION (andremacedo.com) via --branch main"
