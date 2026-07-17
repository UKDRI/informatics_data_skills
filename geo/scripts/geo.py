#!/usr/bin/env python3
"""Query metadata and download data from NCBI Gene Expression Omnibus (GEO).

Metadata is retrieved through NCBI E-utilities (db=gds); data files are pulled
from the GEO FTP tree at https://ftp.ncbi.nlm.nih.gov/geo/ .

Standard library only (urllib) -- no pip install required.

Examples:
    python geo.py metadata GSE2553
    python geo.py samples GSE2553
    python geo.py files GSE2553
    python geo.py download GSE2553 --matrix --out ./geo_out
    python geo.py download GSE2553 --suppl --out ./geo_out
    python geo.py search "breast cancer RNA-seq" --organism "Homo sapiens" --limit 20
    python geo.py metadata-table GSE2553 --out metadata.tsv
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/geo"
USER_AGENT = "geo-skill/1.0 (https://www.ncbi.nlm.nih.gov/geo/)"

# NCBI asks for an email + optional api_key to lift rate limits. Set via env.
NCBI_EMAIL = os.environ.get("NCBI_EMAIL", "")
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")


def _eutil_params(extra):
    p = dict(extra)
    if NCBI_EMAIL:
        p["email"] = NCBI_EMAIL
        p["tool"] = "geo-skill"
    if NCBI_API_KEY:
        p["api_key"] = NCBI_API_KEY
    return p


def http_get(url, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise SystemExit(f"GET failed for {url}: {last}")


def get_json(base, params):
    url = base + "?" + urllib.parse.urlencode(_eutil_params(params))
    return json.loads(http_get(url).decode("utf-8", "replace"))


def geo_ftp_dir(accession):
    """Return the FTP subdirectory + type dir for a GEO accession.

    GSE2553 -> ('series', 'GSE2nnn'), GSM12345 -> ('samples', 'GSM12nnn').
    """
    accession = accession.strip().upper()
    prefix = accession[:3]
    num = accession[3:]
    type_dir = {"GSE": "series", "GSM": "samples", "GPL": "platforms"}.get(prefix)
    if not type_dir:
        raise SystemExit(f"Unsupported accession for FTP download: {accession}")
    stub = f"{prefix}{num[:-3]}nnn" if len(num) > 3 else f"{prefix}nnn"
    return type_dir, stub


def resolve_uid(accession):
    """Resolve a GEO accession (GSE/GSM/GPL/GDS) to a db=gds UID."""
    res = get_json(
        f"{EUTILS}/esearch.fcgi",
        {"db": "gds", "term": f"{accession}[ACCN]", "retmode": "json", "retmax": "20"},
    )
    ids = res.get("esearchresult", {}).get("idlist", [])
    if not ids:
        raise SystemExit(f"No GEO record found for accession {accession}")
    # Prefer the UID whose summary accession matches exactly.
    summ = get_json(
        f"{EUTILS}/esummary.fcgi",
        {"db": "gds", "id": ",".join(ids), "retmode": "json"},
    ).get("result", {})
    for uid in summ.get("uids", []):
        if summ[uid].get("accession", "").upper() == accession.upper():
            return uid, summ[uid]
    uid = ids[0]
    return uid, summ.get(uid, {})


def cmd_metadata(args):
    _, rec = resolve_uid(args.accession)
    if args.json:
        print(json.dumps(rec, indent=2))
        return
    fields = [
        "accession", "title", "taxon", "gdstype", "gpl", "n_samples",
        "pdat", "summary",
    ]
    for f in fields:
        val = rec.get(f, "")
        print(f"{f:12s}: {val}")


def cmd_samples(args):
    _, rec = resolve_uid(args.accession)
    samples = rec.get("samples", [])
    if args.json:
        print(json.dumps(samples, indent=2))
        return
    if not samples:
        print("No sample list in summary (query the SOFT file for full sample metadata).")
        return
    for s in samples:
        print(f"{s.get('accession', '')}\t{s.get('title', '')}")


def list_ftp_files(url):
    """Parse an Apache-style FTP HTML directory listing into filenames."""
    import re
    html = http_get(url).decode("utf-8", "replace")
    names = re.findall(r'href="([^"?/][^"]*)"', html)
    # Keep only real entries in this directory: no absolute URLs (footer links),
    # no protocol/query/anchor junk, no parent-dir links.
    return [n for n in names if "://" not in n and ":" not in n and n not in ("..", ".")]


def cmd_files(args):
    type_dir, stub = geo_ftp_dir(args.accession)
    base = f"{FTP_BASE}/{type_dir}/{stub}/{args.accession.upper()}"
    out = {}
    for sub in ("matrix", "soft", "miniml", "suppl"):
        try:
            files = list_ftp_files(f"{base}/{sub}/")
            if files:
                out[sub] = [f"{base}/{sub}/{f}" for f in files]
        except SystemExit:
            continue
    if args.json:
        print(json.dumps(out, indent=2))
        return
    for sub, urls in out.items():
        print(f"[{sub}]")
        for u in urls:
            print(f"  {u}")
    if not out:
        print("No files found on GEO FTP for this accession.")


def download(url, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    name = url.rstrip("/").split("/")[-1]
    dest = os.path.join(out_dir, name)
    print(f"  downloading {name} ...", file=sys.stderr)
    data = http_get(url)
    with open(dest, "wb") as fh:
        fh.write(data)
    print(f"  saved {dest} ({len(data)} bytes)", file=sys.stderr)
    return dest


def cmd_download(args):
    type_dir, stub = geo_ftp_dir(args.accession)
    base = f"{FTP_BASE}/{type_dir}/{stub}/{args.accession.upper()}"
    subs = []
    if args.matrix:
        subs.append("matrix")
    if args.soft:
        subs.append("soft")
    if args.miniml:
        subs.append("miniml")
    if args.suppl:
        subs.append("suppl")
    if not subs:
        subs = ["matrix"]  # sensible default
    for sub in subs:
        try:
            files = list_ftp_files(f"{base}/{sub}/")
        except SystemExit:
            print(f"[{sub}] not available", file=sys.stderr)
            continue
        for f in files:
            download(f"{base}/{sub}/{f}", os.path.join(args.out, args.accession.upper(), sub))


# ---- nf-core/scrnaseq samplesheet ----
# GEO does not host raw reads; they live in SRA/ENA. We resolve the linked
# SRA study / BioProject from the GEO record, then pull FASTQ links from ENA.
import csv
import re

ENA_PORTAL = "https://www.ebi.ac.uk/ena/portal/api"
SAMPLESHEET_COLS = ["sample", "fastq_1", "fastq_2"]


def clean_sample(name):
    return re.sub(r"\s+", "_", (name or "").strip())


def to_https(url):
    if url.startswith("ftp://"):
        return "https://" + url[len("ftp://"):]
    if not url.startswith("http"):
        return "https://" + url
    return url


def fastq_pair(urls):
    urls = [u for u in urls if u]

    def b(u):
        return u.rsplit("/", 1)[-1].lower()

    r1 = [u for u in urls if any(t in b(u) for t in ("_r1", "_1.fastq", "_1.fq"))]
    r2 = [u for u in urls if any(t in b(u) for t in ("_r2", "_2.fastq", "_2.fq"))]
    if r1 and r2:
        return r1[0], r2[0]
    non_idx = [u for u in urls if not any(t in b(u) for t in ("_i1", "_i2", "_r3", "_3.fastq"))]
    if len(non_idx) >= 2:
        return non_idx[0], non_idx[1]
    if len(non_idx) == 1:
        return non_idx[0], ""
    if urls:
        return urls[0], (urls[1] if len(urls) > 1 else "")
    return "", ""


def resolve_sra_project(accession):
    """Find the SRA study / BioProject linked to a GEO accession."""
    url = ("https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc="
           + accession + "&targ=self&form=text&view=brief")
    text = http_get(url).decode("utf-8", "replace")
    for pat in (r"PRJ[A-Z]+\d+", r"SRP\d+|ERP\d+|DRP\d+", r"SRX\d+|ERX\d+"):
        m = re.search(pat, text)
        if m:
            return m.group(0)
    return None


def ena_runs(project):
    fields = ("run_accession,experiment_accession,sample_accession,sample_alias,"
              "sample_title,library_layout,fastq_ftp")
    url = (f"{ENA_PORTAL}/filereport?accession={project}"
           f"&result=read_run&fields={fields}&format=tsv&limit=0")
    text = http_get(url).decode("utf-8", "replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header = lines[0].split("\t")
    return [dict(zip(header, ln.split("\t"))) for ln in lines[1:]]


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


def cmd_samplesheet(args):
    project = resolve_sra_project(args.accession)
    if not project:
        raise SystemExit(
            f"Could not find a linked SRA/BioProject for {args.accession}. "
            "Check the series relations, or query ENA directly with the SRP/PRJNA accession.")
    print(f"{args.accession} -> SRA project {project}", file=sys.stderr)
    runs = [r for r in ena_runs(project) if r.get("fastq_ftp")]
    if not runs:
        raise SystemExit(
            f"No public FASTQ found in ENA for {project} (linked to {args.accession}). "
            "The raw data may be under controlled access (e.g. dbGaP) or not mirrored to ENA.")
    rows = []
    for r in runs:
        urls = [to_https(l) for l in r.get("fastq_ftp", "").split(";") if l]
        f1, f2 = fastq_pair(urls)
        if args.local_dir:
            run = r.get("run_accession", "run")
            f1 = os.path.join(args.local_dir, run, f1.rsplit("/", 1)[-1]) if f1 else ""
            f2 = os.path.join(args.local_dir, run, f2.rsplit("/", 1)[-1]) if f2 else ""
        sample = r.get(args.group_by) or r.get("sample_accession") or r.get("run_accession")
        rows.append({"sample": clean_sample(sample), "fastq_1": f1, "fastq_2": f2})
    n = write_samplesheet(rows, args.out, args.assay, args.strandedness)
    print(f"Wrote {n} row(s) for {len({r['sample'] for r in rows})} sample(s) to {args.out} "
          f"(nf-core/{'rnaseq' if args.assay == 'bulk' else 'scrnaseq'})", file=sys.stderr)


# ---- harmonized metadata.tsv (shared shape across skills) ----
import html

METADATA_COLS = ["sample", "replicate", "species", "sex", "age",
                 "condition", "genotype", "treatment", "tissue"]
NA = "NA"

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


def geo_sample_soft(gsm):
    url = ("https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc="
           + gsm + "&targ=self&form=text&view=quick")
    return http_get(url).decode("utf-8", "replace")


def parse_geo_sample(text):
    """Pull organism + `!Sample_characteristics_ch*` (tag: value) from SOFT text."""
    attrs = {}
    organism = ""
    for ln in text.splitlines():
        ln = ln.strip()
        if "=" not in ln:
            continue
        key, _, val = ln.partition("=")
        key, val = key.strip(), val.strip()
        if key.startswith("!Sample_organism") and val:
            organism = val
        elif key.startswith("!Sample_characteristics") and val:
            if ":" in val:
                tag, tv = val.split(":", 1)
                attrs.setdefault(tag.strip(), tv.strip())
            else:
                attrs.setdefault(val, "")
    if organism:
        attrs.setdefault("organism", organism)
    return attrs


def cmd_metadata_table(args):
    """Write a harmonized metadata.tsv (one row per sample/GSM).

    Per-sample characteristics are read from each GSM's SOFT record; each GSM is a
    row, with `replicate` taken from a replicate characteristic when present else 1.
    """
    _, rec = resolve_uid(args.accession)
    samples = rec.get("samples", [])
    if not samples:
        raise SystemExit(
            f"No sample list in the GEO summary for {args.accession}; "
            "cannot build a per-sample metadata table.")
    rows = []
    for s in samples:
        gsm = s.get("accession", "")
        attrs = {}
        if gsm:
            try:
                attrs = parse_geo_sample(geo_sample_soft(gsm))
            except SystemExit:
                attrs = {}
        attrs.setdefault("organism", rec.get("taxon", ""))
        replicate = ""
        for k, v in attrs.items():
            if _norm_key(k) in _REPLICATE_KEYS and v:
                replicate = v
                break
        rows.append(harmonize_row(gsm or s.get("title", ""), replicate or "1", attrs))
    n, ncols = write_metadata_tsv(rows, args.out)
    print(f"Wrote {n} sample row(s) x {ncols} column(s) for {args.accession} to {args.out}",
          file=sys.stderr)


def cmd_search(args):
    term = args.query
    if args.organism:
        term += f' AND "{args.organism}"[Organism]'
    if args.type:
        term += f" AND {args.type}[ETYP]"
    res = get_json(
        f"{EUTILS}/esearch.fcgi",
        {"db": "gds", "term": term, "retmode": "json", "retmax": str(args.limit)},
    )
    ids = res.get("esearchresult", {}).get("idlist", [])
    count = res.get("esearchresult", {}).get("count", "0")
    if not ids:
        print(f"0 results for: {term}")
        return
    summ = get_json(
        f"{EUTILS}/esummary.fcgi",
        {"db": "gds", "id": ",".join(ids), "retmode": "json"},
    ).get("result", {})
    if args.json:
        print(json.dumps([summ[u] for u in summ.get("uids", [])], indent=2))
        return
    print(f"{count} total hits; showing {len(ids)}:\n")
    for uid in summ.get("uids", []):
        r = summ[uid]
        print(f"{r.get('accession', ''):12s} {r.get('gdstype', ''):20s} n={r.get('n_samples', '?')}  {r.get('title', '')}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("metadata", help="Series/dataset summary via E-utilities")
    m.add_argument("accession")
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=cmd_metadata)

    s = sub.add_parser("samples", help="List samples (GSMs) in a series")
    s.add_argument("accession")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_samples)

    f = sub.add_parser("files", help="List downloadable files on GEO FTP")
    f.add_argument("accession")
    f.add_argument("--json", action="store_true")
    f.set_defaults(func=cmd_files)

    d = sub.add_parser("download", help="Download files from GEO FTP")
    d.add_argument("accession")
    d.add_argument("--out", default="./geo_out")
    d.add_argument("--matrix", action="store_true", help="series matrix (default)")
    d.add_argument("--soft", action="store_true", help="SOFT family file")
    d.add_argument("--miniml", action="store_true", help="MINiML file")
    d.add_argument("--suppl", action="store_true", help="supplementary/raw files")
    d.set_defaults(func=cmd_download)

    q = sub.add_parser("search", help="Free-text search of GEO DataSets")
    q.add_argument("query")
    q.add_argument("--organism", help='e.g. "Homo sapiens"')
    q.add_argument("--type", help="entry type filter, e.g. gse, gds")
    q.add_argument("--limit", type=int, default=20)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_search)

    mt = sub.add_parser("metadata-table",
                        help="Write a harmonized metadata.tsv (one row per sample/GSM)")
    mt.add_argument("accession", help="GSE accession")
    mt.add_argument("--out", default="metadata.tsv")
    mt.set_defaults(func=cmd_metadata_table)

    ss = sub.add_parser("samplesheet",
                        help="Build an nf-core samplesheet.csv via the linked SRA/ENA data (--assay scrna|bulk)")
    ss.add_argument("accession", help="GSE (or GSM) accession")
    ss.add_argument("--assay", choices=["scrna", "bulk"], required=True,
                    help="scrna -> nf-core/scrnaseq (sample,fastq_1,fastq_2); "
                         "bulk -> nf-core/rnaseq (adds a strandedness column)")
    ss.add_argument("--strandedness", choices=["auto", "forward", "reverse", "unstranded"],
                    default="auto",
                    help="value for the rnaseq strandedness column (only --assay bulk; default auto)")
    ss.add_argument("--out", default="samplesheet.csv")
    ss.add_argument("--group-by", default="sample_accession",
                    help="ENA run field for the `sample` column "
                         "(sample_accession, sample_alias, sample_title, experiment_accession)")
    ss.add_argument("--local-dir",
                    help="write local paths <dir>/<run>/<file> instead of ENA URLs")
    ss.set_defaults(func=cmd_samplesheet)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
