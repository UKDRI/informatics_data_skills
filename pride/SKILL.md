---
name: pride
description: >-
  Query metadata and download data from the PRIDE Archive, EMBL-EBI's proteomics
  identifications database, via the PRIDE Archive REST API v3. Use when working
  with PRIDE/ProteomeXchange accessions (PXD, PRD) — to fetch project metadata,
  list project files (RAW, mzIdentML, mzML, mzTab, MGF, SDRF), download files,
  search projects by keyword, write the project's SDRF sample sheet, or generate a
  bash + SLURM script to download the project's .raw/.zip data files. Triggers:
  "PRIDE", "proteomics", "ProteomeXchange", "PXD", "mass spectrometry data",
  "mzid", "mzML", "RAW files proteomics", "SDRF", "download script proteomics".
---

# PRIDE (PRoteomics IDEntifications Database)

EMBL-EBI's repository for mass-spectrometry proteomics data and a core
ProteomeXchange member. Data lives under project accessions and is served by the
**PRIDE Archive REST API v3** (`https://www.ebi.ac.uk/pride/ws/archive/v3`).

## Accession types

| Prefix | Meaning |
|--------|---------|
| `PXD`  | ProteomeXchange dataset (most common) |
| `PRD`  | Legacy PRIDE accession |

## Tooling

`scripts/pride.py` — standard-library Python (urllib), no dependencies.

```bash
python scripts/pride.py metadata PXD000001              # project metadata
python scripts/pride.py files    PXD000001              # list all files + FTP URLs
python scripts/pride.py files    PXD000001 --ext raw    # only .raw files
python scripts/pride.py download PXD000001 --ext mzid --out ./out
python scripts/pride.py search   "phosphoproteome" --limit 20
python scripts/pride.py samplesheet     PXD000561                        # <acc>.sdrf.tsv
python scripts/pride.py download-script PXD000561 --ext raw --out dl.sh   # bash + SLURM script
```

Add `--json` to any query command for machine-readable output.

## Sample sheet (minimal SDRF)

`samplesheet` writes a **minimal-valid SDRF** (Sample and Data Relationship
Format) conforming to the
[quantms / quantmsdiann minimal metadata definition](https://github.com/bigbio/quantmsdiann/blob/main/docs/usage.md#minimal-valid-metadata-example):
the 19 required columns, tab-delimited, and — critically — the **`.sdrf.tsv`**
extension (quantms rejects `.sdrf`, `.tsv`, and `.csv`). The output name defaults
to `<accession>.sdrf.tsv`; any `--out` you pass has its extension corrected.

```bash
python scripts/pride.py samplesheet PXD000561                       # <acc>.sdrf.tsv
python scripts/pride.py samplesheet PXD000561 --from pride          # submitter SDRF only
python scripts/pride.py samplesheet PXD000001 --from generate --acquisition dda
```

Two sources, chosen with `--from` (default `auto`):

- **Submitter SDRF** (`auto`/`pride`) — downloads the project's SDRF from the
  `/files/sdrf/{accession}` endpoint and **completes** it: any of the 19 minimal
  columns that are absent are appended with sensible defaults, so the result
  always validates. Extra submitter columns are kept.
- **Generated** (`auto` when no SDRF exists, or `generate`) — builds a minimal
  SDRF from the project's MS data files (`.raw`/`.mzML`/`.d`/`.wiff`), one row per
  file, pulling `organism`, `disease`, and `instrument` (as `NT=…;AC=MS:…` CV
  terms) from the project metadata.

The command reports how many of the 19 columns are present and reminds you to
review placeholder values — **acquisition method** (`--acquisition dia|dda`),
instrument, precursor/fragment tolerances, cleavage agent, modification
parameters, organism part, and `factor value[condition]` — before running the
pipeline. Defaults follow the documented example (label-free, Trypsin,
Carbamidomethyl fixed, 10 ppm / 20 ppm, DIA).

## Download script (bash + SLURM)

`download-script` generates a runnable bash script (with a SLURM header) that
downloads the project's data files with one **quiet** `curl`/`wget` command per
file. PRIDE data files are typically vendor **`.raw`** files or **`.zip`**
archives (which for Bruker timsTOF data contain **`.d`** directories).

```bash
python scripts/pride.py download-script PXD000561 --ext raw --tool curl --out dl.sh
python scripts/pride.py download-script PXD040449 --ext zip --unzip --outdir pride_data
sbatch dl.sh        # or: ./dl.sh
```

- `--ext` filters by extension (`raw`, `zip`, `mzML`, …); omit to include everything.
- `--unzip` appends `unzip` steps for `.zip` archives (e.g. to unpack `.d` folders).
- `--tool` (`wget` default / `curl`), `--outdir`, `--out`, `--no-slurm`.
- SLURM header flags: `--job-name`, `--partition`, `--account`, `--cpus`, `--mem`,
  `--time`, `--email` (mirrors the `fastq-download-script` skill).
- Commands use no-progress-bar flags: `curl -fsSL` / `wget -q`.

## File types you'll see

- **RAW** — vendor raw instrument files (large; Thermo `.raw`, etc.)
- **mzML / mzXML** — open spectra formats
- **mzIdentML (`.mzid`)** — identification results
- **mzTab** — summary of identifications/quantification
- **MGF** — peak lists
- **SDRF (`.sdrf.tsv`)** — sample-to-data relationship / experimental design
- **PRIDE XML** — legacy combined format

## How access works (for ad-hoc queries)

- **Project metadata**: `GET /projects/{accession}` → title, protocols, organisms,
  instruments, diseases, PTMs, references, submission/publication dates.
- **Files**: `GET /projects/{accession}/files?pageSize=100&page=0` (paginated).
  Each file record's `publicFileLocations` lists FTP / Aspera / Globus URLs; the
  FTP one is under `ftp.pride.ebi.ac.uk/pride/data/archive/...`.
- **SDRF**: `GET /files/sdrf/{accession}` returns the experimental design table.
- **Search**: `GET /search/projects?keyword=<q>&pageSize=<n>` with facet filters
  (organism, instrument, disease, experiment type) available on the endpoint.
- **Single file**: `GET /files/{fileAccession}`.

## Notes

- FTP URLs are rewritten to HTTPS for downloading; `wget`/`curl` also work directly
  on the FTP links.
- The official `pridepy` Python client / CLI supports faster Aspera & Globus
  transfers for very large datasets.
- SDRF + a config file is the input to the standard `quantms` / SDRF-based
  reprocessing pipelines.
