---
name: ena
description: >-
  Query metadata and download sequencing data from the European Nucleotide
  Archive (ENA) via the ENA Portal and Browser APIs. Use when working with ENA/SRA
  accessions (PRJEB/PRJNA studies, ERR/SRR/DRR runs, ERX/SRX experiments,
  SAMEA/SAMN samples, ERZ analyses) — to list runs and FASTQ download links,
  build custom file reports, run advanced metadata searches, download FASTQ /
  submitted files, or generate an nf-core/scrnaseq or nf-core/rnaseq
  samplesheet.csv. Triggers: "ENA", "European Nucleotide Archive", "SRA", "FASTQ",
  "PRJEB", "PRJNA", "ERR", "SRR", "run accession", "filereport", "samplesheet",
  "rnaseq", "scrnaseq".
---

# ENA (European Nucleotide Archive)

EMBL-EBI's repository for nucleotide sequence data (reads, assemblies,
annotated sequences). It mirrors NCBI SRA, so SRA accessions (`SRR`, `SRP`,
`PRJNA`, `SAMN`) work here too. ENA is the fastest route to **FASTQ files** for
public RNA-seq / DNA-seq studies.

## Accession types

| Prefix | Meaning |
|--------|---------|
| `PRJEB` / `PRJNA` / `PRJDB` | Study / BioProject |
| `ERP` / `SRP` / `DRP` | Study (secondary) |
| `SAMEA` / `SAMN` / `SAMD` | Sample (BioSample) |
| `ERX` / `SRX` / `DRX` | Experiment |
| `ERR` / `SRR` / `DRR` | Run (holds the FASTQ files) |
| `ERZ` | Analysis (e.g. assemblies) |

## Tooling

`scripts/ena.py` — standard-library Python (urllib), no dependencies.

```bash
python scripts/ena.py runs PRJEB1787                 # runs + FASTQ FTP links
python scripts/ena.py report PRJEB1787 --result read_run --fields run_accession,fastq_ftp,fastq_bytes
python scripts/ena.py fields --result read_run       # list all available fields
python scripts/ena.py search --result read_run --query 'tax_eq(9606) AND library_strategy="RNA-Seq"' --limit 20
python scripts/ena.py xml SAMEA1968848               # raw record (XML/JSON/EMBL/FASTA)
python scripts/ena.py download PRJEB1787 --out ./out # download all FASTQ files
python scripts/ena.py samplesheet PRJEB1787 --assay scrna --out samplesheet.csv   # nf-core/scrnaseq
python scripts/ena.py samplesheet PRJEB1787 --assay bulk  --out samplesheet.csv   # nf-core/rnaseq
python scripts/ena.py metadata-table PRJEB1787 --out metadata.tsv   # harmonized sample table
```

Add `--json` to `runs`/`report`/`search` for JSON output.

## Metadata table (metadata.tsv)

`metadata-table` writes the harmonized, tab-delimited `metadata.tsv` shared across
all repository skills: **one row per sample × run (replicate)** with the core
columns `sample, replicate, species, sex, age, condition, genotype, treatment,
tissue`. Species comes from `scientific_name`; the other core fields are matched
from each sample's `SAMPLE_ATTRIBUTES` (fetched from the Browser API sample XML).
Any further characteristic that doesn't map to a core field is **promoted to its
own column** (header = core columns + the union of extras across samples), so
nothing is dropped. **Missing fields are `NA`.**

```bash
python scripts/ena.py metadata-table PRJEB1787 --out metadata.tsv
```

## Samplesheet (nf-core/scrnaseq or /rnaseq)

`samplesheet` writes an nf-core sample sheet, one row per run, with
`fastq_1`/`fastq_2` resolved to the ENA FASTQ URLs (paired reads matched by
`_1`/`_2` / `R1`/`R2`). Runs from the same sample share the `sample` value so the
pipeline concatenates them. **`--assay` is required** — the archive can't tell you
whether the study is single-cell or bulk:

- `--assay scrna` → [nf-core/scrnaseq](https://nf-co.re/scrnaseq/4.2.0/docs/usage/#samplesheet-input)
  columns `sample,fastq_1,fastq_2`.
- `--assay bulk` → [nf-core/rnaseq](https://nf-co.re/rnaseq/3.26.0/docs/usage#samplesheet-input)
  columns `sample,fastq_1,fastq_2,strandedness`. Set `--strandedness`
  (`auto`/`forward`/`reverse`/`unstranded`, default `auto`; `auto` lets the
  pipeline infer it).

```bash
python scripts/ena.py samplesheet PRJEB1787 --assay scrna                  # ENA https URLs
python scripts/ena.py samplesheet PRJEB1787 --assay bulk --strandedness reverse
python scripts/ena.py samplesheet PRJEB1787 --assay scrna --group-by sample_title
python scripts/ena.py samplesheet PRJEB1787 --assay bulk --local-dir ./ena_out/PRJEB1787
```

- `--group-by` chooses which run field becomes `sample` (default
  `sample_accession`; also `sample_alias`, `sample_title`, `experiment_accession`).
- `--local-dir` writes local paths `<dir>/<run>/<file>` (matching `download`
  output) instead of URLs.
- `expected_cells` / `seq_center` are optional scrnaseq columns; add them by hand
  if needed. Check that `fastq_1` (barcodes) and `fastq_2` (cDNA) are the right way
  round for your 10x chemistry.
- **Recommended route to FASTQ**: turn the URL samplesheet into a cluster download
  script with the `fastq-download-script` skill (direct HTTPS download of the ENA
  FASTQ files). Prefer this for ENA-hosted data.
- *Alternative*: pull the same runs from NCBI with sra-tools instead — feed a
  `run_accession` list (`report --result read_run --fields run_accession`) to the
  `sra` skill. Use only when the ENA download is unsuitable (e.g. runs not mirrored
  to ENA, or you specifically want the NCBI `prefetch`/`fasterq-dump` path).

## How access works (for ad-hoc queries)

- **File report** (metadata + download links for a known accession):
  `https://www.ebi.ac.uk/ena/portal/api/filereport?accession=<ACC>&result=read_run&fields=<...>&format=tsv`
  The `fastq_ftp` field is a `;`-separated list of FTP paths (prepend `https://`
  to download over HTTPS). `fastq_md5` / `fastq_bytes` line up positionally for
  integrity checks.
- **Result types** (`--result`): `read_run` (FASTQ), `read_experiment`,
  `analysis` (assemblies/variants), `assembly`, `sample`, `study`, `sequence`,
  `wgs_set`, `taxon`.
- **Return fields**: list them with
  `filereport`/`search` → `returnFields?result=read_run` before crafting `--fields`.
- **Advanced search**: `search?result=read_run&query=<expr>&fields=<...>` with a
  query language, e.g. `tax_tree(9606)`, `country="United Kingdom"`,
  `first_created>=2023-01-01`, `library_strategy="WGS"`.
- **Raw records**: Browser API `https://www.ebi.ac.uk/ena/browser/api/{xml|json|embl|fasta}/<ACC>`.

## Download tips

- Files download over HTTPS from `ftp.sra.ebi.ac.uk`. For large studies, **Aspera**
  (`fasp` links via `--fields fastq_aspera`) or the official `enaBrowserTools`
  (`enaDataGet`, `enaGroupGet`) are faster; `wget`/`curl` on the FTP links also work.
- `--submitted` fetches the originally submitted files (e.g. BAM/CRAM) instead of
  ENA-generated FASTQ.
- Always verify downloads against `fastq_md5`.
