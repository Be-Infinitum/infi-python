#!/usr/bin/env bash
# Copies the SDK contract from the monorepo (INFI_BACKEND, default ../infi/backend) and regenerates the package.
set -euo pipefail
cd "$(dirname "$0")/.."
backend="${INFI_BACKEND:-../infi/backend}"
cp "$backend/api/openapi.sdk.json" "$backend/api/openapi.sdk.yaml" api/
uv run python scripts/generate.py
