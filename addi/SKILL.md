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

## You must always provide these — they are never guessed

`creator` (catalogue), `contactPoint` (catalogue) and `dataset owners`
(workspace_settings) identify the people and party responsible for the dataset. The
skill **refuses to write the workbook** unless you supply all three; it will never
infer them from the environment, a git identity, or an email address. If they are not
in your prompt, **ask the user for them first.** (The template's shared-org
`contactPoint` placeholder is not consent to reuse it.)

## Tooling

`scripts/addi.py` — Python, requires **openpyxl** and **pandas** (this is the one
skill in the collection that is not stdlib-only; see DESIGN.md).

### `info` — discover the template's fields and vocabularies

```bash
python scripts/addi.py info              # human-readable summary
python scripts/addi.py info --json       # full machine-readable dump (all allowed values)
```

Lists the sheets, the mandatory catalogue fields, the always-required user-attributed
fields, every `extendedcatalogue` field (mandatory/kind/multi-select) and each
dropdown's full allowed-value list. Run this first to learn valid inputs.

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
them.

```json
{
  "catalogue": {
    "title": "UK DRI Multi-omics Dementia Cohort",
    "description": "Bulk RNA-seq and clinical data from a dementia cohort.",
    "creator": "Jane Doe; John Smith",
    "contactPoint": "data-team@example.ac.uk",
    "keyword": "dementia, RNA-seq, clinical",
    "identifier": "GSE123456",
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

Providing a table replaces the template's example rows; omitting one clears its example
rows (leaving just the header). `type` must be one of `boolean, date, datetime, decimal,
integer, text, time`; `entity`/`cohort_filter` are booleans; `constraints` references a
`lookups.lookup`.

### `--metadata metadata.tsv` (optional, lowest precedence)

Seeds the schema from a harmonized `metadata.tsv` (from the `geo`/`ena`/`pride`/… skills'
`metadata-table` command): one `fields` row per column with `type` inferred, under a
single dictionary (`--metadata-dict-code`, default `sample_metadata`), plus a best-effort
`Number of Biosamples`. **Precedence:** `--metadata` (lowest) < `--config` < explicit
`--dictionaries`/`--fields`/`--lookups`. Seeded/guessed values are printed as `WARN` —
review them. The always-required user-attributed fields are never taken from metadata.

## Validation rules enforced

- catalogue `title`/`description`/`publisher_name` present (README note 4)
- `creator`, `contactPoint`, `dataset owners` present (addi rule — always from the user)
- `extendedcatalogue` `*` fields present; dropdown values ∈ the `Catalogue_Data` vocab;
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
| `--metadata` | fill | seed schema from a metadata.tsv (lowest precedence) |
| `--metadata-dict-code` | fill | dictionary code for the metadata-seeded table (`sample_metadata`) |
| `--out` | fill | output workbook (`UK_DRI_FAIR_Metadata_filled.xlsx`) |
| `--workbook` | validate | validate a filled `.xlsx` instead of raw inputs |

## Notes

- **Never submits.** The skill writes the workbook; upload to AD Workbench is manual.
- **`workflow_key` is hub-specific.** Which Data Access Requests are enabled depends on
  the target hub (README note 2) and cannot be verified here — confirm it against the hub.
- **A newer portal template** (V1.3+) may add fields or values: point `--template` at the
  new file and re-run `info` to resync — vocabularies and rules are read from the template.
- **Output hygiene (xlsx):** newlines inside a cell are kept; control characters the OOXML
  format forbids are stripped; and text beginning with `=`, `+`, `-` or `@` is prefixed
  with an apostrophe to neutralize spreadsheet formula injection.
