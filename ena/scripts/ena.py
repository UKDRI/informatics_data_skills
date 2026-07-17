#!/usr/bin/env python3
"""Query metadata and download data from the European Nucleotide Archive (ENA).

Uses the ENA Portal API (https://www.ebi.ac.uk/ena/portal/api/) for metadata /
file reports and the ENA Browser API for record XML. Sequence data is downloaded
over HTTPS from the FTP links returned in file reports.

Standard library only (urllib) -- no pip install required.

Examples:
    python ena.py runs PRJEB1787
    python ena.py report PRJEB1787 --result read_run --fields run_accession,fastq_ftp,fastq_bytes
    python ena.py fields --result read_run
    python ena.py xml SAMEA1968848
    python ena.py search --result read_run --query 'tax_eq(9606) AND library_strategy="WGS"' --limit 10
    python ena.py download PRJEB1787 --out ./ena_out
    python ena.py metadata-table PRJEB1787 --out metadata.tsv
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

PORTAL = "https://www.ebi.ac.uk/ena/portal/api"
BROWSER = "https://www.ebi.ac.uk/ena/browser/api"
USER_AGENT = "ena-skill/1.0"

# Fields returned by default for run-level file reports.
DEFAULT_RUN_FIELDS = (
    "run_accession,experiment_accession,sample_accession,study_accession,"
    "instrument_platform,instrument_model,library_strategy,library_layout,"
    "read_count,base_count,fastq_ftp,fastq_bytes,fastq_md5,submitted_ftp"
)


def http_get(url, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise SystemExit(f"GET failed for {url}: {last}")


def portal_get(endpoint, params):
    url = f"{PORTAL}/{endpoint}?" + urllib.parse.urlencode(params)
    return http_get(url).decode("utf-8", "replace")


def parse_tsv(text):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    header = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        cols = ln.split("\t")
        rows.append(dict(zip(header, cols)))
    return rows


# ---- nf-core/scrnaseq samplesheet helpers (shared shape across skills) ----
import csv
import re

SAMPLESHEET_COLS = ["sample", "fastq_1", "fastq_2"]


def clean_sample(name):
    """nf-core converts whitespace in sample names to underscores."""
    return re.sub(r"\s+", "_", (name or "").strip())


def to_https(url):
    if url.startswith("ftp://"):
        return "https://" + url[len("ftp://"):]
    if not url.startswith("http"):
        return "https://" + url
    return url


def fastq_pair(urls):
    """Pick (fastq_1, fastq_2) from the FASTQ URLs of one sequencing run.

    Recognises Illumina R1/R2 and ENA _1/_2 naming; index reads are ignored.
    """
    urls = [u for u in urls if u]

    def b(u):
        return u.rsplit("/", 1)[-1].lower()

    def is_r1(u):
        n = b(u)
        return "_r1" in n or "_1.fastq" in n or "_1.fq" in n
    def is_r2(u):
        n = b(u)
        return "_r2" in n or "_2.fastq" in n or "_2.fq" in n
    def is_index(u):
        n = b(u)
        return "_i1" in n or "_i2" in n or "_r3" in n or "_3.fastq" in n

    r1 = [u for u in urls if is_r1(u)]
    r2 = [u for u in urls if is_r2(u)]
    if r1 and r2:
        return r1[0], r2[0]
    non_idx = [u for u in urls if not is_index(u)]
    if len(non_idx) >= 2:
        return non_idx[0], non_idx[1]
    if len(non_idx) == 1:
        return non_idx[0], ""
    if urls:
        return urls[0], (urls[1] if len(urls) > 1 else "")
    return "", ""


def write_samplesheet(rows, out, assay, strandedness="auto"):
    """Write an nf-core sample sheet.

    assay 'scrna' → nf-core/scrnaseq columns (sample,fastq_1,fastq_2);
    assay 'bulk'  → nf-core/rnaseq columns (+ strandedness).
    """
    cols = list(SAMPLESHEET_COLS) + (["strandedness"] if assay == "bulk" else [])
    rows = sorted(rows, key=lambda x: (x["sample"], x["fastq_1"]))
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            row = dict(r)
            if assay == "bulk":
                row["strandedness"] = strandedness
            w.writerow([row.get(c, "") for c in cols])
    return len(rows)


def rows_from_ena_runs(runs, group_by="sample_accession", local_dir=None):
    rows = []
    for r in runs:
        links = [l for l in r.get("fastq_ftp", "").split(";") if l]
        urls = [to_https(l) for l in links]
        f1, f2 = fastq_pair(urls)
        if local_dir:
            run = r.get("run_accession", "run")
            f1 = os.path.join(local_dir, run, f1.rsplit("/", 1)[-1]) if f1 else ""
            f2 = os.path.join(local_dir, run, f2.rsplit("/", 1)[-1]) if f2 else ""
        sample = r.get(group_by) or r.get("sample_accession") or r.get("run_accession")
        rows.append({"sample": clean_sample(sample), "fastq_1": f1, "fastq_2": f2})
    return rows


# ---- harmonized metadata.tsv (shared shape across skills) ----
import html

METADATA_COLS = ["sample", "replicate", "species", "sex", "age",
                 "condition", "genotype", "treatment", "tissue"]
NA = "NA"

# Source-native annotation names (normalised: lowercased, wrapper-stripped)
# mapped onto the core columns. First match wins; any characteristic that matches
# no core field is promoted to its own extra column (see write_metadata_tsv).
FIELD_KEYS = {
    "species": ["organism", "scientific_name", "species", "organism scientific name"],
    "sex": ["sex", "gender"],
    "age": ["age", "developmental stage", "dev stage", "age at collection", "age at sampling"],
    "condition": ["disease", "disease state", "condition", "phenotype",
                  "health state", "clinical information", "diagnosis"],
    "genotype": ["genotype", "genotype/variation", "variation", "strain",
                 "strain/background", "background"],
    "treatment": ["treatment", "agent", "compound", "stimulus",
                  "perturbation", "dose", "treatment protocol"],
    "tissue": ["tissue", "organism part", "tissue type", "tissue region", "source tissue"],
}
_REPLICATE_KEYS = ("replicate", "biological replicate", "technical replicate",
                   "replicate number")
_IDENTITY_KEYS = ("source name", "sample", "sample name", "sample_accession",
                  "run_accession", "assay name", "name", "title")
_NULLS = {"", "na", "n/a", "none", "null", "unknown", "not applicable",
          "not available", "not collected", "not provided", "missing", "--"}


def _norm_key(k):
    k = (k or "").strip().lower()
    m = re.match(r"(?:characteristics|comment|factor\s*value|factorvalue)\s*\[(.+)\]$", k)
    return m.group(1).strip() if m else k


def _clean_val(v):
    v = re.sub(r"\s+", " ", html.unescape(v or "").strip())
    return "" if v.lower() in _NULLS else v


def _col_name(k):
    """Column-safe name for a promoted extra characteristic."""
    return re.sub(r"[^0-9a-z]+", "_", k.strip().lower()).strip("_") or "field"


def harmonize_row(sample, replicate, attrs):
    """Map source-native (name -> value) annotations onto the metadata columns.

    Core fields (METADATA_COLS) are always present; missing ones become 'NA'. Every
    other characteristic is promoted to its own column so nothing is dropped.
    """
    norm = {}
    for k, v in (attrs or {}).items():
        nk, cv = _norm_key(k), _clean_val(v)
        if nk and cv and nk not in norm:
            norm[nk] = cv
    row = {"sample": _clean_val(sample) or NA,
           "replicate": _clean_val(replicate) or NA}
    used = set(_REPLICATE_KEYS) | set(_IDENTITY_KEYS)
    for field, keys in FIELD_KEYS.items():
        used.update(keys)  # every synonym is consumed, not just the matched one
        val = ""
        for cand in keys:
            if norm.get(cand):
                val = norm[cand]
                break
        row[field] = val or NA
    for k, v in norm.items():
        if k not in used:
            row.setdefault(_col_name(k), v)
    return row


def write_metadata_tsv(rows, out):
    """Write rows as TSV; header = core columns + union of any extra columns."""
    header = list(METADATA_COLS)
    for r in rows:
        for k in r:
            if k not in header:
                header.append(k)
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(header)
        for r in rows:
            w.writerow([r.get(c, NA) for c in header])
    return len(rows), len(header)


def ena_sample_attrs(sample_accession):
    """Parse SAMPLE_ATTRIBUTES (TAG/VALUE) + scientific name from ENA sample XML."""
    try:
        xml = http_get(f"{BROWSER}/xml/{sample_accession}").decode("utf-8", "replace")
    except SystemExit:
        return {}
    attrs = {}
    for tag, val in re.findall(r"<TAG>(.*?)</TAG>\s*<VALUE>(.*?)</VALUE>",
                               xml, re.DOTALL | re.IGNORECASE):
        tag = html.unescape(tag).strip()
        # Drop ENA's own bookkeeping tags (spot/base counts, dates, checklist).
        if tag.upper().startswith("ENA-"):
            continue
        attrs[tag] = html.unescape(val).strip()
    m = re.search(r"<SCIENTIFIC_NAME>(.*?)</SCIENTIFIC_NAME>", xml, re.DOTALL | re.IGNORECASE)
    if m:
        attrs.setdefault("scientific_name", html.unescape(m.group(1)).strip())
    return attrs


def cmd_metadata_table(args):
    """Write a harmonized metadata.tsv (one row per sample x run/replicate).

    Runs are the replicate unit; per-sample characteristics (species, sex, age,
    condition, genotype, treatment) come from each sample's SAMPLE_ATTRIBUTES.
    """
    text = portal_get(
        "filereport",
        {"accession": args.accession, "result": "read_run",
         "fields": "run_accession,sample_accession,scientific_name",
         "format": "tsv", "limit": "0"},
    )
    runs = parse_tsv(text)
    if not runs:
        raise SystemExit(
            f"No read_run records found in ENA for {args.accession}; "
            "cannot build a sample x replicate table.")
    cache = {}
    rows = []
    for r in runs:
        samp = r.get("sample_accession") or r.get("run_accession") or ""
        if samp and samp not in cache:
            cache[samp] = ena_sample_attrs(samp)
        attrs = dict(cache.get(samp, {}))
        if r.get("scientific_name"):
            attrs.setdefault("scientific_name", r["scientific_name"])
        replicate = r.get("run_accession") or "1"
        rows.append(harmonize_row(samp, replicate, attrs))
    n, ncols = write_metadata_tsv(rows, args.out)
    print(f"Wrote {n} sample x replicate row(s) x {ncols} column(s) for "
          f"{args.accession} to {args.out}", file=sys.stderr)


def cmd_samplesheet(args):
    fields = ("run_accession,experiment_accession,sample_accession,sample_alias,"
              "sample_title,library_layout,fastq_ftp")
    text = portal_get(
        "filereport",
        {"accession": args.accession, "result": "read_run", "fields": fields,
         "format": "tsv", "limit": "0"},
    )
    runs = parse_tsv(text)
    runs = [r for r in runs if r.get("fastq_ftp")]
    if not runs:
        raise SystemExit(
            f"No public FASTQ runs found in ENA for {args.accession}. "
            "The data may be under controlled access or not mirrored to ENA.")
    rows = rows_from_ena_runs(runs, group_by=args.group_by, local_dir=args.local_dir)
    n = write_samplesheet(rows, args.out, args.assay, args.strandedness)
    print(f"Wrote {n} row(s) for {len({r['sample'] for r in rows})} sample(s) to {args.out} "
          f"(nf-core/{'rnaseq' if args.assay == 'bulk' else 'scrnaseq'})", file=sys.stderr)


def cmd_report(args):
    fields = args.fields or DEFAULT_RUN_FIELDS
    fmt = "json" if args.json else "tsv"
    text = portal_get(
        "filereport",
        {"accession": args.accession, "result": args.result, "fields": fields,
         "format": fmt, "limit": str(args.limit)},
    )
    if args.json:
        print(text)
    else:
        print(text.rstrip("\n"))


def cmd_runs(args):
    text = portal_get(
        "filereport",
        {"accession": args.accession, "result": "read_run",
         "fields": DEFAULT_RUN_FIELDS, "format": "tsv", "limit": "0"},
    )
    rows = parse_tsv(text)
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    print(f"{len(rows)} run(s) for {args.accession}:\n")
    for r in rows:
        size = r.get("fastq_bytes", "")
        print(f"{r.get('run_accession',''):14s} {r.get('instrument_platform',''):12s} "
              f"{r.get('library_strategy',''):12s} reads={r.get('read_count','?')}")
        for link in filter(None, r.get("fastq_ftp", "").split(";")):
            print(f"    ftp: {link}")


def cmd_fields(args):
    text = portal_get("returnFields", {"result": args.result, "format": "tsv"})
    print(text.rstrip("\n"))


def cmd_search(args):
    fields = args.fields or DEFAULT_RUN_FIELDS
    params = {"result": args.result, "fields": fields,
              "format": "json" if args.json else "tsv", "limit": str(args.limit)}
    if args.query:
        params["query"] = args.query
    text = portal_get("search", params)
    print(text.rstrip("\n"))


def cmd_xml(args):
    """Fetch the raw record (XML by default) via the Browser API."""
    fmt = args.format
    data = http_get(f"{BROWSER}/{fmt}/{args.accession}")
    sys.stdout.write(data.decode("utf-8", "replace"))


def download_file(link, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    url = link if link.startswith("http") else "https://" + link
    name = url.rstrip("/").split("/")[-1]
    dest = os.path.join(out_dir, name)
    if os.path.exists(dest):
        print(f"  exists, skipping {name}", file=sys.stderr)
        return dest
    print(f"  downloading {name} ...", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=600) as r, open(dest + ".part", "wb") as fh:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
    os.replace(dest + ".part", dest)
    print(f"  saved {dest}", file=sys.stderr)
    return dest


def cmd_download(args):
    field = "submitted_ftp" if args.submitted else "fastq_ftp"
    text = portal_get(
        "filereport",
        {"accession": args.accession, "result": args.result,
         "fields": f"run_accession,{field}", "format": "tsv", "limit": "0"},
    )
    rows = parse_tsv(text)
    if not rows:
        raise SystemExit(f"No {args.result} records for {args.accession}")
    total = 0
    for r in rows:
        run = r.get("run_accession", "run")
        for link in filter(None, r.get(field, "").split(";")):
            download_file(link, os.path.join(args.out, run))
            total += 1
    print(f"Downloaded {total} file(s) to {args.out}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("runs", help="List sequencing runs + FASTQ links for a study/sample")
    r.add_argument("accession")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_runs)

    rep = sub.add_parser("report", help="Raw file report (choose result type + fields)")
    rep.add_argument("accession")
    rep.add_argument("--result", default="read_run",
                     help="read_run, read_experiment, analysis, assembly, sample, study, ...")
    rep.add_argument("--fields", help="comma-separated field list (see `fields`)")
    rep.add_argument("--limit", type=int, default=0, help="0 = no limit")
    rep.add_argument("--json", action="store_true")
    rep.set_defaults(func=cmd_report)

    f = sub.add_parser("fields", help="List available return fields for a result type")
    f.add_argument("--result", default="read_run")
    f.set_defaults(func=cmd_fields)

    s = sub.add_parser("search", help="Advanced search of the Portal API")
    s.add_argument("--result", default="read_run")
    s.add_argument("--query", help='e.g. tax_eq(9606) AND library_strategy="WGS"')
    s.add_argument("--fields")
    s.add_argument("--limit", type=int, default=100)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_search)

    x = sub.add_parser("xml", help="Fetch a record via the Browser API (XML/JSON/EMBL/FASTA)")
    x.add_argument("accession")
    x.add_argument("--format", default="xml", help="xml, json, embl, fasta, text")
    x.set_defaults(func=cmd_xml)

    d = sub.add_parser("download", help="Download FASTQ (or submitted) files for a study/run")
    d.add_argument("accession")
    d.add_argument("--out", default="./ena_out")
    d.add_argument("--result", default="read_run")
    d.add_argument("--submitted", action="store_true",
                   help="download originally submitted files instead of ENA FASTQ")
    d.set_defaults(func=cmd_download)

    mt = sub.add_parser("metadata-table",
                        help="Write a harmonized metadata.tsv (one row per sample x replicate)")
    mt.add_argument("accession")
    mt.add_argument("--out", default="metadata.tsv")
    mt.set_defaults(func=cmd_metadata_table)

    ss = sub.add_parser("samplesheet",
                        help="Build an nf-core samplesheet.csv from FASTQ runs (--assay scrna|bulk)")
    ss.add_argument("accession")
    ss.add_argument("--assay", choices=["scrna", "bulk"], required=True,
                    help="scrna -> nf-core/scrnaseq (sample,fastq_1,fastq_2); "
                         "bulk -> nf-core/rnaseq (adds a strandedness column)")
    ss.add_argument("--strandedness", choices=["auto", "forward", "reverse", "unstranded"],
                    default="auto",
                    help="value for the rnaseq strandedness column (only --assay bulk; default auto)")
    ss.add_argument("--out", default="samplesheet.csv")
    ss.add_argument("--group-by", default="sample_accession",
                    help="run field used as the `sample` column "
                         "(sample_accession, sample_alias, sample_title, experiment_accession)")
    ss.add_argument("--local-dir",
                    help="write local paths <dir>/<run>/<file> instead of ENA URLs "
                         "(matches `download` output layout)")
    ss.set_defaults(func=cmd_samplesheet)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
