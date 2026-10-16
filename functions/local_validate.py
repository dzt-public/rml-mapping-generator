"""Key-free, LIMITED DS validation: the DS's SHACL shapes run through a standard SHACL validator.

A Domain Specification is a SHACL shapes graph (plus ds:* metadata) and semantify.it serves DSs
publicly, so without a VER API key the best available check is: fetch the DS, use it as the
shapes graph, and validate with pyshacl. This is NOT VER and does not try to be:

- VER has its own verification rules on top of SHACL; documents can pass here and fail VER,
  and vice versa (e.g. VER accepts a plain JSON string "https://..." where xsd:anyURI is
  demanded and IRI references to nodes the document does not describe — plain SHACL reports
  both as errors).
- Error codes are SHACL constraint components, not VER's numeric codes.

The only changes to the DS shapes are the ones needed to run them as standard SHACL:
- targets: the nodes that declare the DS via ds:compliesWith (instead of sh:targetClass);
- closed shapes ignore rdf:type and ds:compliesWith;
- duplicate sh:in lists (the populated DS can carry an enum node twice) are merged, because
  SHACL allows only one per shape.
Subclass checks (sh:class) use the schema.org + ODTA class hierarchy from vocab_cache/ as the
ontology graph (built on first use by scripts/refresh_vocab_cache.py, public sources).

The return value has the same shape as `rml.verify_rdf_ds()` so the workflow loop is uniform.
"""

import json
import os
import subprocess
import sys

import requests
from rdflib import RDF, RDFS, BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection

SH = Namespace("http://www.w3.org/ns/shacl#")
DS = Namespace("https://vocab.sti2.at/ds/")
PREFIXES = {"schema:": "https://schema.org/", "odta:": "https://odta.io/voc/"}

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VOCAB_CACHE = os.path.join(_HERE, "vocab_cache", "class_hierarchy.json")
_DS_CACHE: dict[str, Graph] = {}


def fetch_ds(ds_uri: str) -> Graph:
    """Fetch a DS (all nested nodes populated) from the public semantify.it endpoint."""
    if ds_uri not in _DS_CACHE:
        resp = requests.get(ds_uri, params={"populate": "true"},
                            headers={"accept": "application/json"}, timeout=60)
        resp.raise_for_status()
        _DS_CACHE[ds_uri] = Graph().parse(data=resp.text, format="json-ld")
    return _DS_CACHE[ds_uri]


def _expand(curie: str) -> URIRef | None:
    for p, ns in PREFIXES.items():
        if curie.startswith(p):
            return URIRef(ns + curie[len(p):])
    return None


def _class_hierarchy() -> Graph:
    g = Graph()
    if not os.path.exists(_VOCAB_CACHE):
        script = os.path.join(_HERE, "scripts", "refresh_vocab_cache.py")
        subprocess.run([sys.executable, script], capture_output=True, timeout=300)
    if not os.path.exists(_VOCAB_CACHE):
        return g
    with open(_VOCAB_CACHE) as f:
        parents = json.load(f).get("parents", {})
    for child, ps in parents.items():
        c = _expand(child)
        for p in ps:
            pp = _expand(p)
            if c is not None and pp is not None:
                g.add((c, RDFS.subClassOf, pp))
    return g


def _shapes_for(ds_uri: str, focus_nodes: list) -> Graph:
    shapes = Graph()
    for t in fetch_ds(ds_uri):
        shapes.add(t)
    root = URIRef(ds_uri)
    shapes.remove((root, SH.targetClass, None))
    for n in focus_nodes:
        shapes.add((root, SH.targetNode, n))
    for node in {n for n in shapes.subjects(SH["in"], None)}:
        lists = list(shapes.objects(node, SH["in"]))
        if len(lists) < 2:
            continue
        items = []
        for lst in lists:
            items += [i for i in Collection(shapes, lst) if i not in items]
            shapes.remove((node, SH["in"], lst))
        merged = BNode()
        Collection(shapes, merged, items)
        shapes.add((node, SH["in"], merged))
    for shape in set(shapes.subjects(SH.closed, Literal(True))):
        lst = BNode()
        Collection(shapes, lst, [RDF.type, DS.compliesWith])
        shapes.add((shape, SH.ignoredProperties, lst))
    return shapes


def verify_rdf_ds_local(rdf_data: str) -> dict:
    """Validate a JSON-LD document against the DS(s) it declares via ds:compliesWith.

    Returns {isValid, engine: "local-shacl", meta: {numTotalErrors, ...},
    reports: [{nodeId, usedDs, verificationReport: {errors}}]} — or {"__error": "..."}.
    """
    try:
        from pyshacl import validate
    except ImportError:
        return {"__error": "pyshacl not installed — pip install pyshacl"}

    try:
        data = Graph().parse(data=rdf_data, format="json-ld")
    except Exception as e:  # noqa: BLE001 — surface any parse failure to the loop
        return {"__error": f"could not parse JSON-LD: {e}"}

    by_ds: dict[str, list] = {}
    for node, ds in data.subject_objects(DS.compliesWith):
        by_ds.setdefault(str(ds), []).append(node)
    if not by_ds:
        return {"__error": "no ds:compliesWith in the document — nothing to validate against"}

    ont = _class_hierarchy()
    reports, total = [], 0
    for ds_uri, nodes in by_ds.items():
        try:
            shapes = _shapes_for(ds_uri, nodes)
        except requests.RequestException as e:
            return {"__error": f"could not fetch DS {ds_uri}: {e}"}
        _, results, _ = validate(data, shacl_graph=shapes, ont_graph=ont,
                                 inference="none", allow_warnings=True)
        per_node: dict = {n: [] for n in nodes}
        for r in results.subjects(RDF.type, SH.ValidationResult):
            focus = results.value(r, SH.focusNode)
            comp = results.value(r, SH.sourceConstraintComponent)
            path = results.value(r, SH.resultPath)
            value = results.value(r, SH.value)
            err = {
                "errorCode": str(comp).rsplit("#", 1)[-1] if comp else None,
                "name": str(results.value(r, SH.resultMessage) or ""),
                "value": str(value) if value is not None else None,
                "dsPath": str(results.value(r, SH.sourceShape)),
                "dataPath": [str(focus), str(path) if path is not None else None],
            }
            per_node[focus if focus in per_node else nodes[0]].append(err)
        for n, errs in per_node.items():
            total += len(errs)
            reports.append({"nodeId": str(n), "usedDs": ds_uri,
                            "verificationReport": {"isValid": not errs, "errors": errs}})

    return {
        "isValid": total == 0,
        "engine": "local-shacl",
        "meta": {"numEntities": len(reports), "numTotalErrors": total},
        "reports": reports,
    }
