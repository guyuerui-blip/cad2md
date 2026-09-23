#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cad2md — turn an STL mesh into an engineering briefing an LLM can read.

Clean-room implementation: binary/ASCII STL parsing, bounding box,
signed-tetrahedron volume, surface area, watertightness and non-manifold
edge detection, unit sanity hints. Pure Python standard library, zero deps.

CLI:
    python cad2md.py model.stl           # Markdown report to stdout + file
    python cad2md.py model.stl --json    # machine-readable JSON
    python cad2md.py                     # self-test on a generated unit cube

Library:
    from cad2md import load_stl, analyze
    tris, kind = load_stl("part.stl")
    meta = analyze(tris)
"""
import math
import os
import struct
import sys

EPS = 1e-9


def parse_binary_stl(raw):
    """Parse a binary STL buffer into a list of 3-vertex triangles."""
    n = struct.unpack("<I", raw[80:84])[0]
    tris = []
    off = 84
    for _ in range(n):
        vals = struct.unpack("<12fH", raw[off:off + 50])
        v = vals[3:12]
        tris.append(((v[0], v[1], v[2]), (v[3], v[4], v[5]), (v[6], v[7], v[8])))
        off += 50
    return tris


def parse_ascii_stl(text):
    """Parse an ASCII STL string into a list of 3-vertex triangles."""
    tris, cur = [], []
    for line in text.splitlines():
        tok = line.split()
        if not tok:
            continue
        if tok[0] == "vertex" and len(tok) == 4:
            cur.append(tuple(float(x) for x in tok[1:4]))
            if len(cur) == 3:
                tris.append(tuple(cur))
                cur = []
    return tris


def load_stl(path):
    """Load an STL file; returns (triangles, kind) where kind is 'ascii'|'binary'."""
    with open(path, "rb") as f:
        raw = f.read()
    head = raw[:80]
    is_ascii = head.lstrip().startswith(b"solid") and (len(raw) < 84 or b"facet" in raw[:512])
    if is_ascii:
        try:
            return parse_ascii_stl(raw.decode("ascii", "ignore")), "ascii"
        except Exception:
            pass
    return parse_binary_stl(raw), "binary"


def analyze(tris):
    """Compute geometry + topology metrics from a triangle soup.

    Returns a dict with triangle count, bounding box, signed volume,
    surface area, watertightness, and boundary / non-manifold edge counts.
    """
    pts = [p for t in tris for p in t]
    if not pts:
        return None
    minv = [min(p[i] for p in pts) for i in range(3)]
    maxv = [max(p[i] for p in pts) for i in range(3)]
    dims = [maxv[i] - minv[i] for i in range(3)]

    # signed volume via the divergence theorem (sum of signed tetra volumes)
    vol = 0.0
    for a, b, c in tris:
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) +
                a[1] * (b[2] * c[0] - b[0] * c[2]) +
                a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0

    # surface area via cross product magnitudes
    area = 0.0
    for a, b, c in tris:
        u = [b[i] - a[i] for i in range(3)]
        w = [c[i] - a[i] for i in range(3)]
        cx = (u[1] * w[2] - u[2] * w[1],
              u[2] * w[0] - u[0] * w[2],
              u[0] * w[1] - u[1] * w[0])
        area += math.sqrt(cx[0] ** 2 + cx[1] ** 2 + cx[2] ** 2) / 2.0

    # topology: pair up edges; boundary edges appear once, non-manifold >2
    edge_count = {}
    key = lambda p: tuple(round(x, 6) for x in p)
    for a, b, c in tris:
        for e in ((a, b), (b, c), (c, a)):
            k = tuple(sorted((key(e[0]), key(e[1]))))
            edge_count[k] = edge_count.get(k, 0) + 1
    boundary_edges = sum(1 for v in edge_count.values() if v == 1)
    nonmanifold = sum(1 for v in edge_count.values() if v > 2)
    watertight = boundary_edges == 0 and nonmanifold == 0

    return {
        "tris": len(tris), "dims": dims, "bbox_min": minv, "bbox_max": maxv,
        "volume": vol, "area": area, "watertight": watertight,
        "boundary_edges": boundary_edges, "nonmanifold_edges": nonmanifold,
    }


def guess_unit(dims):
    """CAD files carry no units; infer plausibility from magnitude."""
    dmax = max(dims)
    if dmax > 1e4:
        return "likely mm (large part, or mixed units — verify)"
    if dmax < 1e-2:
        return "likely m (or a very small model — verify)"
    return "magnitude suggests mm for a typical part; confirm units manually"


def to_markdown(meta, path, kind):
    """Render the analysis as a human/LLM-readable Markdown briefing."""
    import json
    L = ["# CAD summary: {}".format(os.path.basename(path)), "",
         "| Metric | Value |", "|---|---|"]
    L.append("| Format | STL ({}) |".format(kind))
    L.append("| Triangles | {} |".format(meta["tris"]))
    L.append("| Bounding box L x W x H | {:.2f} x {:.2f} x {:.2f} |".format(*meta["dims"]))
    L.append("| Volume | {:.2f} (unit^3) |".format(meta["volume"]))
    L.append("| Surface area | {:.2f} (unit^2) |".format(meta["area"]))
    L.append("| Watertight | {} |".format(
        "yes (print-ready, solid volume valid)" if meta["watertight"]
        else "no ({} boundary edge(s))".format(meta["boundary_edges"])))
    L.append("")
    L.append("## Engineering read")
    L.append("- {}".format(guess_unit(meta["dims"])))
    if meta["nonmanifold_edges"]:
        L.append("- WARNING: {} non-manifold edge(s); repair the mesh before slicing/printing".format(
            meta["nonmanifold_edges"]))
    if abs(meta["volume"]) < EPS:
        L.append("- net volume ~0: normals may be inconsistent (some faces reversed)")
    L.append("")
    L.append("```json")
    L.append(json.dumps({"file": os.path.basename(path), **{k: (round(v, 4) if isinstance(v, float) else v)
                                                            for k, v in meta.items()}},
                        ensure_ascii=False))
    L.append("```")
    return "\n".join(L)


def write_cube_stl(path):
    """Write a unit-cube binary STL (self-test fixture)."""
    s = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 5, 4), (0, 1, 5),
             (1, 6, 5), (1, 2, 6), (2, 7, 6), (2, 3, 7), (3, 4, 7), (3, 0, 4)]
    with open(path, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(faces)))
        for a, b, c in faces:
            f.write(struct.pack("<12fH", 0, 0, 0,
                                *[x for i in (a, b, c) for x in s[i]], 0))


def main():
    import argparse
    import json as _json
    ap = argparse.ArgumentParser(
        prog="cad2md",
        description="STL -> Markdown/JSON geometry summary (mesh in, engineering judgment out)")
    ap.add_argument("stl", nargs="?", help="path to an STL file; omit to run the built-in self-test")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of Markdown")
    ap.add_argument("-o", "--out", help="write result to this file instead of stdout")
    args = ap.parse_args()

    if args.stl:
        path = args.stl
        if not os.path.isfile(path):
            print("error: file not found: {}".format(path), file=sys.stderr)
            return 2
    else:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_selftest_cube.stl")
        write_cube_stl(path)
        print("[selftest] generated unit-cube STL:", path, file=sys.stderr)

    tris, kind = load_stl(path)
    meta = analyze(tris)
    if meta is None:
        print("error: no triangles parsed from {}".format(path), file=sys.stderr)
        return 2

    if args.json:
        payload = _json.dumps({"file": os.path.basename(path), "kind": kind,
                               **{k: (round(v, 4) if isinstance(v, float) else v)
                                  for k, v in meta.items()}}, ensure_ascii=False, indent=1)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(payload)
            print("[wrote]", args.out, file=sys.stderr)
        else:
            print(payload)
        return 0

    md = to_markdown(meta, path, kind)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
        print("[wrote]", args.out, file=sys.stderr)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
