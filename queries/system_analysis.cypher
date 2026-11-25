// =====================================================================
//  System analysis queries on the CubeSat knowledge graph (Neo4j)
//  Run them in Neo4j Browser (http://localhost:7474) one by one.
// =====================================================================

// Q1. Total mass of the satellite and check of requirement R1 (<= 4 kg)
//     Expected: totalMass 2.2 | limit 4.0 | R1 "PASS"
MATCH (p:Part)-[:PART_OF]->(:Part {name: "cubeSat"})
WITH round(sum(p.mass), 2) AS totalMass
MATCH (r:Requirement {name: "r1_mass"})
RETURN totalMass, r.massLimit AS limit,
       CASE WHEN totalMass <= r.massLimit THEN "PASS" ELSE "FAIL" END AS R1;

// Q2. Requirements that no part satisfies (gap detection)
//     Expected: r4_thermalRange
MATCH (r:Requirement)
WHERE NOT EXISTS { ()-[:SATISFIES]->(r) }
RETURN r.name AS unsatisfied, r.doc AS text;

// Q3. Change impact: which parts depend on the battery (graph view)
//     Expected: obc, radio, camera
MATCH path = (:Part {name: "battery"})-[:POWERS|SENDS_DATA*1..3]->(:Part)
RETURN path;

// Q4. Change impact: which requirements are affected by the battery
//     Expected: r2_eclipsePower via battery | r3_imageDownlink via camera, radio
MATCH (:Part {name: "battery"})-[:POWERS|SENDS_DATA*0..3]->(p:Part)-[:SATISFIES]->(r:Requirement)
RETURN DISTINCT r.name AS affectedRequirement, collect(DISTINCT p.name) AS via;
