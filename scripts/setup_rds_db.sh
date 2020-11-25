#!/bin/bash
set -e
set -u

MY_DIR=$(dirname "$(readlink -f "$0")")
# The following variables are used from ENV which
# is populated by summon with the following command
# summon -p `which summon-gopass` -D APP_ENV=int scripts/setup_rds_db.sh
# where the environment is set by the APP_ENV variable

# create db
SQL_CREATE_DB="$(envsubst < scripts/sql/create_db.sql)"

# create user
SQL_CREATE_USER="$(envsubst < scripts/sql/create_user.sql)"

create_user(){
    echo "create user"
    PGPASSWORD=${DB_SUPER_PW} psql -qAt -X -U ${DB_SUPER_USER} -h ${DB_HOST} -p ${DB_PORT} -d template1 -c "${SQL_CREATE_USER}"
}

create_db(){
    echo "create db"
    if [ "$(PGPASSWORD=${DB_SUPER_PW} psql -U ${DB_SUPER_USER} -h ${DB_HOST} -p ${DB_PORT} -d template1 -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" )" = '1' ]; then
      echo "db ${DB_NAME} already exists"
    else
      PGPASSWORD=${DB_SUPER_PW} psql -qAt -X -U ${DB_SUPER_USER} -h ${DB_HOST} -p ${DB_PORT} -d template1 -c "${SQL_CREATE_DB}"
    fi
}

grant_privileges(){
    echo "grant privileges"
    PGPASSWORD=${DB_SUPER_PW} psql -qAt -X -U ${DB_SUPER_USER} -h ${DB_HOST} -p ${DB_PORT} -d ${DB_NAME} -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} to ${DB_USER}";
}

setup_postgis(){
    echo "setup postgis"
    PGPASSWORD=${DB_SUPER_PW} psql -qAt -X -U ${DB_SUPER_USER} -h ${DB_HOST} -p ${DB_PORT} -d ${DB_NAME} -f "${MY_DIR}/sql/install_postgis.sql"
}

echo "[$(date +"%F %T")] start"
create_user
create_db
setup_postgis
grant_privileges
echo "[$(date +"%F %T")] end"
