---
name: sra
description: >-
  Generate the SRA-tools SLURM job scripts (prefetch + fasterq-dump, plus an
  optional cellranger-naming symlink step) that download SRR accessions from NCBI
  SRA and extract them to gzipped FASTQ on the UKDRI cluster. The recommended route
  for single-cell/10x reads, because only fasterq-dump exposes the Chromium read
  structure reliably; also the route for runs not mirrored to ENA. Use when you have
  an SRR_Acc_List.txt (e.g. from the `geo` skill's runtable command or the `ena`
  skill) and want cluster-ready job scripts that run sra-tools via apptainer.
  Triggers: "SRA", "sra-tools", "SRR", "prefetch", "fasterq-dump", "SRR_Acc_List",
  "SLURM sra download", "apptainer sra", "NCBI SRA download", ".sra to fastq",
  "cellranger", "10x", "Chromium", "Chromium 5'", "R1 R2 naming", "fastq symlink",
  "ready for cellranger".
---

# SRA-tools job-script generator

Fills the job-script templates in `templates/` and writes two (or three)
ready-to-submit SLURM scripts that run [sra-tools](https://github.com/ncbi/sra-tools)
via **apptainer**. It only *writes* the scripts — it never submits or runs anything.

**Which route to use** depends on the assay, not on where the data sits:

- **Single-cell / 10x → this skill.** ENA's mirrored 10x FASTQs are unreliable for
  read structure (technical reads inconsistently present and named), so
  `fasterq-dump --include-technical` plus `--read-map` / `--cellranger-links` is the
  way to get the cDNA read right by construction.
- **Bulk RNA-seq → the ENA download script** (`ena samplesheet` →
  `fastq-download-script`). One or two files per run and informative names, so there
  is nothing here to fix. Use this skill for bulk only when runs are not mirrored to
  ENA, or when you specifically want the NCBI path.

## Two steps, in order (plus an optional third)

sra-tools is run as sequential jobs — each reads what the previous wrote:

1. **`run_prefetch.sh`** — `prefetch` each accession in the SRR list into `.sra`
   files under the prefetch directory.
2. **`run_fasterq-dump.sh`** — `fasterq-dump` those `.sra` files into FASTQ, then
   `pigz`-compresses `_1` … `_4.fastq`.
3. **`run_link-cellranger-fastq.sh`** — *only with `--cellranger-links`*. Symlinks
   the 10x cDNA read pair as `<run>_S1_L001_R{1,2}_001.fastq.gz`. See
   *10x / cellranger read naming* below.

The prefetch output directory is automatically wired to be the fasterq-dump input
directory, and the fasterq-dump output directory to be the link step's input.

## 10x / cellranger read naming

`fasterq-dump --include-technical --split-files` names its output **positionally**,
so for 10x the real read pair is **the last two files, not `_1`/`_2`**:

| dumped files | `_1` | `_2` | `_3` | `_4` | typical case | `--read-map` |
|---|---|---|---|---|---|---|
| 2 | R1 | R2 | — | — | index reads not submitted | `1,2` (default) |
| 3 | I1 | R1 | R2 | — | single-index 10x | `2,3` |
| 4 | I1 | I2 | R1 | R2 | dual-index, e.g. Chromium 5′ | `3,4` |

`cellranger count --fastqs` will not accept the dumped names at all: its FASTQ parser
requires the Illumina/bcl2fastq shape `<sample>_S1_L001_R{1,2}_001.fastq.gz` — a bare
`_R1.fastq.gz` is *not* matched. nf-core/scrnaseq accepts that full form too, so
`--cellranger-links` writes exactly one naming that serves both.

- **Symlinks, never renames.** `run_fasterq-dump.sh` skips a run whose `_2.fastq{,.gz}`
  already exists, so renaming would re-trigger a full re-dump; and the index reads stay
  on disk for workflows that need them (`cellrangermulti`, feature barcoding). The links
  are relative (`ln -sfnr`), so the directory stays relocatable and the step is safe to
  re-run.
- **`--read-map` is declared, never detected.** A wrong value yields plausible-looking
  garbage counts rather than an error — **count the dumped files for one run before
  submitting**. The job logs each run's first-record read lengths and warns when the
  declared R1 is not 24–32 bp (16 bp barcode + 10–12 bp UMI). Runs it cannot link are
  warned and skipped, and the job exits non-zero; fix `--read-map`, re-run, and the
  already-linked runs are left untouched.
- **One `--read-map` per directory.** The link step globs the FASTQ directory rather
  than reading the SRR list, so a study mixing 3′ and 5′ runs needs its accession list
  *and* its output directory split.
- **Links are named per run**, not per biological sample. nf-core concatenates rows
  sharing a `sample`, so that is transparent there; a direct `cellranger count` sees
  one sample per run (`--sample SRR111,SRR222`).

Then build a matching sample sheet against the symlinks:

```bash
python ../geo/scripts/geo.py samplesheet GSE110009 --assay scrna \
    --fastq-dir /nfsdata/$USER/gse110009/fastq --fastq-naming cellranger
```

`ena`, `geo` and `arrayexpress` all take `--fastq-dir` + `--fastq-naming
{sra,cellranger}` (and their own `--read-map` for the ENA-URL route).

## Input

An existing **`SRR_Acc_List.txt`** — one accession per line. Pass `--srr-list` either
the **exact file path** or a **directory** that contains `SRR_Acc_List.txt` (the
generator resolves `<dir>/SRR_Acc_List.txt`). Produce it upstream:

- `geo runtable GSExxxxxx` → writes `SraRunTable.csv` + `SRR_Acc_List.txt` directly
- `ena report ACC --result read_run --fields run_accession` → take the
  `run_accession` column into a one-accession-per-line list

For **ENA-hosted bulk** runs the recommended route is *not* this skill — it is the
direct FASTQ download script (`ena samplesheet` → `fastq-download-script`). For
**single-cell**, use this skill even when the runs are on ENA (see above).

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

# 10x dual-index (e.g. Chromium 5'): add the cellranger-naming symlink step
python scripts/sra.py job-scripts --srr-list SRR_Acc_List.txt --workdir ./study1 \
    --cellranger-links --read-map 3,4
```

Typical end-to-end flow — **bulk** (or anything not mirrored to ENA):

```bash
python ../geo/scripts/geo.py runtable GSE110009 --out .   # -> SRR_Acc_List.txt
python scripts/sra.py job-scripts --srr-list SRR_Acc_List.txt --workdir /nfsdata/$USER/gse110009
```

…and **single-cell / 10x**, through to the sample sheet:

```bash
python ../geo/scripts/geo.py runtable GSE110009 --out .
python scripts/sra.py job-scripts --srr-list SRR_Acc_List.txt \
    --workdir /nfsdata/$USER/gse110009 --cellranger-links --read-map 3,4
# sbatch the three scripts in order (see below), then:
python ../geo/scripts/geo.py samplesheet GSE110009 --assay scrna \
    --fastq-dir /nfsdata/$USER/gse110009/fastq --fastq-naming cellranger
```

## Running the generated scripts

They **must run in order**. This skill does not submit them. To serialize them as
dependent SLURM jobs (each starts only if the previous succeeds):

```bash
jid=$(sbatch --parsable run_prefetch.sh)
sbatch --dependency=afterok:$jid run_fasterq-dump.sh
```

With `--cellranger-links` there is a third job:

```bash
jid=$(sbatch --parsable run_prefetch.sh)
jid=$(sbatch --parsable --dependency=afterok:$jid run_fasterq-dump.sh)
sbatch --dependency=afterok:$jid run_link-cellranger-fastq.sh
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
| `--out-dir` | `.` | where the `.sh` files are written |
| `--cellranger-links` | off | also write `run_link-cellranger-fastq.sh` (the 10x R1/R2 symlinks) |
| `--link-dir` | the `--fastq-dir` value | where the symlinks go; needs `--cellranger-links` |
| `--read-map` | `1,2` | which dumped files are the cDNA pair (`2,3` / `3,4` for 10x); needs `--cellranger-links` |
| `--link-time` | `0-02:00:00` | walltime for the link job only; needs `--cellranger-links` |
| `--sif` | `/nfsdata/apptainer/ncbi-sra-tools-3.2.1.sif` | local sra-tools `.sif` path — the default image source |
| `--docker` | `ncbi/sra-tools:3.2.1` | alternative: pull via apptainer (`docker://IMAGE`) |
| `--partition` | `htc` | SLURM partition (all jobs) |
| `--time` | `7-00:00:00` | SLURM walltime `D-HH:MM:SS` (prefetch + fasterq-dump) |
| `--prefetch-cpus` | `2` | `cpus-per-task` for prefetch |
| `--dump-cpus` | `32` | `cpus-per-task` and fasterq-dump/pigz threads |
| `--max-size` | `32g` | prefetch `--max-size` (increase for large runs) |

With no override flags, each generated script is identical to its committed template
apart from the substituted paths. The third script is written only with
`--cellranger-links`; the three flags above are rejected without it.

## Notes

- **`apptainer` and `pigz` must be available on the compute node** — the templates
  bind-mount `-B /nfsdata,/data,/shared` and call `apptainer exec` + `pigz`. The link
  step additionally needs **GNU coreutils `ln --relative`** and **`zcat`**.
- **`--read-map` defaults to `1,2`, which is the wrong answer for most 10x studies.**
  It is right for bulk and for a two-file 10x run only. Count the dumped files for one
  run and set it explicitly — nothing detects a wrong value, and the resulting counts
  look plausible rather than failing.
- **The link step globs the FASTQ directory**, not the SRR list, so a directory shared
  between studies gets links for every run in it under a single `--read-map`.
- **Re-running the link step is safe** — links are replaced in place, and a real
  (non-symlink) file in the way is reported and never overwritten.
- **`--docker` pulls the image on first exec.** For many accessions this repeats
  per invocation; consider pre-pulling once to a local `.sif`
  (`apptainer pull sra-tools.sif docker://ncbi/sra-tools:3.2.1`) and passing `--sif`.
- **`run_prefetch.sh` refuses to overwrite** an existing prefetch directory —
  remove it and re-run if you need to restart.
- **Controlled-access data** (e.g. dbGaP) needs NGC/dbGaP credentials that these
  scripts do not configure; prefetch of protected runs will fail without them.
- The templates in `templates/` are the source of truth and can also be copied and
  edited by hand — the generator just fills the `__TOKEN__` placeholders.
