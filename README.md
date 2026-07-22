# Informatics Data Skills

A collection of [Claude Code](https://docs.claude.com/en/docs/claude-code) **Agent Skills** for obtaining metadata and data from public life-science data repositories — plus helpers that turn what they find into pipeline-ready sample sheets and cluster download scripts.

Each skill gives an agent (or a human at the CLI) one consistent way to:

1. **Search** a repository and **fetch metadata** for an accession.
2. **List** and **download** the associated data files.
3. Produce **pipeline inputs** — a harmonized metadata table, nf-core sample sheets, quantms/DIA-NN minimal SDRFs, and cluster-ready download / job scripts.

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

One skill = one directory = one data source (or one generator).

## What each skill does

- **`geo`** — Search GEO DataSets, fetch series/sample metadata, list and download supplementary/matrix/SOFT/MINiML files, and export the SRA Run Selector list. Raw reads are not held in GEO, so the sample-sheet builder resolves the linked SRA/ENA data for FASTQ links.
- **`ena`** — The canonical source of FASTQ files. List runs and download links, run advanced metadata searches, fetch raw records, and download FASTQ / submitted files. Other sequencing skills route their reads through ENA.
- **`pride`** — Fetch proteomics project metadata, list and download data files (RAW, mzIdentML, mzML, mzTab, MGF, SDRF), search projects, write a minimal-valid SDRF sample sheet for quantms/DIA-NN, and generate a download script for the project's data files.
- **`arrayexpress`** — Fetch functional-genomics study metadata with MAGE-TAB (IDF/SDRF) awareness, classify and download files, print the experimental design, and build an nf-core sample sheet from the SDRF.
- **`biostudies`** — Fetch study metadata, list and download attached files, and search across BioStudies collections (ArrayExpress, BioImage Archive, and standalone submissions).
- **`fastq-download-script`** — Turn a sample sheet (or a plain URL list) into a cluster-ready bash download script with a SLURM header.
- **`sra`** — Turn an accession list into the two sequential SLURM job scripts (`prefetch` → `fasterq-dump`) that download SRR accessions from NCBI SRA and extract them to gzipped FASTQ — the route for runs not mirrored to ENA.

## Cross-cutting features

- **Harmonized metadata table** — every repository skill can write a single `metadata.tsv` that maps each source's differently-named sample annotations into one common schema (sample, species, sex, age, condition, genotype, treatment, tissue, …), one row per sample × replicate, with any extra characteristic promoted to its own column.
- **Sample sheets** — the format follows the target pipeline: nf-core/scrnaseq or nf-core/rnaseq for sequencing (chosen with `--assay`), or a quantms/DIA-NN minimal SDRF for proteomics.
- **Download & job scripts** — generators that emit cluster-ready transfer scripts (direct FASTQ download from ENA/ArrayExpress) or a two-step sra-tools compute job for NCBI SRA. They only *write* the scripts; they never submit them.

Typical end-to-end routes:

```
# ENA FASTQ — recommended default (direct HTTPS download)
ena samplesheet  →  samplesheet.csv  →  fastq-download-script  →  sbatch

# NCBI SRA route — for SRA-only data (e.g. via GEO)
geo runtable  →  SRR_Acc_List.txt  →  sra job-scripts  →  sbatch (in order)
```

## Installing the skills

Claude Code discovers skills under `~/.claude/skills`. Symlink each skill directory there so it stays in sync with this repository:

```bash
# Symlink every skill in this repository into ~/.claude/skills
mkdir -p ~/.claude/skills
REPO="$(pwd)"                     # run from the repository root
for d in geo ena pride arrayexpress biostudies fastq-download-script sra; do
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
