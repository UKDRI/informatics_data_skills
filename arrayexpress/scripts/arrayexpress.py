#!/usr/bin/env python3
"""Query metadata and download data from ArrayExpress (functional genomics).

ArrayExpress is now the functional-genomics collection inside BioStudies, so this
uses the BioStudies REST API (https://www.ebi.ac.uk/biostudies/api/v1) with
ArrayExpress-aware helpers for MAGE-TAB (IDF/SDRF) and raw/processed data.

Standard library only (urllib) -- no pip install required.

Examples:
    python arrayexpress.py metadata E-MTAB-11448
    python arrayexpress.py files    E-MTAB-11448
    python arrayexpress.py sdrf     E-MTAB-11448            # print the SDRF table
    python arrayexpress.py download E-MTAB-11448 --magetab --out ./ae_out
    python arrayexpress.py download E-MTAB-11448 --processed --out ./ae_out
    python arrayexpress.py search "single cell heart" --limit 20
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API = "https://www.ebi.ac.uk/biostudies/api/v1"
FILES = "https://www.ebi.ac.uk/biostudies/files"
COLLECTION = "ArrayExpress"
USER_AGENT = "arrayexpress-skill/1.0"


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


def get_json(url):
    return json.loads(http_get(url).decode("utf-8", "replace"))


def study_json(accession):
    return get_json(f"{API}/studies/{accession}")


def attrs_to_dict(attributes):
    return {a.get("name"): a.get("value") for a in (attributes or []) if isinstance(a, dict)}


def walk_files(node):
    if isinstance(node, dict):
        if node.get("type") == "file" and "path" in node:
            yield node
        for v in node.values():
            yield from walk_files(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_files(v)


def list_files(accession):
    d = study_json(accession)
    return list(walk_files(d.get("section", {})))


def classify(file_rec):
    """Classify a file entry as idf/sdrf/processed/raw/other.

    Prefer the file's own MAGE-TAB attributes (Type/Description), then fall back
    to the filename.
    """
    path = file_rec["path"] if isinstance(file_rec, dict) else str(file_rec)
    p = path.lower()
    if p.endswith(".idf.txt"):
        return "idf"
    if p.endswith(".sdrf.txt"):
        return "sdrf"
    hint = ""
    if isinstance(file_rec, dict):
        hint = " ".join(attrs_to_dict(file_rec.get("attributes")).values()).lower()
    if "processed" in hint or "processed" in p or \
            p.endswith((".counts.txt", ".tsv", ".mtx", ".h5", ".h5ad", ".rds")):
        return "processed"
    if "raw" in hint or p.endswith((".fastq.gz", ".fq.gz", ".cel", ".cel.gz", ".bam", ".cram")):
        return "raw"
    return "other"


def cmd_metadata(args):
    d = study_json(args.accession)
    if args.json:
        print(json.dumps(d, indent=2))
        return
    sec = d.get("section", {})
    sa = attrs_to_dict(sec.get("attributes"))
    ta = attrs_to_dict(d.get("attributes"))
    print(f"accession   : {d.get('accno','')}")
    print(f"title       : {sa.get('Title', ta.get('Title',''))}")
    print(f"release     : {ta.get('ReleaseDate','')}")
    if "Organism" in sa:
        print(f"organism    : {sa['Organism']}")
    if "Description" in sa:
        print(f"\ndescription : {sa['Description']}")
    files = list(walk_files(sec))
    kinds = {}
    for f in files:
        k = classify(f)
        kinds[k] = kinds.get(k, 0) + 1
    print(f"\nfiles       : {len(files)} total  " +
          "  ".join(f"{k}={v}" for k, v in sorted(kinds.items())))


def cmd_files(args):
    files = list_files(args.accession)
    if args.json:
        print(json.dumps(files, indent=2))
        return
    print(f"{len(files)} file(s) for {args.accession}:\n")
    for f in files:
        print(f"{classify(f):10s} {str(f.get('size','?')):>14s}  {f['path']}")


def file_url(accession, path):
    return f"{FILES}/{accession}/{urllib.parse.quote(path)}"


def cmd_sdrf(args):
    files = list_files(args.accession)
    sdrf = [f for f in files if classify(f) == "sdrf"]
    if not sdrf:
        raise SystemExit("No SDRF file found for this accession.")
    data = http_get(file_url(args.accession, sdrf[0]["path"]))
    sys.stdout.write(data.decode("utf-8", "replace"))


def download_file(accession, path, out_dir):
    dest = os.path.join(out_dir, path)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    if os.path.exists(dest):
        print(f"  exists, skipping {path}", file=sys.stderr)
        return
    print(f"  downloading {path} ...", file=sys.stderr)
    req = urllib.request.Request(file_url(accession, path), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=600) as r, open(dest + ".part", "wb") as fh:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
    os.replace(dest + ".part", dest)
    print(f"  saved {dest}", file=sys.stderr)


def cmd_download(args):
    files = list_files(args.accession)
    wanted = set()
    if args.magetab:
        wanted |= {"idf", "sdrf"}
    if args.processed:
        wanted.add("processed")
    if args.raw:
        wanted.add("raw")
    if not wanted:
        wanted = {"idf", "sdrf", "processed", "raw", "other"}  # everything
    sel = [f for f in files if classify(f) in wanted]
    if not sel:
        raise SystemExit("No matching files for the selected categories.")
    out = os.path.join(args.out, args.accession)
    for f in sel:
        download_file(args.accession, f["path"], out)
    print(f"Downloaded {len(sel)} file(s) to {out}", file=sys.stderr)


# ---- nf-core/scrnaseq samplesheet (built from the SDRF) ----
import csv
import io
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


def get_sdrf_text(accession):
    files = list_files(accession)
    sdrf = [f for f in files if classify(f) == "sdrf"]
    if not sdrf:
        raise SystemExit(f"No SDRF file found for {accession}.")
    return http_get(file_url(accession, sdrf[0]["path"])).decode("utf-8", "replace")


def ena_run_fastq(run):
    url = (f"{ENA_PORTAL}/filereport?accession={run}"
           f"&result=read_run&fields=fastq_ftp&format=tsv&limit=0")
    text = http_get(url).decode("utf-8", "replace")
    links = []
    for ln in text.splitlines()[1:]:
        links.extend(x for x in ln.split("\t")[-1].split(";") if x)
    return [to_https(x) for x in links]


def cmd_samplesheet(args):
    rows = list(csv.reader(io.StringIO(get_sdrf_text(args.accession)), delimiter="\t"))
    header = [h.strip() for h in rows[0]]

    def col(name):
        for i, h in enumerate(header):
            if h.lower() == name.lower():
                return i
        return None

    si = col("Source Name")
    ri = col("Comment[ENA_RUN]")
    fi = [i for i, h in enumerate(header) if h.lower() == "comment[fastq_uri]"]
    if si is None:
        raise SystemExit("SDRF has no 'Source Name' column; cannot build a samplesheet.")

    groups = {}  # key -> {sample, run, uris[]}
    order = []
    for idx, row in enumerate(rows[1:]):
        if not any(c.strip() for c in row):
            continue
        sample = row[si].strip() if si < len(row) else ""
        run = row[ri].strip() if ri is not None and ri < len(row) else ""
        key = run or sample or f"row{idx}"
        g = groups.get(key)
        if g is None:
            g = {"sample": sample, "run": run, "uris": []}
            groups[key] = g
            order.append(key)
        for i in fi:
            if i < len(row) and row[i].strip():
                g["uris"].append(to_https(row[i].strip()))
        if sample and not g["sample"]:
            g["sample"] = sample

    out_rows = []
    for key in order:
        g = groups[key]
        urls = g["uris"]
        if not urls and g["run"]:
            urls = ena_run_fastq(g["run"])  # fall back to ENA for this run
        if not urls:
            continue
        f1, f2 = fastq_pair(urls)
        if args.local_dir and g["run"]:
            f1 = os.path.join(args.local_dir, g["run"], f1.rsplit("/", 1)[-1]) if f1 else ""
            f2 = os.path.join(args.local_dir, g["run"], f2.rsplit("/", 1)[-1]) if f2 else ""
        out_rows.append({"sample": clean_sample(g["sample"] or g["run"]),
                         "fastq_1": f1, "fastq_2": f2})

    if not out_rows:
        raise SystemExit(
            "No FASTQ files found in the SDRF (this may be an array study with no "
            "sequencing data, or reads are only in ENA under controlled access).")
    out_rows.sort(key=lambda x: (x["sample"], x["fastq_1"]))
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(SAMPLESHEET_COLS)
        for r in out_rows:
            w.writerow([r.get(c, "") for c in SAMPLESHEET_COLS])
    print(f"Wrote {len(out_rows)} row(s) for {len({r['sample'] for r in out_rows})} "
          f"sample(s) to {args.out}", file=sys.stderr)


def cmd_search(args):
    params = {"query": args.query, "collection": COLLECTION,
              "pageSize": args.limit, "page": 1}
    res = get_json(f"{API}/search?" + urllib.parse.urlencode(params))
    if args.json:
        print(json.dumps(res, indent=2))
        return
    hits = res.get("hits", [])
    print(f"{res.get('totalHits','?')} total hits; showing {len(hits)}:\n")
    for h in hits:
        print(f"{h.get('accession',''):16s} {h.get('title','')}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("metadata", help="Study metadata + file breakdown")
    m.add_argument("accession")
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=cmd_metadata)

    f = sub.add_parser("files", help="List files, classified (idf/sdrf/raw/processed)")
    f.add_argument("accession")
    f.add_argument("--json", action="store_true")
    f.set_defaults(func=cmd_files)

    s = sub.add_parser("sdrf", help="Print the SDRF (sample/data relationship) table")
    s.add_argument("accession")
    s.set_defaults(func=cmd_sdrf)

    d = sub.add_parser("download", help="Download files by category")
    d.add_argument("accession")
    d.add_argument("--magetab", action="store_true", help="IDF + SDRF")
    d.add_argument("--processed", action="store_true", help="processed data matrices")
    d.add_argument("--raw", action="store_true", help="raw data (FASTQ/CEL/BAM)")
    d.add_argument("--out", default="./ae_out")
    d.set_defaults(func=cmd_download)

    q = sub.add_parser("search", help="Search the ArrayExpress collection")
    q.add_argument("query")
    q.add_argument("--limit", type=int, default=20)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_search)

    ss = sub.add_parser("samplesheet",
                        help="Build an nf-core/scrnaseq samplesheet.csv from the SDRF")
    ss.add_argument("accession")
    ss.add_argument("--out", default="samplesheet.csv")
    ss.add_argument("--local-dir",
                    help="write local paths <dir>/<run>/<file> instead of FASTQ URLs")
    ss.set_defaults(func=cmd_samplesheet)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
