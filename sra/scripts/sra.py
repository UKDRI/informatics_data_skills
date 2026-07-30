#!/usr/bin/env python3
"""Generate SRA-tools SLURM job scripts (prefetch + fasterq-dump [+ cellranger links]).

Fills the job-script templates in ``sra/templates/`` from an existing
``SRR_Acc_List.txt`` (one accession per line, e.g. the output of the `geo`
skill's ``runtable`` command) and writes ready-to-submit scripts:

    run_prefetch.sh                prefetch each SRR accession into .sra files
    run_fasterq-dump.sh            fasterq-dump those .sra files into gzipped FASTQ
    run_link-cellranger-fastq.sh   (--cellranger-links) symlink the 10x read pair as
                                   <run>_S1_L001_R{1,2}_001.fastq.gz

The steps MUST run in order (each reads what the previous wrote); this tool only
writes the scripts and never submits anything. Standard library only.

Examples:
    python sra.py job-scripts --srr-list SRR_Acc_List.txt --workdir /nfsdata/$USER/study1
    python sra.py job-scripts --srr-list SRR_Acc_List.txt \\
        --prefetch-dir /nfsdata/$USER/study1/sra --fastq-dir /nfsdata/$USER/study1/fastq
    python sra.py job-scripts --srr-list SRR_Acc_List.txt --workdir ./study1 \\
        --docker ncbi/sra-tools:3.2.1        # pull image via apptainer instead of a .sif
    python sra.py job-scripts --srr-list SRR_Acc_List.txt --workdir ./study1 \\
        --cellranger-links --read-map 3,4    # 10x dual-index (e.g. Chromium 5')
"""
import argparse
import os
import re
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
# The link step is I/O-only and finishes in seconds, so it gets its own short
# walltime rather than sharing the 7-day --time of prefetch/fasterq-dump.
DEFAULT_LINK_TIME = "0-02:00:00"
# Right for bulk and for a two-file 10x run. Single-cell studies commonly need
# 2,3 (single index) or 3,4 (dual index, e.g. Chromium 5') — count the dumped
# files for one run rather than trusting this default (see DESIGN.md, `sra`).
DEFAULT_READ_MAP = "1,2"

_READ_MAP_RE = re.compile(r"([1-4]),([1-4])")


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
                            "__IMAGE__", "__MAXSIZE__", "__NCPU__", "__LINK_TIME__",
                            "__LINK_DIR__", "__READ_MAP__") if w in text]
    if leftover:
        raise SystemExit(f"Template still contains unfilled placeholders: {leftover}")
    return text


def safe_path(value, what):
    """Reject a path that could break out of the generated shell script.

    The templates use unquoted `$var` expansions, so a control character, quote,
    `$` or backtick in a substituted path could escape into an executable line
    (see DESIGN.md "Clean output fields"). Cleaning silently would produce a path
    that does not exist, so this errors instead.
    """
    bad = [c for c in value if ord(c) < 0x20 or ord(c) == 0x7f or c in "\"'$`\\"]
    if bad:
        raise SystemExit(
            f"{what} contains characters that are unsafe in a shell script "
            f"({''.join(sorted(set(bad)))!r}): {value!r}")
    if any(c.isspace() for c in value):
        print(f"warning: {what} contains whitespace; the generated scripts expand "
              f"paths unquoted and will not handle it: {value!r}", file=sys.stderr)
    return value


def parse_read_map(value):
    """Validate a '<r1>,<r2>' read map. Substituted unquoted into bash."""
    m = _READ_MAP_RE.fullmatch((value or "").strip())
    if not m:
        raise SystemExit(
            f"--read-map must be '<r1>,<r2>' with each of 1-4 (e.g. 3,4), got {value!r}. "
            "fasterq-dump numbers its output positionally: 2 files -> 1,2; "
            "3 files (single index) -> 2,3; 4 files (dual index) -> 3,4.")
    r1, r2 = m.group(1), m.group(2)
    if r1 == r2:
        raise SystemExit(f"--read-map R1 and R2 must differ, got {value!r}.")
    return f"{r1},{r2}"


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
    prefetch_dir = safe_path(args.prefetch_dir or os.path.join(args.workdir, "sra"),
                             "the .sra directory")
    fastq_dir = safe_path(args.fastq_dir or os.path.join(args.workdir, "fastq"),
                          "the FASTQ directory")

    # --- the optional third step: cellranger-named symlinks over the dump output ---
    link_only = {"--link-dir": args.link_dir, "--read-map": args.read_map,
                 "--link-time": args.link_time}
    if not args.cellranger_links:
        used = [f for f, v in link_only.items() if v]
        if used:
            raise SystemExit(
                f"{', '.join(used)} only applies with --cellranger-links "
                "(which writes the third job script, run_link-cellranger-fastq.sh).")
    link_dir = safe_path(args.link_dir or fastq_dir, "the symlink directory")
    read_map = parse_read_map(args.read_map or DEFAULT_READ_MAP)

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
    outs = [p_out, f_out]

    if args.cellranger_links:
        # The link step reads the dump output directory and writes symlinks beside it.
        link = fill(read_template("run_link-cellranger-fastq.sh"), {
            "__PARTITION__": args.partition,
            "__LINK_TIME__": args.link_time or DEFAULT_LINK_TIME,
            "__FASTQ_DIR__": fastq_dir,
            "__LINK_DIR__": link_dir,
            "__READ_MAP__": read_map,
        })
        l_out = os.path.join(args.out_dir, "run_link-cellranger-fastq.sh")
        write_script(l_out, link)
        outs.append(l_out)

    # --- report (stderr = progress); never submits ---
    print(f"Wrote {len(outs)} script(s) for {n_acc} accession(s):", file=sys.stderr)
    for o in outs:
        print(f"  {o}", file=sys.stderr)
    print(f"  image:        {image}", file=sys.stderr)
    print(f"  .sra dir:     {prefetch_dir}", file=sys.stderr)
    print(f"  fastq dir:    {fastq_dir}", file=sys.stderr)
    if args.cellranger_links:
        print(f"  symlink dir:  {link_dir}", file=sys.stderr)
        print(f"  read map:     {read_map}  (R1,R2 among the dumped _N files)", file=sys.stderr)
        if read_map == DEFAULT_READ_MAP:
            print("  NOTE: read-map is the default 1,2 — right for bulk and a two-file 10x",
                  file=sys.stderr)
            print("        run, but a 10x run with its technical reads submitted separately",
                  file=sys.stderr)
            print("        needs 2,3 (single index) or 3,4 (dual index, e.g. Chromium 5').",
                  file=sys.stderr)
            print("        Count the dumped files for one run before submitting.",
                  file=sys.stderr)
    print("", file=sys.stderr)
    print(f"Run the {len(outs)} steps IN ORDER — each reads what the previous writes.",
          file=sys.stderr)
    print("To serialize them as dependent SLURM jobs:", file=sys.stderr)
    print(f"  jid=$(sbatch --parsable {p_out})", file=sys.stderr)
    if args.cellranger_links:
        print(f"  jid=$(sbatch --parsable --dependency=afterok:$jid {f_out})", file=sys.stderr)
        print(f"  sbatch --dependency=afterok:$jid {outs[2]}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Then build a matching sample sheet against the symlinks, e.g.:", file=sys.stderr)
        print(f"  ena samplesheet ACC --assay scrna --fastq-dir {link_dir} "
              "--fastq-naming cellranger", file=sys.stderr)
    else:
        print(f"  sbatch --dependency=afterok:$jid {f_out}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    sub.required = True

    js = sub.add_parser(
        "job-scripts",
        help="write run_prefetch.sh + run_fasterq-dump.sh (+ the cellranger link "
             "script) from an SRR_Acc_List.txt")
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
                    help="where the .sh files are written (default: current dir)")
    # optional third step: cellranger-named symlinks for 10x reads
    js.add_argument("--cellranger-links", action="store_true",
                    help="also write run_link-cellranger-fastq.sh, symlinking the 10x "
                         "read pair as <run>_S1_L001_R{1,2}_001.fastq.gz (the naming "
                         "cellranger requires; nf-core/scrnaseq accepts it too)")
    js.add_argument("--link-dir", metavar="DIR",
                    help="where the symlinks go (default: the FASTQ output dir); "
                         "requires --cellranger-links")
    js.add_argument("--read-map", metavar="R1,R2",
                    help=f"which dumped files are the cDNA read pair (default "
                         f"{DEFAULT_READ_MAP}): 2 files -> 1,2; 3 files (single index) "
                         f"-> 2,3; 4 files (dual index, e.g. Chromium 5') -> 3,4. "
                         f"Declared, never detected; requires --cellranger-links")
    js.add_argument("--link-time", metavar="D-HH:MM:SS",
                    help=f"walltime for the link job only (default {DEFAULT_LINK_TIME}); "
                         f"requires --cellranger-links")
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
