# Data Skills — Design

A collection of Claude Code **Agent Skills** for obtaining metadata and data from
public life-science data repositories, plus helpers that turn what they find into
pipeline-ready sample sheets, cluster download scripts, and a data-portal
submission workbook.

## Purpose

Give an agent (or a human at the CLI) one consistent, mostly dependency-free way
(stdlib-only except `addi` — see *Conventions*) to:

1. **Search** each repository and **fetch metadata** for an accession.
2. **List** and **download** the associated data files.
3. Produce **pipeline inputs** — a harmonized `metadata.tsv` sample table,
   nf-core/scrnaseq or nf-core/rnaseq sample sheets, quantms/DIA-NN minimal SDRFs,
   SLURM-ready bash download scripts, and SRA-tools two-step SLURM job scripts.
4. Produce a **submission workbook** — fill the UK DRI FAIR-metadata Excel
   template for upload to the ADDI / AD Workbench data portal (`addi`).

Data sources covered:

| Skill | Repository | Operator |
|-------|------------|----------|
| `geo` | Gene Expression Omnibus | NCBI |
| `ena` | European Nucleotide Archive | EMBL-EBI |
| `pride` | PRIDE (proteomics identifications) | EMBL-EBI |
| `arrayexpress` | ArrayExpress (functional genomics) | EMBL-EBI (in BioStudies) |
| `biostudies` | BioStudies | EMBL-EBI |
| `fastq-download-script` | (generator, no external API) | — |
| `sra` | NCBI SRA, via sra-tools (generator, no external API) | — |
| `addi` | UK DRI FAIR-metadata workbook for the ADDI / AD Workbench portal (generator, no external API) | — |

## Repository layout

```
data_skills/
├── DESIGN.md                 # this file
├── geo/
│   ├── SKILL.md              # frontmatter (name/description triggers) + usage docs
│   └── scripts/geo.py        # standalone CLI
├── ena/
│   ├── SKILL.md
│   └── scripts/ena.py
├── pride/
│   ├── SKILL.md
│   └── scripts/pride.py
├── arrayexpress/
│   ├── SKILL.md
│   └── scripts/arrayexpress.py
├── biostudies/
│   ├── SKILL.md
│   └── scripts/biostudies.py
├── fastq-download-script/
│   ├── SKILL.md
│   └── scripts/make_download_script.py
├── sra/
│   ├── SKILL.md
│   ├── scripts/sra.py
│   └── templates/                # cluster-specific job-script boilerplate
│       ├── run_prefetch.sh
│       └── run_fasterq-dump.sh
└── addi/
    ├── SKILL.md
    ├── scripts/addi.py
    └── templates/                # the shipped ADDI submission workbook
        └── template_UK_DRI_FAIR_Metadata_w_ExtendedCatalogue_V1.2..xlsx
```

One skill = one directory = one data source (or one generator). The directory
name is the skill `name`; `SKILL.md` frontmatter carries the trigger-rich
`description` used for skill selection.

`sra` is the first skill with a **`templates/`** folder: it holds literal,
ready-to-edit SLURM job scripts carrying the UKDRI cluster specifics (partition,
the sra-tools apptainer image, bind mounts, the `pigz` loop). They are the source
of truth; the generator fills their `__TOKEN__` placeholders (see below). `addi`
follows the same template-backed idea for a different file type: its `templates/`
holds the shipped `.xlsx` submission workbook, which the generator opens and fills
in place (see *addi* below).

## Conventions (apply to every skill)

- **Standard-library Python only** (`urllib`, `csv`, `json`, `argparse`, `re`).
  No `pip install`, no virtualenv — the scripts run anywhere Python 3 exists.
  This is a deliberate tradeoff: portability and zero-setup over the ergonomics
  of `requests`/`pandas`. **One documented exception: `addi`.** It must read and
  write a richly-formatted `.xlsx` workbook (zipped XML with shared strings,
  styles, dropdown data-validations, and a hidden controlled-vocabulary sheet),
  which stdlib cannot do faithfully. It therefore depends on **openpyxl** (load and
  edit the shipped template in place, preserving its validations and colors) and
  **pandas** (ingesting the dictionaries/fields/lookups tables). `xlsxwriter` is
  deliberately *not* used: it can only create new workbooks, never edit an existing
  one, so it could not fill the template without rebuilding every sheet, validation
  and color from scratch — drifting from the exact file the portal expects.
- **Self-contained scripts.** Skills do not import from each other. Small helpers
  (HTTP GET with retries, FASTQ R1/R2 pairing, SLURM header) are duplicated across
  scripts rather than shared, so any skill directory can be copied out and still work
  once its dependencies are present (stdlib alone for every skill but `addi`, which
  also needs openpyxl/pandas).
- **Subcommand CLIs** via `argparse`: `metadata`, `files`, `search`, `download`
  are the common verbs; each skill adds source-specific ones.
- **`--json` flag** on query commands for machine-readable output; human-readable
  tabular text otherwise.
- **stdout = data, stderr = progress.** Downloads and generators print status to
  stderr and write payload to files or stdout, so output can be piped.
- **Robust HTTP**: every request retries with backoff; downloads stream in 1 MB
  chunks to a `.part` file then atomically rename, and skip files that already exist.
- **Clear failure**: controlled-access / missing-data / no-SDRF cases raise a
  `SystemExit` with an actionable message rather than producing an empty file.
- **No unsolicited credentials.** Never put an email address or any other user
  credential (API key, token, password) into a request or a generated file unless
  the **user explicitly asks for it in their prompt**. This is stricter than "only
  when mandatory": the credential's mere availability is **not** consent — even
  when it sits in the environment (`NCBI_EMAIL`, `NCBI_API_KEY`, …) or in a flag
  default, do not read, send, or embed it unless the user has explicitly told you
  to include it. No API used here requires one: the NCBI `email`/`api_key` only
  lift `geo`'s rate limit, and the SLURM `--email` (`fastq-download-script`,
  `pride`) is just a `--mail-user` notification address. When the user has not
  asked, omit the field entirely — never hardcode, default, infer, or
  opportunistically pull a credential from the environment.
- **Clean output fields.** Every value written into a generated file —
  `metadata.tsv`, `samplesheet.csv`, the PRIDE `.sdrf.tsv`, and the generated
  bash/SLURM download & job scripts — must be reduced to a single safe token: CR
  (`\r`), LF (`\n`), other control characters, and any literal **tab inside a
  value** are replaced with `_`, so no value can span lines, break a CSV/TSV row,
  or escape a shell comment / quoted argument. Ordinary spaces in free-text fields
  are preserved. A **tab is allowed only as the field separator** in the
  tab-delimited outputs (`metadata.tsv`, `.sdrf.tsv`) — never within a value. The
  nf-core `sample` column is normalized to a conservative filename/CLI-safe set
  (`[A-Za-z0-9._-]`): whitespace and unsafe/control characters → `_`, while the safe
  and meaningful `.` and `-` are kept — because it becomes file paths and pipeline
  rule names. Deliberately *not* stricter (`.`/`-` stripped would be overkill and
  would mangle real IDs). The generator warns when it rewrites a sample name, and —
  more importantly — **errors when two distinct inputs collapse to the same
  `sample`**, since nf-core concatenates rows sharing a `sample` value and would
  otherwise silently pool different biological samples. Every skill implements this
  at each field-write site — a duplicated `_safe_field` helper (control chars → `_`)
  and `_clean_val`, `clean_sample`/`finalize_sample_ids` for the `sample` column —
  on top of the structural quoting `csv.writer` gives the CSV/TSV outputs. For
  `addi` the rule adapts to the **xlsx cell model**: a newline inside a cell is
  legal and cannot break a row, so newlines are preserved; but values are still
  stripped of the control characters the OOXML format forbids, and any text value
  beginning with `=`, `+`, `-`, or `@` is prefixed with a leading apostrophe to
  neutralize spreadsheet formula injection.
- **Two ways to emit a SLURM script.** Most generators **string-build** the script
  (and its `#SBATCH` header) in Python from generic, commented-placeholder defaults
  (`fastq-download-script`, the `pride` download script). Where the script carries
  heavy **cluster-specific boilerplate** — apptainer `exec`, `.sif` image, bind
  mounts, a `pigz` loop — it instead lives as an editable file under the skill's
  `templates/` folder, and the generator does plain `__TOKEN__` substitution (`sra`).
  The template variant keeps the boilerplate readable and hand-editable; unflagged
  output is byte-identical to the committed template apart from the filled tokens.

## Per-skill design

### geo (NCBI E-utilities + GEO FTP)
- **Metadata/search**: E-utilities `esearch`/`esummary` on `db=gds`. Resolves an
  accession to a UID, prefers the summary whose accession matches exactly.
- **Files/download**: GEO FTP tree. The bucket path masks the last three digits
  (`GSE2553` → `series/GSE2nnn/GSE2553/{matrix,soft,miniml,suppl}/`). Directory
  listings are scraped from the Apache HTML index (absolute/footer links filtered).
- **Optional NCBI `email`/`api_key`** can lift rate limits, but per *No unsolicited
  credentials* they are sent **only when the user passes `--use-ncbi-credentials`**.
  The env vars `NCBI_EMAIL` / `NCBI_API_KEY` are read but ignored without that flag —
  their presence alone is never treated as consent.
- **Raw reads are not in GEO** — see the GEO→ENA bridge below.
- **SRA Run Selector**: `runtable` resolves the linked SRA study and writes
  `SraRunTable.csv` + `SRR_Acc_List.txt` via `efetch db=sra rettype=runinfo`
  (with `usehistory` so large studies work).

### ena (ENA Portal + Browser APIs)
- **Portal API** `filereport` / `search` / `returnFields` for run/experiment/
  analysis metadata and FASTQ links; `fastq_ftp` is a `;`-separated list.
- **Browser API** for raw records (XML/JSON/EMBL/FASTA).
- The canonical source of **FASTQ files**; other skills route reads through it.

### pride (PRIDE Archive REST API v3)
- Base `https://www.ebi.ac.uk/pride/ws/archive/v3`.
- `metadata` = `/projects/{acc}`; `files` = `/projects/{acc}/files` (paginated);
  each file's `publicFileLocations` yields the FTP URL (rewritten to HTTPS).
- Proteomics-specific extras: `samplesheet` (minimal SDRF) and `download-script`
  (see below).

### arrayexpress (BioStudies API, functional-genomics conventions)
- ArrayExpress is a **collection inside BioStudies**; access is the BioStudies API
  with `collection=ArrayExpress`.
- Adds MAGE-TAB awareness: file classification (`idf`/`sdrf`/`raw`/`processed`)
  using each file's own attributes then filename; an `sdrf` command; and a
  samplesheet builder that parses the SDRF.

### biostudies (BioStudies REST API v1)
- Base `https://www.ebi.ac.uk/biostudies/api/v1`.
- `metadata` = `/studies/{acc}` (PageTab JSON). Files are nested in the
  `section`/`subsections` tree as `type:"file"` entries; a recursive walker
  enumerates them. Download URL = `/biostudies/files/{acc}/{path}`.

### fastq-download-script (generator)
- Pure transform: reads an nf-core/scrnaseq or /rnaseq sample sheet (it keys off
  the `fastq_*` columns, so the extra `strandedness` column is ignored) or a plain
  URL list, and emits a bash script. No network calls.

### sra (generator, template-backed)
- The **NCBI SRA route** to FASTQ, complementary to the ENA hub: for runs not
  mirrored to ENA, or when pulling directly from NCBI via sra-tools.
- **Two sequential steps.** `run_prefetch.sh` downloads each SRR accession into
  `.sra` files; `run_fasterq-dump.sh` extracts those to FASTQ and `pigz`-compresses
  them. The prefetch output dir is wired to be the fasterq-dump input dir. The two
  must run in order; the generator only writes them and **never submits** — it
  prints the `sbatch --parsable` / `--dependency=afterok` serialization command.
- **Input** is a one-accession-per-line list — either an exact file path or a
  directory containing `SRR_Acc_List.txt`. Upstream skills own list creation:
  `geo runtable` writes `SRR_Acc_List.txt` directly; from `ena`, take the
  `run_accession` column of a `report`/`filereport` into a one-per-line list.
- For **ENA-hosted** runs this skill is the *alternative*, not the default — the
  recommended route is the direct FASTQ download script (`ena samplesheet` →
  `fastq-download-script`). Use `sra` when runs are not mirrored to ENA, or when the
  NCBI `prefetch`/`fasterq-dump` path is specifically wanted.
- **Image** defaults to the UKDRI `.sif`; `--sif PATH` overrides, or `--docker
  IMAGE` sets `sif=docker://IMAGE` so apptainer pulls it. The `apptainer exec` line
  is identical either way (apptainer accepts a `docker://` URI).
- Runs `scripts/sra.py job-scripts`, filling `templates/run_{prefetch,fasterq-dump}.sh`.

### addi (generator, template-backed — ADDI / AD Workbench FAIR-metadata workbook)
- Produces a **submission workbook** rather than querying a repository or building
  pipeline inputs — and, like `fastq-download-script` and `sra`, makes no network
  calls. It fills the shipped UK DRI FAIR-metadata Excel template
  (`templates/template_UK_DRI_FAIR_Metadata_w_ExtendedCatalogue_V1.2..xlsx`) that is
  uploaded to the ADDI / AD Workbench data portal. The workbook follows the
  Molgenis/EMX2-style catalogue-import layout (a catalogue plus a data dictionary).
- **Two halves of one workbook:**
  - *Catalogue metadata* — the dataset as a whole. `settings` (`visibility`,
    `workflow_key`, and the `allow_*`/`expose_*` toggles), `workspace_settings`
    (airlock/geography/owner/auto-approval), `catalogue` (a key/value block: `title`,
    `description`, `creator`, `contactPoint`, `license`, `versionInfo`, `keyword`,
    `identifier`, `accessRights`, `publisher_name`, `publisher_url`, `language`), and
    `extendedcatalogue` (a **form-style** block, rows 7–20: Study Data Language,
    Data Timepoints, Diseases, Study Types, Biomarkers, human-subjects toggle,
    participant countries, participant/biosample counts, sample types, Biobank,
    Organization, Logo, Data Types).
  - *Data dictionary / schema* — the actual tables and columns. `dictionaries` (one
    row per data table/file: `code`/`name`/`description`), `fields` (one row per
    variable: `dictionary_code`, `name`, `label`, `type`, `constraints`→lookup,
    `description`, `uri`, `entity`, `cohort_filter`), and `lookups` (the enumerated
    value sets referenced by `fields.constraints`).
- **Controlled vocabularies live in the hidden `Catalogue_Data` sheet** and are wired
  into the `extendedcatalogue` dropdowns via list data-validations (col A Study Data
  Language, B Diseases, C Study Types, D Biomarkers, E participant countries, F sample
  types, G Data Types, plus Federated-results and Access-Level columns). The skill
  **reads these from the template** rather than hardcoding them, so it never drifts
  from the shipped file.
- **Subcommands** (following the shared verb style):
  - `info` — describe the template: list its sheets, the mandatory fields
    (`catalogue` title/description/publisher_name; the `*`-marked `extendedcatalogue`
    fields), and dump each dropdown's allowed values (`--json` for machine output).
    Lets an agent discover valid inputs before filling.
  - `fill` — the core generator. Loads the template and writes user-supplied values
    into the exact cells, **preserving all dropdowns, prompts, colors, and the hidden
    vocab sheet**, then saves to `--out`. Inputs, in **increasing precedence**: an
    optional `--metadata metadata.tsv` seeds the schema (one `fields` row per column,
    `type` inferred) and descriptive catalogue / extendedcatalogue values (see below);
    a JSON/YAML `--config` supplies scalar catalogue / extendedcatalogue / settings
    values; and `--dictionaries` / `--fields` / `--lookups` (TSV or CSV, read with
    pandas) give the schema tables explicitly. Where they overlap, the explicit
    `--config` / `--dictionaries` / `--fields` / `--lookups` values override anything
    seeded from `--metadata`; the always-required user-attributed fields (below) come
    from `--config` (or an interactive prompt), never from `--metadata`. Multi-select
    (green) fields spread their values across the Value1..Value6 columns (**max 6**);
    single-value fields write only Value1 (col D); grey cells are never written. The
    template ships **pre-filled with example values** (`TITLE`/`DESCRIPTION`/…
    placeholders, sample dropdown selections) — `fill` overwrites placeholders and
    clears leftover examples so the output carries only user data. The exceptions are
    a few cells holding a genuine UK DRI **default** rather than an example: the
    `catalogue` `license`/`publisher_*`/`language`/`contactPoint` defaults, and the
    `extendedcatalogue` `Organization` and Logo (`URL`) fields — these are kept when
    the user provides no value, and cleared/overwritten only when the user does.
  - `validate` — check a filled workbook (or the inputs) against the template's rules
    without submitting.
  - All three commands accept `--template PATH` to target a different template file
    (default: the shipped V1.2 workbook).
- **Rules enforced** (from the README sheet + the embedded data-validations):
  mandatory fields present (the README's `title`/`description`/`publisher_name` and
  the `*`-marked `extendedcatalogue` fields, plus the always-required user-attributed
  fields below); dropdown values ∈ the `Catalogue_Data` vocab; `visibility`
  ∈ {private, internal}; catalogue/dictionary `code` = letters/numbers/underscore
  (dictionary `code` and field `name` additionally must not start with a number);
  field `type` ∈ {boolean, date, datetime, decimal, integer, text, time}; boolean
  fields carry no constraints; `fields.dictionary_code` resolves to a
  `dictionaries.code`; `fields.constraints` / `lookups.lookup` cross-reference;
  keywords comma-separated.
- **User-attributed fields are always required from the user.** `creator`
  (catalogue), `dataset owners` (workspace_settings), and `contactPoint` (catalogue)
  identify the people and party responsible for the dataset. The template's README
  marks only `title`/`description`/`publisher_name` as mandatory, but `addi` adds
  these three as a deliberate **exception to (addition beyond) the README's mandatory
  set**: they must always be filled from user-provided input, and the skill will not
  write the workbook until it has all three. The skill (and the agent driving it) must
  **never guess, infer, or auto-fill them** from the environment, the git identity,
  the user's email, or any prior context; if the user has not supplied all three,
  **ask for them before filling** rather than falling back to a default. In
  particular, the template's shared-org `contactPoint` placeholder
  (`ukdri-informatics@ukdri.ac.uk`) is **not** consent to keep or reuse it, and the
  user's personal email is never substituted in — this is the *No unsolicited
  credentials* rule applied to authorship/contact fields. `publisher_*` are ordinary
  defaults and may be kept unless the user overrides them.
- **Inputs are typically derived from a pre-generated `metadata.tsv`.** The normal
  workflow first runs one of the repository skills' `metadata-table` command (see
  below) to obtain the harmonized `metadata.tsv` for the study, then feeds it to
  `addi` (e.g. `fill --metadata metadata.tsv`) so the dictionary/fields and
  descriptive catalogue values are seeded from that table rather than typed by hand.
  The user-attributed fields above still come from the user, never from the table.
- **Generate, don't submit** — `fill` writes the workbook only; the skill never
  uploads to AD Workbench (mirrors `sra` and the download-script generators).

## Cross-cutting feature: harmonized metadata table

Every repository skill (`geo`, `ena`, `pride`, `arrayexpress`, `biostudies`)
exposes a **`metadata-table`** command that writes a **`metadata.tsv`** (default
`--out metadata.tsv`) — a single tab-delimited table that harmonizes each source's
native, differently-named sample annotations into one common schema. This is the
upstream, human-readable view of a study; the sample-sheet builders below — and the
`addi` submission workbook — consume the same underlying records.

- **One row per sample × replicate.** Each biological sample is emitted once per
  replicate (technical or biological, as the source reports them), so a study with
  three samples in duplicate produces six rows.
- **Tab-delimited**, `.tsv` extension, with a header row. Chosen over CSV because
  free-text annotation fields (condition, treatment, additional information)
  routinely contain commas. Field values are cleaned per **Clean output fields**
  above; the separator tab is the only tab.
- **Core columns, always present, in this order:**

  | Column | Meaning |
  |--------|---------|
  | `sample` | sample identifier / accession (source-native) |
  | `replicate` | replicate label or number within the sample |
  | `species` | organism, scientific name where available |
  | `sex` | sex of the organism |
  | `age` | age of the organism / at sampling |
  | `condition` | disease state or experimental condition |
  | `genotype` | genotype / strain |
  | `treatment` | treatment or perturbation applied |
  | `tissue` | sampled tissue / organism part |

- **Dynamic extra columns.** Any further characteristic obtained from a metadata
  query that does not map to a core field is **promoted to its own column** (name
  sanitised, e.g. `cell type` → `cell_type`). The header is the core columns
  followed by the union of every extra characteristic seen across the study's
  samples, so nothing is silently dropped and the width varies per study.
- **Missing → `NA`.** When a row has no value for a column — a core field the
  source omitted, or an extra column another sample contributed — the cell is the
  literal string `NA` rather than empty, so every row has the full column set and
  the table is unambiguous to parse.
- **BioSample enrichment.** When a sample identifier is a BioSample accession
  (`SAME*` / `SAMEA*` / `SAMN*` / `SAMD*`), the EBI BioSamples API
  (`/biosamples/samples/{acc}`) is queried to fill missing core fields and add its
  extra characteristics. GEO `GSM*` samples are resolved through GEO (SOFT), and
  ENA already carries this data in the sample XML, so neither issues a second call.

Each source maps its native metadata into this schema:

```
ena          filereport / sample XML characteristics ──► columns
geo          SOFT sample characteristics (Sample_characteristics_ch*) ──► columns
pride        project sample metadata / SDRF characteristics ──► columns
arrayexpress SDRF (Characteristics[...], FactorValue[...]) ──► columns
biostudies   PageTab section attributes ──► columns
```

Field names differ across repositories (e.g. `Characteristics[organism]`,
`sample_characteristics`, `organism`); each skill owns the mapping from its native
keys to the core columns and promotes every unmatched characteristic to its own
extra column.

## Cross-cutting feature: sample sheets

Two distinct sample-sheet formats, chosen by domain:

### Sequencing → nf-core (`geo`, `ena`, `arrayexpress`)
The `samplesheet` command targets one of two nf-core pipelines, selected with the
**required `--assay` flag** — the caller states whether the study is single-cell or
bulk, because it cannot be reliably inferred from the metadata:

- **`--assay scrna`** → nf-core/scrnaseq: columns `sample,fastq_1,fastq_2`
  ([spec](https://nf-co.re/scrnaseq/4.2.0/docs/usage/#samplesheet-input)).
- **`--assay bulk`** → nf-core/rnaseq: columns `sample,fastq_1,fastq_2,strandedness`
  ([spec](https://nf-co.re/rnaseq/3.26.0/docs/usage#samplesheet-input)). The extra
  `strandedness` column is set from `--strandedness` (one of
  `auto`/`forward`/`reverse`/`unstranded`, default `auto` — the pipeline infers it
  by subsampling), since the archives do not expose per-run strandedness.

One row per run; rows sharing a `sample` value are concatenated by the pipeline.

- **Pairing**: R1/R2 detected from filename (`_1`/`_2`, `R1`/`R2`); index reads
  (`_I1`, `_R3`, `_3`) are dropped; falls back to positional order.
- **`--group-by`** chooses which field becomes `sample` (default `sample_accession`).
- **`--local-dir`** emits local paths matching the `download` layout instead of URLs.
- **Field hygiene**: the `sample` value must be normalized to a conservative
  filename/CLI-safe set (`[A-Za-z0-9._-]`; whitespace and unsafe/control chars →
  `_`, keeping `.`/`-`), warning on rewrite and **erroring on a collision** (two
  distinct inputs → one `sample`, which the pipeline would silently concatenate).
  Every other field is cleaned per **Clean output fields** above — for the nf-core
  sheets and the PRIDE `.sdrf.tsv` alike.

Each source feeds the same builder differently:

```
ena          filereport(read_run) ─────────────► rows
geo          SOFT text ─► SRA/BioProject ─► ENA filereport ─► rows
arrayexpress SDRF (Source Name / ENA_RUN / FASTQ_URI) ─► rows
                          └─(no URI)─► ENA filereport per run ─► rows
```

### Proteomics → quantms/quantmsdiann minimal SDRF (`pride`)
Conforms to the
[minimal-valid-metadata definition](https://github.com/bigbio/quantmsdiann/blob/main/docs/usage.md#minimal-valid-metadata-example):
**19 required columns, in order, tab-delimited, `.sdrf.tsv` extension** (the
pipeline rejects `.sdrf`/`.tsv`/`.csv`). The command enforces the extension and
validates column coverage (`N/19`). Two sources via `--from`:

- **`auto`/`pride`** — download the submitter SDRF and *complete* it: append any
  missing minimal columns with defaults; keep extra submitter columns.
- **`auto` (no SDRF) / `generate`** — build a minimal SDRF from the MS data files,
  one row per file, enriched with `organism`/`disease`/`instrument` (as
  `NT=…;AC=MS:…` CV terms) from project metadata.

Placeholder defaults follow the documented example (label-free, Trypsin,
Carbamidomethyl fixed, 10 ppm / 20 ppm, DIA; `--acquisition dia|dda`). The command
warns which values are guesses and need review.

## Cross-cutting feature: download scripts

Two of the generators are **transfer-script** generators: they emit bash scripts
with a **SLURM header** and **quiet** transfers (no progress bars),
`curl -fsSL --retry 3` or `wget -q --tries=3`. Any value embedded in the script —
the `# sample:` / `# <category>:` comments and file names — must be cleaned per
**Clean output fields** above so that a newline in a free-text value cannot escape a
comment or quoted argument into an executable line.

- **`fastq-download-script`** — from a sample sheet's `fastq_*` URL columns (or a
  URL list). One command per file, grouped by `# sample:`. `--tool`, `--outdir`,
  `--no-slurm`, and SLURM flags (`--job-name`/`--partition`/`--account`/`--cpus`/
  `--mem`/`--time`/`--email`).
- **`pride download-script`** — directly from a project's `.raw`/`.zip` files.
  `--ext` filters by extension; `--unzip` appends `unzip` steps for `.zip`
  archives (e.g. Bruker `.d` directories). Same SLURM/tool options.

A third generator, **`sra`**, is a complementary FASTQ route rather than a transfer
script: instead of curl/wget over ENA URLs, it emits a two-step **sra-tools compute
job** (`prefetch` → `fasterq-dump`, run via apptainer) from an `SRR_Acc_List.txt`.
Use it for runs not mirrored to ENA or when pulling directly from NCBI. It is
template-backed (see `sra` above) and never submits.

Typical pipelines:

```
# ENA FASTQ — recommended default route (direct HTTPS download)
ena samplesheet PRJEB1787 ─► samplesheet.csv
fastq-download-script samplesheet.csv --tool curl ─► download_fastq.sh ─► sbatch

# NCBI SRA route — default for SRA-only data (e.g. via GEO), and the ENA alternative
geo runtable GSE110009 ─► SRR_Acc_List.txt
sra job-scripts --srr-list SRR_Acc_List.txt ─► run_prefetch.sh + run_fasterq-dump.sh ─► sbatch (in order)
```

## Key design decisions

1. **Stdlib-only** — maximizes portability for an agent that may run in an
   arbitrary environment; accepted cost is more verbose HTTP/CSV code. The single
   documented exception is `addi`, which needs openpyxl/pandas to fill the `.xlsx`
   template (see decision 10).
2. **Self-contained skills over a shared library** — a skill must survive being
   copied out of the collection, so helpers are duplicated intentionally.
3. **ENA as the FASTQ hub** — GEO and ArrayExpress do not host raw reads, so both
   resolve to ENA. GEO uses the lightweight SOFT text endpoint
   (`acc.cgi?...&form=text&view=brief`) to find the linked BioProject/SRA rather
   than downloading the (large) series matrix. For ENA-hosted data the recommended
   default is the FASTQ download script (`ena samplesheet` → `fastq-download-script`,
   direct HTTPS). The `sra` skill is the deliberate **alternative route**: for runs
   not mirrored to ENA, or when pulling straight from NCBI, it goes via sra-tools
   (`prefetch`/`fasterq-dump`) instead of ENA URLs.
4. **One harmonized metadata schema across all sources** — repositories name the
   same biological facts differently; mapping them to a shared core column set
   (with `NA` for absent fields) while promoting any further characteristic to its
   own column gives a uniform, parseable view without discarding source-specific
   detail. Sample IDs that are BioSamples are enriched from the EBI BioSamples API.
5. **Sample-sheet format follows the pipeline, not one fixed schema** — proteomics
   (quantms SDRF) and sequencing differ fundamentally, and within sequencing
   nf-core/scrnaseq and nf-core/rnaseq differ (the latter adds `strandedness`). The
   `samplesheet` command emits the format the chosen pipeline expects (`--assay`).
6. **Complete rather than reject** — the PRIDE SDRF path fills gaps with reviewed
   placeholders so the output always validates, instead of failing when a
   submitter omitted columns.
7. **Endpoints verified live** — the API shapes were confirmed against the running
   services (PRIDE v3 paths, ENA field lists, BioStudies file tree) rather than
   assumed from memory, because these APIs drift.
8. **Template-backed generation for cluster-specific tooling** — the `sra` job
   scripts carry UKDRI specifics (apptainer image, bind mounts, `pigz` loop) that
   read far better as an editable job script than as Python string fragments, so
   they live under `templates/` and the generator only substitutes tokens.
9. **Generate, don't submit; document serialization** — `sra` writes the two
   scripts and prints the `sbatch --dependency=afterok` command, but never runs
   `sbatch`. The prefetch→fasterq-dump ordering is enforced by the user (or that
   dependency); the tool only writes the scripts and never runs them, like the
   other script generators.
10. **Fill the template in place, don't rebuild it (`addi`)** — the workbook's
    dropdowns, per-cell prompts, cell colors and hidden controlled-vocabulary sheet
    are exactly what the ADDI importer and human reviewers expect. Editing the
    shipped template with openpyxl preserves all of it and keeps the vocabularies as
    a single source of truth read at runtime; regenerating with xlsxwriter would
    duplicate (and risk drifting from) the validations the template already encodes.
    This — not convenience — is why `addi` is the one skill permitted third-party
    dependencies. It is the xlsx analog of `sra`'s `__TOKEN__` substitution.

## Verified endpoint reference

| Skill | Base / key endpoint |
|-------|---------------------|
| geo | `eutils.ncbi.nlm.nih.gov/entrez/eutils` (`db=gds`); `ftp.ncbi.nlm.nih.gov/geo/` |
| ena | `www.ebi.ac.uk/ena/portal/api/{filereport,search,returnFields}`; `.../browser/api/{xml,json,...}` |
| pride | `www.ebi.ac.uk/pride/ws/archive/v3/{projects,files,search}` |
| arrayexpress | `www.ebi.ac.uk/biostudies/api/v1` (`collection=ArrayExpress`); files at `/biostudies/files/{acc}/{path}` |
| biostudies | `www.ebi.ac.uk/biostudies/api/v1/{studies,search}` |

## Adding a new skill

1. Create `<name>/SKILL.md` with `name` + a trigger-rich `description`.
2. Create `<name>/scripts/<name>.py`: stdlib-only, argparse subcommands, retrying
   HTTP GET, `--json` on queries, streamed downloads, stderr progress.
3. If it produces sequencing FASTQ, emit the nf-core/scrnaseq columns so the
   `fastq-download-script` skill can consume it.
4. Verify each subcommand against a live accession before documenting it.
5. If it emits a cluster script that is mostly fixed boilerplate, keep that script
   in a `templates/` folder with `__TOKEN__` placeholders and fill it by
   substitution (see `sra`) rather than string-building it in Python.

## Known limitations

- **Controlled-access data** (e.g. human reads under dbGaP) is not downloadable;
  the sample-sheet commands detect the empty ENA result and report it.
- **PRIDE generate-mode placeholders** (acquisition method, enzyme, tolerances,
  modifications, factor value) are best-effort guesses — PRIDE metadata does not
  expose per-run values — and must be reviewed before running quantms.
- **R1/R2 pairing** is filename-heuristic; unusual naming may need manual fixup,
  and 10x barcode/cDNA orientation should be confirmed for the chemistry.
- **Large studies** download sequentially; for scale, prefer ENA Aspera links or a
  SLURM job array over the generated per-file script.
- **`sra` job scripts** assume the compute node has `apptainer` and `pigz` and the
  UKDRI bind mounts (`/nfsdata,/data,/shared`); `--docker` pulls the image on first
  exec (pre-pull to a `.sif` for many accessions); controlled-access/dbGaP runs need
  NGC credentials that the generated scripts do not set up.
- **Output field hygiene** is a *cleaning* rule (offending characters replaced with
  `_`), not escape-encoding — a value containing a newline is made safe but not
  round-trippable, so a cleaned field cannot be mapped back to its original bytes.
  Download-script generators additionally **skip** (with a warning) any URL that
  contains a control character or a `"`, rather than emit it into the shell.
- **`addi` reads its vocabularies and rules from the shipped template**, so a newer
  portal template (e.g. V1.3+) may add fields or allowed values: point `--template`
  at the new file and re-run `info` to resync. The skill fills and validates the
  workbook but **never submits** it to AD Workbench, and it cannot confirm
  hub-specific settings — notably which `workflow_key` Data Access Requests are
  enabled on the target hub (README note 2) — which must be checked against that hub.
  Multi-select fields are capped at the template's **six** Value columns.
