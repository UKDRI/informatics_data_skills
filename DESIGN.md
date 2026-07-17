# Data Skills — Design

A collection of Claude Code **Agent Skills** for obtaining metadata and data from
public life-science data repositories, plus helpers that turn what they find into
pipeline-ready sample sheets and cluster download scripts.

## Purpose

Give an agent (or a human at the CLI) one consistent, dependency-free way to:

1. **Search** each repository and **fetch metadata** for an accession.
2. **List** and **download** the associated data files.
3. Produce **pipeline inputs** — nf-core/scrnaseq sample sheets, quantms/DIA-NN
   minimal SDRFs, and SLURM-ready bash download scripts.

Data sources covered:

| Skill | Repository | Operator |
|-------|------------|----------|
| `geo` | Gene Expression Omnibus | NCBI |
| `ena` | European Nucleotide Archive | EMBL-EBI |
| `pride` | PRIDE (proteomics identifications) | EMBL-EBI |
| `arrayexpress` | ArrayExpress (functional genomics) | EMBL-EBI (in BioStudies) |
| `biostudies` | BioStudies | EMBL-EBI |
| `fastq-download-script` | (generator, no external API) | — |

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
└── fastq-download-script/
    ├── SKILL.md
    └── scripts/make_download_script.py
```

One skill = one directory = one data source (or one generator). The directory
name is the skill `name`; `SKILL.md` frontmatter carries the trigger-rich
`description` used for skill selection.

## Conventions (apply to every skill)

- **Standard-library Python only** (`urllib`, `csv`, `json`, `argparse`, `re`).
  No `pip install`, no virtualenv — the scripts run anywhere Python 3 exists.
  This is a deliberate tradeoff: portability and zero-setup over the ergonomics
  of `requests`/`pandas`.
- **Self-contained scripts.** Skills do not import from each other. Small helpers
  (HTTP GET with retries, FASTQ R1/R2 pairing, SLURM header) are duplicated across
  scripts rather than shared, so any skill directory can be copied out and still work.
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

## Per-skill design

### geo (NCBI E-utilities + GEO FTP)
- **Metadata/search**: E-utilities `esearch`/`esummary` on `db=gds`. Resolves an
  accession to a UID, prefers the summary whose accession matches exactly.
- **Files/download**: GEO FTP tree. The bucket path masks the last three digits
  (`GSE2553` → `series/GSE2nnn/GSE2553/{matrix,soft,miniml,suppl}/`). Directory
  listings are scraped from the Apache HTML index (absolute/footer links filtered).
- **Honors** `NCBI_EMAIL` / `NCBI_API_KEY` env vars to lift rate limits.
- **Raw reads are not in GEO** — see the GEO→ENA bridge below.

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
- Pure transform: reads an nf-core/scrnaseq sample sheet (or a plain URL list)
  and emits a bash script. No network calls.

## Cross-cutting feature: sample sheets

Two distinct sample-sheet formats, chosen by domain:

### Sequencing → nf-core/scrnaseq (`geo`, `ena`, `arrayexpress`)
Columns `sample,fastq_1,fastq_2` per the
[nf-core/scrnaseq spec](https://nf-co.re/scrnaseq/4.2.0/docs/usage/#samplesheet-input).
One row per run; rows sharing a `sample` value are concatenated by the pipeline.

- **Pairing**: R1/R2 detected from filename (`_1`/`_2`, `R1`/`R2`); index reads
  (`_I1`, `_R3`, `_3`) are dropped; falls back to positional order.
- **`--group-by`** chooses which field becomes `sample` (default `sample_accession`).
- **`--local-dir`** emits local paths matching the `download` layout instead of URLs.

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

Two generators emit bash scripts with a **SLURM header** and **quiet** transfers
(no progress bars): `curl -fsSL --retry 3` or `wget -q --tries=3`.

- **`fastq-download-script`** — from a sample sheet's `fastq_*` URL columns (or a
  URL list). One command per file, grouped by `# sample:`. `--tool`, `--outdir`,
  `--no-slurm`, and SLURM flags (`--job-name`/`--partition`/`--account`/`--cpus`/
  `--mem`/`--time`/`--email`).
- **`pride download-script`** — directly from a project's `.raw`/`.zip` files.
  `--ext` filters by extension; `--unzip` appends `unzip` steps for `.zip`
  archives (e.g. Bruker `.d` directories). Same SLURM/tool options.

Typical pipeline:

```
ena samplesheet PRJEB1787 ─► samplesheet.csv
fastq-download-script samplesheet.csv --tool curl ─► download_fastq.sh ─► sbatch
```

## Key design decisions

1. **Stdlib-only** — maximizes portability for an agent that may run in an
   arbitrary environment; accepted cost is more verbose HTTP/CSV code.
2. **Self-contained skills over a shared library** — a skill must survive being
   copied out of the collection, so helpers are duplicated intentionally.
3. **ENA as the FASTQ hub** — GEO and ArrayExpress do not host raw reads, so both
   resolve to ENA. GEO uses the lightweight SOFT text endpoint
   (`acc.cgi?...&form=text&view=brief`) to find the linked BioProject/SRA rather
   than downloading the (large) series matrix.
4. **Two sample-sheet formats, not one** — sequencing and proteomics pipelines
   expect fundamentally different inputs; forcing one schema would be wrong for both.
5. **Complete rather than reject** — the PRIDE SDRF path fills gaps with reviewed
   placeholders so the output always validates, instead of failing when a
   submitter omitted columns.
6. **Endpoints verified live** — the API shapes were confirmed against the running
   services (PRIDE v3 paths, ENA field lists, BioStudies file tree) rather than
   assumed from memory, because these APIs drift.

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
