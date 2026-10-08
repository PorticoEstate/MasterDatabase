# AktivKommune – Activity Normalisation

**Status:** Draft v0.2 for internal review · **Date:** 6 October 2026
**Artefacts:** `AktivKommune_activity_mapping_v0.2.xlsx`, `export_mapping.py`, `export/*.json`

> AI-assisted first draft. The mapping and this document must be reviewed by someone who knows the domain before production use or sharing with the client.

---

## 1. Executive summary

The activity names in AktivKommune are free-form, set up separately in each municipality, and mix several kinds of information in one field (what people do, who books, what kind of room, opening status). That makes them unsuitable for search as they are.

We propose a **master vocabulary of our own, split into facets**, with every source value mapped to it:

- **450 exported names** (446 after normalisation) are mapped to **208 concepts** in **7 facets**.
- Sports link to **NIF** as an *external reference*, not as the backbone. NIF covers sport only, and its structure mixes sports with organisation types (Bedrift, Studentidrett).
- Search uses a **hierarchy** (searching "Ballsport" also finds fotball) and **alternative names** (searching "symjehall" finds Svømmehall).
- **92% of resources** are covered by high-confidence mappings. 69 names (medium) and 23 names (low) need human review.
- Three problems need fixing at the source: the **exported parent/child relations are unreliable**, some names are **HTML-encoded twice**, and **~1,770 resources are tagged only "Idrett" or "Kultur"**, which is too broad to be useful in search.

---

## 2. Problem

| Observation (from the 6 Oct export) | Consequence |
|---|---|
| 450 names across 17 municipalities; 295 used in only one municipality | Little shared vocabulary; search depends on how each municipality spelled things |
| Bokmål/nynorsk variants, typos, plurals (*symjehall*, *speidarar*, *meningheter*) | The same thing appears under several names |
| One field mixes activity, event type, organisation, target group, venue and status (*Fotball*, *Barnebursdag*, *Sameie*, *VGS*, *Møterom*, *Stengt*) | Cannot filter meaningfully |
| Attributes hidden in names (*Barnebursdag 3–12 år*, *Fotball (1/4 av 11'er bane)*) | Duplicates; attributes can't be searched |
| Activity IDs are local to each instance; the same municipality + ID resolves to different names | IDs cannot be used as keys across instances |
| NIF list covers sport only and includes organisation-type parents | Not usable as the full taxonomy |

---

## 3. Design principles

1. **Own the vocabulary; link to external code lists.** The master vocabulary is ours. NIF (and later others, e.g. Kulturrådet or SSB) are attached as links (`exact`, `close`, `parent`).
2. **One field, one meaning.** Each concept belongs to exactly one facet. Mixed source values are split into a primary and a secondary concept.
3. **Shallow hierarchy.** At most three levels (e.g. Idrett → Ballsport → Fotball). A concept may have two parents where that helps search (Dans under both Kultur and Idrett).
4. **Stable IDs, changeable labels.** Everything refers to `concept_id`, never to labels.
5. **Attributes are not concepts.** Age, pitch size, stand size and municipality are stored as attributes on the activity or resource.
6. **Never delete source data; map it.** Every source value gets an entry, including noise, which is mapped to *Exclude* with a reason.
7. **Human in the loop.** Automated proposals are confidence-scored, and a reviewer approves or overrides them.

---

## 4. Model

### 4.1 Facets

| Facet | Answers | Examples | Concepts* |
|---|---|---|---|
| **Activity** | What do people do? | Fotball, Kor, Tur og vandring, Sjakk | 109 |
| **Event** | What kind of booking or event? | Møte, Konferanse, Barnebursdag, Konsert | 28 |
| **Organisation** | Who books? | Humanitær organisasjon, Grendelag, Privatperson | 24 |
| **Target group** | Who is it for? | Barn, Seniorer, Skole, Kommunal intern bruk | 12 |
| **Venue** | What kind of space? *(belongs on the resource)* | Møterom, Svømmehall, Kulturlokale | 25 |
| **Service** | Services that aren't activities | Utlån av utstyr, Veiledning og rådgivning | 6 |
| **Exclude** | Not searchable | Uspesifisert, Stengt/utilgjengelig, Testdata, Avklares | 4 |

\*Counts include parent nodes.

### 4.2 Concept

Each concept has:

- `concept_id` – stable key, with a prefix per facet (`ACT-`, `EVT-`, `ORG-`, `GRP-`, `VEN-`, `SRV-`, `EXC-`)
- `label.nb` (required) and `label.nn` (optional, shown in the UI)
- `broader` – parent concept ID(s)
- `altLabels` – synonyms, spelling variants and nynorsk forms, generated from the source values that map to the concept
- `nif` – optional link: `{code, match}` or `{parent, match}`
- `note`

Activity roots: **Idrett, Kultur, Friluftsliv, Læring, Fritid og hobby**.

### 4.3 Mapping

The mapping connects a **normalised source value** to one or more concept IDs:

```
source value (any instance) ──normalise──▶ key ──▶ [concept_id, ...] + attributes | exclude
```

- Compound values map to several concepts: `kano/kajakk → [Kano, Kajakk]`
- Hidden attributes are extracted: `barnebursdag 3 - 12 år → [Barnebursdag, Barn] + {ageMin: 3, ageMax: 12}`
- Noise is excluded with a reason: `stengt → exclude (status)`

### 4.4 Normalisation

These rules must be **identical** in the export, ingest and search code (`normalise()` in `export_mapping.py`):

1. HTML-decode twice (the source has `&amp;#40;`)
2. Trim and collapse whitespace
3. Lowercase

### 4.5 NIF linkage

| Match type | Meaning | Example |
|---|---|---|
| `exact` | Same sport, NIF SportCode | Fotball → 261 |
| `close` | Near equivalent | Stuping → 452 *Stup* |
| `parent` | Only a NIF group matches | Ski → parent *Ski* |
| `broad` | Top-level category, no code | Idrett, Kultur |
| `none` | No NIF equivalent | Kor, Sjakk, E-sport |

Known problems in the NIF file: a duplicate SportCode (992), a test row (*Testgrenen*), the same sport under several parents (*5-kamp* ×3, *Futsal* ×3), Latin-1 encoding, and non-sport parents (*Bedrift*, *Studentidrett*, *Idrett for funksjonshemmede*).

### 4.6 Confidence

| Level | Meaning | Names | Share of resources |
|---|---|---|---|
| **H** | Unambiguous | 358 | 91.7% |
| **M** | Reasonable interpretation | 69 | 7.4% |
| **L** | Guess; needs a domain expert or the source owner | 23 | 1.0% |

---

## 5. Workbook (`AktivKommune_activity_mapping_v0.2.xlsx`)

| Sheet | Purpose |
|---|---|
| **README** | Short guide, facet definitions, rules |
| **Summary** | Live counts by facet, confidence and NIF linkage (weighted by resources); data-quality figures |
| **Value_Mapping** | **Review sheet**, one row per exported name |
| **Concepts** | Master vocabulary |
| **Source_Hierarchy_Check** | Evidence that the exported parent/child relations are unreliable |
| **NIF_Reference** | NIF list in UTF-8 with quality flags |

**Colour coding:** yellow = reviewer input · grey = formulas (don't edit).

### Review workflow

1. Sort `Value_Mapping` by **# resources** (descending), so the values with most impact come first.
2. Filter on confidence **L**, then **M**. High-confidence rows can largely be bulk-approved.
3. Set **review status**: `Approved` / `Changed` / `Rejected` / `Ask source owner`.
4. To change a mapping, choose a concept in **final concept (override)**. Leave *proposed concept* as it is, for the audit trail.
5. Need a new concept? Add a row in **Concepts** (new ID, facet, label, broader), then select it.
6. Fill **pref_label_nn** where a nynorsk label should be shown.
7. Save in Excel, then run the export.

---

## 6. Export (`export_mapping.py`)

```bash
pip install openpyxl
python export_mapping.py AktivKommune_activity_mapping_v0.2.xlsx --out export --test
python export_mapping.py AktivKommune_activity_mapping_v0.2.xlsx --approved-only   # reviewed rows only
```

The script reads cached formula values, so **save the workbook in Excel first**. It exits with an error if any check fails, so it can be used as a CI gate.

**Checks:** unknown concepts, missing parents, cycles in the hierarchy, duplicate concept labels, and spelling variants that map to different concepts.

### Output files

**`vocabulary.json`** – grouped by facet, flat within each facet, keyed on ID

```json
{
  "facets": {
    "activity": {
      "ACT-018": {
        "label": { "nb": "Fotball" },
        "broader": ["ACT-012"],
        "altLabels": ["innefotball", "minifotball"],
        "nif": { "match": "exact", "code": 261, "name": "Fotball" }
      }
    }
  }
}
```

**`mapping.json`** – keyed on the normalised source value

```json
{
  "normalisation": "html-decode x2, trim, collapse spaces, lowercase",
  "values": {
    "kano/kajakk": { "concepts": ["ACT-079", "ACT-078"], "confidence": "H", "status": "Proposed", "sourceNames": ["Kano/kajakk"] },
    "barnebursdag 3 - 12 år": { "concepts": ["EVT-021", "GRP-001"], "attributes": { "ageMin": 3, "ageMax": 12 } },
    "stengt": { "concepts": [], "exclude": true, "reason": "status" }
  }
}
```

**`search_tests.json`** – generated regression tests

| Type | Checks |
|---|---|
| `altLabel` | Searching for a variant finds its concept (*symjehall* → Svømmehall) |
| `hierarchy` | Searching for a parent finds its children (*Ballsport* → Fotball, Håndball…) |
| `exclude` | Excluded values return nothing (*stengt*) |

The file is overwritten on every export, so keep hand-written tests in a separate file.

**Why the hierarchy is flat with `broader` links rather than a nested tree:** it handles concepts with two parents, moving a concept is a one-field change, and diffs stay readable. A tree view can be generated whenever one is needed.

---

## 7. How search uses it

1. **Indexing:** each resource or activity gets the concept IDs (plus parent IDs) and attributes from `mapping.json`.
2. **Synonyms:** `label` and `altLabels` are fed to the search engine as synonyms.
3. **Query expansion:** a match on a concept is expanded to all its narrower concepts through `broader`.
4. **Facet filters:** the UI filters by facet (Activity, Target group, Venue…), never on raw source values.
5. **Exclusion:** `exclude` values are never indexed for search. Status values (*Stengt*) belong in booking availability.

---

## 8. Known issues

| # | Issue | Evidence | Proposed action | Owner |
|---|---|---|---|---|
| 1 | Exported parent/child relations unreliable | 95 municipality + ID pairs resolve to >1 name; *Fotball → Skole*; *Idrett* has 6,833 children | Re-export keyed on `(instance_id, activity_id)`; until then, don't use the source hierarchy | Export / data team |
| 2 | Names HTML-encoded twice | 4 names, e.g. `Fotball &amp;#40;…` | Fix encoding at the source; normalisation handles it in the meantime | Source systems |
| 3 | Broad-only tagging | ~1,770 resources tagged only *Idrett*/*Kultur* | Re-tag resources with specific activities | Municipalities |
| 4 | Many low-use values | 295 names in one municipality only; 149 with 0 resources | Retire in the source systems after review | Municipalities |
| 5 | Booker/price categories in the activity field | *Offentlig / Privat / Frivillig organisasjon* ("Halv pris") | Move to a separate booker-type attribute | Product |
| 6 | Unclear values | e.g. *messe* (trade fair or church service?), *saltimer*, *kamera* | Ask the source owners | Reviewer |
| 7 | `Resource Count` not validated | Same export as issue 1 | Confirm it is counted per instance | Export / data team |

---

## 9. Governance (proposed)

- **Vocabulary owner:** one named person who approves new concepts and structural changes.
- **New source values** go into a review queue (status `Proposed`), not straight into search.
- **Versioning:** every export is tagged (v0.2, v0.3…). Concept IDs are never reused; deprecated concepts are marked, not deleted.
- **Lifecycle:** use `sist_sett` / activity status to flag values no longer seen in the source.
- **Later:** once the vocabulary is stable, move the master from Excel into the database tables (`concept`, `concept_label`, `source_mapping`, `external_match`) and generate the JSON from there.

---

## 10. Next steps

1. Review the high-impact values and all L/M rows in `Value_Mapping`.
2. Re-export the parent/child relations with an instance key (issue 1).
3. Agree on the facet model and the booker-type attribute with the product team.
4. Load the `--approved-only` export into a test environment and run `search_tests.json` against the real search engine.
5. Decide on nynorsk labels and fill `pref_label_nn`.
6. Plan re-tagging of resources that only have broad tags.

---

## Open questions for review

- Is **Venue** in scope for activity search, or should it live only on the resource model?
- Should **Target group** be a facet in its own right, or attributes (age, user group)?
- Should NIF be the **only** external code list, or should culture be linked to another standard as well?
- Which values with 0 resources should be retired, and who decides?
