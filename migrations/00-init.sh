#!/bin/bash
set -euf -o pipefail

psql -v ON_ERROR_STOP=1 --username "postgres" --dbname "postgres" <<-EOSQL
    CREATE ROLE graha WITH login;
    CREATE DATABASE graha WITH OWNER graha;
EOSQL
