#!/bin/bash
set - e
set - u

# The following variables are used from ENV which
# is populated by summon with the following command
# summon -p `which summon-gopass` -D APP_ENV=int scripts/setup_rds_db.sh
# where the environment is set by the APP_ENV variable
# DB_NAME
# DB_USER
# DB_PW
# DB_HOST
# DB_PORT
# RDS_SUPERUSER

# The PGPASSWORD ENV Variable is set to suppress
# psql PW prompt
# Its value is taken from RDS_SUPERUSER_PW which is set
# by summon as well
PGPASSWORD=${RDS_SUPERUSER_PW}

# create db
SQL_DB="$(envsubst < scripts/sql/create_db.sql)"

# create user
SQL_USER="$(envsubst < scripts/sql/create_user.sql)"

create_user(){
    echo "create user"
    echo ${SQL_USER}
    # Note: RDS_SUPERUSER password is taken from env variable
    # PGPASSWORD set above (env variable RDS_SUPERUSER_PW)
    echo "-qAt -X -U ${RDS_SUPERUSER} -h ${DB_HOST} -p ${DB_PORT} -d template1 -c ${SQL_USER}"
}

create_db(){
    echo "create db"
    echo ${SQL_DB}
    echo "-qAt -X -U ${RDS_SUPERUSER} -h ${DB_HOST} -p ${DB_PORT} -d template1 -c ${SQL_DB}"
}

create_user
create_db
#setup_postgis
