---
name: addi
description: >-
  Fill the UK DRI FAIR-metadata Excel workbook for a data submission to the ADDI /
  AD Workbench data portal (AD Data Initiative). Use when preparing a catalogue +
  data-dictionary submission: describe the study (catalogue / extendedcatalogue,
  settings, workspace_settings) and its data tables (dictionaries, fields, lookups),
  validate against the template's controlled vocabularies and rules, and write a
  filled .xlsx — optionally seeding the schema from a pre-generated metadata.tsv.
  Produces files only; never uploads. Triggers: "ADDI", "AD Workbench", "AD Data
  Initiative", "FAIR metadata", "data portal submission", "submission workbook",
  "catalogue", "extendedcatalogue", "data dictionary", "dictionaries", "fields",
  "lookups", "UK DRI FAIR Metadata".
---

# ADDI / AD Workbench submission-workbook filler

Fills the shipped UK DRI FAIR-metadata Excel template in
`templates/template_UK_DRI_FAIR_Metadata_w_ExtendedCatalogue_V1.2..xlsx` and writes a
ready-to-submit workbook for the ADDI / AD Workbench data portal. It only *writes* the
file — it never uploads or submits anything.

The template follows the Molgenis/EMX2 catalogue-import layout and has two halves:

- **Catalogue metadata** — the dataset as a whole: `catalogue` (title, description,
  creator, contactPoint, license, keyword, identifier, publisher_*, language),
  `extendedcatalogue` (diseases, study types, biomarkers, participant counts, sample
  types, data types, …), `settings` (visibility, workflow_key, toggles) and
  `workspace_settings` (airlock/geography/owners/auto-approval).
- **Data dictionary** — the actual data tables and columns: `dictionaries` (one row
  per table), `fields` (one row per variable) and `lookups` (enumerated value sets).

The controlled vocabularies for the `extendedcatalogue` dropdowns live in a hidden
`Catalogue_Data` sheet; the skill reads them from the template (never hardcodes them).

## Fidelity — the template is edited in place

The workbook carries dropdown data-validations (some referencing `Catalogue_Data`),
cell colors, per-cell prompts, threaded comments and a document sensitivity label.
`fill` preserves **all** of it: it copies every part of the original workbook verbatim
and rewrites only the cells it changes (as inline strings, so the shared-strings table
is untouched). The output differs from the template only in the values you supplied.

## Responsible-party fields — default to UK DRI, but ask

`creator` (catalogue), `contactPoint` (catalogue) and `dataset owners`
(workspace_settings) identify the people and party responsible for the dataset. Each may
be left out, in which case the template's UK DRI value is kept and a `WARN` says so:

| Field | Kept default |
|-------|--------------|
| `catalogue.creator` | `UK Dementia Research Institute` |
| `catalogue.contactPoint` | `ukdri-informatics@ukdri.ac.uk` |
| `workspace_settings.dataset owners` | `UK Dementia Research Institute` |

They do **not** block the write. But **ask the user whether these should be changed**
before filling, and tell them which defaults you kept — silently shipping the
institutional default is the failure mode to avoid.

**Never guess a person.** These are never derived from the environment, a git identity,
or the user's own email address. The only permitted fallback is the template's own
institutional value — that is why `contactPoint` falls back to the shared-org address and
never to the user's personal one. Run `info` to see the current defaults.

## Tooling

`scripts/addi.py` — Python, requires **openpyxl** and **pandas** (this is the one
skill in the collection that is not stdlib-only; see DESIGN.md).

### `info` — discover the template's fields and vocabularies

```bash
python scripts/addi.py info              # human-readable summary
python scripts/addi.py info --json       # full machine-readable dump (all allowed values)
```

Lists the sheets, the mandatory catalogue fields, the responsible-party fields with the
defaults that would be kept, the sample-type overflow cell, every `extendedcatalogue`
field (mandatory/kind/multi-select) and each dropdown's full allowed-value list. Run this
first to learn valid inputs.

### `fill` — write a submission workbook

```bash
python scripts/addi.py fill \
    --config catalogue.json \
    --dictionaries dicts.tsv --fields fields.tsv --lookups lookups.tsv \
    --out UK_DRI_FAIR_Metadata_filled.xlsx
```

### `validate` — check inputs or a filled workbook

```bash
python scripts/addi.py validate --config catalogue.json --fields fields.tsv    # inputs
python scripts/addi.py validate --workbook UK_DRI_FAIR_Metadata_filled.xlsx     # a filled file
```

`fill` runs the same validation first and refuses to write on any ERROR.

## Inputs

### `--config` (JSON, or YAML if PyYAML is installed)

Scalar catalogue / extendedcatalogue / settings / workspace_settings values. Keys match
the template field names (case- and parenthetical-insensitive, so `"Study Data
Language"` matches `*Study Data Language (Multi-select)`). Multi-select fields take a
list (max 6 values, spread across the Value1..Value6 columns); single-value fields take
a scalar.

Unprovided `extendedcatalogue` fields have their shipped example values cleared —
**except `Organization` and `Logo` (URL)**, which fall back to the template's UK DRI
defaults (`UK Dementia Research Institute` and `www.ukdri.ac.uk`) unless you override
them. On the `catalogue` sheet the ALL-CAPS placeholders (`TITLE`, `IDENTETIFIER`, …) are
cleared when unprovided, while the genuine UK DRI defaults are kept:
`license`, `publisher_name`, `publisher_url`, `language`, `contactPoint`, `creator`,
`accessRights`.

Two keys have rules worth knowing:

- **`identifier` — a DOI, or blank.** `10.5281/zenodo.123456`, `doi:10.…` and
  `https://doi.org/10.…` are all accepted and normalized to the canonical
  `https://doi.org/10.…` (with a `WARN` naming the rewrite). A repository accession such
  as `GSE123456` is an **ERROR** — this field is for a citable dataset DOI, not the source
  accession. Leave it out if the dataset has no DOI.
- **`accessRights` — optional, free text.** Blank is valid; the template's
  `non-commercial use` is kept when you supply nothing.

```json
{
  "catalogue": {
    "title": "UK DRI Multi-omics Dementia Cohort",
    "description": "Bulk RNA-seq and clinical data from a dementia cohort.",
    "creator": "Jane Doe; John Smith",
    "contactPoint": "data-team@example.ac.uk",
    "keyword": "dementia, RNA-seq, clinical",
    "identifier": "https://doi.org/10.5281/zenodo.123456",
    "accessRights": "non-commercial use",
    "publisher_name": "UK DRI"
  },
  "workspace_settings": { "dataset owners": "pi-alice@example.ac.uk", "auto_approved": "no" },
  "settings": { "visibility": "internal" },
  "extendedcatalogue": {
    "Study Data Language": ["English"],
    "Diseases": ["Alzheimer's Disease", "Vascular Dementia"],
    "Study Types": ["Observational", "Longitudinal"],
    "Data on human research participants": "Yes",
    "Number of Research Participants": 240,
    "Data Types": ["Clinical", "Omics - Transcriptomics"]
  }
}
```

### `--dictionaries` / `--fields` / `--lookups` (TSV or CSV)

The data-dictionary tables. Column headers match the template sheets:

- **dictionaries**: `code, name, description`
- **fields**: `dictionary_code, name, label, type, constraints, description, uri, entity, cohort_filter`
- **lookups**: `lookup, name, description, uri`

Providing a table (even an empty one, header only) replaces the template's example rows.
**Omitting a table leaves that sheet untouched — the template's `test_demographics` /
`SEX` example rows stay in the output**, so pass every sheet you care about, or seed them
from `--metadata`. `type` must be one of `boolean, date, datetime, decimal, integer, text,
time`; `entity`/`cohort_filter` are booleans; `constraints` references a `lookups.lookup`.

### `--metadata metadata.tsv` (optional, lowest precedence)

Seeds the data dictionary from a harmonized `metadata.tsv` (from the `geo`/`ena`/`pride`/…
skills' `metadata-table` command) — **all three schema tables**:

- **dictionaries** — one row for the table (`--metadata-dict-code`, default
  `sample_metadata`).
- **fields** — one row per column, `type` inferred, `constraints` pointing at the column's
  lookup where one was derived.
- **lookups** — from each **categorical column's unique values**. A column qualifies when
  its inferred type is `text`, it has 2…`--lookup-max-values` (default 20) distinct
  non-`NA` values, that count is below the row count (so free-text columns are skipped),
  and it is not `sample`/`sample_id`/`id`/`replicate`. The lookup name is the column name
  upper-cased (`condition` → `CONDITION`).

It also seeds `Number of Biosamples` and the **sample types** — from the `tissue` column,
falling back to `sample_type` / `source_name`. Values are matched case-insensitively
against the template's 11 terms; anything unmatched goes to the `J16` overflow cell
(below).

**Precedence:** `--metadata` (lowest) < `--config` < explicit
`--dictionaries`/`--fields`/`--lookups`; an explicit `--lookups` replaces the seeded set
wholesale (which may leave seeded `constraints` dangling — a `WARN` tells you). Every
seeded value is printed as `WARN` — a lookup recovered this way only holds the values
present in that one table, so review it for completeness. The responsible-party fields are
never taken from metadata.

## The `J16` overflow cell

*Type of Sample From Which Data Were Derived* (row 16) has only 11 allowed terms (Blood,
Brain tissue, CSF, DNA (Genomic), Stool, iPSC, Peripheral blood, Plasma, RNA (Genomic),
Serum from blood, Urine). A value matching none of them is **not an error**: the skill
warns you, listing the allowed terms, and writes the proposed term into **`J16`** — the
cell just past `Value6`, which has no dropdown attached. Several such values are
comma-separated into that one cell, and the matched terms still fill `Value1..Value6`.

`J16` is exempt from vocabulary validation; a filled workbook with a non-empty `J16`
validates with a `WARN`. **Tell the user** which term was parked there — it is a proposal
the ADDI importer may ignore, so a genuinely new sample type still has to be raised with
ADDI. Every *other* dropdown still hard-errors on an out-of-vocabulary value.

## Validation rules enforced

- catalogue `title`/`description`/`publisher_name` present (README note 4)
- `identifier` is a DOI or blank; `accessRights` unconstrained (addi rules)
- `creator`, `contactPoint`, `dataset owners` → `WARN` + UK DRI default if absent, never
  an ERROR (addi rule)
- `extendedcatalogue` `*` fields present; dropdown values ∈ the `Catalogue_Data` vocab
  (except the row-16 sample-type overflow into `J16`, which only `WARN`s);
  multi-selects ≤ 6; single fields single-valued; integer fields numeric
- `settings.visibility` ∈ {private, internal} (README note 1)
- dictionary `code` / field `name` = letters/numbers/underscore, not starting with a
  number (README notes 3, 8, 10); field `type` ∈ the allowed set (11); boolean fields
  carry no constraints (12); `fields.dictionary_code` resolves to a `dictionaries.code`
  (9); `fields.constraints` references a `lookups.lookup` (13)

## Options

| Flag | Command | Meaning |
|------|---------|---------|
| `--template` | all | template `.xlsx` (default: shipped V1.2 workbook) |
| `--json` | info | full machine-readable dump |
| `--config` | fill/validate | JSON/YAML scalar values |
| `--dictionaries`/`--fields`/`--lookups` | fill/validate | schema tables (TSV/CSV) |
| `--metadata` | fill | seed dictionaries/fields/lookups from a metadata.tsv (lowest precedence) |
| `--metadata-dict-code` | fill | dictionary code for the metadata-seeded table (`sample_metadata`) |
| `--lookup-max-values` | fill | max distinct values for a column to become a lookup (`20`) |
| `--out` | fill | output workbook (`UK_DRI_FAIR_Metadata_filled.xlsx`) |
| `--workbook` | validate | validate a filled `.xlsx` instead of raw inputs |

## Notes

- **Never submits.** The skill writes the workbook; upload to AD Workbench is manual.
- **Dropdown values are written in the vocabulary's own casing**, so `"diseases":
  ["dementia"]` lands in the cell as `Dementia` and satisfies the data-validation.
- **Report every `WARN` to the user** — kept defaults, seeded lookups, a `J16` proposal and
  a normalized DOI are all things they need to confirm before submitting.
- **`workflow_key` is hub-specific.** Which Data Access Requests are enabled depends on
  the target hub (README note 2) and cannot be verified here — confirm it against the hub.
- **A newer portal template** (V1.3+) may add fields or values: point `--template` at the
  new file and re-run `info` to resync — vocabularies and rules are read from the template.
- **Output hygiene (xlsx):** newlines inside a cell are kept; control characters the OOXML
  format forbids are stripped; and text beginning with `=`, `+`, `-` or `@` is prefixed
  with an apostrophe to neutralize spreadsheet formula injection.
