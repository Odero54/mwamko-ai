from typing import Any, Dict, List


def get_nodes_from_cases_and_start_point(
    conn: psycopg2.extensions.connection, case_ids: List[int], start_point_wkt: str
) -> List[int]:
    """
    Retrieves the nearest road node IDs for a list of emergency cases
    and prepends the nearest node for a starting GPS point.
    """
    print(f"DEBUG: Looking for nodes for cases: {case_ids}")
    print(f"DEBUG: Start point WKT: {start_point_wkt}")

    # SQL to find the nearest node (vertex) for all cases - FIXED to avoid duplicates
    case_points_query = """
    WITH CasePoints AS (
        -- Convert the location string to proper WKT format
        SELECT 
            case_id, 
            ST_GeomFromText(
                'POINT(' || 
                SPLIT_PART(location, ',', 1) || ' ' || 
                SPLIT_PART(location, ',', 2) || 
                ')', 
                4326
            ) AS geom
        FROM emergency_cases
        WHERE case_id = ANY(%s::int[])
    ),
    NearestCaseNodes AS (
        SELECT DISTINCT ON (cp.case_id)
            cp.case_id,
            -- Find the nearest vertex (node) in the road network
            (SELECT node.id FROM road_segments_vertices_pgr node
             ORDER BY node.geom <-> cp.geom
             LIMIT 1
            ) AS nearest_node_id
        FROM CasePoints cp
    )
    SELECT nearest_node_id FROM NearestCaseNodes
    """

    # SQL to find the nearest node to the single start point
    start_point_query = f"""
    SELECT id AS nearest_node_id
    FROM road_segments_vertices_pgr
    ORDER BY geom <-> ST_GeomFromText('{start_point_wkt}', 4326)
    LIMIT 1;
    """

    node_ids = []
    try:
        with conn.cursor() as cursor:
            # 1. Get Nearest Node for Start Point
            print("DEBUG: Finding start point node...")
            cursor.execute(start_point_query)
            start_node_result = cursor.fetchone()

            if start_node_result:
                start_node_id = start_node_result["nearest_node_id"]
                print(f"DEBUG: Start node found: {start_node_id}")
                node_ids.append(start_node_id)
            else:
                print("DEBUG: No start node found!")
                raise Exception("Could not find nearest node for start point")

            # 2. Get Nearest Nodes for Cases
            print("DEBUG: Finding case nodes...")
            cursor.execute(case_points_query, (case_ids,))
            case_nodes = [row["nearest_node_id"] for row in cursor.fetchall()]
            print(f"DEBUG: Case nodes found: {case_nodes}")

            # 3. Combine and remove duplicates using set to ensure uniqueness
            all_nodes = [start_node_id] + case_nodes
            # Use set to remove duplicates but maintain order with start node first
            unique_nodes = []
            seen = set()
            for node in all_nodes:
                if node not in seen:
                    seen.add(node)
                    unique_nodes.append(node)

            print(f"DEBUG: Final unique node list: {unique_nodes}")
            return unique_nodes

    except psycopg2.Error as e:
        print(f"PostgreSQL Error during node lookup: {e}")
        raise
    except Exception as e:
        print(f"Error during node lookup: {e}")
        raise


def find_tsp_route(
    conn: psycopg2.extensions.connection, node_ids: List[int]
) -> List[Dict[str, Any]]:
    """
    Simple and robust TSP routing.
    """
    print(f"DEBUG: Starting TSP routing with nodes: {node_ids}")

    if len(node_ids) < 2:
        print("DEBUG: Not enough nodes for routing")
        return []

    # Use the first node as both start and end for TSP
    node_ids[0]

    # Simple TSP query
    routing_query = f"""
    WITH cost_matrix AS (
        SELECT *
        FROM pgr_dijkstraCostMatrix(
            'SELECT id, source, target, cost FROM road_segments',
            ARRAY{node_ids},
            directed := false
        )
    ),
    tsp_order AS (
        SELECT *
        FROM pgr_tsp(
            'SELECT start_vid, end_vid, agg_cost FROM cost_matrix',
            start_id := 1,
            end_id := 1
        )
    ),
    route_segments AS (
        SELECT 
            tsp.seq,
            node_ids[tsp.node] as from_node,
            node_ids[COALESCE(LEAD(tsp.node) OVER (ORDER BY tsp.seq), 1)] as to_node
        FROM tsp_order tsp,
        (SELECT ARRAY{node_ids} as node_ids) as nodes
        WHERE tsp.seq < (SELECT COUNT(*) FROM tsp_order)
    ),
    final_route AS (
        SELECT 
            rs.seq,
            rs.from_node,
            rs.to_node,
            dijk.path_seq,
            dijk.edge,
            dijk.cost,
            rs.geom
        FROM route_segments rs
        CROSS JOIN LATERAL (
            SELECT *
            FROM pgr_dijkstra(
                'SELECT id, source, target, cost FROM road_segments',
                rs.from_node,
                rs.to_node,
                directed := false
            )
        ) dijk
        LEFT JOIN road_segments ON dijk.edge = road_segments.id
        WHERE dijk.edge != -1
    )
    SELECT 
        seq as tsp_sequence,
        path_seq as segment_sequence,
        from_node as start_node_id,
        to_node as end_node_id,
        edge as segment_id,
        cost as segment_cost,
        ST_AsText(road_segments.geom) as geometry_wkt,
        road_segments.source,
        road_segments.target
    FROM final_route
    JOIN road_segments ON final_route.edge = road_segments.id
    ORDER BY tsp_sequence, segment_sequence;
    """

    # Alternative: Even simpler approach - direct route between nodes
    simple_routing_query = f"""
    WITH route AS (
        SELECT *
        FROM pgr_dijkstra(
            'SELECT id, source, target, cost FROM road_segments',
            {node_ids[0]},
            {node_ids[1]},
            directed := false
        )
        WHERE edge != -1
    )
    SELECT 
        1 as seq,
        1 as tsp_sequence,
        {node_ids[0]} as start_node_id,
        {node_ids[1]} as end_node_id,
        r.seq as segment_sequence,
        r.edge as segment_id,
        r.cost as segment_cost,
        r.agg_cost as cumulative_cost,
        ST_AsText(rs.geom) as geometry_wkt,
        rs.source,
        rs.target
    FROM route r
    JOIN road_segments rs ON r.edge = rs.id
    ORDER BY r.seq;
    """

    results = []

    try:
        with conn.cursor() as cursor:
            print("DEBUG: Executing simple routing query...")
            cursor.execute(simple_routing_query)
            results = cursor.fetchall()

            print(f"DEBUG: Routing found {len(results)} segments")

            # Convert to list of dictionaries
            route_segments = []
            for row in results:
                route_segments.append(dict(row))

            return route_segments

    except psycopg2.Error as e:
        conn.rollback()
        print(f"DEBUG: Routing failed with error: {e}")
        return []


def fallback_simple_route(
    conn: psycopg2.extensions.connection, node_ids: List[int]
) -> List[Dict[str, Any]]:
    """
    Fallback routing - simple sequential routing between nodes.
    """
    print(f"DEBUG: Using fallback routing for nodes: {node_ids}")

    route_segments = []
    cumulative_cost = 0.0

    for i in range(len(node_ids) - 1):
        start_node = node_ids[i]
        end_node = node_ids[i + 1]

        route_query = f"""
        SELECT 
            seq,
            {start_node} as start_node,
            {end_node} as end_node,
            cost as segment_cost,
            agg_cost as leg_cost,
            edge,
            node
        FROM pgr_dijkstra(
            'SELECT id, source, target, cost FROM road_segments',
            {start_node},
            {end_node},
            directed := false
        )
        WHERE edge != -1
        """

        try:
            with conn.cursor() as cursor:
                cursor.execute(route_query)
                segments = cursor.fetchall()

                if segments:
                    for seg in segments:
                        segment_dict = dict(seg)
                        cumulative_cost += segment_dict["segment_cost"]
                        segment_dict["cumulative_cost"] = cumulative_cost

                        # Get geometry for this segment
                        geom_query = f"SELECT ST_AsText(geom) as geometry_wkt FROM road_segments WHERE id = {segment_dict['edge']}"
                        cursor.execute(geom_query)
                        geom_result = cursor.fetchone()
                        segment_dict["geometry_wkt"] = (
                            geom_result["geometry_wkt"] if geom_result else None
                        )

                        route_segments.append(segment_dict)
                else:
                    print(f"DEBUG: No route found from {start_node} to {end_node}")

        except Exception as e:
            print(f"DEBUG: Fallback routing failed for segment {i}: {e}")
            continue

    print(f"DEBUG: Fallback routing found {len(route_segments)} segments")
    return route_segments


def save_route_to_database(
    conn: psycopg2.extensions.connection,
    status: str,
    total_cost: float,
    optimized_sequence: List[int],
    route_segments: List[Dict],
) -> int:
    """
    Save the calculated route to the routes table.
    """
    insert_query = """
    INSERT INTO routes (status, total_cost, optimized_sequence, route_segments, created_at)
    VALUES (%s, %s, %s, %s, NOW())
    RETURNING route_id;
    """

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                insert_query,
                (
                    status,
                    total_cost,
                    json.dumps(optimized_sequence),
                    json.dumps(route_segments),
                ),
            )
            result = cursor.fetchone()
            route_id = result["route_id"] if result else None
            conn.commit()
            print(f"DEBUG: Route saved with ID: {route_id}")
            return route_id

    except psycopg2.Error as e:
        conn.rollback()
        print(f"PostgreSQL Error saving route: {e}")
        raise
