# The package is generated from the contract (ADR 0055). `make check` runs the same as CI, minus the backend.
INFI_BACKEND ?= ../infi/backend

.PHONY: generate check-generated sync-contract typecheck test build examples check

generate:
	uv run python scripts/generate.py

# Fails if src/beinfi/_generated/ is not exactly what the generator produces from api/openapi.sdk.json.
check-generated: generate
	git diff --exit-code -- src/beinfi/_generated

sync-contract:
	./scripts/sync_contract.sh

typecheck:
	uv run mypy

test:
	uv run pytest

build:
	uv build

# Examples against the real backend (needs INFI_SECRET_KEY).
examples:
	uv run python examples/run_all.py

check: check-generated typecheck test build
