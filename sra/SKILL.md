---
name: sra
description: >-
  Generate the two SRA-tools SLURM job scripts (prefetch + fasterq-dump) that
  download SRR accessions from NCBI SRA and extract them to gzipped FASTQ on the
  UKDRI cluster. Use when you have an SRR_Acc_List.txt (e.g. from the `geo`
  skill's runtable command or the `ena` skill) and want cluster-ready job scripts
  that run sra-tools via apptainer — a route to FASTQ for runs not mirrored to
  ENA, or when pulling directly from NCBI. Triggers: "SRA", "sra-tools", "SRR",
  "prefetch", "fasterq-dump", "SRR_Acc_List", "SLURM sra download", "apptainer
  sra", "NCBI SRA download", ".sra to fastq".
---

# SRA-tools job-script generator

Fills the two job-script templates in `templates/` and writes two ready-to-submit
SLURM scripts that run [sra-tools](https://github.com/ncbi/sra-tools) via
**apptainer**. It only *writes* the scripts — it never submits or runs anything.

FASTQ downloads normally go through ENA (the `ena` / `fastq-download-script`
skills). This skill is the **NCBI SRA route**: use it when runs are not mirrored to
ENA, or when you want to pull them directly from NCBI.

## Two steps, in order

sra-tools is run as two sequential jobs — the second reads what the first wrote:

1. **`run_prefetch.sh`** — `prefetch` each accession in the SRR list into `.sra`
   files under the prefetch directory.
2. **`run_fasterq-dump.sh`** — `fasterq-dump` those `.sra` files into FASTQ, then
   `pigz`-compresses `_1/_2/_3.fastq`.

The prefetch output directory is automatically wired to be the fasterq-dump input
directory.

## Input

An existing **`SRR_Acc_List.txt`** — one accession per line. Pass `--srr-list` either
the **exact file path** or a **directory** that contains `SRR_Acc_List.txt` (the
generator resolves `<dir>/SRR_Acc_List.txt`). Produce it upstream:

- `geo runtable GSExxxxxx` → writes `SraRunTable.csv` + `SRR_Acc_List.txt` directly
- `ena report ACC --result read_run --fields run_accession` → take the
  `run_accession` column into a one-accession-per-line list

For **ENA-hosted** runs the recommended route is *not* this skill — it is the direct
FASTQ download script (`ena samplesheet` → `fastq-download-script`). Reach for `sra`
only as an **alternative**: runs not mirrored to ENA, or when you specifically want
the NCBI `prefetch`/`fasterq-dump` path.

## Tooling

`scripts/sra.py` — standard-library Python, no dependencies.

```bash
# Simplest: --workdir sets DIR/sra (.sra files) and DIR/fastq (reads)
python scripts/sra.py job-scripts --srr-list SRR_Acc_List.txt --workdir /nfsdata/$USER/study1

# Explicit directories
python scripts/sra.py job-scripts --srr-list SRR_Acc_List.txt \
    --prefetch-dir /nfsdata/$USER/study1/sra --fastq-dir /nfsdata/$USER/study1/fastq

# Pull the sra-tools image via apptainer instead of using the cluster .sif
python scripts/sra.py job-scripts --srr-list SRR_Acc_List.txt --workdir ./study1 \
    --docker ncbi/sra-tools:3.2.1
```

Typical end-to-end flow:

```bash
python ../geo/scripts/geo.py runtable GSE110009 --out .   # -> SRR_Acc_List.txt
python scripts/sra.py job-scripts --srr-list SRR_Acc_List.txt --workdir /nfsdata/$USER/gse110009
```

## Running the generated scripts

They **must run in order**. This skill does not submit them. To serialize them as
dependent SLURM jobs (fasterq-dump starts only if prefetch succeeds):

```bash
jid=$(sbatch --parsable run_prefetch.sh)
sbatch --dependency=afterok:$jid run_fasterq-dump.sh
```

## sra-tools image

By default the scripts use a **local `.sif` image path** — the UKDRI image
`/nfsdata/apptainer/ncbi-sra-tools-3.2.1.sif`. Override with either:

- **`--sif PATH`** — a different local `.sif` image path (the default image
  source), or
- **`--docker IMAGE`** — set `sif=docker://IMAGE`, so `apptainer exec` pulls the
  image itself (default `ncbi/sra-tools:3.2.1`). Still runs through apptainer.

The official NCBI image is [`ncbi/sra-tools`](https://hub.docker.com/r/ncbi/sra-tools)
on Docker Hub; `3.2.1` matches the cluster `.sif`. Other tags (verified 2026-07-22)
include `3.0.0`, `3.0.1`, `3.1.0`, `3.3.0`, `3.4.1`, and `latest`.

`--sif` and `--docker` are mutually exclusive.

## Options

| Flag | Default | Meaning |
|------|---------|---------|
| `--srr-list` | *(required)* | list file, or a dir containing `SRR_Acc_List.txt` |
| `--workdir` | — | base dir → `DIR/sra` and `DIR/fastq` (or set both dirs below) |
| `--prefetch-dir` | `WORKDIR/sra` | `.sra` output dir (prefetch output = fasterq-dump input) |
| `--fastq-dir` | `WORKDIR/fastq` | FASTQ output dir |
| `--out-dir` | `.` | where the two `.sh` files are written |
| `--sif` | `/nfsdata/apptainer/ncbi-sra-tools-3.2.1.sif` | local sra-tools `.sif` path — the default image source |
| `--docker` | `ncbi/sra-tools:3.2.1` | alternative: pull via apptainer (`docker://IMAGE`) |
| `--partition` | `htc` | SLURM partition (both jobs) |
| `--time` | `7-00:00:00` | SLURM walltime `D-HH:MM:SS` (both jobs) |
| `--prefetch-cpus` | `2` | `cpus-per-task` for prefetch |
| `--dump-cpus` | `32` | `cpus-per-task` and fasterq-dump/pigz threads |
| `--max-size` | `32g` | prefetch `--max-size` (increase for large runs) |

With no override flags, the generated scripts are identical to the committed
templates apart from the substituted paths.

## Notes

- **`apptainer` and `pigz` must be available on the compute node** — the templates
  bind-mount `-B /nfsdata,/data,/shared` and call `apptainer exec` + `pigz`.
- **`--docker` pulls the image on first exec.** For many accessions this repeats
  per invocation; consider pre-pulling once to a local `.sif`
  (`apptainer pull sra-tools.sif docker://ncbi/sra-tools:3.2.1`) and passing `--sif`.
- **`run_prefetch.sh` refuses to overwrite** an existing prefetch directory —
  remove it and re-run if you need to restart.
- **Controlled-access data** (e.g. dbGaP) needs NGC/dbGaP credentials that these
  scripts do not configure; prefetch of protected runs will fail without them.
- The templates in `templates/` are the source of truth and can also be copied and
  edited by hand — the generator just fills the `__TOKEN__` placeholders.
