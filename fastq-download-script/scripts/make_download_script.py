#!/usr/bin/env python3
"""Generate a bash download script (with a SLURM header) for FASTQ files.

Reads FASTQ URLs from an nf-core/scrnaseq-style samplesheet.csv (the output of
the `ena` / `arrayexpress` / `geo` skills' `samplesheet` command) or from a plain
list of URLs, and writes a runnable bash script with one quiet `curl`/`wget`
command per file, grouped per samplesheet row.

Standard library only. Generates a script; does not download anything itself.

Examples:
    python make_download_script.py samplesheet.csv
    python make_download_script.py samplesheet.csv --tool curl --outdir fastq --out dl.sh
    python make_download_script.py urls.txt --urls --job-name ena_dl --partition short
    python make_download_script.py samplesheet.csv --time 12:00:00 --mem 8G --email me@org.ac.uk
"""
import argparse
import csv
import re
import sys

# --- output field hygiene (see DESIGN.md "Clean output fields") ---
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")  # CR, LF, tab, other control chars


def _safe_field(v):
    """Value safe for one line/cell: control chars -> _, runs of spaces collapsed."""
    return re.sub(r" +", " ", _CTRL_RE.sub("_", v or "")).strip()


def urls_from_samplesheet(path):
    """Return [(sample, [urls])] preserving row order; only http(s)/ftp URLs."""
    out = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        fastq_cols = [c for c in cols if c and c.lower().startswith("fastq")]
        if not fastq_cols:
            raise SystemExit(
                f"No 'fastq_*' columns found in {path}. "
                "Is this a samplesheet? For a plain URL list, pass --urls.")
        sample_col = next((c for c in cols if c and c.lower() == "sample"), None)
        for i, row in enumerate(reader):
            sample = (row.get(sample_col) if sample_col else None) or f"row{i + 1}"
            urls = []
            for c in fastq_cols:
                v = (row.get(c) or "").strip()
                if v and (v.startswith("http") or v.startswith("ftp")):
                    if _CTRL_RE.search(v) or '"' in v:
                        print(f"warning: skipping unsafe URL in {c}: {v!r}", file=sys.stderr)
                        continue
                    urls.append(v)
                elif v:
                    print(f"warning: skipping non-URL value in {c}: {v}", file=sys.stderr)
            if urls:
                out.append((sample, urls))
    return out


def urls_from_list(path):
    out = []
    with open(path) as fh:
        for i, line in enumerate(fh):
            u = line.strip()
            if u and not u.startswith("#") and (u.startswith("http") or u.startswith("ftp")):
                if _CTRL_RE.search(u) or '"' in u:
                    print(f"warning: skipping unsafe URL: {u!r}", file=sys.stderr)
                    continue
                out.append((f"file{i + 1}", [u]))
    return out


def download_cmd(tool, url, outdir):
    name = _safe_field(url.rstrip("/").split("/")[-1])
    dest = f'"{outdir}/{name}"'
    if tool == "curl":
        # -f fail on HTTP errors, -s silent (no progress bar), -S show errors,
        # -L follow redirects, --retry for transient failures.
        return f'curl -fsSL --retry 3 --create-dirs -o {dest} "{url}"'
    # wget: -q fully quiet (no progress bar), retries, -O explicit output path.
    return f'wget -q --tries=3 --waitretry=5 -O {dest} "{url}"'


def slurm_header(args):
    lines = ["#!/bin/bash", "#"]
    sb = [f"#SBATCH --job-name={args.job_name}"]
    if args.partition:
        sb.append(f"#SBATCH --partition={args.partition}")
    else:
        sb.append("# #SBATCH --partition=<your_partition>   # set for your cluster")
    if args.account:
        sb.append(f"#SBATCH --account={args.account}")
    else:
        sb.append("# #SBATCH --account=<your_account>        # set if required")
    sb += [
        f"#SBATCH --cpus-per-task={args.cpus}",
        f"#SBATCH --mem={args.mem}",
        f"#SBATCH --time={args.time}",
        "#SBATCH --output=slurm-%j.out",
        "#SBATCH --error=slurm-%j.err",
    ]
    if args.email:
        sb.append("#SBATCH --mail-type=END,FAIL")
        sb.append(f"#SBATCH --mail-user={args.email}")
    else:
        sb.append("# #SBATCH --mail-type=END,FAIL")
        sb.append("# #SBATCH --mail-user=<you@example.org>")
    return "\n".join(lines + sb)


def build_script(groups, args):
    parts = []
    if not args.no_slurm:
        parts.append(slurm_header(args))
        parts.append("")
    else:
        parts.append("#!/bin/bash")
    parts.append("set -euo pipefail")
    parts.append("")
    parts.append(f'OUTDIR="{args.outdir}"')
    parts.append('mkdir -p "$OUTDIR"')
    parts.append("")
    n_files = 0
    for sample, urls in groups:
        parts.append(f"# sample: {_safe_field(sample)}")
        for u in urls:
            parts.append(download_cmd(args.tool, u, "$OUTDIR"))
            n_files += 1
        parts.append("")
    parts.append(f'echo "Downloaded {n_files} file(s) to $OUTDIR"')
    parts.append("")
    return "\n".join(parts), n_files


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", help="samplesheet.csv (default) or a URL list (with --urls)")
    p.add_argument("--urls", action="store_true", help="treat input as a plain list of URLs (one per line)")
    p.add_argument("--tool", choices=["wget", "curl"], default="wget", help="downloader (default wget)")
    p.add_argument("--outdir", default="fastq", help="directory files are downloaded into")
    p.add_argument("--out", default="download_fastq.sh", help="path for the generated script")
    p.add_argument("--no-slurm", action="store_true", help="omit the SLURM header (plain bash)")
    # SLURM header options
    p.add_argument("--job-name", default="fastq_download")
    p.add_argument("--partition")
    p.add_argument("--account")
    p.add_argument("--cpus", default="1")
    p.add_argument("--mem", default="4G")
    p.add_argument("--time", default="24:00:00")
    p.add_argument("--email")
    args = p.parse_args()

    groups = urls_from_list(args.input) if args.urls else urls_from_samplesheet(args.input)
    if not groups:
        raise SystemExit("No FASTQ URLs found in the input.")
    script, n = build_script(groups, args)
    with open(args.out, "w") as fh:
        fh.write(script)
    import os
    os.chmod(args.out, 0o755)
    print(f"Wrote {args.out}: {n} download command(s) across {len(groups)} row(s) "
          f"using {args.tool}.", file=sys.stderr)
    if not args.no_slurm:
        print(f"Submit with: sbatch {args.out}   (or run directly: ./{args.out})", file=sys.stderr)


if __name__ == "__main__":
    main()
