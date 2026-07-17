---
name: ena
description: >-
  Query metadata and download sequencing data from the European Nucleotide
  Archive (ENA) via the ENA Portal and Browser APIs. Use when working with ENA/SRA
  accessions (PRJEB/PRJNA studies, ERR/SRR/DRR runs, ERX/SRX experiments,
  SAMEA/SAMN samples, ERZ analyses) — to list runs and FASTQ download links,
  build custom file reports, run advanced metadata searches, download FASTQ /
  submitted files, or generate an nf-core/scrnaseq samplesheet.csv. Triggers:
  "ENA", "European Nucleotide Archive", "SRA", "FASTQ", "PRJEB", "PRJNA", "ERR",
  "SRR", "run accession", "filereport", "samplesheet".
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
python scripts/ena.py samplesheet PRJEB1787 --out samplesheet.csv   # nf-core/scrnaseq sheet
```

Add `--json` to `runs`/`report`/`search` for JSON output.

## Samplesheet (nf-core/scrnaseq)

`samplesheet` writes a CSV with the columns
[nf-core/scrnaseq](https://nf-co.re/scrnaseq/4.2.0/docs/usage/#samplesheet-input)
expects — `sample,fastq_1,fastq_2` — one row per run, with `fastq_1`/`fastq_2`
resolved to the ENA FASTQ URLs (paired reads matched by `_1`/`_2` / `R1`/`R2`).
Runs from the same sample share the `sample` value so the pipeline concatenates them.

```bash
python scripts/ena.py samplesheet PRJEB1787                       # ENA https URLs
python scripts/ena.py samplesheet PRJEB1787 --group-by sample_title
python scripts/ena.py samplesheet PRJEB1787 --local-dir ./ena_out/PRJEB1787
```

- `--group-by` chooses which run field becomes `sample` (default
  `sample_accession`; also `sample_alias`, `sample_title`, `experiment_accession`).
- `--local-dir` writes local paths `<dir>/<run>/<file>` (matching `download`
  output) instead of URLs.
- `expected_cells` / `seq_center` are optional scrnaseq columns; add them by hand
  if needed. Check that `fastq_1` (barcodes) and `fastq_2` (cDNA) are the right way
  round for your 10x chemistry.
- Turn the URL samplesheet into a cluster download script with the
  `fastq-download-script` skill.

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
