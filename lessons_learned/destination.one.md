# Lessons Learned — destination.one

## When to use this file

Apply this guidance when the source data:

- Has the top-level structure `{ "status": "...", "count": N, "items": [...], ... }`
- Items contain a `global_id` field shaped like `t_NNNNNNN`, `e_NNN`, `p_NNN` (prefix + numeric ID)
- Items have a `type` field with values like `"Tour"`, `"Event"`, `"POI"`, `"Hotel"`, `"Article"`, etc.
- Contain a `source` field referencing `destination.one`
- Use the standard destination.one field set (`texts[]`, `media_objects[]`, `addresses[]`, `attributes[]`, `ratings[]`, `numbers[]`, `categories[]`, `features[]`, `keywords[]`, `geo`, `subitems[]`, `hyperObjects[]`)

If the data structure matches but the entity type differs (e.g. `"Hotel"`, `"POI"`), still apply the field-semantic rules below; pick a different DS based on `type`.

## Top-level structure

- **Always** iterate items via `$.items[*]` — the root is an envelope object, not the array.
- Useful counts: `$.count`, `$.overallcount`. Skip `$.channels` and `$.facetGroups` (paging metadata).

## DS choice by `type`

| destination.one `type` | Recommended DS | Notes |
|---|---|---|
| `"Tour"` | **Trail v2** (`odta:Trail`, `hSsrCTQowvYH`) | tracks, hikes, cycling routes |
| `"Event"` | **Event v2** (`schema:Event`, `ywkngcBEETdh`) | |
| `"POI"` (generic, mixed categories) | **Place v2** (`schema:Place`, `gGDiyXWKpGpu`) | per the POI fallback rule in `odta-dzt.md` |
| `"Hotel"` / lodging | **Lodging Business v2** (`schema:LodgingBusiness`, `xVTuYwJrJrfq`) | |
| `"Restaurant"` / dining | **Food Establishment** (`schema:FoodEstablishment`, `zmoYZEMoSAKS`) | |
| `"Museum"` | **Museum** (`schema:Museum`, `CFdoUqQAkeBa`) | |
| `"Article"` | not yet mapped | ask user — could be `schema:Article` (no v2 DS at the moment) |

When items contain **mixed types**, split the source data per `type` and run one mapping per DS.

## Field semantics

### Identifiers and core

- **`global_id`** is the stable identifier (e.g. `t_100300586`). Prefer it over `id` for subject IRIs and `schema:identifier`. Format: `<prefix>_<digits>`.
- **`title`** → `schema:name` as `rdf:langString @de`.
- **`changed`** → `schema:sdDatePublished` (ISO timestamp). `created` is usually redundant — skip.
- **`type`** is the destination.one type, not a schema.org type — used only for DS selection.

### Texts (`texts[]` array of `{rel, type, value}`)

| `rel` value | Mapping | Notes |
|---|---|---|
| `"details"` (with `type='text/plain'`) | `schema:description` | main German description |
| `"details"` (with `type='text/html'`) | skip — duplicate of plain text |
| `"open-data-nrw-detail"` | skip — duplicate of `details` |
| `"teaser"` | skip — short variant of description |
| `"WEB_SEO_TITEL"` / `"WEB_SEO_BESCHREIBUNG"` / `"WEB_SEO_KEYWORDS"` | skip — SEO variants |
| `"ROUTE_START"` (Tour) | `odta:startLocation` → `schema:Place.schema:name` |
| `"ROUTE_ZIEL"` (Tour) | `odta:endLocation` → `schema:Place.schema:name` |
| `"INFO_WEGBELAG"` (Tour) | `schema:additionalProperty` → `PropertyValue` `name="surface"` |
| `"TourMoreInfos_directions"` / `"TourMoreInfos_parking"` / `"TourMoreInfos_publicTransit"` / `"TourMoreInfos_gettingThere"` | skip for now — no clean Trail mapping |

### Geo (`geo` object)

- **`geo.main.{latitude,longitude}`** = the START coordinates (first point of the route).
- **`geo.geometry.value`** = a space-separated polyline `lat lng lat lng …`. Maps to `schema:geo` → `schema:GeoShape.schema:line`.
- **End coordinates** are the LAST `lat lng` pair of `geo.geometry.value` — extract via a custom function (`func:lastGeometryPoint`).
- **`geo.entry`** is usually empty `[]` — skip unless you see entries.

### Tour-specific quantitatives

- `length` → meters; map to `odta:length` → `QuantitativeValue` (`unitCode: "MTR"`).
- `duration` → seconds; map to `odta:estimatedDuration` (`xsd:duration`) via `func:secondsToISODuration`.
- `elevationMin` / `elevationMax` → meters; map to `odta:lowestPoint` / `odta:highestPoint`.
- `totalAscent` / `totalDescent` → meters; map to `odta:uphillElevation` / `odta:downhillElevation`. **`numbers[]`** entries `ROUTE_HOEHENMETER` / `ROUTE_HOEHENMETER_DESC` duplicate these — skip `numbers[]`.
- **`features[]` containing `"Rundweg"`** indicates a circular trail, but **prefer to derive `odta:circularTrail` from polyline endpoints** via `func:isCircular` — more reliable than the flag.

### Ratings (`ratings[]` array of `{type, value}`)

| `type` | Mapping |
|---|---|
| `"difficulty"` | `odta:difficulty` → `PropertyValue` (`name="difficulty"`, numeric `value`). DS also allows `odta:GenericDifficultyScale` enum, but PropertyValue preserves the original numeric (0–100) |
| `"Kondition"` | `schema:additionalProperty` → `PropertyValue` `name="Kondition"` |
| `"eT4"` | `schema:additionalProperty` → `PropertyValue` `name="eT4"` (internal source rating, ask user before keeping) |

### Attributes (`attributes[]` array of `{key, value}`)

| `key` | Mapping |
|---|---|
| `"licenseurl"` | `schema:sdLicense` (Trail level) — use the URL value |
| `"license"` (e.g. `"PD"`) | skip — redundant with `licenseurl` |
| `"URL_TITLE"` | skip — internal URL slug |
| `"AiOptimized"` | skip — internal source annotation |

### Addresses (`addresses[]` array of `{name, web, phone, ..., rel}`)

| `rel` | Mapping |
|---|---|
| `"author"` | `schema:sdPublisher` → `Organization` (use `name`, `web`, `phone`) |
| `"copyright"` | typically same Organization as `author` — skip as redundant |

### Media (`media_objects[]`)

Each entry has `{url, alt, description, source, license, width, height, id}`. Map to `schema:image` → `ImageObject`:

| Source field | ImageObject property | Notes |
|---|---|---|
| `url` | `schema:contentUrl` (required) | `xsd:anyURI` |
| `alt` | `schema:name` | German |
| `description` | `schema:caption` | `rdf:langString @de` |
| `source` | `schema:copyrightNotice` | photographer / credit string |
| `license` | `schema:license` | code (`"CC-BY-SA"`, `"PD"`) → URL via `func:licenseCodeToUrl` |
| `width` | `schema:width` → `QuantitativeValue` | `unitCode: "E37"` (pixels) |
| `height` | `schema:height` → `QuantitativeValue` | `unitCode: "E37"` |

Use `id` (e.g. `m_3187305`) as the second segment of the image IRI: `ex:image/{trail.global_id}-{media.id}`.

### Categories / keywords / features

- `categories[]`, `keywords[]`, `features[]` are **all string arrays**. Merge them all into `schema:keywords` (literal `xsd:string`, multiple values) via `func:mergeKeywords`.
- Drop `"Rundweg"` from features (already captured via `odta:circularTrail`).
- Categories may contain empty strings (`""`) — filter them out in the merge function.

## Always-skip list (destination.one tours)

These fields are consistently empty, redundant, or irrelevant for `Tour` items:

- `country`, `city`, `zip`, `street`, `district`, `postoffice`, `phone2` — a tour has no postal address; data inconsistent
- `cuisine_types`, `payment` — empty for tours
- `timeIntervals`, `kitchenTimeIntervals`, `alwaysOpen`, `deliveryTimeIntervals`, `timeIntervalExceptions`, `occurrences` — empty / not relevant
- `numbers[]` — redundant to `totalAscent` / `totalDescent`
- `seasons[]` — month-by-month suitability, no Trail property fits cleanly
- `subitems[]` (Segments) — usually empty inner geo
- `hyperObjects[]`, `author`, `company` — typically empty
- `created` — redundant to `changed`
- `source.url/value` — redundant to publisher
- `areas[]` — unstructured strings, no clean mapping (mixes regions, cities, organizations)

## Reusable custom functions

These functions have been validated against destination.one data and can be reused as-is:

- `func:secondsToISODuration` — `8460` → `"PT2H21M"`
- `func:isCircular` — polyline string → boolean (compares first/last point with tolerance 0.0005)
- `func:lastGeometryPoint` — polyline string + `"lat"`/`"lng"` → `xsd:double`
- `func:timestampToDate` — ISO timestamp → `YYYY-MM-DD`
- `func:licenseCodeToUrl` — `"CC-BY-SA"` → `"https://creativecommons.org/licenses/by-sa/4.0/"` (also handles `CC-BY`, `CC0`, `PD`)
- `func:mergeKeywords` — combines `categories`, `keywords`, `features` arrays, dedupes, drops `"Rundweg"` and empty strings

## RocketRML pitfalls (encountered with destination.one data)

These are not destination.one-specific but were confirmed during the trail mapping:

1. **Object arrays get destroyed when passed to FnO functions** — RocketRML stringifies each object in the array to `"[object Object]"`. Filter functions like `getRatingByType(ratings, ...)` cannot work. **Workaround:** use a separate sub-mapping with a JSONPath filter in its iterator (e.g. `"$.items[*].ratings[?(@.type=='difficulty')]"`) and join from the parent.

2. **String/number arrays pass through correctly** — so `mergeKeywords(categories, keywords, features)` works because all three are arrays of primitives.

3. **`$(.)` for primitive array elements does not parse** — RocketRML rejects this syntax with a JS syntax error. **Workaround:** wrap primitive iteration in a function that takes the parent array and returns the filtered list.

4. **Unreferenced mappings do not run** — every mapping must be the root or be joined from another. **Workaround:** use wrapper sub-mappings (e.g. `CreativeWork` for description, `PropertyValue` for difficulty) joined from the parent. The DS often allows these wrapper ranges.

5. **`schema:description` / `schema:sdLicense` cannot be emitted as literals from a filtered iterator** — the join mechanism only produces IRI-typed objects. **Workaround:** use `CreativeWork` wrapper with `schema:text` / `schema:url`. Both are allowed by Trail v2, Event v2, Place v2.

6. **`$.items[*].xxx[?(@.key=='yyy')]` filters in iterators DO work** in RocketRML's jsonpath-plus engine. This is the primary tool to replace object-array filter functions.

## Open questions / known unknowns

- `seasons[]` — could it be modeled as multiple `OpeningHoursSpecification` entries? Place v2 supports those, but Trail v2 does not have a season property.
- `addresses[?rel='author']` returning multiple authors — never observed in destination.one, but the model should support multiple `schema:sdPublisher` triples if it occurs.
- `subitems[*]` — Segments could be modeled as `odta:containsSection` → `schema:ItemList`, but the destination.one data is too sparse to justify the complexity; skipped here.
