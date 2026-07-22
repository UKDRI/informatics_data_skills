---
name: geo
description: >-
  Query metadata and download data from the NCBI Gene Expression Omnibus (GEO).
  Use when working with GEO accessions (GSE series, GSM samples, GPL platforms,
  GDS datasets) — to search GEO DataSets, fetch series/sample metadata, list
  supplementary/raw files, download series matrix, SOFT, MINiML, and
  supplementary files, build an nf-core/scrnaseq or nf-core/rnaseq samplesheet.csv
  from the linked SRA/ENA data, or download the SRA Run Selector files
  (SraRunTable.csv, SRR_Acc_List.txt). Triggers: "GEO", "GSE", "GSM", "gene
  expression omnibus", "series matrix", "GEO supplementary", "samplesheet",
  "rnaseq", "scrnaseq", "SraRunTable", "SRR_Acc_List", "SRA Run Selector".
---

# GEO (Gene Expression Omnibus)

NCBI's public repository for functional genomics data (microarray, RNA-seq, and
more). Metadata comes from NCBI **E-utilities** (`db=gds`); data files live on
the **GEO FTP tree** (`https://ftp.ncbi.nlm.nih.gov/geo/`).

## Accession types

| Prefix | Meaning | Example |
|--------|---------|---------|
| `GSE`  | Series (a study/experiment) | `GSE2553` |
| `GSM`  | Sample | `GSM12345` |
| `GPL`  | Platform (array/sequencer) | `GPL96` |
| `GDS`  | Curated DataSet | `GDS507` |

## Tooling

`scripts/geo.py` — standard-library Python (urllib), no dependencies.

```bash
python scripts/geo.py metadata GSE2553          # series summary
python scripts/geo.py samples  GSE2553          # list GSMs in the series
python scripts/geo.py files    GSE2553          # list FTP files (matrix/soft/miniml/suppl)
python scripts/geo.py download GSE2553 --matrix --out ./out   # series matrix
python scripts/geo.py download GSE2553 --suppl  --out ./out   # raw/supplementary
python scripts/geo.py search "breast cancer RNA-seq" --organism "Homo sapiens" --type gse
python scripts/geo.py samplesheet GSE110009 --assay scrna --out samplesheet.csv  # nf-core/scrnaseq
python scripts/geo.py samplesheet GSE110009 --assay bulk  --out samplesheet.csv  # nf-core/rnaseq
python scripts/geo.py metadata-table GSE2553 --out metadata.tsv     # harmonized sample table
python scripts/geo.py runtable GSE110009 --out .    # SraRunTable.csv + SRR_Acc_List.txt
```

Add `--json` to any query command for machine-readable output.

## SRA Run Selector files (`runtable`)

`runtable` reproduces the two files the
[SRA Run Selector](https://www.ncbi.nlm.nih.gov/Traces/study/) offers for a study:

- **`SraRunTable.csv`** — the full SRA `runinfo` table (run/experiment/sample
  accessions, library layout, platform, sizes, BioSample/BioProject, taxonomy, …).
- **`SRR_Acc_List.txt`** — the run accessions, one per line (the `Run` column).

It resolves the SRA study / BioProject linked to the GEO accession, then fetches
the table via E-utilities (`esearch` + `efetch db=sra rettype=runinfo`).

```bash
python scripts/geo.py runtable GSE110009 --out ./GSE110009
```

- `SRR_Acc_List.txt` feeds `prefetch`/`fasterq-dump` (SRA Toolkit); for ENA FASTQ
  URLs use `samplesheet` or the `ena` skill instead. To build an nf-core sample sheet
  whose fastq names match the `fasterq-dump` output, pass the `SraRunTable.csv` to
  `samplesheet --from-runtable` (see below).
- If the series has no SRA data (or it is controlled-access), the command reports
  it rather than writing empty files.

## Metadata table (metadata.tsv)

`metadata-table` writes the harmonized, tab-delimited `metadata.tsv` shared across
all repository skills: **one row per sample (GSM)** with the core columns
`sample, replicate, species, sex, age, condition, genotype, treatment, tissue`.
Species comes from `!Sample_organism_ch*`; the other core fields are matched from
each sample's `!Sample_characteristics_ch*` (`tag: value`) lines in its SOFT
record. Any further characteristic is **promoted to its own column** (header = core
columns + the union of extras across samples), so nothing is dropped. `replicate`
is a replicate characteristic when the submitter provides one, else `1`. **Missing
fields are `NA`.**

```bash
python scripts/geo.py metadata-table GSE2553 --out metadata.tsv
```

Note: this fetches one SOFT record per sample, so large series take a while.

## Samplesheet (nf-core/scrnaseq or /rnaseq)

GEO does not host raw reads — they live in SRA/ENA. `samplesheet` resolves the
SRA study / BioProject linked to a GEO series (from the series relations), pulls
the FASTQ links from ENA, and writes an nf-core sample sheet. **`--assay` is
required** — the archive can't tell you whether the study is single-cell or bulk:

- `--assay scrna` → [nf-core/scrnaseq](https://nf-co.re/scrnaseq/4.2.0/docs/usage/#samplesheet-input)
  columns `sample,fastq_1,fastq_2`.
- `--assay bulk` → [nf-core/rnaseq](https://nf-co.re/rnaseq/3.26.0/docs/usage#samplesheet-input)
  columns `sample,fastq_1,fastq_2,strandedness` (`--strandedness`, default `auto`).

```bash
python scripts/geo.py samplesheet GSE110009 --assay scrna              # ENA https URLs
python scripts/geo.py samplesheet GSE110009 --assay bulk --strandedness reverse
python scripts/geo.py samplesheet GSE110009 --assay scrna --local-dir ./fastq
```

- `--group-by` / `--local-dir` behave as in the `ena` skill.
- If the series has no public FASTQ in ENA (e.g. human data under dbGaP controlled
  access), the command reports that clearly — the reads are not downloadable here.
- Feed the resulting samplesheet to the `fastq-download-script` skill for a
  cluster download script.

### From a runtable (SRA Toolkit fastq names)

When you fetch reads with the SRA Toolkit (`prefetch` + `fasterq-dump` over
`SRR_Acc_List.txt`) instead of ENA, the local files are named by run accession.
`--from-runtable` builds the sample sheet **offline** from a local `SraRunTable.csv`
(from `runtable`) so the fastq columns match those filenames — single vs paired is
read from the table's `LibraryLayout` column:

- `SINGLE` → `fastq_1 = <dir>/SRRxxxxxxx.fastq`, `fastq_2` empty
- `PAIRED` → `fastq_1 = <dir>/SRRxxxxxxx_1.fastq`, `fastq_2 = <dir>/SRRxxxxxxx_2.fastq`

`--fastq-dir DIR` is required (it prefixes every fastq path). No ENA request is made.
In this mode `--group-by` names a runtable column (e.g. `SampleName`, `Sample`,
`Experiment`); the default falls back to `SampleName` → `Sample` → `Run`.

```bash
python scripts/geo.py runtable    GSE110009 --out ./GSE110009
# ... prefetch / fasterq-dump using ./GSE110009/SRR_Acc_List.txt -> ./fastq/ ...
python scripts/geo.py samplesheet GSE110009 --assay bulk \
    --from-runtable ./GSE110009/SraRunTable.csv --fastq-dir ./fastq
```

Download flags: `--matrix` (default), `--soft`, `--miniml`, `--suppl`. Combine as
needed; files land in `<out>/<ACCESSION>/<subdir>/`.

## Rate limits & auth

NCBI allows 3 requests/sec anonymously, 10/sec with an API key. All commands work
anonymously and **send no credentials by default**.

Credentials are **opt-in only**: even if `NCBI_EMAIL` / `NCBI_API_KEY` are set in
the environment, they are ignored unless you pass `--use-ncbi-credentials` on the
command — presence of the env vars is not consent (see the *No unsolicited
credentials* rule in `DESIGN.md`). Only supply them when you explicitly want to.

```bash
export NCBI_EMAIL="you@example.org"
export NCBI_API_KEY="..."          # optional, from NCBI account settings
python scripts/geo.py search "asthma" --use-ncbi-credentials   # opt in to send them
```

## How access works (for ad-hoc queries)

- **Search**: `esearch.fcgi?db=gds&term=<query>` → UID list.
- **Summary**: `esummary.fcgi?db=gds&id=<uid>&retmode=json`. Note GEO UIDs are not
  the accession: series UIDs are `200000000 + GSE number`.
- **Full metadata**: download the SOFT family file (`*_family.soft.gz`) or MINiML
  for complete per-sample characteristics — the esummary does not contain them.
- **FTP layout**: `geo/series/GSExxxnnn/GSE####/{matrix,soft,miniml,suppl}/` where
  the `xxxnnn` bucket masks the last three digits (e.g. `GSE2553` →
  `series/GSE2nnn/GSE2553/`). Samples use `geo/samples/…`, platforms `geo/platforms/…`.

## Notes

- Raw sequencing reads for RNA-seq series are usually **not** in GEO itself — they
  are in SRA/ENA. Use the `ena` skill with the linked `SRP`/`PRJNA` study accession
  (found in the series metadata `relations`) to fetch FASTQ files.
- The `GEOquery` R/Bioconductor package is the standard alternative for R users.
