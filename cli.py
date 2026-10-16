#!/usr/bin/env python3
"""CLI tool for executing YARRRML mappings and validating the output against a Domain Specification.

Runs against the OpenDataGermany APIs (RCK/VER) or fully locally, per `mode` in the config.

Usage:
    rml-cli --config config.yaml --source data.json --mapping mapping.yml
    rml-cli --config config.yaml --source data.json --mapping mapping.yml --output output/
    rml-cli --config config.yaml --source data.json --mapping mapping.yml --skip-validation
    rml-cli --config config.yaml --source data.json --mapping mapping.yml --functions functions.json
"""

import argparse
import json
import os
import sys

from functions import rml


def run(config: dict, source_path: str, mapping_path: str, output_dir: str | None, skip_validation: bool,
        functions_path: str | None = None):
    rml.init(config)

    out_dir = output_dir or config.get("output_dir", "output/")
    os.makedirs(out_dir, exist_ok=True)

    print(f"Loading source data from {source_path}")
    with open(source_path) as f:
        source_data = f.read()

    print(f"Loading mapping from {mapping_path}")
    with open(mapping_path) as f:
        mapping = f.read()

    functions = None
    if functions_path:
        print(f"Loading custom functions from {functions_path}")
        with open(functions_path) as f:
            functions = json.load(f)

    local = rml.mode() == "local"
    print("Running RocketRML locally..." if local else "Running RCK mapping...")
    result = rml.map_json_to_rdf(source_data, mapping, "input", functions)
    if result.startswith("RCK API"):
        print(f"{'MAPPING' if local else 'RCK'} FAILED: {result}")
        sys.exit(1)

    try:
        from rdflib import Graph
        g = Graph()
        g.parse(data=result, format="json-ld")
        print(f"{'MAPPING' if local else 'RCK'} SUCCESS: {len(g)} triples")
    except ImportError:
        print(f"{'MAPPING' if local else 'RCK'} SUCCESS")

    if not skip_validation:
        print("Running limited local SHACL check (not VER)..." if local else "Running VER validation...")
        # /rdf/verify (verify_rdf) reports success for documents the TS import
        # REJECTS. Always use the DS report endpoint here.
        rep = rml.verify_rdf_ds(result)
        if rep.get("__error"):
            print(f"{'LOCAL-SHACL' if local else 'VER'} ERROR: {rep['__error']}")
        elif rep.get("isValid"):
            print("LOCAL-SHACL PASSED (limited check — not a VER result)" if local
                  else "VER PASSED (verify-ds)")
        else:
            n = (rep.get("meta") or {}).get("numTotalErrors")
            print(f"LOCAL-SHACL FAILED: {n} error(s)" if local else f"VER FAILED (verify-ds): {n} error(s)")
            seen = set()
            for r in (rep.get("reports") or []):
                for e in ((r.get("verificationReport") or {}).get("errors") or []):
                    k = (e.get("errorCode"), e.get("name"), str(e.get("value"))[:70],
                         str((e.get("dataPath") or [None])[-1])[:60])
                    if k in seen:
                        continue
                    seen.add(k)
                    print(f"   {k[0]} {k[1]}: {k[2]}  @ {k[3]}")
    else:
        print("Skipping validation")

    stem = os.path.splitext(os.path.basename(mapping_path))[0]
    output_path = os.path.join(out_dir, f"{stem}.output.jsonld")
    with open(output_path, "w") as f:
        f.write(result)
    print(f"Output saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Execute a YARRRML mapping and validate the output against a Domain Specification"
    )
    parser.add_argument("--config", "-c", required=True, help="Path to config YAML file")
    parser.add_argument("--source", "-s", required=True, help="Path to source data file")
    parser.add_argument("--mapping", "-m", required=True, help="Path to YARRRML mapping file")
    parser.add_argument("--output", "-o", help="Output directory (overrides config)")
    parser.add_argument("--skip-validation", action="store_true", help="Skip the validation step")
    parser.add_argument("--functions", "-f",
                        help='JSON file mapping function URIs to JS source, e.g. {"http://onlim.com/func/x": "(([v]) => v)"}')

    args = parser.parse_args()

    import yaml
    with open(args.config) as f:
        config = yaml.safe_load(f)

    run(config, args.source, args.mapping, args.output, args.skip_validation, args.functions)


if __name__ == "__main__":
    main()
