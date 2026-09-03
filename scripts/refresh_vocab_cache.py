"""Rebuild the cached schema.org + ODTA class hierarchy.

The mappings need a transitive subClassOf closure to decide which of a record's
source @type values may be emitted as rdf:type (see lessons_learned/thh-tours.md).
Pulling ~1.3 MB of vocabulary on every run is wasteful and makes the mapping depend
on a live service, so the closure is cached here and refreshed on demand.

  python3 scripts/refresh_vocab_cache.py          # refresh if older than 30 days
  python3 scripts/refresh_vocab_cache.py --force  # always refresh

Cache: vocab_cache/class_hierarchy.json  (parents/children + provenance + fetchedAt)
"""
import json, os, sys, collections, urllib.request, datetime

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HERE, "vocab_cache", "class_hierarchy.json")
MAX_AGE_DAYS = 30
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

SOURCES = {
    "schema.org": "https://semantify.it/voc/schema-29.3",
    "odta":       "https://semantify.it/voc/unGdYZATQmET?specification-version=2",
}
KEEP_PREFIXES = ("schema:", "odta:")


def fetch(url):
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def build():
    parents = collections.defaultdict(set)
    stats = {}
    for name, url in SOURCES.items():
        doc = fetch(url)
        graph = doc.get("@graph") or []
        n_edges = 0
        for node in graph:
            cid = str(node.get("@id", ""))
            if not cid.startswith(KEEP_PREFIXES):
                continue
            sc = node.get("rdfs:subClassOf")
            for p in (sc if isinstance(sc, list) else [sc] if sc else []):
                pid = p.get("@id") if isinstance(p, dict) else p
                if pid and str(pid).startswith(KEEP_PREFIXES):
                    parents[cid].add(str(pid)); n_edges += 1
        stats[name] = {"url": url, "graphNodes": len(graph), "subClassOfEdges": n_edges}
        print(f"  {name:<11} {len(graph):>5} nodes, {n_edges:>5} subClassOf edges")
    children = collections.defaultdict(set)
    for c, ps in parents.items():
        for p in ps:
            children[p].add(c)
    return parents, children, stats


def save(parents, children, stats):
    payload = {
        "fetchedAt": datetime.datetime.now(datetime.timezone.utc)
                        .replace(microsecond=0).isoformat(),
        "maxAgeDays": MAX_AGE_DAYS,
        "sources": stats,
        "keepPrefixes": list(KEEP_PREFIXES),
        "parents": {k: sorted(v) for k, v in sorted(parents.items())},
        "children": {k: sorted(v) for k, v in sorted(children.items())},
    }
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"\ncache -> {CACHE}")
    print(f"  {len(parents)} classes with parents, {len(children)} with children")


def age_days():
    if not os.path.exists(CACHE):
        return None
    d = json.load(open(CACHE))
    then = datetime.datetime.fromisoformat(d["fetchedAt"])
    return (datetime.datetime.now(datetime.timezone.utc) - then).days


if __name__ == "__main__":
    force = "--force" in sys.argv
    a = age_days()
    if a is not None and not force and a < MAX_AGE_DAYS:
        print(f"cache is {a} day(s) old (limit {MAX_AGE_DAYS}) — nothing to do; use --force to refresh")
        sys.exit(0)
    print("refreshing vocabulary cache" + (f" (cache {a} days old)" if a is not None else " (no cache yet)"))
    save(*build())
