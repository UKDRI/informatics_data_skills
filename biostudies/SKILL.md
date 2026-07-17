---
name: biostudies
description: >-
  Query metadata and download data from EMBL-EBI BioStudies, the database that
  holds descriptions of biological studies and links their data across
  collections (ArrayExpress, BioImages, BioModels, EGA-linked studies, and
  standalone submissions). Use when working with BioStudies accessions (S-BSST,
  S-BIAD, S-EPMC, S-XXXX...) — to fetch study metadata, list and download attached
  files, or search across collections. Triggers: "BioStudies", "S-BSST",
  "S-BIAD", "BioImage Archive", "supplementary study data EBI".
---

# BioStudies

EMBL-EBI's database for holding descriptions of biological studies, linking data
from other databases and hosting supplementary files that have no dedicated
archive. Several collections live inside it, including **ArrayExpress** (see the
sibling `arrayexpress` skill) and the **BioImage Archive** (`S-BIAD`). Served by
the **BioStudies REST API** (`https://www.ebi.ac.uk/biostudies/api/v1`).

## Accession types

| Prefix | Collection |
|--------|------------|
| `S-BSST` | General BioStudies submissions |
| `S-BIAD` | BioImage Archive |
| `E-MTAB`, `E-GEOD`, ... | ArrayExpress (use the `arrayexpress` skill) |
| `S-EPMC` | Europe PMC-linked studies |
| `S-BSMS`, `S-EGAS`, ... | Other collections |

## Tooling

`scripts/biostudies.py` — standard-library Python (urllib), no dependencies.

```bash
python scripts/biostudies.py metadata S-BSST123           # study metadata
python scripts/biostudies.py files    S-BSST123           # list attached files
python scripts/biostudies.py download S-BSST123 --out ./out
python scripts/biostudies.py download S-BSST123 --match .csv --out ./out
python scripts/biostudies.py search   "spatial transcriptomics" --limit 20
python scripts/biostudies.py search   "cancer" --collection BioImages
python scripts/biostudies.py metadata-table S-BSST123 --out metadata.tsv   # harmonized sample table
```

Add `--json` to any query command for machine-readable output.

## Metadata table (metadata.tsv)

`metadata-table` writes the harmonized, tab-delimited `metadata.tsv` shared across
all repository skills: **one row per sample subsection** with the core columns
`sample, replicate, species, sex, age, condition, genotype, treatment, tissue`.
Because BioStudies is heterogeneous, this is best-effort: it locates sample-like
subsections in the PageTab tree (type mentions "sample", or attributes carry an
organism) and maps their attributes to the core fields, **promoting** any
unmatched characteristic to its own column so nothing is dropped. When a sample's
id is a BioSample (`SAME*`/`SAMEA*`/`SAMN*`/`SAMD*`), the EBI BioSamples API is
queried to fill missing and extra fields. When a study has no per-sample structure,
a single study-level row is emitted from the section attributes. **Missing fields
are `NA`.**

```bash
python scripts/biostudies.py metadata-table S-BSST123 --out metadata.tsv
```

## How access works (for ad-hoc queries)

- **Study metadata (PageTab JSON)**: `GET /api/v1/studies/{accession}`. The record
  has `accno`, top-level `attributes`, and a nested `section` tree. Files are
  spread through `section` / `subsections` as objects with `type: "file"`, a
  `path`, `size`, and `attributes` — walk the tree recursively to enumerate them.
- **File download**: `https://www.ebi.ac.uk/biostudies/files/{accession}/{path}`
  (URL-encode the path). The study's `/info` endpoint also gives `httpLink` /
  `ftpLink` / `globusLink` pointing at the FIRE folder root for bulk transfer.
- **Search**: `GET /api/v1/search?query=<q>&pageSize=<n>&page=<p>`; add
  `collection=<name>` to restrict. Response has `totalHits` and `hits[]`
  (each with `accession`, `title`, `author`, `type`), plus `facets`.
- **Directory root (bulk)**: `GET /api/v1/studies/{accession}/info` →
  `relPath`, `httpLink` (e.g. `https://ftp.ebi.ac.uk/biostudies/fire/…`).

## Notes

- Large image/data collections are best pulled in bulk via the `ftpLink` /
  `globusLink` from `/info` rather than file-by-file.
- For the ArrayExpress functional-genomics collection specifically (E-MTAB etc.),
  use the `arrayexpress` skill, which adds IDF/SDRF-aware helpers on top of this API.
