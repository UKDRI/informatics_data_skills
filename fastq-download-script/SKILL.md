---
name: fastq-download-script
description: >-
  Generate a runnable bash download script (with a SLURM job header) for FASTQ
  files from ENA and ArrayExpress. Use when you have a samplesheet.csv (from the
  `ena`, `arrayexpress`, or `geo` skills) or a list of FASTQ URLs and want a
  cluster-ready script that downloads each file with a quiet curl/wget command,
  one per samplesheet row. Triggers: "download script", "bash script for FASTQ",
  "wget/curl FASTQ", "SLURM download job", "sbatch fastq", "batch download reads".
---

# FASTQ download script generator

Turns FASTQ URLs into a self-contained bash script that downloads each file with
a **quiet** `curl`/`wget` command (no progress bars), preceded by a typical
**SLURM** job header so it can be submitted with `sbatch`. It only *writes* the
script — it does not download anything itself.

## Input

- **A samplesheet.csv** (default) — the nf-core/scrnaseq sheet produced by the
  `ena` / `arrayexpress` / `geo` skills. All `fastq_*` columns that contain
  `http(s)`/`ftp` URLs are collected, one download command per URL, grouped under
  a `# sample:` comment per row. (Rows with local paths are skipped with a warning.)
- **A plain URL list** (`--urls`) — one FASTQ URL per line.

## Tooling

`scripts/make_download_script.py` — standard-library Python, no dependencies.

```bash
# From a samplesheet (default: wget, ./fastq, download_fastq.sh)
python scripts/make_download_script.py samplesheet.csv

# Choose curl, output dir, and script name
python scripts/make_download_script.py samplesheet.csv --tool curl --outdir fastq --out dl.sh

# Tune the SLURM header
python scripts/make_download_script.py samplesheet.csv \
    --job-name ena_dl --partition short --time 12:00:00 --cpus 1 --mem 8G \
    --email you@org.ac.uk --account myproj

# From a plain URL list, no SLURM header (plain bash)
python scripts/make_download_script.py urls.txt --urls --no-slurm
```

Typical end-to-end flow:

```bash
python ../ena/scripts/ena.py samplesheet PRJEB1787 --out samplesheet.csv
python scripts/make_download_script.py samplesheet.csv --tool curl --out dl.sh
sbatch dl.sh          # or: ./dl.sh
```

## What the generated script contains

- SLURM header (`#SBATCH` lines): `--job-name`, `--cpus-per-task`, `--mem`,
  `--time`, `--output`/`--error` logs, plus commented placeholders for
  `--partition`, `--account`, and email (uncommented when you pass the flags).
  Use `--no-slurm` for a plain bash script.
- `set -euo pipefail` and `mkdir -p "$OUTDIR"`.
- One quiet download command per file:
  - **curl**: `curl -fsSL --retry 3 --create-dirs -o "$OUTDIR/<file>" "<url>"`
    (`-f` fail on HTTP errors, `-s` silent = no progress bar, `-S` still show
    errors, `-L` follow redirects).
  - **wget**: `wget -q --tries=3 --waitretry=5 -O "$OUTDIR/<file>" "<url>"`
    (`-q` fully quiet = no progress bar).

## Options

| Flag | Default | Meaning |
|------|---------|---------|
| `--tool` | `wget` | `wget` or `curl` |
| `--outdir` | `fastq` | download destination directory |
| `--out` | `download_fastq.sh` | generated script path (made executable) |
| `--urls` | off | treat input as a plain URL list |
| `--no-slurm` | off | omit the SLURM header |
| `--job-name` | `fastq_download` | SLURM job name |
| `--partition` / `--account` | — | cluster-specific (commented placeholder if unset) |
| `--cpus` / `--mem` / `--time` | `1` / `4G` / `24:00:00` | SLURM resources |
| `--email` | — | enables `--mail-type=END,FAIL` + `--mail-user` |

## Notes

- Adjust `--partition`, `--account`, and time/memory to your HPC — the defaults
  are conservative placeholders.
- FASTQ downloads are I/O bound, so 1 CPU is usually enough; the commands run
  sequentially. For large studies, consider a SLURM job array or the ENA Aspera
  links (see the `ena` skill) instead.
- Verify integrity against the ENA `fastq_md5` values after download.
