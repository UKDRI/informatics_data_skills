#!/usr/bin/env python3
"""Query metadata and download data from EMBL-EBI BioStudies.

Uses the BioStudies REST API (https://www.ebi.ac.uk/biostudies/api/v1). Files are
downloaded from https://www.ebi.ac.uk/biostudies/files/{accession}/{path}.

Standard library only (urllib) -- no pip install required.

Examples:
    python biostudies.py metadata S-BSST123
    python biostudies.py files    S-BSST123
    python biostudies.py download S-BSST123 --out ./bs_out
    python biostudies.py search "spatial transcriptomics" --limit 20
    python biostudies.py search "cancer" --collection BioImages --limit 10
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
USER_AGENT = "biostudies-skill/1.0"


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


def cmd_metadata(args):
    d = study_json(args.accession)
    if args.json:
        print(json.dumps(d, indent=2))
        return
    print(f"accession : {d.get('accno','')}")
    top = attrs_to_dict(d.get("attributes"))
    sec = d.get("section", {})
    secattr = attrs_to_dict(sec.get("attributes"))
    for key in ("Title", "ReleaseDate", "AttachTo"):
        if key in top:
            print(f"{key:10s}: {top[key]}")
    for key in ("Title", "Description", "Organism"):
        if key in secattr:
            print(f"{key:10s}: {secattr[key]}")
    print(f"\nfiles     : {count_files(sec)} file entries "
          f"(run `files {args.accession}` to list)")


def walk_files(node):
    """Recursively yield file dicts (type == 'file') from a study section tree."""
    if isinstance(node, dict):
        if node.get("type") == "file" and "path" in node:
            yield node
        for v in node.values():
            yield from walk_files(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_files(v)


def count_files(section):
    return sum(1 for _ in walk_files(section))


def list_files(accession):
    d = study_json(accession)
    return list(walk_files(d.get("section", {})))


def cmd_files(args):
    files = list_files(args.accession)
    if args.json:
        print(json.dumps(files, indent=2))
        return
    print(f"{len(files)} file(s) for {args.accession}:\n")
    for f in files:
        size = f.get("size", "?")
        desc = attrs_to_dict(f.get("attributes")).get("Description", "")
        print(f"{f['path']}\t{size}\t{desc}")


def file_url(accession, path):
    quoted = urllib.parse.quote(path)
    return f"{FILES}/{accession}/{quoted}"


def download_file(accession, path, out_dir):
    url = file_url(accession, path)
    dest = os.path.join(out_dir, path)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    if os.path.exists(dest):
        print(f"  exists, skipping {path}", file=sys.stderr)
        return dest
    print(f"  downloading {path} ...", file=sys.stderr)
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
    files = list_files(args.accession)
    if args.match:
        files = [f for f in files if args.match.lower() in f["path"].lower()]
    if not files:
        raise SystemExit("No matching files.")
    out = os.path.join(args.out, args.accession)
    for f in files:
        download_file(args.accession, f["path"], out)
    print(f"Downloaded {len(files)} file(s) to {out}", file=sys.stderr)


def cmd_search(args):
    params = {"query": args.query, "pageSize": args.limit, "page": 1}
    if args.collection:
        params["collection"] = args.collection
    url = f"{API}/search?" + urllib.parse.urlencode(params)
    res = get_json(url)
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

    m = sub.add_parser("metadata", help="Study metadata for an accession")
    m.add_argument("accession")
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=cmd_metadata)

    f = sub.add_parser("files", help="List files attached to a study")
    f.add_argument("accession")
    f.add_argument("--json", action="store_true")
    f.set_defaults(func=cmd_files)

    d = sub.add_parser("download", help="Download study files")
    d.add_argument("accession")
    d.add_argument("--match", help="only files whose path contains this substring")
    d.add_argument("--out", default="./bs_out")
    d.set_defaults(func=cmd_download)

    q = sub.add_parser("search", help="Search BioStudies")
    q.add_argument("query")
    q.add_argument("--collection", help="restrict to a collection, e.g. BioImages, ArrayExpress")
    q.add_argument("--limit", type=int, default=20)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_search)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
