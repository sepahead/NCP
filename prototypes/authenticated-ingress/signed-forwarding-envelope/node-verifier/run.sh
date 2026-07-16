#!/usr/bin/env bash
# Quarantined independent verifier runner. A pass grants no production or release claim.
set -euo pipefail
umask 077

cd "$(dirname "$0")"

npm ci --ignore-scripts --no-audit
npm run verify-profile
npm run build
npm test
