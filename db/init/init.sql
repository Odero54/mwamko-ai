-- Create database if not exists
DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_database WHERE datname = 'mwamko'
   ) THEN
      CREATE DATABASE mwamko;
   END IF;
END
$do$;

-- Connect to DB
\c mwamko;

-- Enable PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_raster;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Enable pgRouting
CREATE EXTENSION IF NOT EXISTS pgrouting;

-- Optional useful extensions
CREATE EXTENSION IF NOT EXISTS hstore;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";