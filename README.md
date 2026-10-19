# rml-mapping-generator

A Claude Code skill (plus a small Python CLI) that **generates, debugs, and validates
YARRRML/RML mappings**: structured source data (JSON/CSV/XML) in, Linked Data conforming to a
semantify.it Domain Specification (schema.org / ODTA) out — through an iterative
map → execute (RCK/RocketRML) → verify (VER `/rdf/verify-ds`) loop.

**No OpenDataGermany API key? Use `mode: local`.** The mapping then runs on open-source
[RocketRML](https://github.com/semantifyit/RocketRML) on your machine, DSs come from public
semantify.it — but **verification is limited**: without VER, the output is only checked with a
standard SHACL validator against the DS's shapes. The skill asks which mode you want at the start
of a run.

| | `api` mode | `local` mode |
|---|---|---|
| Needs | OpenDataGermany / Onlim API keys | Node.js ≥ 18 — no keys |
| Mapping | RCK API | RocketRML + yarrrml-parser, locally (same output as RCK) |
| DSs | DVS + semantify.it lists | public semantify.it |
| Verification | VER `/rdf/verify-ds` (authoritative) | limited: standard SHACL (pyshacl) against the public DS — not VER |

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
- **`functions/rml.py`** — mapping execution, DS fetches and validation, in either mode with the
  same function signatures. In `api` mode validation always uses the strict
  `POST /rdf/verify-ds` report — the weak `/rdf/verify` endpoint passes documents the import
  rejects.
- **`local_engine/`** — `local` mode's mapping runner (Node.js): yarrrml-parser + RocketRML,
  plus the two YARRRML extensions RCK supports and stock yarrrml-parser does not (positional
  function parameters, references with nested parentheses).
- **`functions/local_validate.py`** — `local` mode's limited check: the DS's SHACL shapes run
  with the standard pyshacl validator. It does not reimplement VER.
- **`cli.py`** — run an existing mapping non-interactively:
  `python cli.py --config config.yaml --source data.json --mapping mapping.yml`

## Setup

Requires **Python 3.10+**.

```bash
cp config.yaml.example config.yaml
```

**`api` mode** — fill in the API keys, org IDs and DS list URL in `config.yaml`, then:

```bash
pip install -e .
```

**`local` mode** (no keys) — set `mode: "local"` and a public `ds_list_url` in `config.yaml`, then:

```bash
pip install -e ".[local]"            # adds pyshacl
npm install --prefix local_engine    # RocketRML + yarrrml-parser (needs Node.js >= 18)
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
| `functions/rml.py` | mapping / DS / validation calls, `api` or `local` mode |
| `functions/local_validate.py` | key-free SHACL validation (`local` mode) |
| `local_engine/` | key-free RocketRML runner (`local` mode) |
| `cli.py` | non-interactive mapping runner |
| `config.yaml.example` | config template (copy to `config.yaml`) |
| `output/` | final mappings, field-mapping tables, JSON-LD outputs |
| `rml_test/` | working directory for in-progress runs (gitignored) |
