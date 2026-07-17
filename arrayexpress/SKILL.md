---
name: arrayexpress
description: >-
  Query metadata and download data from ArrayExpress, EMBL-EBI's functional
  genomics collection (now hosted in BioStudies). Use when working with
  ArrayExpress accessions (E-MTAB, E-GEOD, E-MEXP, E-PROT...) — to fetch study
  metadata, list and classify files (IDF/SDRF MAGE-TAB, raw, processed), print the
  SDRF experimental design, download data by category, or build an
  nf-core/scrnaseq or nf-core/rnaseq samplesheet.csv from the SDRF. Triggers:
  "ArrayExpress", "E-MTAB", "MAGE-TAB", "SDRF", "IDF", "functional genomics
  experiment", "microarray experiment EBI", "samplesheet", "rnaseq", "scrnaseq".
---

# ArrayExpress (EMBL functional genomics)

EMBL-EBI's archive of functional genomics experiments (microarray and
sequencing-based). Since 2021 it is a **collection within BioStudies**, so access
goes through the BioStudies REST API (`https://www.ebi.ac.uk/biostudies/api/v1`)
with the `ArrayExpress` collection — this skill adds MAGE-TAB (IDF/SDRF)
awareness on top.

## Accession types

| Prefix | Meaning |
|--------|---------|
| `E-MTAB` | Direct MAGE-TAB submissions (most common) |
| `E-GEOD` | Imported from NCBI GEO |
| `E-MEXP`, `E-TABM` | Legacy submissions |
| `E-PROT` | Proteomics (legacy) |

## Tooling

`scripts/arrayexpress.py` — standard-library Python (urllib), no dependencies.

```bash
python scripts/arrayexpress.py metadata E-MTAB-11448          # summary + file breakdown
python scripts/arrayexpress.py files    E-MTAB-11448          # list files, classified
python scripts/arrayexpress.py sdrf     E-MTAB-11448          # print the SDRF table
python scripts/arrayexpress.py download E-MTAB-11448 --magetab --out ./out
python scripts/arrayexpress.py download E-MTAB-11448 --processed --out ./out
python scripts/arrayexpress.py download E-MTAB-11448 --raw --out ./out
python scripts/arrayexpress.py search   "single cell heart" --limit 20
python scripts/arrayexpress.py samplesheet E-MTAB-13991 --assay scrna  # nf-core/scrnaseq
python scripts/arrayexpress.py samplesheet E-MTAB-13991 --assay bulk   # nf-core/rnaseq
python scripts/arrayexpress.py metadata-table E-MTAB-11448 --out metadata.tsv  # harmonized sample table
```

Add `--json` to `metadata`/`files`/`search` for machine-readable output.

## Metadata table (metadata.tsv)

`metadata-table` parses the study's **SDRF** into the harmonized, tab-delimited
`metadata.tsv` shared across all repository skills: **one row per SDRF row (sample
× replicate)** with the core columns `sample, replicate, species, sex, age,
condition, genotype, treatment, tissue`. `Source Name` becomes `sample`, a
technical/biological replicate column (or `1`) becomes `replicate`, and the
`Characteristics[...]` / `FactorValue[...]` columns are mapped to the core fields.
Any characteristic that doesn't map to a core field is **promoted to its own
column**, so nothing is dropped. When a row carries a BioSample id (`Source Name`
or `Comment[BioSD_SAMPLE]`), the EBI BioSamples API is queried to fill missing and
extra fields. **Missing fields are `NA`.**

```bash
python scripts/arrayexpress.py metadata-table E-MTAB-11448 --out metadata.tsv
```

## Samplesheet (nf-core/scrnaseq or /rnaseq)

`samplesheet` parses the study's **SDRF** and writes an nf-core sample sheet. It
reads `Source Name` (→ `sample`), `Comment[ENA_RUN]`, and `Comment[FASTQ_URI]`,
grouping the R1/R2 rows of each run into one samplesheet row. If a run has no
`FASTQ_URI`, the FASTQ links are fetched from ENA by run accession. **`--assay` is
required** — the archive can't tell you whether the study is single-cell or bulk:

- `--assay scrna` → [nf-core/scrnaseq](https://nf-co.re/scrnaseq/4.2.0/docs/usage/#samplesheet-input)
  columns `sample,fastq_1,fastq_2`.
- `--assay bulk` → [nf-core/rnaseq](https://nf-co.re/rnaseq/3.26.0/docs/usage#samplesheet-input)
  columns `sample,fastq_1,fastq_2,strandedness` (`--strandedness`, default `auto`).

```bash
python scripts/arrayexpress.py samplesheet E-MTAB-13991 --assay scrna              # FASTQ URLs
python scripts/arrayexpress.py samplesheet E-MTAB-13991 --assay bulk --strandedness reverse
python scripts/arrayexpress.py samplesheet E-MTAB-13991 --assay scrna --local-dir ./fastq
```

- Errors clearly if the SDRF has no FASTQ (e.g. array-only studies, or reads only
  in ENA under controlled access).
- Feed the samplesheet to the `fastq-download-script` skill for a cluster download
  script.

## MAGE-TAB: the two key files

- **IDF (`*.idf.txt`)** — Investigation Description Format: study-level metadata
  (title, protocols, contacts, experimental factors).
- **SDRF (`*.sdrf.txt`)** — Sample and Data Relationship Format: one row per
  assay, mapping samples → protocols → raw/processed data files, and (for
  sequencing) the linked ENA run accessions.

Download both with `--magetab`. The `sdrf` command prints the SDRF directly so you
can inspect the experimental design and find ENA run accessions for raw reads.

## How access works (for ad-hoc queries)

- **Metadata**: `GET /api/v1/studies/{accession}` (PageTab JSON). Files live in the
  `section`/`subsections` tree as `type: "file"` entries with a `path`.
- **File download**: `https://www.ebi.ac.uk/biostudies/files/{accession}/{path}`.
- **Search**: `GET /api/v1/search?query=<q>&collection=ArrayExpress`.

## Notes

- For sequencing experiments, **raw FASTQ files are stored in ENA**, not
  ArrayExpress. The SDRF lists the ENA run/experiment accessions (`ERR*/SRR*`,
  `ERX*`) — feed those to the `ena` skill to download reads. Processed matrices
  are usually attached directly to the ArrayExpress record.
- This skill and the `biostudies` skill hit the same API; use this one for
  functional-genomics conventions, the other for general BioStudies collections.
