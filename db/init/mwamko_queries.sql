CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgrouting;

SELECT * FROM constraints;
--DROP TABLE IF EXISTS road_segments_vertices_pgr;
--DROP TABLE IF EXISTS road_segments;


-- Create Spatial Indexes
CREATE INDEX road_segments_geom_idx
    ON road_segments
    USING GIST (geometry);

CREATE INDEX constraints_geom_idx
    ON constraints
    USING GIST (geometry);


CREATE TABLE rescue_vehicles (
    -- STATIC VEHICLE INFORMATION
    vehicle_id VARCHAR(50) PRIMARY KEY, -- Unique ID (e.g., 'AMB-001', 'FIRE-005')
    registration_plate VARCHAR(20) UNIQUE NOT NULL, -- License Plate for identification
    vehicle_type VARCHAR(50) NOT NULL,    -- e.g., 'Ambulance', '4x4', 'Motorcycle'
    max_passenger_capacity INTEGER NOT NULL, -- Max number of people (patients/crew) it can carry
    
    -- DYNAMIC/REAL-TIME STATUS
    status VARCHAR(20) NOT NULL,          -- e.g., 'AVAILABLE', 'DISPATCHED', 'EN_ROUTE_TO_HOSPITAL', 'OUT_OF_SERVICE'
    current_occupancy INTEGER DEFAULT 0,  -- Current number of non-crew people/patients on board
    last_update_ts TIMESTAMP WITH TIME ZONE NOT NULL, -- Timestamp of the last GPS ping
    
    -- GEOSPATIAL DATA (Real-Time Location)
    geometry GEOMETRY(Point, 4326)            -- PostGIS Point geometry for real-time location
);


-- Comments for documentation (optional, but good practice)
COMMENT ON TABLE rescue_vehicles IS 'Stores the static information and real-time location/status of all Mwamko AI rescue units.';
COMMENT ON COLUMN rescue_vehicles.geometry IS 'Real-time GPS location of the vehicle (SRID 4326).';


CREATE INDEX rescue_vehicles_geom_idx
    ON rescue_vehicles
    USING GIST (geometry);


INSERT INTO rescue_vehicles (
    vehicle_id, registration_plate, vehicle_type, max_passenger_capacity, status, last_update_ts, geom
)
VALUES 
(
    'AMB-TT01', 
    'KCT 101A', 
    'Ambulance', 
    4, 
    'AVAILABLE', 
    NOW(), 
    ST_SetSRID(ST_MakePoint(38.35, -3.5), 4326) -- Example: Near Voi, Taita Taveta
);

SELECT * FROM rescue_vehicles;   


ALTER TABLE road_segments
    ADD COLUMN source integer,
    ADD COLUMN target integer;

select * from road_segments;


-- 1. Rename travel time column (e.g., base_travel_time_min) to 'cost'
ALTER TABLE road_segments
    RENAME COLUMN base_travel_time_min TO cost;

ALTER TABLE constraints
    RENAME COLUMN geometry TO geom;

ALTER TABLE road_segments
    RENAME COLUMN geometry TO geom;



-- Build the Network Topology

-- viewing available pgRouting functions
SELECT proname 
FROM pg_proc 
WHERE proname LIKE 'pgr_%' 
ORDER BY proname;


-- ALTER TABLE road_segments DROP COLUMN IF EXISTS source, DROP COLUMN IF EXISTS target;

ALTER TABLE road_segments
    ADD COLUMN source integer,
    ADD COLUMN target integer;

select * from rescue_vehicles;


-- Creating Network Topology Steps

UPDATE road_segments SET source = NULL, target = NULL;

-- Create a new vertices table (nodes) by dumping all segment points and snapping them
CREATE TABLE road_segments_vertices_pgr AS
SELECT
    row_number() OVER () AS id,
    (ST_DumpPoints(geom)).geom
FROM road_segments;

CREATE INDEX road_segments_vertices_geom_idx
    ON road_segments_vertices_pgr
    USING GIST (geom);

-- Snap points to form intersections (Crucial for a clean graph)
UPDATE road_segments_vertices_pgr
SET geom = ST_SetSRID(
    ST_MakePoint(
        ROUND(ST_X(geom)::numeric, 5), -- Round X coordinate to 5 decimal places
        ROUND(ST_Y(geom)::numeric, 5)  -- Round Y coordinate to 5 decimal places
    ),
    4326 -- Set the SRID back to 4326
);

-- Remove duplicates
ALTER TABLE road_segments_vertices_pgr
ADD COLUMN x_coord DOUBLE PRECISION,
ADD COLUMN y_coord DOUBLE PRECISION;

UPDATE road_segments_vertices_pgr
SET x_coord = ST_X(geom),
    y_coord = ST_Y(geom);

-- Create a composite B-tree index on the coordinates
-- This index is key to speeding up the duplicate check.
CREATE INDEX road_segments_pgr_coords_idx
    ON road_segments_vertices_pgr (x_coord, y_coord);

WITH RankedVertices AS (
    SELECT
        id,
        ROW_NUMBER() OVER(PARTITION BY x_coord, y_coord ORDER BY id ASC) as rn
    FROM road_segments_vertices_pgr
)
DELETE FROM road_segments_vertices_pgr
WHERE id IN (
    SELECT id
    FROM RankedVertices
    WHERE rn > 1 -- Keep only the rows that are NOT the first occurrence (rn = 1)
);

-- Essential indexes for KNN searches
CREATE INDEX CONCURRENTLY IF NOT EXISTS road_segments_vertices_pgr_geom_idx 
ON road_segments_vertices_pgr USING GIST (geom);

CREATE INDEX CONCURRENTLY IF NOT EXISTS road_segments_geom_idx 
ON road_segments USING GIST (geom);

-- Optional: Indexes for the points if doing frequent point-based queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS road_segments_startpoint_idx 
ON road_segments USING GIST (ST_StartPoint(geom));

CREATE INDEX CONCURRENTLY IF NOT EXISTS road_segments_endpoint_idx 
ON road_segments USING GIST (ST_EndPoint(geom));

ANALYZE road_segments_vertices_pgr;
ANALYZE road_segments;

-- Populate Source/Target
WITH segment_points AS (
    SELECT 
        id,
        ST_StartPoint(geom) AS start_geom,
        ST_EndPoint(geom) AS end_geom,
        source AS current_source,
        target AS current_target
    FROM road_segments
    WHERE geom IS NOT NULL
),
vertex_matches AS (
    SELECT 
        sp.id,
        v_start.id AS new_source,
        v_end.id AS new_target
    FROM segment_points sp
    LEFT JOIN LATERAL (
        SELECT id
        FROM road_segments_vertices_pgr
        WHERE ST_DWithin(sp.start_geom, geom, 0.01)
        ORDER BY sp.start_geom <-> geom
        LIMIT 1
    ) v_start ON true
    LEFT JOIN LATERAL (
        SELECT id
        FROM road_segments_vertices_pgr
        WHERE ST_DWithin(sp.end_geom, geom, 0.01)
        ORDER BY sp.end_geom <-> geom
        LIMIT 1
    ) v_end ON true
    WHERE v_start.id IS NOT NULL 
       AND v_end.id IS NOT NULL
       AND (sp.current_source IS DISTINCT FROM v_start.id 
         OR sp.current_target IS DISTINCT FROM v_end.id)
)
UPDATE road_segments r
SET 
    source = vm.new_source,
    target = vm.new_target
FROM vertex_matches vm
WHERE r.id = vm.id;

-- Verification
SELECT count(*) AS total_segments,
       count(source) AS segments_with_source
FROM road_segments;

SELECT count(*) AS total_unmatched_segments
FROM road_segments
WHERE source IS NULL OR target IS NULL;

SELECT id, geom, ST_Length(geom::geography) AS length_m
FROM road_segments
WHERE source IS NULL OR target IS NULL
LIMIT 10;

DELETE FROM road_segments
WHERE source IS NULL OR target IS NULL;

-- Verify deletion
SELECT count(*) AS total_segments, 
       count(source) AS segments_with_source
FROM road_segments;


select * from road_segments;


-- DROP TABLE IF EXISTS road_segments_vertices_pgr;

SELECT pgr_version();


-- List available pgRouting functions
SELECT proname 
FROM pg_proc 
WHERE proname LIKE 'pgr_%' 
ORDER BY proname;

CREATE INDEX IF NOT EXISTS road_segments_source_idx ON road_segments (source);
CREATE INDEX IF NOT EXISTS road_segments_target_idx ON road_segments (target);


-- Find the Largest Connected Component ID
SELECT cc.component, count(*) AS component_size
FROM pgr_connectedComponents(
    'SELECT id, source, target, cost FROM road_segments'
) AS cc
GROUP BY cc.component
ORDER BY component_size DESC
LIMIT 1;

-- Find the Two Nodes on the Largest Component
SELECT node
FROM pgr_connectedComponents(
    'SELECT id, source, target, cost FROM road_segments'
) AS cc
WHERE cc.component = 1 -- Replace 1 with the actual largest component ID from Step 1
ORDER BY RANDOM()
LIMIT 2;

-- Basic Shortest path query
SELECT *
FROM pgr_dijkstra(
    'SELECT id, source, target, cost FROM road_segments', -- The graph definition
    283, -- start_vid (source node ID)
    3762, -- end_vid (target node ID)
    directed := false -- Assuming road segments are directed (one-way or two-way with separate rows)
);

-- Find closest Node (lon, lat)
CREATE OR REPLACE FUNCTION find_closest_node(
    p_lon DOUBLE PRECISION,
    p_lat DOUBLE PRECISION
)
RETURNS BIGINT AS $$
DECLARE
    closest_node_id BIGINT;
BEGIN
    -- 1. Create a PostGIS Point from the input coordinates
    WITH input_point AS (
        SELECT ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326) AS geom
    )
    -- 2. Find the closest vertex (node) in the graph using KNN (<->)
    SELECT v.id INTO closest_node_id
    FROM road_segments_vertices_pgr AS v
    ORDER BY v.geom <-> (SELECT geom FROM input_point)
    LIMIT 1;

    RETURN closest_node_id;
END;
$$ LANGUAGE plpgsql;

-- Apply the function find_closest_node
SELECT *
FROM pgr_dijkstra(
    'SELECT id, source, target, cost FROM road_segments', 
    find_closest_node(38.3, -3.4),  -- Starting Node ID (Vehicle)
    find_closest_node(38.4, -3.3),  -- Ending Node ID (Incident)
    directed := false
);

SELECT find_closest_node(38.3, -3.4) AS start_node,
       find_closest_node(38.4, -3.3) AS end_node;

SELECT cc.component
FROM (
    -- Get all unique nodes in the graph
    SELECT source AS node FROM road_segments
    UNION 
    SELECT target AS node FROM road_segments
) AS nodes
JOIN pgr_connectedComponents(
    -- CORRECTED: Removed 'directed' column
    'SELECT id, source, target, cost FROM road_segments' 
) AS cc ON nodes.node = cc.node
WHERE nodes.node IN (283, 3762) -- Using your verified node IDs
GROUP BY cc.component
HAVING count(DISTINCT nodes.node) = 2;


SELECT node
FROM pgr_connectedComponents(
    'SELECT id, source, target, cost FROM road_segments'
) AS cc
WHERE cc.component = 1
ORDER BY node
LIMIT 2;


SELECT
    route.seq,
    route.node AS node_id,
    rs.id AS edge_id,
    route.cost,
    route.agg_cost,
    rs.geom -- The geometry of the road segment
FROM pgr_dijkstra(
    -- 1. Graph SQL: Selects ID, source, target, and travel time (cost)
    'SELECT id, source, target, cost FROM road_segments',
    1, -- Start Node ID
    2, -- End Node ID
    directed := false -- Assumes two-way travel, safer for general road data
) AS route
-- 2. Join back to the road_segments table to get the geometry and original segment ID
JOIN road_segments AS rs ON route.edge = rs.id
ORDER BY route.seq;



SELECT id, source, target, 
    CASE
        -- Check if the road segment intersects ANY constraint polygon
        WHEN EXISTS (
            SELECT 1 
            FROM constraints AS c 
            WHERE ST_Intersects(rs.geom, c.geom)
        ) THEN 
            -- If intersected, assign an extremely high cost (1,000,000 seconds) 
            -- This makes the path functionally impossible/unattractive
            1000000 
        ELSE 
            -- If clean, use the normal travel time (cost)
            cost 
    END AS cost 
FROM road_segments AS rs;


-- Final Flood Aware Query
SELECT *
FROM pgr_dijkstra(
    -- The graph definition now includes the CASE statement for flood avoidance
    'SELECT id, source, target, ' ||
    'CASE WHEN EXISTS (SELECT 1 FROM constraints AS c WHERE ST_Intersects(rs.geom, c.geom)) ' ||
    'THEN 1000000 ELSE cost END AS cost ' ||
    'FROM road_segments AS rs',
    1, -- Start Node ID
    2, -- End Node ID
    directed := false
);


-- The Flood-Aware TSP Query
SELECT id, source, target, 
    CASE 
        WHEN EXISTS (
            SELECT 1 FROM constraints AS c 
            WHERE ST_Intersects(rs.geom, c.geom)
        ) THEN 
            1000000 -- Penalty in minutes (1,000,000 minutes ≈ 1.9 years)
        ELSE 
            cost 
    END AS cost 
FROM road_segments AS rs;



SELECT * FROM (VALUES (1, 1), (2, 283), (3, 3762)) AS t(id, node);


-- create a temporary cost matrix
-- DROP TABLE IF EXISTS temp_cost_matrix;
CREATE TEMP TABLE IF NOT EXISTS temp_cost_matrix AS
SELECT *
FROM pgr_dijkstraCostMatrix(
    'SELECT id, source, target, 
        CASE 
            WHEN EXISTS (SELECT 1 FROM constraints AS c WHERE ST_Intersects(rs.geom, c.geom)) 
            THEN 1000000 
            ELSE cost 
        END AS cost 
    FROM road_segments AS rs',
    ARRAY[1, 283, 3762],
    directed := false
);


-- DROP TABLE IF EXISTS temp_cost_matrix_mapped;

CREATE TEMP table IF NOT EXISTS temp_cost_matrix_mapped AS
WITH nodes AS (
    SELECT 
        ROW_NUMBER() OVER (ORDER BY start_vid) as seq_id,
        start_vid as original_id
    FROM (
        SELECT DISTINCT start_vid FROM temp_cost_matrix
    ) AS distinct_nodes
)
SELECT 
    n1.seq_id as start_vid,
    n2.seq_id as end_vid,
    c.agg_cost
FROM temp_cost_matrix c
JOIN nodes n1 ON c.start_vid = n1.original_id
JOIN nodes n2 ON c.end_vid = n2.original_id;

-- Solve TCP with proper node mapping
SELECT 
    tsp.seq,
    tsp.node AS matrix_index,
    CASE tsp.node
        WHEN 1 THEN 1
        WHEN 2 THEN 283
        WHEN 3 THEN 3762
    END AS original_node_id,
    tsp.cost,
    tsp.agg_cost
FROM pgr_tsp(
    'SELECT start_vid, end_vid, agg_cost FROM temp_cost_matrix_mapped',
    1,  -- start_id (now using sequential index)
    1   -- end_id (now using sequential index)
) AS tsp
ORDER BY tsp.seq;


-- Available function signatures
SELECT proname, pg_get_function_arguments(oid)
FROM pg_proc 
WHERE proname LIKE 'pgr%tsp%' OR proname LIKE 'pgr%TSP%'
ORDER BY proname;


-- Define the original set of points for mapping
WITH PointsToVisit AS (
    SELECT id, node AS original_node_id
    FROM (VALUES (1, 1), (2, 283), (3, 3762)) AS t(id, node)
),
-- 1. Solve the Flood-Aware TSP and create the sequence of legs
TSPPairs AS (
    SELECT
        tsp.seq,
        tsp.node AS start_matrix_id,
        LEAD(tsp.node, 1, tsp.node) OVER (ORDER BY tsp.seq) AS end_matrix_id,
        CASE tsp.node
            WHEN 1 THEN 1
            WHEN 2 THEN 283
            WHEN 3 THEN 3762
        END AS start_node_id,
        LEAD(CASE tsp.node
            WHEN 1 THEN 1
            WHEN 2 THEN 283
            WHEN 3 THEN 3762
        END, 1, 0) OVER (ORDER BY tsp.seq) AS end_node_id -- Use 0 as placeholder for the last node
    FROM pgr_tsp(
        'SELECT start_vid, end_vid, agg_cost FROM temp_cost_matrix_mapped',
        1,  -- start_id (matrix index)
        1   -- end_id (matrix index)
    ) AS tsp
    WHERE tsp.seq < (SELECT COUNT(*) FROM PointsToVisit) -- Exclude the final return to start
),
-- 2. Map the TSP sequence into the individual road segments using Dijkstra
SegmentRoutes AS (
    SELECT
        tp.seq,
        tp.start_node_id,
        tp.end_node_id,
        route.agg_cost AS leg_cost,
        route.edge AS edge_id -- The segment ID
    FROM TSPPairs AS tp
    -- LATERAL JOIN runs the Dijkstra function for EACH leg (row) in TSPPairs
    JOIN LATERAL pgr_dijkstra(
        -- The Flood-Aware Graph Definition (Same as before)
        'SELECT id, source, target, 
            CASE 
                WHEN EXISTS (SELECT 1 FROM constraints AS c WHERE ST_Intersects(rs.geom, c.geom)) 
                THEN 1000000 
                ELSE cost 
            END AS cost 
        FROM road_segments AS rs',
        tp.start_node_id,
        tp.end_node_id,
        directed := false
    ) AS route ON route.edge != -1 -- Ignore the first and last dummy rows
    WHERE tp.end_node_id != 0 -- Exclude the final placeholder row
)
-- 3. Final selection: Join routes to geometry and calculate total cost
SELECT
    sr.seq,
    sr.start_node_id,
    sr.end_node_id,
    sr.leg_cost,
    SUM(sr.leg_cost) OVER (ORDER BY sr.seq) AS cumulative_cost,
    rs.geom AS geometry -- The actual line geometry for mapping
FROM SegmentRoutes AS sr
JOIN road_segments AS rs ON sr.edge_id = rs.id
ORDER BY sr.seq, rs.id;

-- DROP TABLE temp_cost_matrix;

select * from road_segments_vertices_pgr;
select * from road_segments;
select * from users;
select * from emergency_cases;

SELECT case_id, location FROM emergency_cases;

UPDATE emergency_cases 
SET location = 
    CASE 
        WHEN location LIKE '%,%' THEN 
            -- Split by comma and swap the values
            SPLIT_PART(location, ',', 2) || ',' || SPLIT_PART(location, ',', 1)
        ELSE 
            location  -- Keep as is if no comma found
    END;

SELECT case_id, location FROM emergency_cases;

select * from routes;
--drop table users;

select * from invites;
select * from users;

delete from invites 
where id = 2;


-- Run this in your database
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'users' 
ORDER BY ordinal_position;

-- ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT NOW();

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

select * from users;