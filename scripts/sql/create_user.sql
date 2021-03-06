BEGIN;
DO $$
BEGIN
CREATE ROLE ${DB_USER} WITH
    NOSUPERUSER INHERIT NOCREATEROLE NOCREATEDB LOGIN NOREPLICATION NOBYPASSRLS 
    PASSWORD '${DB_PW}' VALID UNTIL 'infinity';
EXCEPTION WHEN DUPLICATE_OBJECT THEN
  RAISE NOTICE 'not creating role ${DB_USER} -- it already exists';
END
$$;
ALTER ROLE ${DB_USER}
    SET log_statement TO 'all';
COMMIT;