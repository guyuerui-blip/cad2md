#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-test: icosphere tessellation accuracy boundary.

Clean-room: golden-ratio 12-vertex icosahedron -> normalize to unit sphere
-> midpoint subdivision per level -> write binary STL -> read back through
the cad2md parse/analyze pipeline. Verifies:
  1) every level stays watertight with no non-manifold edges;
  2) volume/area converge monotonically to the analytic sphere, error shrinking;
  3) quantified accuracy boundary: from which level is relative error < 1%.

Usage: python selftest_icosphere.py   # prints PASS if all asserts hold
"""
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cad2md as cad  # noqa: E402

R = 10.0  # sphere radius, engineering-scale integer magnitude
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_selftest_icosphere.stl")


def icosahedron():
    t = (1.0 + math.sqrt(5.0)) / 2.0
    raw = [
        (-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0),
        (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
        (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1),
    ]
    norm = math.sqrt(1.0 + t * t)
    verts = [tuple(v[i] / norm * R for i in range(3)) for v in raw]
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    ]
    return verts, faces


def subdivide(verts, faces):
    """Midpoint subdivision projected back onto the sphere (standard icosphere)."""
    mid = {}
    new_faces = []
    for a, b, c in faces:
        m = {}
        for e in ((a, b), (b, c), (c, a)):
            k = tuple(sorted(e))
            if k not in mid:
                pa, pb = verts[k[0]], verts[k[1]]
                q = tuple((pa[i] + pb[i]) / 2.0 for i in range(3))
                nq = math.sqrt(sum(x * x for x in q)) or 1.0
                mid[k] = len(verts)
                verts.append(tuple(q[i] / nq * R for i in range(3)))
            m[e] = mid[tuple(sorted(e))]
        ab, bc, ca = m[(a, b)], m[(b, c)], m[(c, a)]
        new_faces += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
    return verts, new_faces


def write_stl(path, verts, faces):
    with open(path, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(faces)))
        for a, b, c in faces:
            f.write(struct.pack("<12fH", 0, 0, 0,
                                *[x for i in (a, b, c) for x in verts[i]], 0))


def main():
    vol_exact = 4.0 / 3.0 * math.pi * R ** 3
    area_exact = 4.0 * math.pi * R ** 2
    verts, faces = icosahedron()
    prev_v_err = prev_a_err = float("inf")
    pass1 = None
    for lvl in range(4):
        if lvl:
            verts, faces = subdivide(verts, faces)
        write_stl(OUT, verts, faces)
        tris, kind = cad.load_stl(OUT)
        assert kind == "binary" and len(tris) == len(faces), "STL read-back face count mismatch"
        meta = cad.analyze(tris)
        assert meta["watertight"], \
            "L{} lost watertightness: boundary={} nonmanifold={}".format(
                lvl, meta["boundary_edges"], meta["nonmanifold_edges"])
        v_err = abs(meta["volume"] - vol_exact) / vol_exact
        a_err = abs(meta["area"] - area_exact) / area_exact
        print("L{}: tris={} vol_err={:.4%} area_err={:.4%}".format(
            lvl, meta["tris"], v_err, a_err))
        assert v_err < prev_v_err and a_err < prev_a_err, "L{} error did not shrink".format(lvl)
        prev_v_err, prev_a_err = v_err, a_err
        if pass1 is None and v_err < 0.01 and a_err < 0.01:
            pass1 = lvl
    os.remove(OUT)  # fixture is a self-test intermediate; not committed
    assert pass1 is not None, "did not reach 1% accuracy within four levels"
    print("[PASS] topology + convergence asserts all pass; "
          "error <1% from subdivision level L{} ({} faces)".format(pass1, 20 * 4 ** pass1))


if __name__ == "__main__":
    main()
