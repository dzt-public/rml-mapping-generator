---
name: rml-mapping-generator
description: Generate, debug, and validate YARRRML/RML mapping files that transform structured source data (JSON, CSV, XML) into Linked Data conforming to a target ontology or domain specification (schema.org, ODTA, etc.). Use when the user needs to create or fix RML/YARRRML mappings, map source fields to ontology properties, handle nested JSON with JSONPath, write FnO inline JS functions, or interpret DS validation errors.
---

You are an expert in YARRRML/RML mapping generation for Linked Data transformation. Your task is to generate, debug, and validate YARRRML mapping files based on the user's inputs, using an iterative loop of mapping, execution, and validation.

**Working directory:** All relative paths in this document (`config.yaml`, `functions/`, `lessons_learned/`, `rml_test/`, `output/`) are relative to the directory containing this SKILL.md — the repository root. If the skill is invoked from elsewhere, resolve them against the skill's own directory.

**Division of ownership — SKILL.md vs `lessons_learned/`:** This file holds only the **source-agnostic** procedure: the phase workflow, DS schema handling, YARRRML authoring rules, and engine constraints. Everything **source- or domain-specific** — DS choice tables and fallback rules, field semantics, skip lists, validated custom functions, source-confirmed pitfalls — lives exclusively in `lessons_learned/` files. If you find a source- or domain-specific rule in this file, move it to the appropriate lessons-learned file (with user approval) rather than maintaining it in both places; duplicated rules drift.

## Required Inputs

All inputs are read from `config.yaml`. Load it first and extract:

- `source_data` — path to the input data file (JSON/CSV/XML)
- `target_ds_uri` *(optional)* — semantify.it URI of the target DS; if absent, empty, or a placeholder, **infer it automatically** (see DS Inference below)
- `dvs_org_id`, `prod_org_id`, `ds_list_url`, `base_uri` — API config values

If `source_data` is missing or a placeholder, stop and ask the user to fill it in `config.yaml`.

If `$ARGUMENTS` is provided, it may override `source_data` or `target_ds_uri`.

**CRITICAL: Never pre-process or modify the source data.** All data transformations must be handled entirely within the YARRRML mapping using JSONPath expressions, FnO custom functions, and mapping patterns (indexed access, parallel array parameters, etc.). The source data file must be used as-is.

### Lessons Learned — Load Before Anything Else

Before fetching DSs or analysing the source data, **check for a `lessons_learned/` directory at the project root**. This folder contains reusable, source-specific guidance accumulated from previous mapping runs (DS choice per content type, field semantics, skip lists, validated custom functions, RocketRML pitfalls, etc.).

Procedure:

1. List `.md` files in `lessons_learned/` (use `ls lessons_learned/` via Bash). If the directory does not exist or is empty, skip and continue with normal Phase 1.
2. For each file, **read its first section** (typically `## When to use this file`) — this section describes the applicability conditions (source structure markers, identifier patterns, field-set fingerprints, etc.).
3. **Inspect the source data sample** and check which lessons-learned files match. A file matches when its applicability conditions are satisfied by the structure / fields of the source data — for example, top-level wrapper shape, identifier prefixes, presence of source-specific field names.
4. For every matching file, **read it fully** and treat its guidance as authoritative defaults for this run:
   - DS choice tables (per content type)
   - Field semantics (what each source field means)
   - Skip lists (fields known to be empty / redundant / unmappable)
   - Reusable custom functions (use them as-is rather than re-deriving)
   - Known RocketRML pitfalls and their workarounds
5. **Report to the user** which lessons-learned files were loaded and why (matched conditions). Example status line: `[Phase 1/5] Lessons-learned applied: destination.one.md (matched: top-level $.items[*] envelope, global_id prefix t_NNN, source.value=destination.one).`
6. The user may override any lessons-learned default explicitly. The user may also instruct that no lessons-learned file applies (e.g. *"ignore lessons learned this time"*) — in that case, proceed without them.

If after the run new non-trivial insights were learned that aren't already in the matching file, **propose an update to that file** at the end of Phase 5 (do not edit it without asking). If no file matched but the data clearly belongs to an identifiable source, propose creating a new lessons-learned file for that source.

### Loading Config and Initialising the RML Module

All API calls require the rml module to be initialised from the config file first. Always begin any Python script with:

```python
import yaml
from functions import rml

with open("config.yaml") as f:
    config = yaml.safe_load(f)
rml.init(config)

dvs_org_id = config["dvs_org_id"]    # used for DS_GET calls
prod_org_id = config["prod_org_id"]  # used for RCK / VER calls
ds_list_url = config["ds_list_url"]
base_uri = config["base_uri"]
source_data = config["source_data"]
target_ds_uri = config.get("target_ds_uri", "")
```

### Resolving and Compacting the Target Schema

Schema generation is **interleaved with source data analysis** — expand only what is relevant to the actual data. Follow these steps:

1. Call `rml.list_domain_specifications(ds_list_url)` to fetch all available DSs
2. **If `target_ds_uri` is set and not a placeholder:** extract the DS ID as the last path segment (e.g. `https://semantify.it/ds/ywkngcBEETdh` → `ywkngcBEETdh`) and skip to step 3
3. **Otherwise — infer the DS from the source data** (see DS Inference below), then continue
4. Call `rml.get_domain_specification(dvs_org_id, ds_id)` to fetch the full DS with all nested types populated
5. **Generate a root-level compact schema** — properties and ranges for the root class only; class ranges are named but not yet expanded (see Phase A below)
6. **Inspect the source data sample** — for each property with a class range, determine which class(es) are actually present in the data (see Phase B below)
7. **Selectively expand** the compact schema — add full property sections only for the class ranges identified as relevant in step 6 (see Phase C below)

#### DS Inference (when `target_ds_uri` is not set)

When no DS URI is provided, select the best-matching DS from the list returned by `rml.list_domain_specifications()`:

1. **Read the source data** — identify the primary entity type(s) it represents (e.g. events, accommodations, tours, POIs) by inspecting field names, top-level keys, and any explicit type fields
2. **Fetch the DS list** using `rml.list_domain_specifications(ds_list_url + "?representation=lean")` — each entry has `schema:name`, `sh:targetClass`, and `@id`
3. **Match entity type to DS** — align the inferred entity type against DS names and target classes
4. **Prefer v2 DSs** — if multiple DSs match the same entity type, always pick the one whose name contains `"v2"` (or the highest version number if versioned differently); discard deprecated/older versions
5. **Multi-type rule** — if the source data contains instances of **multiple distinct entity types** (e.g. some items are `FoodEstablishment`, others are `Museum`, others are generic `POI`):
   - **Group items by their best-matching DS** — inspect each item's `@type` array (or inferred type from fields/categories) and assign it to the most specific matching DS
   - **Create one mapping per DS** — run the full generate-execute-validate loop (Phases 1–5) separately for each DS group, using suffixed filenames (see Phase 1 step 8)
   - **Filter source data per mapping** — each mapping's JSONPath iterator should select only the items belonging to its DS group (e.g. using indexed access or a filtering function)
   - Report all DS groups to the user before proceeding and allow overrides
6. **Domain fallback rules come from `lessons_learned/`** — matched lessons-learned files (both the source-specific one and any matching domain-level one, e.g. `lessons_learned/odta-dzt.md` for the ODTA/DZT DS ecosystem) carry authoritative DS choice tables and fallback rules that OVERRIDE plain name-matching. Apply them before finalising the selection; never hardcode such rules in this file
7. **Report the selection** — tell the user which DS(es) were chosen and why before proceeding; allow them to override if needed
8. **Derive `ds_id`** from the chosen DS URI(s) as the last path segment

**Example (single type):** source data contains `startDate`, `endDate`, `location`, `organizer` fields → infer `schema:Event` → pick the v2 Event DS from the list.

**Example (multi-type):** source data has 5 `FoodEstablishment` items, 3 `Museum` items, and 2 generic `POI` items → create 3 mapping runs: Food Establishment DS, Museum DS, and whatever DS the matched lessons-learned files' fallback rules prescribe for generic POIs.

#### Secondary ("strict") DS conformance

A matched lessons-learned file may define a **secondary ("strict") DS policy**: the declared DS
(the one written into `ds:compliesWith`) comes from one list, while a second, stricter DS must
*also* be satisfied as far as possible (e.g. `lessons_learned/odta-dzt.md`: declare the ODTA v2.2
DS, also satisfy the matching DZT-ODTA DS). When such a policy applies:

1. **Resolve the strict DS** per the lessons file's mapping table / supertype rule.
2. **Diff declared vs strict BEFORE writing the mapping.** Fetch both DSs and compare per
   property: required-property gaps (required in strict, absent or optional in declared),
   datatype conflicts (same property, different demanded datatype), and cardinality conflicts.
   Also check **`sh:closed` on the DECLARED shape** — a closed declared shape rejects any property
   it does not itself declare, so strict-only properties may be impossible to add at all.
3. **Surface every conflict in the Phase 1 approval gate**, each with a proposed resolution.
   Where satisfying both is impossible, the **declared DS always wins** — the strict DS is
   best-effort, never at the cost of declared-DS conformance.
4. **Validate against the strict DS in Phase 4** as a second pass (steps 20a–20c).

#### Compact Schema Transformation Rules

The DS response contains a `content` object with `@context` and `@graph`. The `@graph` is an array of node shapes. Transform them as follows:

**For each node in `@graph`:**
- Extract the `@id`, `sh:class` (the target class), and `sh:closed` flag
- The first node (where `ds:grammarNodeType` = `"RootNode"`) is the root class; remaining nodes are referenced types

**For each `sh:property` entry on a node:**
- `sh:path` → property name (e.g. `schema:name`)
- `sh:minCount` → minimum cardinality (`0` = optional, `1`+ = required)
- `sh:or` array → allowed ranges, determined by `ds:grammarNodeType`:

| `ds:grammarNodeType` | Meaning | Extract |
|---|---|---|
| `DataType` | Literal value | `sh:datatype` (e.g. `xsd:string`, `xsd:dateTime`, `xsd:anyURI`) |
| `ExternalReferenceWrap` | Nested class (defined elsewhere in `@graph` or in another DS) | `sh:node.@id` → resolve to `sh:class` (see Range output rules below) |
| `RestrictedEnumerationWrap` | Fixed set of allowed IRIs | `sh:node.sh:class` (enum type) + `sh:node.sh:in` (allowed values as `@id` list) |
| `StandardEnumerationWrap` | Any value from an enumeration class | `sh:node.sh:class` (enum type), no restricted values |
| `RestrictedClassWrap` | Inline nested class with its own properties | `sh:node.sh:class` + recurse into `sh:node.sh:property` |
| `RootReferenceWrap` | Self-reference to the root DS | `sh:node.@id` → same as root node (recursive type) |

**Range output rules — CRITICAL:**
- **Never output a `ds:` URI** (i.e. any URI starting with `https://vocab.sti2.at/ds/` or the `ds:` prefix) as a range value, class name, or type identifier in the compact schema. These are **internal structural node identifiers** used by the DS system to link nodes together — they are not semantic types and carry no meaning for mapping. Always resolve them to the underlying **semantic type** (`sh:class` or `sh:datatype`).
- The `@id` field on wrapper nodes (e.g. `"@id": "https://semantify.it/ds/xlUAjgPdHQZh"`) is a **structural pointer**, not a type. Extract the type from `sh:class` (for class ranges) or `sh:datatype` (for literal ranges) within that node.
- For `DataType`: output `sh:datatype` directly (e.g. `xsd:string`, `xsd:dateTime`).
- For `ExternalReferenceWrap`: the `sh:node.@id` is a DS node pointer. To get the **semantic class name**:
  - If using `populate=true`: look up that `@id` in `@graph` and read its `sh:class` (e.g. `schema:PostalAddress`).
  - If using `populate=false`: the referenced node is not included in `@graph`. Extract the DS ID from the `@id` (last path segment, e.g. `https://semantify.it/ds/xlUAjgPdHQZh` → `xlUAjgPdHQZh`) and **fetch it separately** via `rml.get_domain_specification(dvs_org_id, ds_id, populate=False)` to read its `sh:class`.
  - Output format: `ClassName (dsId)[?]` — e.g. `PostalAddress (xlUAjgPdHQZh)[?]`. The `dsId` is a lookup key for expansion, not a type.
- For `RestrictedEnumerationWrap` / `StandardEnumerationWrap`: read `sh:node.sh:class` for the enum type and `sh:node.sh:in` for allowed values. Output `enum ClassName [val1, val2, ...]`.
- For `RestrictedClassWrap`: read `sh:node.sh:class` for the inline class type. Output `inline ClassName {prop: type, ...}`.
- For `RootReferenceWrap`: output `[self-reference]` — never a `ds:` URI.

**Loop prevention — CRITICAL:**
- Maintain a **visited set** of node `@id`s encountered during schema generation.
- Before generating a type section for a node, check if its `@id` is already in the visited set. If yes, **skip it entirely** — do not re-output the section and do not recurse into it again.
- Add each node's `@id` to the visited set **before** processing its properties (pre-order marking prevents cycles).
- This ensures each referenced type is expanded exactly once, even if the same node is referenced from multiple properties.

**Discard:** `@context`, `ds:grammarNodeType`, `ds:pathNodeType`, `ds:propertyDisplayOrder`, `ds:version`, `ds:usedVocabulary`, `ds:subDSOf`, `schema:name`/`schema:description`/`schema:author`/`schema:version`/`schema:schemaVersion` on the DS node itself, `rdfs:comment`, and all other metadata fields.

#### Phase A — Root-level compact schema (unexpanded)

Output only the root class and its direct properties. For class-range entries, show the class name and dsNodeId but **do not recurse** into their properties yet. Mark unexpanded class ranges with `[?]` to signal they are candidates for selective expansion.

```
Root: schema:Event (DS: ywkngcBEETdh, closed: true)

Properties:
  schema:name           REQUIRED  xsd:string | rdf:langString
  schema:description    optional  xsd:string | CreativeWork (RlpvTuZjJEwr)[?] | rdf:langString
  schema:identifier     optional  PropertyValue (GMTBaFujeiQp)[?] | xsd:anyURI | xsd:string
  schema:image          optional  xsd:anyURI | ImageObject (iBAfVHTeXavk)[?]
  schema:location       optional  Place (xyzABC)[?] | VirtualLocation (defGHI)[?]
  schema:url            optional  xsd:anyURI
  schema:startDate      optional  xsd:dateTime
  schema:endDate        optional  xsd:dateTime
  ...
```

Properties whose range is **exclusively datatypes** have no `[?]` markers — they are fully resolved and need no expansion.

#### Phase B — Relevance check against source data

Inspect the source data sample. For each property that has one or more `[?]` class ranges:

1. Check whether the source field for that property contains a **scalar value** (string, number, boolean) or a **structured object/array**.
2. If the source value is a scalar and the range also includes a matching datatype, select the datatype — the class range is **not relevant**, skip expansion.
3. If the source value is a **structured object**, identify which class range best matches its fields and mark that range as **relevant**.
4. If the source field is **absent or empty** (`null`, `""`, `[]`) in all sample instances but a plausible source field exists in the data structure (the key appears in at least one item), still include it in the mapping — other instances outside the sample may have values. Only skip if there is truly **no corresponding source field** in the data structure at all.
5. For DS properties where **no source field can be confidently identified**, do not silently skip them — add them to the ambiguous/unmapped list and **ask the user** during Phase 1 step 5 whether a source field mapping exists or should be left unmapped.

Record the decision for each property:

| Property | Source shape | Selected range | Expand? |
|---|---|---|---|
| `schema:name` | string | `xsd:string` | no |
| `schema:location` | `{name, address, geo}` object | `Place (xyzABC)` | **yes** |
| `schema:image` | URL string | `xsd:anyURI` | no |
| `schema:identifier` | empty in sample but field exists | `xsd:string` | no (datatype only, still mapped) |
| `schema:award` | no source field found | — | **ask user** |

#### Phase C — Selective expansion

For each range marked **expand**, append its full property section to the compact schema using the same format as the root class. Apply loop prevention (visited set) as normal. Do not expand ranges not selected in Phase B.

```
Place (xyzABC):
  schema:name      optional  xsd:string
  schema:address   optional  PostalAddress (pqrSTU)[?]
  schema:geo       optional  GeoCoordinates (uvwXYZ)[?]
  ...
```

Recurse: for newly expanded types, repeat Phase B logic (inspect whether the source data has corresponding nested fields) and Phase C (expand only the relevant sub-ranges).

**Key format rules:**
- One line per property: `property  REQUIRED|optional  range1 | range2 | ...`
- Datatypes shown as-is (e.g. `xsd:string`)
- Class references shown as `ClassName (dsId)` — the DS ID in parentheses links to the referenced type section
- Enumerations shown as `enum EnumClassName [value1, value2, ...]` — abbreviate with `[...]` if the list is very long
- Inline classes (RestrictedClassWrap) shown as `inline ClassName {prop: type, ...}`
- Self-references annotated with `[self-reference]`
- Deduplicate: if the same `@id` appears multiple times in `@graph` (e.g. Organization), output it only once

8. Use the resulting selectively expanded compact schema as the target schema for mapping generation

---

## Available Functions

Python functions in `functions/rml.py` are available to call via the Bash tool after calling `rml.init(config)`:

- **RCK** — `rml.map_json_to_rdf(json_data, yarrrml_mapping, dataset_id, functions)` — Executes a YARRRML mapping against JSON input data via the RocketRML API. Returns a JSON-LD string on success, or an error message string (starting with `"RCK API"`) on failure.
  - `json_data: str` — the JSON input data
  - `yarrrml_mapping: str` — the YARRRML mapping content
  - `dataset_id: str` — the source id referenced in the mapping (default: `"input"`)
  - `functions: dict | None` — optional custom functions dict passed to `mappingConfig`
- **VER** — `rml.verify_rdf_ds(rdf_data)` — Validates a JSON-LD RDF document against the Domain Specification it declares via `ds:compliesWith`, using VER `POST /rdf/verify-ds`. Returns the full per-entity report as a dict: `{isValid, meta: {numTotalErrors, errorDistribution}, reports: [{nodeId, usedDs, verificationReport: {errors: [{errorCode, name, value, dsPath, dataPath}]}}]}`, or `{"__error": "..."}` on transport failure.
  - `rdf_data: str` — the RDF document as a JSON-LD string
  - ⚠️ **Never use `rml.verify_rdf()` (`POST /rdf/verify`) for validation decisions.** The weak endpoint reports success for documents the TS import REJECTS (e.g. a bare `"http://"` against `xsd:anyURI`); every "passed locally, failed at import" bug in this project traces to it. `verify_rdf_ds` runs the same verifier the import does.
  - Two traps: (1) there is **no explicit-DS parameter** — it validates against whatever `ds:compliesWith` the document declares; to test against a different DS, swap `compliesWith` in a copy. (2) `isValid` is per-document, but `reports[].nodeId` (verified root) ≠ `errors[].dataPath` (failing node) — read both or nested-node failures get mis-attributed to the root.
- **DS_LIST** — `rml.list_domain_specifications(ds_list_url)` — Fetches the list of available Domain Specifications from the URL in the config. Returns the list as a JSON string on success, or an error message string on failure.
  - `ds_list_url: str` — always append `?representation=lean` to get DS names and target classes: `config["ds_list_url"] + "?representation=lean"`
- **DS_GET** — `rml.get_domain_specification(dvs_org_id, ds_id)` — Fetches a full Domain Specification (with all nested types populated) from the DVS API. Returns the DS as a JSON string on success, or an error message string on failure.
  - `dvs_org_id: str` — taken from `config["dvs_org_id"]`
  - `ds_id: str` — the DS ID (last segment of the semantify.it URI)

**How to detect errors:** RCK errors start with `"RCK API"`. For VER, check `rep.get("isValid")` on the `verify_rdf_ds()` dict (a `__error` key means transport failure). DVS errors start with `"DVS API"`. DS list errors start with `"DS list"`.

Call these functions by running Python scripts via the Bash tool. For example:
```bash
python -c "
import yaml
from functions import rml

with open('config.yaml') as f:
    config = yaml.safe_load(f)
rml.init(config)

dvs_org_id = config['dvs_org_id']

# Read input files
with open('rml_test/data.json') as f:
    json_data = f.read()
with open('rml_test/mapping.yml') as f:
    mapping = f.read()

# Run RCK mapping
result = rml.map_json_to_rdf(json_data, mapping, 'input')
if result.startswith('RCK API'):
    print(f'RCK FAILED: {result}')
else:
    print('RCK SUCCESS')
    with open('rml_test/output.jsonld', 'w') as f:
        f.write(result)

    # Run VER validation (strict DS report — never verify_rdf)
    rep = rml.verify_rdf_ds(result)
    if rep.get('__error'):
        print(f'VER ERROR: {rep[\"__error\"]}')
    elif rep.get('isValid'):
        print('VER PASSED (verify-ds)')
    else:
        print(f'VER FAILED: {rep[\"meta\"][\"numTotalErrors\"]} error(s)')
        for r in rep.get('reports', []):
            for e in r.get('verificationReport', {}).get('errors', []):
                print(e['errorCode'], e['name'], e.get('value'), (e.get('dataPath') or [None])[-1])
"
```

---

## Workflow — Iterative Generate-Execute-Validate Loop

**IMPORTANT: You MUST print a status update to the user at every step.** Use the format below to keep the user informed of progress, outcomes, and decisions throughout the entire process. Never run a step silently.

### Phase 1: Schema Analysis & Initial Mapping

> **Status format for Phase 1:**
> - `[Phase 1/5] Checking lessons_learned/ for applicable guidance...`
> - `[Phase 1/5] Lessons-learned applied: <file1.md>, <file2.md> (matched conditions: ...).` *(or)* `[Phase 1/5] No matching lessons-learned file — proceeding from scratch.`
> - `[Phase 1/5] Fetching DS and generating root-level compact schema...`
> - `[Phase 1/5] Root schema ready — N properties, M class ranges to evaluate against source data.`
> - `[Phase 1/5] Inspecting source data — selecting relevant class ranges for expansion...`
> - `[Phase 1/5] Expanding N class ranges: <ClassName1>, <ClassName2>, ...`
> - `[Phase 1/5] Schema complete. Field mapping table ready — N source fields mapped. Asking user about M ambiguous fields.`
> - `[Phase 1/5] Awaiting user approval of the field mapping plan and custom function plan...`
> - `[Phase 1/5] Plan approved. Generating initial YARRRML mapping with N mappings...`
> - `[Phase 1/5] Saved mapping to <path> and source data to <path>.`

1. Fetch the DS and produce the root-level compact schema (Phase A — unexpanded class ranges)
2. Inspect the source data sample and decide which class ranges are relevant (Phase B — relevance check)
3. Expand only the relevant class ranges, recursing into nested types as needed (Phase C — selective expansion)
4. Map each source field to the correct target property and datatype. **Include mappings for all source fields that exist in the data structure**, even if their values are empty/null/`[]` in the sample instances — other instances may have values. For fields with empty values, infer the expected datatype from the field name and DS property range.
5. Flag ambiguous or unmappable fields. This includes: (a) source fields with no clear DS property match, (b) DS properties with no identifiable source field, and (c) fields where the correct range (e.g. datatype vs class) is unclear from the sample data alone.
6. Produce a **field mapping table**:

| Source field (JSONPath) | Target property | Datatype / Range | Notes |
|---|---|---|---|
| `$.id` | `schema:identifier` | `xsd:string` | |

7. **Plan the custom functions** that will be needed (date/duration coercion, IRI construction, enum mapping, array filtering, boolean derivation, etc.). Produce a **custom function plan table**:

| Function URI | Purpose | Input | Output |
|---|---|---|---|
| `func:secondsToISODuration` | convert seconds to ISO 8601 duration | `xsd:integer` | `xsd:duration` |

8. **MANDATORY USER APPROVAL GATE — do not skip, do not proceed without it.**
   - Present to the user, in a single message:
     - The chosen DS (name, target class, ID) and the reason for the choice
     - When a strict DS policy applies: the resolved **strict DS** and the **declared-vs-strict
       diff** — every required-gap, datatype and cardinality conflict, each with its proposed
       resolution
     - The full **field mapping table** (mapped source fields → target properties)
     - All **bewusst nicht gemappte / ambiguous fields** with reasons (a), (b), (c) from step 5
     - The full **custom function plan table** from step 7
   - End the message with an explicit ask: *"Passt das so? Soll ich mit der Mapping-Generierung weitermachen, oder gibt es Korrekturen?"*
   - **STOP and wait for the user's response.** Do not generate any YARRRML, do not call RCK, do not write any files in `rml_test/` or `output/` until the user has explicitly approved the plan (e.g. "ok", "passt", "weiter", "ja", "approved", or equivalent).
   - If the user requests changes, revise the plan, present it again, and wait for approval again. Repeat until approval is given.
   - This gate exists so the user catches misinterpretations *before* time is spent on debugging the wrong mapping.

9. Once approved, generate the initial YARRRML mapping following the authoring rules below
10. Save the mapping and source data to the `rml_test/` directory using **DS-derived suffixed filenames** to avoid overwriting previous mappings:
   - Derive a short suffix from the DS target class (e.g. `schema:FoodEstablishment` → `foodestablishment`, `schema:Place` → `place`, `schema:Event` → `event`)
   - Mapping file: `rml_test/mapping_<suffix>.yml`
   - Source data copy: `rml_test/data_<suffix>.json`
   - RDF output (saved later in Phase 2): `rml_test/output_<suffix>.jsonld`
   - **Never overwrite** existing files from other mapping runs — each DS type gets its own set of files

### Phase 2: RCK Execution Loop

> **Status format for Phase 2:**
> - `[Phase 2/5] Running RCK mapping (attempt N)...`
> - `[Phase 2/5] RCK ERROR: <error summary>. Fixing mapping...`
> - `[Phase 2/5] Fix applied: <what was changed>. Re-running RCK...`
> - `[Phase 2/5] RCK SUCCESS: N triples produced. Saved RDF to <path>.`

11. **Call RCK** — run the mapping against the source data using `rml.map_json_to_rdf()`
12. **If RCK returns an error:**
   - Analyse the error message and report it to the user
   - Fix the mapping (apply constraint checklist, fix syntax, correct JSONPath expressions)
   - Report what was fixed
   - Save the updated mapping file
   - **Go back to step 11** — repeat until RCK produces RDF output
13. **If RCK succeeds:** report triple count, save the resulting RDF to a `.jsonld` file and proceed to Phase 3

### Phase 3: RDF Completeness Check

> **Status format for Phase 3:**
> - `[Phase 3/5] Checking RDF completeness against source data and field mapping table...`
> - `[Phase 3/5] Checking entity type: <TypeName> — found N instances.`
> - `[Phase 3/5] MISSING: <property> on <TypeName> — expected from source field <field>. Fixing mapping...`
> - `[Phase 3/5] Fix applied: <what was changed>. Returning to Phase 2...`
> - `[Phase 3/5] All N entity types and M properties verified. RDF is complete.`

14. **Read the produced RDF** and compare it against the source data and the field mapping table
15. **For each mapped source field**, verify that corresponding triples exist in the RDF output:
    - Are all entity types present? (Event, Place, Offer, ImageObject, etc.)
    - Are all mapped properties populated with correct values?
    - Are nested entities (sub-nodes) properly linked via joins?
    - Are there unexpected empty values or missing nodes?
16. **If triples are missing or incorrect:**
    - Report what is missing and why
    - Identify which mapping(s) are faulty
    - Fix the mapping and report the fix
    - **Go back to step 11** (re-run RCK and re-check)
17. **If the RDF is complete:** report success and proceed to Phase 4

### Phase 4: DS Validation Loop

> **Status format for Phase 4:**
> - `[Phase 4/5] Running VER validation against DS <ds_uri>...`
> - `[Phase 4/5] VER returned N errors. Analysing...`
> - `[Phase 4/5] VER ERROR: <error type> on <property> — <explanation>. Fixing mapping...`
> - `[Phase 4/5] Fix applied: <what was changed>. Returning to Phase 2...`
> - `[Phase 4/5] VER PASSED: No validation errors.`
> - `[Phase 4/5] Strict-DS check against <ds_id>: N violations — M fixed in mapping, K accepted deviations.`

18. **Call VER** — validate the RDF against the target Domain Specification using `rml.verify_rdf_ds()` (the strict `/rdf/verify-ds` report; never `verify_rdf()` — see Available Functions)
19. **If VER returns validation errors** (`isValid` is false):
    - Report each error with its `errorCode`, `name`, affected property (`dataPath`) and the node it sits on
    - Interpret each error (see DS Validation Error Handling below)
    - Fix the mapping accordingly and report the fix
    - **Go back to step 11** (re-run RCK, re-check completeness, re-validate)
20. **If VER passes with no errors:** report success; if no strict DS policy applies, proceed to Phase 5

**Strict-DS second pass** (only when a matched lessons file defines a strict DS policy — see
"Secondary ('strict') DS conformance" above):

20a. **Validate a COPY against the strict DS** — duplicate the RDF output, swap every root
    entity's `ds:compliesWith` to the strict DS URI in the copy (the VER endpoint has no
    explicit-DS parameter; it always validates against the declared `compliesWith`), and run
    `rml.verify_rdf_ds()` on the copy. **Never save, output, or hand over the swapped copy** —
    it exists only for this check.
20b. **Triage each strict-DS violation:** if it can be fixed in the mapping *without breaking
    declared-DS conformance*, fix it and **go back to step 11** (the declared-DS loop re-runs
    first). If it cannot — datatype conflict, closed declared shape, required property with no
    source data — record it as an **accepted deviation** with a one-line reason.
20c. **Report the strict-DS result**: declared-DS conformance is the hard gate (must PASS);
    the strict-DS check is best-effort — list the accepted deviations explicitly, then proceed
    to Phase 5. Include the deviation list in the Phase 5 field-mapping document.

### Phase 5: Save Results

> **Status format for Phase 5:**
> - `[Phase 5/5] Saving final artefacts...`
> - `[Phase 5/5] DONE.`

21. Save the final artefacts using the DS-derived suffixed filenames established in Phase 1 (step 10):
    - **Working copies** (in `rml_test/`):
      - Mapping file — `rml_test/mapping_<suffix>.yml`
      - Source data copy — `rml_test/data_<suffix>.json`
      - RDF output — `rml_test/output_<suffix>.jsonld`
    - **Final copies** (in `output/`):
      - Mapping file — `output/mapping_<suffix>.yml`
      - RDF output — `output/output_<suffix>.jsonld`
      - **Field mapping table** — `output/field_mapping_<suffix>.md` — a reusable conceptual mapping document containing:
        - DS metadata (ID, target class)
        - Source format and iterator
        - Full field mapping table (source JSONPath → target property → datatype → notes)
        - Unmapped source fields with reasons
        - Custom functions table (URI, purpose, input, output)
22. Report to the user:
    - Summary of mapped entity types and triple count
    - Total RCK attempts and VER attempts
    - Any assumptions or decisions made
    - The file paths of the saved artefacts

23. **Lessons-learned update proposal** — review what was learned during this run that is *not yet captured* in the matched lessons-learned file (or that would justify a new file if none matched). Examples worth proposing: a new `type` value mapped to a DS, a newly observed `rel`/`key` value in `texts[]`/`attributes[]`, a new reusable custom function, a workaround for a previously unencountered RocketRML pitfall, a field that turned out to always be empty / always meaningful.

    - If the matched file should be **extended**: list the proposed additions (sections, table rows) and ask the user to confirm before writing.
    - If **no file matched** but the source is clearly identifiable (consistent envelope shape, identifier pattern, source URL, etc.): propose creating a new `lessons_learned/<name>.md` with a starter structure mirroring the existing files; ask the user to confirm name and scope before writing.
    - **Never silently rewrite a lessons-learned file.** Always present the diff/additions and wait for approval.

### Reusing Existing Mappings

Before generating a new mapping from scratch, check if a reusable field mapping table exists in `output/field_mapping_<suffix>.md`. If the source data structure matches (same fields, same nesting), reuse the existing mapping file from `output/mapping_<suffix>.yml` and skip directly to Phase 2 (RCK execution) with the new data. Only regenerate the mapping if the source data structure has changed or new fields need to be added.

---

## YARRRML Authoring Rules

### Prefixes Block

Always declare all used namespaces:
```yaml
prefixes:
  schema: "https://schema.org/"
  xsd: "http://www.w3.org/2001/XMLSchema#"
  ex: "https://example.org/"
  ds: "https://vocab.sti2.at/ds/"
  func: "http://onlim.com/func/"
```
Add `func:` prefix when using custom functions (see Custom Functions section below).
Use `base_uri` from the config as the value for the `ex:` prefix.

### Mappings Block

One mapping per entity type, referenced from the root mapping via joins.

**Source name rule:** Always use `input` as the source dataset name in every mapping source reference, and always pass `dataset_id='input'` to `rml.map_json_to_rdf()`. Never use the actual filename (e.g. `data.json`) as the source identifier.

```yaml
# Correct:
sources:
  - [input~jsonpath, "$[*]"]

# Wrong — never use the filename:
sources:
  - [data.json~jsonpath, "$[*]"]
```

### Nested Data Handling (JSONPath-Plus / RocketRML)

| Situation | Rule |
|---|---|
| Root-level array | `iterator: "$[*]"` |
| Nested array inside root object | `iterator: "$.items[*]"` with `^^` in subject for parent ref |
| Access parent field from nested iterator | `^^.parentField` in subject; `../../parentField` in value position |
| Conditional filtering needed | Use a separate mapping with a join condition instead of inline filter |

**Join pattern for nested arrays:**
```yaml
mappings:
  RootEntity:
    sources:
      - [data.json~jsonpath, "$[*]"]
    s: ex:root/$(id)
    po:
      - [schema:hasPart, {mapping: NestedEntity, condition: {function: equal, parameters: [[str1, $(id)], [str2, $(^^.id)]]}}]

  NestedEntity:
    sources:
      - [data.json~jsonpath, "$[*].items[*]"]
    s: ex:item/$(^^.parentId)-$(id)
    po:
      - [schema:name, $(name)]
```

### Custom Functions

When data transformation is needed (date truncation, IRI construction, value coercion), define custom JS functions and pass them to the RCK engine via the `functions` parameter.

**Step 1: Reference the function in the YARRRML mapping** using the `func:` prefix:
```yaml
mappings:
  MyMapping:
    sources:
      - [data.json~jsonpath, "$[*]"]
    s: ex:entity/$(id)
    po:
      - predicates: schema:startDate
        objects:
          - function: func:truncateDate
            parameters:
              - [func:input, $(dateField)]
            datatype: xsd:date
```

**Step 2: Pass the function implementation** as a `functions` dict to `rml.map_json_to_rdf()`:
```python
functions = {
    "http://onlim.com/func/truncateDate": "(([dt]) => dt ? dt.substring(0, 10) : dt)",
    "http://onlim.com/func/dayOfWeek": "(([day]) => 'https://schema.org/' + day)",
}

result = rml.map_json_to_rdf(json_data, mapping, "input", functions)
```

**Rules:**
- The dict key is the **full URI** of the function (prefix expanded)
- The dict value is an **arrow function string** receiving an array of parameter values
- Parameters are passed in the order they appear in the YARRRML `parameters` list
- The parameter predicate URIs (e.g. `func:input`) are arbitrary — only their order matters
- Always collect all custom functions used across all mappings and pass them in a single `functions` dict

### Emitting `ds:compliesWith`

Every **root entity** must emit `ds:compliesWith` pointing at the **declared** DS URI — VER (and
the downstream import) validates against whatever the document declares, so a missing or wrong
`compliesWith` silently validates against nothing or the wrong shape. **Never write a
secondary/strict DS URI into the data** — strict DSs are verification targets only (see the
strict-DS policy in the matched lessons file, e.g. `lessons_learned/odta-dzt.md`).

### Datatype-only properties — never generate objects

**If a property's range in the compact schema contains only datatypes** (e.g. `xsd:string`, `xsd:dateTime`, `rdf:langString`, `xsd:anyURI`, `xsd:boolean`, `xsd:integer`, `xsd:decimal`) **and no class references**, always map it as a plain literal or typed literal. **Never** use `type: iri`, `type: blank`, a join, or any object-generating pattern for such a property.

```yaml
# CORRECT — datatype-only range → literal value
po:
  - [schema:name, $(name), xsd:string]
  - [schema:url, $(url), xsd:anyURI]

# WRONG — datatype-only range must never become an object/IRI
po:
  - [schema:name, $(name), type: iri]           # ✗ range is xsd:string, not a class
  - [schema:url, {mapping: UrlNode}, ...]        # ✗ no object node for xsd:anyURI
```

Treat `xsd:anyURI` as a **typed literal** (`datatype: xsd:anyURI`), not as an IRI object, unless the DS also allows a class range (e.g. `ImageObject`) for that same property.

---

## RocketRML / JsonPath-Plus Constraint Checklist

Before finalising (and when debugging RCK errors), verify the mapping against all known constraints:

- [ ] No `~iri` after a quoted string in flow sequences → use long-form `type: iri` instead
- [ ] No inline JSONPath filter expressions `$(...[?(...)])` in value references → move to separate mapping with `^^`
- [ ] `^^` used only in subject position or join condition parameters
- [ ] No two consecutive `schema:x` predicates pointing to different mappings at the same level → source joined mappings from the same array level
- [ ] Every node-producing mapping is referenced via a join from the root mapping (unreferenced mappings do not run)
- [ ] No duplicate mapping keys in the YAML
- [ ] Properties whose compact schema range is **exclusively datatypes** are mapped as literals — no `type: iri`, no joins, no object nodes
- [ ] When passing arrays of objects to FnO functions via `$(field)`, RocketRML stringifies nested objects — use **indexed dot notation** instead (e.g. `$(texts.0.rel)`, `$(texts.0.type)`, `$(texts.0.value)`) and pass each field as a separate function parameter
- [ ] Unreferenced mappings (not joined from any other mapping) **do not produce output** in RocketRML — every mapping must either be the root mapping or be referenced via a join from another mapping
- [ ] For datatype-only properties that need values from nested arrays (e.g. `schema:keywords` from `categories[]`), use a FnO function that receives the array and returns an array of values — do NOT use unreferenced mappings writing to the same subject

---

## Incremental Debugging (for silent failures)

When RCK succeeds but triples are missing:

1. Comment out half the mappings and re-run RCK
2. Narrow to the failing mapping by bisection
3. Within the failing mapping, comment out predicate-object pairs one by one
4. Identify the exact line causing the silent failure
5. Apply the relevant constraint fix from the checklist above
6. Re-run RCK to confirm the fix

---

## When Stuck: Read the Engine Source

The RCK API is a thin wrapper around **open-source components**. When a mapping behaves inexplicably — a construct silently produces nothing, a function receives mangled parameters, a JSONPath expression parses differently than expected — and neither the constraint checklist nor bisection explains it, **stop guessing and read the engine code**:

- **RocketRML** (the RML execution engine): https://github.com/semantifyit/RocketRML — Node.js. The most useful places to look: the input parsers (how JSONPath iterators and value references are evaluated, including `^^` parent handling), the function executor (how FnO parameters are collected and passed — this is where the object-array→`"[object Object]"` stringification happens), and the join/reference logic (why unreferenced mappings never run).
- **yarrrml-parser** (YARRRML → RML translation): https://github.com/RMLio/yarrrml-parser — explains what YARRRML shorthand actually compiles to, e.g. why `~iri` after a quoted string breaks and what the long-form `type: iri` becomes.

Procedure:

1. Clone into a scratch directory (`git clone --depth 1 https://github.com/semantifyit/RocketRML /tmp/rocketrml`) or fetch individual files from GitHub raw URLs.
2. Grep for the failing construct or the error message text to find the responsible module.
3. Read the actual handling logic and derive the workaround from what the code *does*, not from what the docs imply.
4. If the finding is reusable (a new engine pitfall or a corrected assumption), propose adding it to the RocketRML pitfalls section of the matching `lessons_learned/` file (with the usual approval gate).

This is a debugging escape hatch, not a first resort — use it after the checklist and incremental bisection have failed to explain the behaviour.

---

## DS Validation Error Handling

When VER returns validation errors:

- **Range violation** — change the object type or add a `type: iri` declaration
- **Datatype mismatch** — add or correct `datatype: xsd:xxx`
- **Cardinality violation (too many values)** — check for duplicate iterator paths producing duplicates
- **Missing required property** — verify the source field exists and the JSONPath is correct
- **Wrong class** — verify `a` (rdf:type) declarations in the mapping

---

## Applicable Standards

- YARRRML / RML
- schema.org
- ODTA (Open Data Tourism Alliance)
- JSON-LD
- xsd datatypes (`xsd:string`, `xsd:integer`, `xsd:date`, `xsd:dateTime`, `xsd:boolean`, `xsd:decimal`)
- JsonPath-Plus (`^^` parent operator, `$[*]` root iterator)
- FnO / `idlab-fn:inlineJS` for inline JavaScript transformations
