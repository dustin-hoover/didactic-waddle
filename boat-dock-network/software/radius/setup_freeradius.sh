#!/usr/bin/env bash
# Boat Dock Network — wire FreeRADIUS 3.2 to the DockOS billing database (doc 22).
#   sudo DB_NAME=dockos DB_PASS=... RADIUS_DB_PASS=... ./setup_freeradius.sh
# Creates the least-privilege `radius` DB role (doc 21 §11), installs the sql module,
# enables it, and validates the config. Idempotent.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DB_HOST="${DB_HOST:-127.0.0.1}"; DB_PORT="${DB_PORT:-5432}"; DB_NAME="${DB_NAME:-dockos}"
RADIUS_DB_USER="${RADIUS_DB_USER:-radius}"; RADIUS_DB_PASS="${RADIUS_DB_PASS:?set RADIUS_DB_PASS}"
READ_CLIENTS="${READ_CLIENTS:-yes}"
RADDB="${RADDB:-/etc/freeradius/3.0}"
PSQL=(sudo -u postgres psql -v ON_ERROR_STOP=1 -q -d "$DB_NAME")

# 1) least-privilege role: reads only the authorize VIEWS + nas; writes only accounting.
#    Views run with their owner's rights, so this role never sees service_instances,
#    passwords of other tables, invoices, or member data directly.
"${PSQL[@]}" <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${RADIUS_DB_USER}') THEN
    CREATE ROLE ${RADIUS_DB_USER} LOGIN PASSWORD '${RADIUS_DB_PASS}';
  ELSE
    ALTER ROLE ${RADIUS_DB_USER} LOGIN PASSWORD '${RADIUS_DB_PASS}';
  END IF;
END \$\$;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ${RADIUS_DB_USER};
GRANT SELECT ON radcheck, radreply, radusergroup, radgroupcheck, radgroupreply, nas TO ${RADIUS_DB_USER};
GRANT SELECT, INSERT, UPDATE ON radacct, radpostauth TO ${RADIUS_DB_USER};
GRANT USAGE ON SEQUENCE radacct_radacctid_seq, radpostauth_id_seq TO ${RADIUS_DB_USER};
SQL

# 2) install + enable the sql module
sed -e "s|@DB_HOST@|${DB_HOST}|" -e "s|@DB_PORT@|${DB_PORT}|" -e "s|@DB_USER@|${RADIUS_DB_USER}|" \
    -e "s|@DB_PASS@|${RADIUS_DB_PASS}|" -e "s|@DB_NAME@|${DB_NAME}|" -e "s|@READ_CLIENTS@|${READ_CLIENTS}|" \
    "$HERE/sql.conf.tmpl" > "$RADDB/mods-available/sql"
chown root:freerad "$RADDB/mods-available/sql"; chmod 640 "$RADDB/mods-available/sql"
ln -sf ../mods-available/sql "$RADDB/mods-enabled/sql"

# 3) validate (the stock default site already calls -sql in authorize/accounting/post-auth)
freeradius -C -X >/tmp/freeradius-check.log 2>&1 && echo "FreeRADIUS config OK" \
  || { tail -30 /tmp/freeradius-check.log; exit 1; }
