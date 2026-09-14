#!/bin/bash
set -euo pipefail

for DB in "$POSTGRES_APP_DB" "${POSTGRES_APP_DB}_test" "$POSTGRES_TEMPORAL_DB" "$POSTGRES_KEYCLOAK_DB"; do
  EXISTS=$(psql -U "$POSTGRES_USER" -tAc "SELECT 1 FROM pg_database WHERE datname='${DB}'")
  if [ "$EXISTS" != "1" ]; then
    psql -U "$POSTGRES_USER" -c "CREATE DATABASE \"${DB}\" OWNER \"${POSTGRES_USER}\";"
  fi
done
