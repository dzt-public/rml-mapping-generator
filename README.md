# rml-mapping-generator

A Claude Code skill (plus a small Python CLI) that **generates, debugs, and validates
YARRRML/RML mappings**: structured source data (JSON/CSV/XML) in, Linked Data conforming to a
semantify.it Domain Specification (schema.org / ODTA) out — through an iterative
map → execute (RCK/RocketRML) → verify (VER `/rdf/verify-ds`) loop.

## How it works

- **`SKILL.md`** — the single source of truth for the workflow: DS resolution and selective
  schema expansion, a user-approved field-mapping plan, YARRRML authoring rules, the
  RocketRML constraint checklist, and the validation loop. Only **source-agnostic** rules
  live here.
- **`lessons_learned/`** — reusable, per-source and per-domain guidance accumulated from
  previous runs (DS choice tables, field semantics, skip lists, validated custom functions,
  engine pitfalls). The skill loads matching files first and treats them as authoritative;
  after a run it proposes updates. **Anything source- or domain-specific belongs here, never
  in `SKILL.md`.**
  - `odta-dzt.md` — domain-level rules for the ODTA/DZT DS ecosystem (any source)
  - `destination.one.md` — source-specific field semantics
- **`functions/rml.py`** — the API client (RCK mapping execution, DVS domain-specification
  fetches, VER validation). Validation always uses the strict `POST /rdf/verify-ds` report —
  the weak `/rdf/verify` endpoint passes documents the import rejects.
- **`cli.py`** — run an existing mapping non-interactively:
  `python cli.py --config config.yaml --source data.json --mapping mapping.yml`

## Setup

Requires **Python 3.10+** with `pyyaml`, `requests` (and optionally `rdflib` for triple counts).

```bash
cp config.yaml.example config.yaml   # then fill in API keys, org IDs, DS list URL
```

`config.yaml` is gitignored — credentials never enter the repo.

## Using the skill

**As a project:** open this repository in Claude Code and run `/yarrrml-mapping` (a thin
wrapper around `SKILL.md`), or just ask for a mapping — the skill drives the whole loop,
including a mandatory approval gate on the field-mapping plan before any generation.

**As an installed skill:** clone the repository into your skills directory:

```bash
git clone https://github.com/dzt-public/rml-mapping-generator \
  ~/.claude/skills/rml-mapping-generator
```

All paths in `SKILL.md` are relative to the directory containing it.

## Layout

| Path | Purpose |
|---|---|
| `SKILL.md` | the workflow (source-agnostic rules only) |
| `lessons_learned/` | per-source / per-domain guidance, loaded by applicability fingerprint |
| `functions/rml.py` | RCK / DVS / VER API client |
| `cli.py` | non-interactive mapping runner |
| `config.yaml.example` | config template (copy to `config.yaml`) |
| `output/` | final mappings, field-mapping tables, JSON-LD outputs |
| `rml_test/` | working directory for in-progress runs (gitignored) |
