# Informatics Data Skills

A collection of [Claude Code](https://docs.claude.com/en/docs/claude-code) **Agent Skills** for obtaining metadata and data from public life-science data repositories — plus helpers that turn what they find into pipeline-ready sample sheets and cluster download scripts.

Each skill gives an agent (or a human at the CLI) one consistent, **dependency-free** way to:

1. **Search** each repository and **fetch metadata** for an accession.
2. **List** and **download** the associated data files.
3. Produce **pipeline inputs** — nf-core/scrnaseq sample sheets, quantms/DIA-NN minimal SDRFs, and SLURM-ready bash download scripts.

> [!NOTE]
> The scripts use the **Python 3 standard library only** — no `pip install`, no virtualenv. Any skill directory can be copied out on its own and still work.

## Skills

| Skill | Repository | Operator |
|-------|------------|----------|
| [`geo`](geo/) | Gene Expression Omnibus | NCBI |
| [`ena`](ena/) | European Nucleotide Archive | EMBL-EBI |
| [`pride`](pride/) | PRIDE (proteomics identifications) | EMBL-EBI |
| [`arrayexpress`](arrayexpress/) | ArrayExpress (functional genomics) | EMBL-EBI (in BioStudies) |
| [`biostudies`](biostudies/) | BioStudies | EMBL-EBI |
| [`fastq-download-script`](fastq-download-script/) | (generator, no external API) | — |

One skill = one directory = one data source (or one generator). The directory name is the skill `name`; `SKILL.md` frontmatter carries the trigger-rich `description` used for skill selection.

## Repository layout

```
informatics_data_skills/
├── DESIGN.md                 # design & architecture notes
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

## Quick start

Every script is a subcommand CLI you can run directly with Python 3 — no setup:

```bash
# Fetch metadata for a GEO series
python geo/scripts/geo.py metadata GSE2553

# List runs and FASTQ download links for an ENA study
python ena/scripts/ena.py runs PRJEB1787

# Fetch a PRIDE proteomics project's metadata
python pride/scripts/pride.py metadata PXD000001
```

Add `--json` to any query command for machine-readable output.

### End-to-end: study → sample sheet → cluster download script

```bash
# 1. Build an nf-core/scrnaseq samplesheet from an ENA study
python ena/scripts/ena.py samplesheet PRJEB1787 --out samplesheet.csv

# 2. Turn it into a quiet, SLURM-ready bash download script
python fastq-download-script/scripts/make_download_script.py samplesheet.csv --tool curl --out dl.sh

# 3. Submit it
sbatch dl.sh          # or: ./dl.sh
```

## Common commands per skill

<details>
<summary><strong>geo</strong> — NCBI Gene Expression Omnibus</summary>

```bash
python geo/scripts/geo.py metadata GSE2553                     # series summary
python geo/scripts/geo.py samples  GSE2553                     # list GSMs in the series
python geo/scripts/geo.py files    GSE2553                     # list FTP files
python geo/scripts/geo.py download GSE2553 --matrix --out ./out
python geo/scripts/geo.py search "breast cancer RNA-seq" --organism "Homo sapiens" --type gse
python geo/scripts/geo.py samplesheet GSE110009 --out samplesheet.csv
```

Raw reads are **not** in GEO — `samplesheet` resolves the linked SRA/BioProject and pulls FASTQ links from ENA. To lift rate limits, set `NCBI_EMAIL` / `NCBI_API_KEY` **and** pass `--use-ncbi-credentials` (opt-in; the env vars are ignored otherwise).
</details>

<details>
<summary><strong>ena</strong> — European Nucleotide Archive</summary>

```bash
python ena/scripts/ena.py runs PRJEB1787                       # runs + FASTQ FTP links
python ena/scripts/ena.py report PRJEB1787 --result read_run --fields run_accession,fastq_ftp,fastq_bytes
python ena/scripts/ena.py fields --result read_run             # list available fields
python ena/scripts/ena.py search --result read_run --query 'tax_eq(9606) AND library_strategy="RNA-Seq"' --limit 20
python ena/scripts/ena.py xml SAMEA1968848                     # raw record (XML/JSON/EMBL/FASTA)
python ena/scripts/ena.py download PRJEB1787 --out ./out
python ena/scripts/ena.py samplesheet PRJEB1787 --out samplesheet.csv
```

ENA is the canonical source of **FASTQ files**; the `geo` and `arrayexpress` skills route reads through it.
</details>

<details>
<summary><strong>pride</strong> — PRIDE proteomics identifications</summary>

```bash
python pride/scripts/pride.py metadata PXD000001               # project metadata
python pride/scripts/pride.py files    PXD000001 --ext raw     # only .raw files
python pride/scripts/pride.py download PXD000001 --ext mzid --out ./out
python pride/scripts/pride.py search   "phosphoproteome" --limit 20
python pride/scripts/pride.py samplesheet     PXD000561        # writes <acc>.sdrf.tsv
python pride/scripts/pride.py download-script PXD000561 --ext raw --out dl.sh
```

`samplesheet` writes a **minimal-valid SDRF** for [quantms/quantmsdiann](https://github.com/bigbio/quantmsdiann/blob/main/docs/usage.md#minimal-valid-metadata-example) (19 required columns, `.sdrf.tsv`). `download-script` emits a bash + SLURM script for the project's `.raw`/`.zip` files.
</details>

<details>
<summary><strong>arrayexpress</strong> — EMBL functional genomics (in BioStudies)</summary>

```bash
python arrayexpress/scripts/arrayexpress.py metadata E-MTAB-11448      # summary + file breakdown
python arrayexpress/scripts/arrayexpress.py files    E-MTAB-11448      # list files, classified
python arrayexpress/scripts/arrayexpress.py sdrf     E-MTAB-11448      # print the SDRF table
python arrayexpress/scripts/arrayexpress.py download E-MTAB-11448 --magetab --out ./out
python arrayexpress/scripts/arrayexpress.py search   "single cell heart" --limit 20
python arrayexpress/scripts/arrayexpress.py samplesheet E-MTAB-13991 --out samplesheet.csv
```

A collection inside BioStudies, with MAGE-TAB (IDF/SDRF) awareness. `samplesheet` parses the SDRF and falls back to ENA for any run missing a `FASTQ_URI`.
</details>

<details>
<summary><strong>biostudies</strong> — EMBL-EBI BioStudies</summary>

```bash
python biostudies/scripts/biostudies.py metadata S-BSST123             # study metadata
python biostudies/scripts/biostudies.py files    S-BSST123             # list attached files
python biostudies/scripts/biostudies.py download S-BSST123 --match .csv --out ./out
python biostudies/scripts/biostudies.py search   "spatial transcriptomics" --limit 20
python biostudies/scripts/biostudies.py search   "cancer" --collection BioImages
```

For the ArrayExpress functional-genomics collection (`E-MTAB` etc.), use the `arrayexpress` skill, which adds IDF/SDRF helpers on top of the same API.
</details>

<details>
<summary><strong>fastq-download-script</strong> — bash + SLURM generator</summary>

```bash
# From a samplesheet (default: wget, ./fastq, download_fastq.sh)
python fastq-download-script/scripts/make_download_script.py samplesheet.csv

# Choose curl, output dir, script name; tune the SLURM header
python fastq-download-script/scripts/make_download_script.py samplesheet.csv \
    --tool curl --outdir fastq --out dl.sh \
    --job-name ena_dl --partition short --time 12:00:00 --email you@org.ac.uk

# From a plain URL list, no SLURM header
python fastq-download-script/scripts/make_download_script.py urls.txt --urls --no-slurm
```

Pure transform — it only *writes* the script (one quiet `curl`/`wget` command per file). It does not download anything itself.
</details>

## Sample sheets

Two distinct formats, chosen by domain:

- **Sequencing → nf-core/scrnaseq** (`geo`, `ena`, `arrayexpress`): columns `sample,fastq_1,fastq_2` per the [nf-core/scrnaseq spec](https://nf-co.re/scrnaseq/4.2.0/docs/usage/#samplesheet-input), one row per run. R1/R2 are detected from the filename (`_1`/`_2`, `R1`/`R2`); index reads are dropped. `--group-by` chooses the `sample` field; `--local-dir` emits local paths instead of URLs.
- **Proteomics → quantms/quantmsdiann minimal SDRF** (`pride`): the 19 required columns, tab-delimited, `.sdrf.tsv` extension. The command either **completes** the submitter SDRF or **generates** one from the MS data files, then reports column coverage (`N/19`) and flags placeholder values that need review.

## Conventions

These apply to every skill (see [`DESIGN.md`](DESIGN.md) for the full rationale):

- **Standard-library Python only** (`urllib`, `csv`, `json`, `argparse`, `re`) — portability over ergonomics.
- **Self-contained scripts** — skills do not import from each other; small helpers are duplicated so any directory can be copied out and still work.
- **Subcommand CLIs** via `argparse` (`metadata`, `files`, `search`, `download`, …), with `--json` on query commands.
- **stdout = data, stderr = progress** — output can be piped.
- **Robust HTTP** — every request retries with backoff; downloads stream to a `.part` file then atomically rename, and skip files that already exist.
- **Clear failure** — controlled-access / missing-data cases raise an actionable `SystemExit` rather than producing an empty file.

## Verified endpoint reference

| Skill | Base / key endpoint |
|-------|---------------------|
| geo | `eutils.ncbi.nlm.nih.gov/entrez/eutils` (`db=gds`); `ftp.ncbi.nlm.nih.gov/geo/` |
| ena | `www.ebi.ac.uk/ena/portal/api/{filereport,search,returnFields}`; `.../browser/api/{xml,json,...}` |
| pride | `www.ebi.ac.uk/pride/ws/archive/v3/{projects,files,search}` |
| arrayexpress | `www.ebi.ac.uk/biostudies/api/v1` (`collection=ArrayExpress`); files at `/biostudies/files/{acc}/{path}` |
| biostudies | `www.ebi.ac.uk/biostudies/api/v1/{studies,search}` |

## Known limitations

- **Controlled-access data** (e.g. human reads under dbGaP) is not downloadable; the sample-sheet commands detect the empty ENA result and report it.
- **PRIDE generate-mode placeholders** (acquisition method, enzyme, tolerances, modifications, factor value) are best-effort guesses and must be reviewed before running quantms.
- **R1/R2 pairing** is filename-heuristic; unusual naming may need manual fixup, and 10x barcode/cDNA orientation should be confirmed for the chemistry.
- **Large studies** download sequentially; for scale, prefer ENA Aspera links or a SLURM job array over the generated per-file script.

## License

[MIT](LICENSE) © 2026 UK Dementia Research Institute
