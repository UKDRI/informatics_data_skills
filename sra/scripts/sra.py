#!/usr/bin/env python3
"""Generate SRA-tools SLURM job scripts (prefetch + fasterq-dump).

Fills the two job-script templates in ``sra/templates/`` from an existing
``SRR_Acc_List.txt`` (one accession per line, e.g. the output of the `geo`
skill's ``runtable`` command) and writes two ready-to-submit scripts:

    run_prefetch.sh       prefetch each SRR accession into .sra files
    run_fasterq-dump.sh   fasterq-dump those .sra files into gzipped FASTQ

The two steps MUST run in order (fasterq-dump reads what prefetch wrote); this
tool only writes the scripts and never submits anything. Standard library only.

Examples:
    python sra.py job-scripts --srr-list SRR_Acc_List.txt --workdir /nfsdata/$USER/study1
    python sra.py job-scripts --srr-list SRR_Acc_List.txt \\
        --prefetch-dir /nfsdata/$USER/study1/sra --fastq-dir /nfsdata/$USER/study1/fastq
    python sra.py job-scripts --srr-list SRR_Acc_List.txt --workdir ./study1 \\
        --docker ncbi/sra-tools:3.2.1        # pull image via apptainer instead of a .sif
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(os.path.dirname(HERE), "templates")

# UKDRI cluster defaults — these reproduce the committed templates verbatim.
DEFAULT_SIF = "/nfsdata/apptainer/ncbi-sra-tools-3.2.1.sif"
# Verified 2026-07-22 to exist on Docker Hub (docker://ncbi/sra-tools:3.2.1);
# tags also include 3.0.0/3.0.1/3.1.0/3.3.0/3.4.1 and latest.
DEFAULT_DOCKER = "ncbi/sra-tools:3.2.1"
DEFAULT_PARTITION = "htc"
DEFAULT_TIME = "7-00:00:00"
DEFAULT_PREFETCH_CPUS = "2"
DEFAULT_DUMP_CPUS = "32"
DEFAULT_MAXSIZE = "32g"


def read_template(name):
    path = os.path.join(TEMPLATE_DIR, name)
    try:
        with open(path) as fh:
            return fh.read()
    except OSError as e:
        raise SystemExit(f"Cannot read template {path}: {e}")


def fill(text, tokens):
    """Replace every __TOKEN__ in `text`; error if any placeholder is left over."""
    for k, v in tokens.items():
        text = text.replace(k, v)
    leftover = [w for w in ("__PARTITION__", "__CPUS__", "__TIME__", "__SRR_LIST__",
                            "__PREFETCH_DIR__", "__FASTQ_INDIR__", "__FASTQ_DIR__",
                            "__IMAGE__", "__MAXSIZE__", "__NCPU__") if w in text]
    if leftover:
        raise SystemExit(f"Template still contains unfilled placeholders: {leftover}")
    return text


def write_script(path, text):
    with open(path, "w") as fh:
        fh.write(text)
    os.chmod(path, 0o755)


def resolve_srr_list(arg):
    """Accept an exact file path or a directory containing SRR_Acc_List.txt."""
    if os.path.isdir(arg):
        cand = os.path.join(arg, "SRR_Acc_List.txt")
        if not os.path.isfile(cand):
            raise SystemExit(
                f"No SRR_Acc_List.txt in directory {arg}. Point --srr-list at the "
                "exact file, or at a dir containing SRR_Acc_List.txt (e.g. the "
                "`geo runtable` / `ena` output dir).")
        return cand
    if not os.path.isfile(arg):
        raise SystemExit(
            f"SRR list not found: {arg}\n"
            "Provide an existing one-accession-per-line file (e.g. SRR_Acc_List.txt "
            "from `geo runtable` or the `ena` skill), or a directory containing it.")
    return arg


def cmd_job_scripts(args):
    # --- resolve the SRR list (exact file path or a dir holding SRR_Acc_List.txt) ---
    srr_file = resolve_srr_list(args.srr_list)
    with open(srr_file) as fh:
        n_acc = sum(1 for line in fh if line.strip() and not line.startswith("#"))
    if n_acc == 0:
        raise SystemExit(f"SRR list {srr_file} is empty (no accessions).")

    # --- resolve directories: --workdir provides defaults, explicit flags override ---
    if not args.workdir and not (args.prefetch_dir and args.fastq_dir):
        raise SystemExit(
            "Provide --workdir DIR (used as DIR/sra and DIR/fastq), or set both "
            "--prefetch-dir and --fastq-dir explicitly.")
    prefetch_dir = args.prefetch_dir or os.path.join(args.workdir, "sra")
    fastq_dir = args.fastq_dir or os.path.join(args.workdir, "fastq")

    # --- resolve the sra-tools image (mutually exclusive: local .sif or docker pull) ---
    if args.sif and args.docker:
        raise SystemExit("--sif and --docker are mutually exclusive.")
    if args.docker:
        image = f"docker://{args.docker}"
    elif args.sif:
        image = args.sif
    else:
        image = DEFAULT_SIF

    srr_list = os.path.abspath(srr_file)

    prefetch = fill(read_template("run_prefetch.sh"), {
        "__PARTITION__": args.partition,
        "__CPUS__": args.prefetch_cpus,
        "__TIME__": args.time,
        "__SRR_LIST__": srr_list,
        "__PREFETCH_DIR__": prefetch_dir,
        "__IMAGE__": image,
        "__MAXSIZE__": args.max_size,
    })
    # fasterq-dump reads the prefetch output directory as its input.
    fasterq = fill(read_template("run_fasterq-dump.sh"), {
        "__PARTITION__": args.partition,
        "__CPUS__": args.dump_cpus,
        "__TIME__": args.time,
        "__FASTQ_INDIR__": prefetch_dir,
        "__FASTQ_DIR__": fastq_dir,
        "__IMAGE__": image,
        "__NCPU__": args.dump_cpus,
    })

    os.makedirs(args.out_dir, exist_ok=True)
    p_out = os.path.join(args.out_dir, "run_prefetch.sh")
    f_out = os.path.join(args.out_dir, "run_fasterq-dump.sh")
    write_script(p_out, prefetch)
    write_script(f_out, fasterq)

    # --- report (stderr = progress); never submits ---
    print(f"Wrote {p_out} and {f_out} for {n_acc} accession(s).", file=sys.stderr)
    print(f"  image:        {image}", file=sys.stderr)
    print(f"  .sra dir:     {prefetch_dir}", file=sys.stderr)
    print(f"  fastq dir:    {fastq_dir}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Run the two steps IN ORDER — fasterq-dump reads what prefetch writes.", file=sys.stderr)
    print("To serialize them as dependent SLURM jobs:", file=sys.stderr)
    print(f"  jid=$(sbatch --parsable {p_out})", file=sys.stderr)
    print(f"  sbatch --dependency=afterok:$jid {f_out}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    sub.required = True

    js = sub.add_parser(
        "job-scripts",
        help="write run_prefetch.sh + run_fasterq-dump.sh from an SRR_Acc_List.txt")
    js.add_argument("--srr-list", required=True, metavar="PATH",
                    help="one-accession-per-line list file (e.g. SRR_Acc_List.txt), "
                         "or a directory containing SRR_Acc_List.txt")
    js.add_argument("--workdir", metavar="DIR",
                    help="base dir; defaults .sra to DIR/sra and fastq to DIR/fastq")
    js.add_argument("--prefetch-dir", metavar="DIR",
                    help="explicit .sra output dir (overrides --workdir)")
    js.add_argument("--fastq-dir", metavar="DIR",
                    help="explicit FASTQ output dir (overrides --workdir)")
    js.add_argument("--out-dir", default=".", metavar="DIR",
                    help="where the two .sh files are written (default: current dir)")
    # sra-tools image
    js.add_argument("--sif", metavar="PATH",
                    help=f"local sra-tools .sif image path — the default image "
                         f"source (default path: {DEFAULT_SIF})")
    js.add_argument("--docker", metavar="IMAGE", nargs="?", const=DEFAULT_DOCKER,
                    help=f"pull the image via apptainer instead of a .sif; "
                         f"docker://IMAGE (default IMAGE: {DEFAULT_DOCKER})")
    # SLURM / sra-tools resources (defaults reproduce the templates)
    js.add_argument("--partition", default=DEFAULT_PARTITION)
    js.add_argument("--time", default=DEFAULT_TIME, help="SLURM walltime (D-HH:MM:SS)")
    js.add_argument("--prefetch-cpus", default=DEFAULT_PREFETCH_CPUS,
                    help="cpus-per-task for the prefetch job")
    js.add_argument("--dump-cpus", default=DEFAULT_DUMP_CPUS,
                    help="cpus-per-task and fasterq-dump/pigz threads")
    js.add_argument("--max-size", default=DEFAULT_MAXSIZE,
                    help="prefetch --max-size (increase for large runs)")
    js.set_defaults(func=cmd_job_scripts)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
