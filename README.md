# Informatics Data Skills

A collection of [Claude Code](https://docs.claude.com/en/docs/claude-code) **Agent Skills** for obtaining metadata and data from public life-science data repositories — plus helpers that turn what they find into pipeline-ready sample sheets, cluster download scripts, and a data-portal submission workbook.

Each skill gives an agent (or a human at the CLI) one consistent way to:

1. **Search** a repository and **fetch metadata** for an accession.
2. **List** and **download** the associated data files.
3. Produce **pipeline inputs** — a harmonized metadata table, nf-core sample sheets, quantms/DIA-NN minimal SDRFs, and cluster-ready download / job scripts.
4. Produce a **submission workbook** — fill the UK DRI FAIR-metadata Excel template for the ADDI / AD Workbench data portal.

## Skills

| Skill | Repository | Operator |
|-------|------------|----------|
| [`geo`](geo/) | Gene Expression Omnibus | NCBI |
| [`ena`](ena/) | European Nucleotide Archive | EMBL-EBI |
| [`pride`](pride/) | PRIDE (proteomics identifications) | EMBL-EBI |
| [`arrayexpress`](arrayexpress/) | ArrayExpress (functional genomics) | EMBL-EBI (in BioStudies) |
| [`biostudies`](biostudies/) | BioStudies | EMBL-EBI |
| [`fastq-download-script`](fastq-download-script/) | FASTQ download-script generator | — |
| [`sra`](sra/) | NCBI SRA download job-script generator (sra-tools) | — |
| [`addi`](addi/) | ADDI / AD Workbench FAIR-metadata submission workbook | — |

One skill = one directory = one data source (or one generator).

## What each skill does

- **`geo`** — Search GEO DataSets, fetch series/sample metadata, list and download supplementary/matrix/SOFT/MINiML files, and export the SRA Run Selector list. Raw reads are not held in GEO, so the sample-sheet builder resolves the linked SRA/ENA data for FASTQ links.
- **`ena`** — The metadata hub for sequencing runs, and the FASTQ source for bulk data. List runs and download links, run advanced metadata searches, fetch raw records, and download FASTQ / submitted files. Other sequencing skills resolve their runs through ENA; single-cell reads are better fetched with `sra` (see below).
- **`pride`** — Fetch proteomics project metadata, list and download data files (RAW, mzIdentML, mzML, mzTab, MGF, SDRF), search projects, write a minimal-valid SDRF sample sheet for quantms/DIA-NN, and generate a download script for the project's data files.
- **`arrayexpress`** — Fetch functional-genomics study metadata with MAGE-TAB (IDF/SDRF) awareness, classify and download files, print the experimental design, and build an nf-core sample sheet from the SDRF.
- **`biostudies`** — Fetch study metadata, list and download attached files, and search across BioStudies collections (ArrayExpress, BioImage Archive, and standalone submissions).
- **`fastq-download-script`** — Turn a sample sheet (or a plain URL list) into a cluster-ready bash download script with a SLURM header.
- **`sra`** — Turn an accession list into sequential SLURM job scripts (`prefetch` → `fasterq-dump`, plus an optional symlink step that gives 10x reads the `_S1_L001_R{1,2}_001.fastq.gz` naming cellranger requires) that download SRR accessions from NCBI SRA and extract them to gzipped FASTQ. The recommended route for **single-cell** reads — only `fasterq-dump --include-technical` exposes the Chromium read structure reliably — and the route for anything not mirrored to ENA.
- **`addi`** — Fill the UK DRI FAIR-metadata Excel template for an ADDI / AD Workbench submission: describe the study (catalogue) and its data tables (dictionaries/fields/lookups), validate against the template's controlled vocabularies and rules, and write a filled `.xlsx` — optionally seeding the schema from a `metadata.tsv`. The template is edited in place so its dropdowns, colors and comments are preserved. Writes files only; never uploads. Requires `openpyxl` + `pandas`.

## Cross-cutting features

- **Harmonized metadata table** — every repository skill can write a single `metadata.tsv` that maps each source's differently-named sample annotations into one common schema (sample, species, sex, age, condition, genotype, treatment, tissue, …), one row per sample × replicate, with any extra characteristic promoted to its own column.
- **Sample sheets** — the format follows the target pipeline: nf-core/scrnaseq or nf-core/rnaseq for sequencing (chosen with `--assay`), or a quantms/DIA-NN minimal SDRF for proteomics.
- **Download & job scripts** — generators that emit cluster-ready transfer scripts (direct FASTQ download from ENA/ArrayExpress) or a two-step sra-tools compute job for NCBI SRA (three-step with `--cellranger-links`). They only *write* the scripts; they never submit them.

Typical end-to-end routes — **split by assay, not ranked overall**:

```
# BULK RNA-seq — ENA direct HTTPS download
ena samplesheet --assay bulk  →  samplesheet.csv  →  fastq-download-script  →  sbatch

# SINGLE-CELL — the sra route, for the 10x read structure
geo runtable  →  SRR_Acc_List.txt
sra job-scripts --cellranger-links --read-map 3,4  →  3 scripts  →  sbatch (in order)
geo samplesheet --assay scrna --fastq-dir ./fastq --fastq-naming cellranger
    →  samplesheet.csv  →  nf-core/scrnaseq (aligner cellranger)

# PROTEOMICS — a different domain; no reads, no R1/R2
pride download-script  →  sbatch;   pride samplesheet  →  .sdrf.tsv
```

## Installing the skills

Claude Code discovers skills under `~/.claude/skills`. Symlink each skill directory there so it stays in sync with this repository:

```bash
# Symlink every skill in this repository into ~/.claude/skills
mkdir -p ~/.claude/skills
REPO="$(pwd)"                     # run from the repository root
for d in geo ena pride arrayexpress biostudies fastq-download-script sra addi; do
    ln -s "$REPO/$d" ~/.claude/skills/"$d"
done
```

To add a single skill, symlink just that directory:

```bash
ln -s "$(pwd)/geo" ~/.claude/skills/geo
```

Because these are symlinks, `git pull` in this repository updates the installed skills automatically. Remove a skill with `rm ~/.claude/skills/<name>` (this deletes only the link, not the repository).

## Design

See [`DESIGN.md`](DESIGN.md) for the architecture, conventions, and rationale behind every skill.

## License

[MIT](LICENSE) © 2026 UK Dementia Research Institute
