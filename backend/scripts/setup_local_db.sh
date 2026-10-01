#!/usr/bin/env bash
# Creates the local development databases, owned by role "bellz". Idempotent.
#
#   bash backend/scripts/setup_local_db.sh
#
# Needs sudo to act as the postgres superuser on the local server. It never
# touches an existing role or database. Production uses Supabase, not this.
set -euo pipefail

ROLE="${DB_ROLE:-bellz}"
DBS=("creatorops" "creatorops_test")   # the test database is dropped/recreated by the test suite
PSQL=(sudo -u postgres psql -v ON_ERROR_STOP=1 -qAt)

role_exists=$("${PSQL[@]}" -c "SELECT 1 FROM pg_roles WHERE rolname = '$ROLE'")
if [ -z "$role_exists" ]; then
  read -rsp "Choose a password for the new role '$ROLE': " PW; echo
  # Password goes through a psql variable so quotes in it cannot break the statement.
  "${PSQL[@]}" -v pw="$PW" <<< "CREATE ROLE $ROLE LOGIN PASSWORD :'pw';"
  echo "created role $ROLE"
else
  echo "role $ROLE already exists (left unchanged)"
fi

for db in "${DBS[@]}"; do
  exists=$("${PSQL[@]}" -c "SELECT 1 FROM pg_database WHERE datname = '$db'")
  if [ -z "$exists" ]; then
    "${PSQL[@]}" -c "CREATE DATABASE $db OWNER $ROLE;"
    echo "created database $db (owner $ROLE)"
  else
    echo "database $db already exists (left unchanged)"
  fi
done

cat <<MSG

Put this in backend/.env (replace <password>):
  DATABASE_URL=postgresql+psycopg://$ROLE:<password>@localhost:5432/creatorops

Then:
  cd backend && alembic upgrade head
  TEST_DATABASE_URL=postgresql+psycopg://$ROLE:<password>@localhost:5432/creatorops_test pytest
MSG
