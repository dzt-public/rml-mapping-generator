# Lessons Learned — ODTA / DZT domain rules (cross-source)

## When to use this file

Apply this guidance whenever the **target DS ecosystem is ODTA / DZT** — i.e. the config's
`ds_list_url` points at a semantify.it list of ODTA Domain Specifications — regardless of which
source feed the data comes from. This file is **domain-level**: combine it with the matching
**source-specific** lessons file (e.g. `destination.one.md`); on conflict, the
source-specific file wins for field semantics, this file wins for DS-ecosystem policy.

## The sanctioned DS lists

Three DS lists matter — know which is which:

| List | Name | Entries | Use |
|---|---|---|---|
| `CRkyvcqGqeUu` | ODTA Domain Specifications v2.2 | 37 (incl. `[DEPRECATED]`) | **what goes in `ds:compliesWith`** |
| `sLQnFffNEgar` | DZT KSW Filters | 20, none deprecated | DZT-sanctioned target set — prefer it when picking the declared DS |
| `WaDfPoiWnLkC` | DZT-ODTA Domain Specifications | 14, own ids | **verification target only — never written into the data** |

## `compliesWith` policy: declare ODTA, also satisfy DZT-ODTA

(User rules, 2026-08-10/13; re-confirmed 2026-09-04.)

1. **Instances ALWAYS carry the ODTA v2.2 DS URI in `ds:compliesWith`.** DZT-ODTA ids are only
   ever used to *check* conformance, never written into the output.
2. **Additionally, the output must TRY to satisfy the matching DZT-ODTA ("strict") DS.** Pick the
   strict DS by **specificity**: the DZT-ODTA entry for the type itself when one exists; only when
   it does not, the DZT-ODTA entry of the nearest SUPERTYPE (use the class hierarchy in
   `vocab_cache/`). Do NOT also verify against a supertype profile when a specific one exists —
   the specific one is the gate.
3. **Before writing ANY mapping, diff the declared DS against the strict one** (required-property
   gaps, datatype conflicts, cardinality conflicts) and check **`sh:closed` on the DECLARED
   shape** — a closed declared shape rejects outright any property it does not itself declare.
   Surface every conflict in the approval gate. Known real conflict: the two Event DSs demand
   different datatypes for root `startDate`/`endDate` (`xsd:dateTime` vs `xsd:date`) — this made
   every record unimportable while local fixtures passed. TIC's declared shape (`wNrMWBpNQYJm`)
   is closed; Event's is open.
4. **Validate against the strict DS by swapping `compliesWith` in a COPY** of the output
   (the VER endpoint has no explicit-DS parameter). Declared-DS violations are hard failures;
   strict-DS violations are fixed where possible without breaking declared-DS conformance, and
   the irreconcilable rest is reported.

### ODTA v2.2 ↔ DZT-ODTA mapping (by `sh:targetClass`, verified live 2026-09-04)

| Target class | Declared DS (ODTA v2.2) | Strict DS (DZT-ODTA) |
|---|---|---|
| `schema:Place` | Place v2 `gGDiyXWKpGpu` | `DbBNtkSpgUwh` |
| `schema:Event` | Event v2 `ywkngcBEETdh` | `jyjQsWSEeAQX` |
| `odta:Trail` | Trail v2 `hSsrCTQowvYH` | `hzTsQqcMekUR` |
| `odta:CaveOrMine` | Cave or Mine v2 `jnZaRInTzjeu` | `HxhSviiMsKId` |
| `schema:FoodEstablishment` | Food Establishment `zmoYZEMoSAKS` | `AaFBzPmVTJAN` |
| `schema:LodgingBusiness` | Lodging Business v2 `xVTuYwJrJrfq` | `QprCpMlvliqG` |
| `schema:TouristInformationCenter` | Tourist Information Center `wNrMWBpNQYJm` | `GZEIIZmhlOWs` |
| `schema:LandmarksOrHistoricalBuildings` | Landmarks or Historical Buildings `nFVMlquREalK` | `UPHREguYTbkT` |
| `schema:TouristAttraction` | Tourist Attraction `pxNgHzzhpeUu` | `iUqeLKlAZEfT` |
| `schema:LocalBusiness` | Local Business `dXppPkIfxyxA` | `yIvoweKSnsgU` |
| `schema:HealthAndBeautyBusiness` | Health and Beauty Business v2 `uFXQamNEucCf` | `zdtrZLgbRiOq` |
| `odta:Sauna` | Sauna v2 `WyKAkGKfqhDb` | `TuFtNpjaQiNW` |
| `schema:City` | City `ESInPjvLlsNf` | `TJmxdWjslGSm` |
| `odta:Infrastructure` | Infrastructure `zhOveThNnLDZ` | `yfmIKWfqKVrk` |

**Types with no DZT-ODTA entry of their own** → strict DS of the nearest supertype
(confirmed cases: **Museum** `CFdoUqQAkeBa` → Place `DbBNtkSpgUwh`, **Zoo** `sOieryftnQGi` →
Place `DbBNtkSpgUwh`). For other types (Park, Event Venue v2, Nature Attraction v2,
ProtectedArea v2, Public Swimming Pool v2, Sports Activity Location v2), derive the nearest
supertype with a DZT-ODTA entry from the class hierarchy — do not guess. `odta:Certificate`
and `odta:OccupancyMeasurement` have no Place-lineage supertype: declared DS only.

Re-verify the table when either list changes: fetch both lists with
`?representation=lean` and re-match on `sh:targetClass`.

## DS choice rules

- **Generic POI / TouristAttraction fallback:** when the best-matching DS for an item would be
  `TouristAttraction`, use **Place v2** (`schema:Place`, `gGDiyXWKpGpu`) instead. The same applies
  to generic Points of Interest (type `"POI"`, mixed categories, no specific niche): always
  **Place v2** — never `TouristAttraction` or `LocalBusiness` for generic POI data.
- **Always prefer the `v2` DS** when one exists for the entity type; **never pick a
  `[DEPRECATED]` DS**, even if its name matches better.

## Mapping rules

- **A real DS property always beats `schema:additionalProperty`.** If the DS has a real property
  for a piece of information, map it there — never route the same information through
  `additionalProperty` as well as, or instead of, the real property. `additionalProperty` is only
  for data with no DS home.
  - Facility/service enums belong in `schema:amenityFeature`
    (`schema:LocationFeatureSpecification` with `name` + `value`), accessibility statements in
    `schema:accessibilityFeature` (same node type).
  - **Exception — restricted enumerations:** a real property whose range is a *restricted* enum is
    NOT automatically the better target. If the source emits values outside the enum, mapping to it
    silently drops data or fails VER — prefer `additionalProperty` in that case.
- **Multiple `rdf:type` is allowed.** Emit the DS root class **and** semantic subtypes/leaf types
  as additional `a` triples rather than squeezing them into `schema:additionalType`. `sh:closed`
  on a DS constrains *properties*, not types.
