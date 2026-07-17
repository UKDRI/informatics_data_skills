---
name: geo
description: >-
  Query metadata and download data from the NCBI Gene Expression Omnibus (GEO).
  Use when working with GEO accessions (GSE series, GSM samples, GPL platforms,
  GDS datasets) — to search GEO DataSets, fetch series/sample metadata, list
  supplementary/raw files, download series matrix, SOFT, MINiML, and
  supplementary files, or build an nf-core/scrnaseq samplesheet.csv from the
  linked SRA/ENA data. Triggers: "GEO", "GSE", "GSM", "gene expression omnibus",
  "series matrix", "GEO supplementary", "samplesheet".
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
python scripts/geo.py samplesheet GSE110009 --out samplesheet.csv   # nf-core/scrnaseq sheet
```

Add `--json` to any query command for machine-readable output.

## Samplesheet (nf-core/scrnaseq)

GEO does not host raw reads — they live in SRA/ENA. `samplesheet` resolves the
SRA study / BioProject linked to a GEO series (from the series relations), pulls
the FASTQ links from ENA, and writes a
[nf-core/scrnaseq](https://nf-co.re/scrnaseq/4.2.0/docs/usage/#samplesheet-input)
sheet (`sample,fastq_1,fastq_2`).

```bash
python scripts/geo.py samplesheet GSE110009                        # ENA https URLs
python scripts/geo.py samplesheet GSE110009 --group-by sample_title
python scripts/geo.py samplesheet GSE110009 --local-dir ./fastq
```

- `--group-by` / `--local-dir` behave as in the `ena` skill.
- If the series has no public FASTQ in ENA (e.g. human data under dbGaP controlled
  access), the command reports that clearly — the reads are not downloadable here.
- Feed the resulting samplesheet to the `fastq-download-script` skill for a
  cluster download script.

Download flags: `--matrix` (default), `--soft`, `--miniml`, `--suppl`. Combine as
needed; files land in `<out>/<ACCESSION>/<subdir>/`.

## Rate limits & auth

NCBI allows 3 requests/sec anonymously, 10/sec with an API key. Set env vars to
be a good citizen and lift limits:

```bash
export NCBI_EMAIL="you@example.org"
export NCBI_API_KEY="..."   # optional, from NCBI account settings
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
