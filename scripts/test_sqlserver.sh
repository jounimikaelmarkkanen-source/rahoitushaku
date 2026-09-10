#!/usr/bin/env bash
set -euo pipefail
umask 077
docker build -f tests/Dockerfile -t funding-registry:test .
# Only disposable resources with task-specific names; no host ports or production data.
env_file="$(mktemp /tmp/funding-sql-env.XXXXXX)"
python3 -c 'import secrets; print("MSSQL_SA_PASSWORD=F9!"+secrets.token_hex(24))' > "$env_file"
cleanup() {
  docker rm -f funding-test-sql >/dev/null 2>&1 || true
  docker network rm funding-registry-test >/dev/null 2>&1 || true
  rm -f "$env_file"
}
if docker container inspect funding-test-sql >/dev/null 2>&1; then
  printf '%s\n' 'A funding-test-sql container already exists. Refusing to replace it.'
  rm -f "$env_file"
  exit 2
fi
docker network create funding-registry-test >/dev/null
trap cleanup EXIT
python3 scripts/run_bounded.py 180 docker run -d --name funding-test-sql --network funding-registry-test --platform linux/amd64 \
  --memory 4g --env-file "$env_file" -e ACCEPT_EULA=Y -e MSSQL_PID=Developer \
  mcr.microsoft.com/mssql/server:2022-latest >/dev/null
python3 scripts/run_bounded.py 300 docker run --rm --network funding-registry-test --env-file "$env_file" \
  funding-registry:test
