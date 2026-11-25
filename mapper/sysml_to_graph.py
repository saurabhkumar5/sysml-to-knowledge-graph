"""
Step 6: SysML v2 JSON  ->  knowledge graph (nodes + edges)

Input : data/elements.json        (from fetch_model.py, SysML v2 API)
Rules : mapper/mapping_rules.toml (the "dictionary")
Output: data/graph.json           (nodes and edges, tool independent)
        data/graph.cypher         (same graph as Cypher, for Neo4j in step 7)

Usage (from the project root):
    python3 mapper/sysml_to_graph.py
"""
import collections
import json
import tomllib  # built into Python 3.11+

ELEMENTS_FILE = "data/elements.json"
RULES_FILE = "mapper/mapping_rules.toml"


class Mapper:
    def __init__(self, elements, rules):
        self.rules = rules
        self.by_id = {e["@id"]: e for e in elements}   # fast lookup by @id
        self.elements = elements
        self.nodes = {}   # node id -> node
        self.edges = []   # list of edges

    # ---------------------------------------------------------- helpers
    def get(self, ref):
        """Follow a reference like {"@id": "..."} to the element."""
        if isinstance(ref, dict) and "@id" in ref:
            return self.by_id.get(ref["@id"])
        return None

    def refs(self, element, field):
        """Return the referenced elements of a field (field can be one ref or a list)."""
        value = element.get(field)
        if isinstance(value, dict):
            value = [value]
        return [self.get(v) for v in (value or []) if self.get(v)]

    def name(self, element):
        return element.get("declaredName") or element.get("name") or ""

    def resolve_chain(self, feature):
        """A reference like 'battery.powerOut' is a Feature with chainingFeature
        [battery, powerOut]. Return the list of elements in the chain."""
        if feature is None:
            return []
        chain = self.refs(feature, "chainingFeature")
        return chain if chain else [feature]

    def add_edge(self, source, target, edge_type, via=None, **props):
        if source in self.nodes and target in self.nodes:
            edge = {"source": source, "target": target, "type": edge_type, "props": props}
            if via:
                edge["props"]["sysml_id"] = via   # keep the id of the SysML relationship
            self.edges.append(edge)

    # ---------------------------------------------------- rule 1: nodes
    def map_nodes(self):
        for e in self.elements:
            label = self.rules["nodes"].get(e["@type"])
            if not label:
                continue
            allowed_owners = self.rules["owner_filter"].get(e["@type"])
            owner = self.get(e.get("owner"))
            if allowed_owners and (owner is None or owner["@type"] not in allowed_owners):
                continue
            if not self.name(e):
                continue
            self.nodes[e["@id"]] = {
                "id": e["@id"],
                "label": label,
                "props": {
                    "sysml_id": e["@id"],
                    "name": self.name(e),
                    "qualified_name": e.get("qualifiedName"),
                    "sysml_type": e["@type"],
                },
            }

    # ----------------------------------------- rule 4: values -> properties
    def literal(self, expression):
        """Read '0.3 [kg]' or '9.6' from an expression tree. Returns (value, unit)."""
        if expression is None:
            return None, None
        if expression["@type"] in ("LiteralRational", "LiteralInteger", "LiteralString", "LiteralBoolean"):
            return expression.get("value"), None
        if expression["@type"] == "OperatorExpression" and expression.get("operator") == "[":
            number, unit_ref = self.refs(expression, "argument")[:2]
            value, _ = self.literal(number)
            unit_id = (unit_ref.get("referent") or {}).get("@id")
            return value, self.rules["units"].get(unit_id, unit_id)
        return None, None   # formulas like totalMass = a + b + ... are not stored

    def map_properties(self):
        for node_id, node in self.nodes.items():
            element = self.by_id[node_id]
            for attribute in self.refs(element, "ownedFeature"):
                if attribute["@type"] != "AttributeUsage":
                    continue
                for relationship in self.refs(attribute, "ownedRelationship"):
                    if relationship["@type"] == "FeatureValue":
                        value, unit = self.literal(self.get(relationship.get("value")))
                        if value is not None:
                            node["props"][self.name(attribute)] = value
                            if unit:
                                node["props"][self.name(attribute) + "_unit"] = unit
        # documentation text -> 'doc' property
        for e in self.elements:
            if e["@type"] == "Documentation" and e.get("owner", {}).get("@id") in self.nodes:
                self.nodes[e["owner"]["@id"]]["props"]["doc"] = (e.get("body") or "").strip()

    # --------------------------------------- ports: one node per part + port
    def map_ports(self):
        """Ports are defined in the part definition (Battery::powerIn), so leftPanel and
        rightPanel share the same PortUsage. In the graph each part gets its own port
        node: id = <part id>/<port id>."""
        self.port_nodes = {}
        for node_id, node in list(self.nodes.items()):
            if node["label"] != "Part":
                continue
            for port in self.refs(self.by_id[node_id], "feature"):
                if port["@type"] != "PortUsage":
                    continue
                port_type = (self.refs(port, "type") or [{}])[0]
                conjugated = port_type.get("@type") == "ConjugatedPortDefinition"
                base_def = self.get(port_type.get("owner")) if conjugated else port_type
                pid = f"{node_id}/{port['@id']}"
                self.nodes[pid] = {
                    "id": pid,
                    "label": "Port",
                    "props": {
                        "sysml_id": port["@id"],
                        "name": f"{node['props']['name']}.{self.name(port)}",
                        "direction": "in" if conjugated else "out",
                        "port_def": self.name(base_def) if base_def else None,
                    },
                }
                self.port_nodes[(node_id, port["@id"])] = pid
                self.add_edge(node_id, pid, "HAS_PORT")

    def port_of(self, feature):
        """'battery.powerOut' -> id of the port node of this battery."""
        chain = self.resolve_chain(feature)
        if len(chain) >= 2:
            return self.port_nodes.get((chain[-2]["@id"], chain[-1]["@id"]))
        return None

    def target_of(self, feature):
        """'cubeSat.battery' -> id of the battery node (last element of the chain)."""
        chain = self.resolve_chain(feature)
        return chain[-1]["@id"] if chain else None

    # ------------------------------------------- rule 2: reference -> edge
    def map_reference_edges(self):
        for node_id, node in list(self.nodes.items()):
            element = self.by_id.get(node_id)
            if element is None:
                continue
            for definition in self.refs(element, "definition"):
                self.add_edge(node_id, definition["@id"], "TYPED_BY")
            owner = self.get(element.get("owner"))
            if node["label"] == "Part" and owner and owner["@type"] == "PartUsage":
                self.add_edge(node_id, owner["@id"], "PART_OF")

    # ------------------------------------ rule 3: relationship element -> edge
    def map_relationship_edges(self):
        flow_names = self.rules["port_flow_edges"]
        for e in self.elements:
            t = e["@type"]

            if t == "ConnectionUsage":
                src = self.port_of(self.get(e.get("sourceFeature")))
                tgt = self.port_of(((self.refs(e, "targetFeature")) or [None])[0])
                self.add_edge(src, tgt, "CONNECTED_TO", via=e["@id"])
                # simplified analysis view: part -POWERS-> part
                if src in self.nodes and tgt in self.nodes:
                    kind = flow_names.get(self.nodes[src]["props"]["port_def"])
                    if kind:
                        self.add_edge(src.split("/")[0], tgt.split("/")[0], kind, via=e["@id"])

            elif t == "SatisfyRequirementUsage":
                requirement = self.get(e.get("satisfiedRequirement"))
                subject = self.get(e.get("subjectParameter"))
                for fv in self.refs(subject, "ownedRelationship") if subject else []:
                    if fv["@type"] == "FeatureValue":
                        expr = self.get(fv.get("value"))
                        part = self.target_of(self.get(expr.get("referent")))
                        self.add_edge(part, requirement["@id"], "SATISFIES", via=e["@id"])

            elif t == "RequirementVerificationMembership":
                # verify r1_mass;  ->  a local requirement that references r1_mass
                local_req = (self.refs(e, "ownedRelatedElement") or [None])[0]
                requirement = None
                for rel in self.refs(local_req, "ownedRelationship") if local_req else []:
                    if rel["@type"] == "ReferenceSubsetting":
                        requirement = self.get(rel.get("referencedFeature"))
                # walk up the owners until the verification case definition
                case = self.get(e.get("owner")) or (self.refs(e, "source") or [None])[0]
                while case and case["@type"] != "VerificationCaseDefinition":
                    case = self.get(case.get("owner"))
                if case and requirement:
                    self.add_edge(case["@id"], requirement["@id"], "VERIFIES", via=e["@id"])

            elif t == "AllocationUsage":
                action = self.target_of(self.get(e.get("sourceFeature")))
                part = self.target_of((self.refs(e, "targetFeature") or [None])[0])
                self.add_edge(action, part, "ALLOCATED_TO", via=e["@id"])

            elif t == "TransitionUsage":
                source, target = self.get(e.get("source")), self.get(e.get("target"))
                if target and target["@id"] in self.nodes and (source is None or source["@id"] not in self.nodes):
                    self.nodes[target["@id"]]["props"]["initial"] = True   # entry; then safeMode;
                    continue
                trigger = None
                for accept in self.refs(e, "triggerAction"):
                    payload = self.get(accept.get("payloadParameter"))
                    types = self.refs(payload, "type") if payload else []
                    trigger = self.name(types[0]) if types else None
                if source and target:
                    self.add_edge(source["@id"], target["@id"], "TRANSITION",
                                  via=e["@id"], name=self.name(e), trigger=trigger)

            elif t == "SuccessionAsUsage":
                owner = self.get(e.get("owner"))
                if owner and owner["@type"] == "ActionDefinition":
                    a = self.target_of(self.get(e.get("sourceFeature")))
                    b = self.target_of((self.refs(e, "targetFeature") or [None])[0])
                    self.add_edge(a, b, "NEXT", via=e["@id"])

            elif t == "ExhibitStateUsage":
                for state_def in self.refs(e, "definition"):
                    self.add_edge(e["owner"]["@id"], state_def["@id"], "EXHIBITS", via=e["@id"])

            elif t == "FlowUsage":
                # message: from operator.sendCommand to groundStation.receiveCommand
                ends = []
                for event in self.refs(e, "ownedFeature"):
                    for rel in self.refs(event, "ownedRelationship"):
                        if rel["@type"] == "ReferenceSubsetting":
                            chain = self.resolve_chain(self.get(rel.get("referencedFeature")))
                            if chain:
                                participant = chain[0]
                                ptype = (self.refs(participant, "definition") or [None])[0]
                                ends.append(ptype["@id"] if ptype else None)
                payload = (self.refs(e, "payloadType") or [{}])[0]
                if len(ends) == 2:
                    self.add_edge(ends[0], ends[1], "MESSAGE", via=e["@id"],
                                  name=self.name(e), payload=self.name(payload) if payload else None)

            elif t == "UseCaseDefinition":
                for actor in self.refs(e, "actorParameter"):
                    for actor_def in self.refs(actor, "definition"):
                        self.add_edge(actor_def["@id"], e["@id"], "ACTOR_OF")
                subject = self.get(e.get("subjectParameter"))
                for subject_def in self.refs(subject, "definition") if subject else []:
                    self.add_edge(e["@id"], subject_def["@id"], "HAS_SUBJECT")

    # ------------------------------------------------------------- run
    def run(self):
        self.map_nodes()
        self.map_properties()
        self.map_ports()
        self.map_reference_edges()
        self.map_relationship_edges()
        return {"nodes": list(self.nodes.values()), "edges": self.edges}


def to_cypher(graph):
    """Write the graph as Cypher statements (MERGE = create or update by sysml id)."""
    lines = ["// Generated by mapper/sysml_to_graph.py", "MATCH (n) DETACH DELETE n;"]
    for n in graph["nodes"]:
        lines.append(f"MERGE (n:{n['label']} {{id: {json.dumps(n['id'])}}}) SET n += {props(n['props'])};")
    for e in graph["edges"]:
        lines.append(
            f"MATCH (a {{id: {json.dumps(e['source'])}}}), (b {{id: {json.dumps(e['target'])}}}) "
            f"MERGE (a)-[r:{e['type']}]->(b) SET r += {props(e['props'])};"
        )
    return "\n".join(lines) + "\n"


def props(d):
    items = []
    for k, v in d.items():
        if v is None:
            continue
        items.append(f"`{k}`: {json.dumps(v)}")
    return "{" + ", ".join(items) + "}"


def main():
    with open(ELEMENTS_FILE, encoding="utf-8") as f:
        elements = json.load(f)
    with open(RULES_FILE, "rb") as f:
        rules = tomllib.load(f)

    graph = Mapper(elements, rules).run()

    with open("data/graph.json", "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)
    with open("data/graph.cypher", "w", encoding="utf-8") as f:
        f.write(to_cypher(graph))

    print(f"Input : {len(elements)} SysML elements")
    print(f"Output: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges\n")
    print("Nodes by label:")
    for label, count in collections.Counter(n["label"] for n in graph["nodes"]).most_common():
        print(f"  {count:3d}  {label}")
    print("\nEdges by type:")
    for edge_type, count in collections.Counter(e["type"] for e in graph["edges"]).most_common():
        print(f"  {count:3d}  {edge_type}")
    print("\nSaved: data/graph.json, data/graph.cypher")


if __name__ == "__main__":
    main()
