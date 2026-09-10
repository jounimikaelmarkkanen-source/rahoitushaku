#!/usr/bin/env bash
set -euo pipefail
# Re-run the SQL test even when dependency/image layers are already cached.
# No host ports, host data mounts or production credentials are used.
python3 scripts/run_bounded.py 600 docker build --platform linux/amd64 \
  -f tests/Dockerfile.sql-buildcheck -t funding-registry:sql-buildcheck \
  --build-arg "FUNDING_SQL_TEST_RUN=$(date -u +%Y%m%dT%H%M%SZ)" .
