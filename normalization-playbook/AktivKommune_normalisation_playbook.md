# AktivKommune – Playbook for normalising the instances

**Status:** Draft v0.1 for internal review · **Date:** 11 November 2026
**Companion file:** `AktivKommune_common_hierarchies_v0.1.xlsx` (the proposed common lists and the crosswalk from existing names)

> AI-assisted first draft. It must be reviewed by someone who knows the AktivKommune data model and the municipalities before it is used or shared with the client. The database steps are written without access to the actual schema and are marked as assumptions.

---

## 1. Executive summary

We are changing approach. Instead of mapping incoming data from each AktivKommune instance into a separate master vocabulary, we will **normalise the instances themselves**. Every instance will use the same three lists, in the structure the instances already have (`id`, `name`, `parent_id`):

| List | Common entries (proposed) | Existing names in the exports | Use per resource |
|---|---|---|---|
| **Aktivitet** | 212 (option A) or 139 (option B) | 461 | Many |
| **Lokaletype** | 105 | 212 | Exactly one |
| **Facility** | 156 | 387 | Many |

- The lists are **strictly common**: every instance has exactly the same entries with the same ids. No local entries.
- The earlier mapping work is reused. It has become the **crosswalk**: for every existing name, which common entry replaces it, or whether it is retired or moved.
- Normalising an instance is a repeatable procedure of eight steps (section 6): inventory, crosswalk, municipality sign-off, backup, load the common lists, re-link resources, retire old entries, verify.
- We recommend a pilot on one or two instances before rolling out in waves.
- **One decision is needed before the pilot:** the scope of the aktivitet tree (section 4).

---

## 2. Background and what changes

### Findings from the exports (6–9 October 2026, 17 municipalities)

- Each instance maintains its own lists. Most names are local: 295 of 450 activity names and 314 of 387 facility names occur in only one municipality.
- The same thing is spelled many ways (bokmål/nynorsk, typos, plurals, HTML-encoded characters).
- The lists mix kinds of information. Aktivitet contains organisation types, target groups, venue types and status text ("Stengt"). Facility contains 75 capacity values ("Kapasitet 1-20") and room types. Lokaletype contains activities and equipment.
- Ids are local. The same id means different things in different instances.
- The parent/child relations in the activity export are unreliable (the same municipality + id resolves to several names). They must be re-exported per instance before anyone relies on them.

### Old approach and new approach

| | Old (mapping layer) | New (normalise the instances) |
|---|---|---|
| Where the cleaning happens | In a separate layer, on every load | Once, in each instance |
| Source lists | Stay as they are | Replaced by the common lists |
| Structure | Facets, several concepts per value, attributes | `id`, `name`, `parent_id` – one tree per list |
| Ongoing work | New local values must be mapped continuously | New entries are added centrally, for all instances |
| Search | Depends on the mapping being up to date | Works directly on the instance data |

### What happens to the earlier deliverables

- The mapping workbooks and JSON exports are **superseded** as a runtime solution.
- Their content lives on in the companion workbook: the concepts became the common trees, and the value mappings became the crosswalk sheets.

---

## 3. Target structure

Each of the three lists is a table with the columns the instances already use:

| Column | Rule |
|---|---|
| `id` | Same value in every instance. Never reused, never renumbered. |
| `name` | Bokmål name, unique within the list. |
| `parent_id` | Empty for top-level entries; otherwise the `id` of exactly one parent in the same list. |

Rules:

1. **One parent per entry.** No entry sits in two places. (Dans is under Kultur, not also under Idrett.)
2. **Shallow.** At most four levels, for example Idrett → Ballsport → Håndball → Sandhåndball.
3. **One meaning per list.** Aktivitet is what happens, lokaletype is what kind of space it is, facility is what the space has.
4. **No numbers or status in names.** Capacity, sizes, quantities, age ranges and "stengt" are not list entries.
5. **Strictly common.** Instances cannot add, rename or move entries. Changes go through the central process (section 8).
6. **Lokaletype: exactly one per resource.** Aktivitet and facility: as many as apply.

**Proposed id range (to be confirmed):** ids start at 10001 in each list. This keeps them clear of existing local ids while old and new entries exist side by side during migration.

**Open point – nynorsk:** if nynorsk municipalities need nynorsk names, that requires either a name column per language or a translation mechanism in the application. The workbook has a `name_nn` column to collect the names; how they are stored is a product decision.

---

## 4. The common hierarchies

The full lists are in the companion workbook, one sheet per list, with a crosswalk sheet for each.

### 4.1 Aktivitet – decision needed

Today the aktivitet list holds more than activities. There are two ways to handle that:

| | **Option A – keep everything as branches** | **Option B – activities and events only** |
|---|---|---|
| Top-level entries | Idrett, Kultur, Friluftsliv, Læring, Fritid og hobby, Arrangement, Organisasjonstype, Målgruppe, Lokale, Tjeneste | Idrett, Kultur, Friluftsliv, Læring, Fritid og hobby, Arrangement |
| Size | 212 entries | 139 entries |
| Existing names that get a common entry | 435 of 461 | 279 of 461 |
| What happens to organisation types, target groups, services | Stay in the tree under their own branch | Removed from aktivitet; need another home (organisation data, a target-group field) or are dropped |
| What happens to venue names in aktivitet (Møterom, Gymsal…) | Stay under "Lokale" (duplicates lokaletype) | Removed; the resource's lokaletype carries this |
| Effort per instance | Lower – almost everything is re-linked | Higher – links must be removed or moved, and municipalities may lose filters they use |
| Result | Closest to today; aktivitet still mixes meanings | Cleaner list; better search filters |

**Assessment (opinion):** option B gives the better end state, but only if there is somewhere to put organisation type and target group. If those fields don't exist and won't be built now, option A is the pragmatic first step. The tree is built so that the "A only" branches can be removed later without touching the rest.

The workbook marks every entry with `A + B` or `A only`.

In both options these are **retired** from aktivitet: status text (Stengt, Vedlikehold, Ferie – 13 names), catch-alls (Annet, Generelt – 6 names) and test or system text (4 names). Three names need clarifying with the municipality (Mini, NRG, Treklang).

### 4.2 Lokaletype

- 105 entries under 11 top-level entries: Idrett innendørs, Idrett utendørs, Bad og basseng, Kultur og scene, Verksted og studio, Møte og undervisning, Forsamling og sosialt, Mat og servering, Uteområde og friluft, Overnatting, Næring og service.
- 183 of 212 existing names map to a common entry.
- 28 are retired because they aren't venue types: activities (Sjakk, Barnebursdag), equipment (Kano, Lerret, Sykler), "Stengt", "Fiktivt rom", catch-alls. Resources that have one of these as their lokaletype must be given a real one (step 6.6).
- One needs clarifying ("Kvitsøygata 3").
- "– privateid" and "lite/stort" are dropped from the name. If ownership or size matters, it belongs in a field on the resource.

### 4.3 Facility

- 156 entries under 13 top-level entries: AV og teknikk; Scene, musikk og dans; Idrettsanlegg og bane; Idrettsutstyr; Bad og basseng; Kjøkken og servering; Møblering; Garderobe og sanitær; Tilgjengelighet; Infrastruktur og service; Lek og spill; Friluft og uteområde; Utlånsutstyr.
- 297 of 387 existing names map to a common entry.
- **75 capacity values move to the capacity field on the resource** ("Kapasitet 1-20" → capacity 20). The extracted numbers are in the crosswalk.
- 14 room-type names (Møterom, Forsamlingslokale…) move to lokaletype. One name (Foredrag) is retired.
- Sizes and quantities in names disappear ("75 tommer TV-skjerm" → Skjerm/TV). If that detail is needed, it belongs in the resource description.

### 4.4 Status of the lists

The lists are a proposal built from the names found in 17 municipalities. They have not been reviewed by domain experts. Section 5 describes how to get them approved.

---

## 5. Phase 0 – before any instance is touched

| # | Task | Output | Owner (proposed) |
|---|---|---|---|
| 0.1 | Decide aktivitet scope (option A or B) | Decision | Product owner |
| 0.2 | Review and approve the three common lists | Approved lists v1.0 with final ids | Product owner + domain experts |
| 0.3 | Confirm the data model: tables, link tables, where historical bookings point | Short technical note | AktivKommune technical team |
| 0.4 | Confirm capacity field, and fields for organisation type / target group if option B | Decision, possibly a change request | Product owner |
| 0.5 | Decide how common lists are distributed and locked in the instances | Mechanism (script, admin function, shared table) | Technical team |
| 0.6 | Re-export all three lists **per instance** with instance id, entry id, name, parent id, active flag and usage counts | One inventory per instance | Technical team |
| 0.7 | Build and test the migration scripts on a copy of one instance | Tested scripts | Technical team |
| 0.8 | Agree communication to municipalities | Information letter, sign-off template | Project lead |

Step 0.6 matters because the current exports are aggregated across municipalities, lokaletype has no usage counts, and the resource counts are links rather than distinct resources.

---

## 6. Procedure per instance

Run these steps for each instance, first in a test copy, then in production.

### 6.1 Inventory

Export the instance's own aktivitet, lokaletype and facility lists with id, name, parent id, active flag, and the number of resources (and bookings, if relevant) using each entry.

### 6.2 Build the instance crosswalk

For each existing entry, look up the name in the crosswalk sheet and record the action:

| Action | Meaning |
|---|---|
| **Map** | Replace with the common entry (and a second one where "also link to" is filled) |
| **Move** | Move the information to another list or field (lokaletype, capacity) |
| **Retire** | Remove; nothing replaces it |
| **Clarify** | Ask the municipality what it means before deciding |

Names not found in the crosswalk are new. Map them by hand and add them to the central crosswalk so the next instance benefits.

### 6.3 Municipality review and sign-off

Send the municipality a short list of what changes for them:

- entries that are merged or renamed;
- entries that are retired, and how many resources that affects;
- resources that will get a different lokaletype;
- anything marked Clarify.

Get written sign-off from the municipality's administrator. Set a deadline; no answer on low-impact rows should not block the migration.

### 6.4 Backup and freeze

- Take a backup of the affected tables (or the whole instance).
- Agree a short change freeze on the three lists with the municipality.

### 6.5 Load the common lists

Insert the approved common entries with their fixed ids. Old and new entries now exist side by side; nothing points to the new ones yet.

### 6.6 Re-link resources

Assumption: resources link to aktivitet and facility through link tables, and carry lokaletype as a single reference. Confirm in step 0.3.

- **Aktivitet and facility:** for every link to an old entry, create a link to the common entry (and the second one, where given). Remove duplicates that arise when two old entries map to the same common entry.
- **Lokaletype:** set each resource to the common lokaletype. For resources whose old lokaletype is retired or a catch-all, the municipality chooses the right one from the common list (prepared in 6.3).
- **Capacity:** where a resource has a capacity "facility", write the number to the capacity field unless the field already has a value. Where they differ, list the conflict for the municipality.
- **Room types found in facility:** only use them to set lokaletype if the resource has none or a catch-all.

Illustrative SQL (table and column names are placeholders):

```sql
-- crosswalk loaded as: xw_aktivitet(old_id, new_id)   -- one row per old->new pair
INSERT INTO resource_aktivitet (resource_id, aktivitet_id)
SELECT DISTINCT ra.resource_id, xw.new_id
FROM resource_aktivitet ra
JOIN xw_aktivitet xw ON xw.old_id = ra.aktivitet_id
WHERE NOT EXISTS (
  SELECT 1 FROM resource_aktivitet x
  WHERE x.resource_id = ra.resource_id AND x.aktivitet_id = xw.new_id);

DELETE FROM resource_aktivitet
WHERE aktivitet_id IN (SELECT id FROM aktivitet WHERE id < 10001);
```

### 6.7 Historical data

Decide in step 0.3 which of these applies:

- **Bookings and applications point to activity ids:** re-point them with the same crosswalk, so history and statistics remain consistent. For retired entries, keep the old entry as inactive rather than deleting it, so history still resolves.
- **They store the name as text:** leave history as it is.

### 6.8 Retire old entries

- Deactivate (don't delete) all old entries first. Delete only after the acceptance period (for example 30 days), and only those with no remaining references.
- Lock the lists against local editing.

### 6.9 Verify

| Check | Expected |
|---|---|
| Entries in each list | Identical to the common list (same ids, names, parent ids) |
| Links to old entries | 0 |
| Resources without lokaletype | 0 |
| Resources with more than one lokaletype | 0 |
| Resources that had at least one activity before, and have none now | 0, or explained by retired entries and signed off |
| Number of resources before and after | Equal |
| Orphans (parent_id pointing to nothing) | 0 |
| Spot check in the UI: search and filter on 10 common activities | Works, with expected results |

### 6.10 Sign-off and close

- The municipality confirms the result in their instance.
- Record the migration date, the crosswalk used and the verification results.
- Feed new names and corrections back into the central crosswalk.

---

## 7. Special cases

| Case | Example | Handling |
|---|---|---|
| Compound names | "Kano/kajakk", "Dans/ musikk/ kor/ korps" | Aktivitet and facility: link to each part. Lokaletype: one type; the municipality confirms. |
| Broad tags only | Resource tagged only "Idrett" | Keep the link to Idrett. Ask the municipality to add specific activities; this improves search most. |
| Details in names | "Barnebursdag 3–12 år", "Fotball (1/4 av 11'er bane)" | Map to the plain entry. Age or pitch size goes in the description or a proper field. |
| Booker or price categories | "Offentlig", "Privat", "Frivillig organisasjon" (Halv pris) | Not activities. Confirm how pricing uses them before retiring; they may be referenced by price rules. |
| Status text | "Stengt", "Vedlikehold", "Ferie" | Retire. Check first whether they are used to block calendars; if so, the blocking needs another mechanism. |
| Internal use | "Internt Bergen kommune" | Option A: maps to Kommunal intern bruk. Option B: needs a decision. |
| Unknown names | "Mini", "NRG", "Kvitsøygata 3" | Clarify with the municipality; default is retire. |
| Inactive entries | Entries no longer in use | Don't migrate; deactivate. |
| Entries used by integrations | Ids referenced by external systems or reports | Find them in step 0.3; they need a coordinated change. |

---

## 8. Governance after normalisation

- **Owner:** one named owner of the common lists.
- **Change process:** municipalities request new entries; the owner decides; approved changes are released to all instances at once, on a fixed schedule (for example quarterly).
- **Ids:** never reused. Entries are deactivated, not deleted.
- **Versioning:** each release of the lists has a version number and a change log.
- **Locking:** instances cannot edit the three lists locally.
- **New instances:** start with the common lists; no local lists.

---

## 9. Rollout plan (proposed)

| Phase | Content | Exit criterion |
|---|---|---|
| **0 – Prepare** | Section 5 | Lists approved, scripts tested on a copy |
| **1 – Pilot** | One small and one large instance | Verification passed; municipality sign-off; lessons recorded |
| **2 – Adjust** | Update lists, crosswalk, scripts and this playbook | Version 1.0 of the playbook |
| **3 – Waves** | Remaining instances in groups of 4–6 | Each instance verified and signed off |
| **4 – Lock and hand over** | Lock lists, start governance | Owner and change process in place |

Suggested pilot candidates, as an opinion to be tested: one instance with few local names, and one large instance with many (Bergen or Stavanger), so both ends are exercised early.

Effort and duration depend on the answers in step 0.3 and are not estimated here.

---

## 10. Roles (proposed)

| Role | Responsibility |
|---|---|
| Product owner | Decisions on scope, lists and fields; owns governance |
| Domain experts (sport, culture) | Review the common lists |
| AktivKommune technical team | Data model, scripts, running the migration |
| Project lead | Plan, communication, sign-offs |
| Municipality administrator | Reviews changes for own instance; classifies resources where needed; signs off |

---

## 11. Risks

| Risk | Consequence | Mitigation |
|---|---|---|
| Municipalities lose categories they rely on | Resistance, workarounds in free text | Review in 6.3; clear rule for requesting new common entries |
| Old entries are referenced by price rules, calendars blocks, reports or integrations | Broken pricing or reports | Find references in 0.3; deactivate before deleting; acceptance period |
| Crosswalk errors | Resources get the wrong activity or lokaletype | Confidence marking; municipality review; verification; backup |
| Lokaletype forced to one value loses information | Multi-purpose rooms are harder to find | Use Flerbruksrom/Flerbrukshall; rely on aktivitet and facility for the rest |
| Instances drift apart again | Back to today's situation | Lock the lists; central change process |
| Data model differs from the assumptions here | Steps in section 6 need rework | Step 0.3 before anything else |
| Personal data in the tables being backed up or exported | Compliance issue | The three lists hold no personal data, but bookings do. If backups or exports include bookings or applicants, involve the Data Privacy Officer first. |

---

## 12. Open questions

1. Aktivitet scope: option A or B? If B, where do organisation type and target group live?
2. Does every instance have the same schema and version?
3. How do resources link to aktivitet and facility, and do bookings reference activity ids?
4. Is there a capacity field on the resource in all instances?
5. Are "Stengt"-type entries used to block booking?
6. Do price rules reference activity or booker categories?
7. How should nynorsk names be handled?
8. Should the common ids start at 10001, or is there a better convention in the platform?
9. Are there more instances than the 17 in the exports (for example Narvik, Åfjord, Averøy, Gamvik, Inderøy, Nordreisa, Øksnes, Sogndal), and when can they be inventoried?
10. Is NIF linkage still wanted? If so, it can be kept as a separate reference table against the common aktivitet ids.
