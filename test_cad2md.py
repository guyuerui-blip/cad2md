"""Unit tests for cad2md. Run with: python -m pytest test_cad2md.py"""
import math
import os
import struct

import cad2md as cad

HERE = os.path.dirname(os.path.abspath(__file__))


def _write_cube(path):
    s = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 5, 4), (0, 1, 5),
             (1, 6, 5), (1, 2, 6), (2, 7, 6), (2, 3, 7), (3, 4, 7), (3, 0, 4)]
    with open(path, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(faces)))
        for a, b, c in faces:
            f.write(struct.pack("<12fH", 0, 0, 0, *[x for i in (a, b, c) for x in s[i]], 0))


def test_unit_cube_volume_and_area(tmp_path):
    p = tmp_path / "cube.stl"
    _write_cube(str(p))
    tris, kind = cad.load_stl(str(p))
    assert kind == "binary"
    assert len(tris) == 12
    meta = cad.analyze(tris)
    assert meta["watertight"] is True
    assert meta["boundary_edges"] == 0
    assert meta["nonmanifold_edges"] == 0
    assert abs(meta["volume"] - 1.0) < 1e-6
    assert abs(meta["area"] - 6.0) < 1e-6
    assert all(abs(d - 1.0) < 1e-6 for d in meta["dims"])


def test_empty_mesh_returns_none():
    assert cad.analyze([]) is None


def test_guess_unit_magnitude_hints():
    assert "mm" in cad.guess_unit([50000.0, 1.0, 1.0])
    assert "m" in cad.guess_unit([0.001, 0.001, 0.001])
    assert "confirm" in cad.guess_unit([50.0, 30.0, 20.0])


def test_markdown_contains_key_fields(tmp_path):
    p = tmp_path / "cube.stl"
    _write_cube(str(p))
    tris, kind = cad.load_stl(str(p))
    md = cad.to_markdown(cad.analyze(tris), str(p), kind)
    assert "Watertight" in md
    assert "Volume" in md
    assert "```json" in md


def test_signed_volume_detects_reversed_normals(tmp_path):
    """A cube with all faces wound the wrong way yields negative volume."""
    p = tmp_path / "rev.stl"
    s = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
    faces = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 4, 5), (0, 5, 1),
             (1, 5, 6), (1, 6, 2), (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0)]
    with open(str(p), "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(faces)))
        for a, b, c in faces:
            f.write(struct.pack("<12fH", 0, 0, 0, *[x for i in (a, b, c) for x in s[i]], 0))
    tris, _ = cad.load_stl(str(p))
    meta = cad.analyze(tris)
    assert meta["volume"] < 0


def test_ascii_stl_parsing(tmp_path):
    """ASCII STL is auto-detected and parsed (README advertises ascii support)."""
    p = tmp_path / "tri.stl"
    p.write_text(
        "solid tri\n"
        "facet normal 0 0 -1\n outer loop\n"
        "  vertex 0 0 0\n  vertex 1 1 0\n  vertex 1 0 0\n"
        " endloop\nendfacet\n"
        "facet normal 0 0 -1\n outer loop\n"
        "  vertex 0 0 0\n  vertex 0 1 0\n  vertex 1 1 0\n"
        " endloop\nendfacet\n"
        "endsolid tri\n"
    )
    tris, kind = cad.load_stl(str(p))
    assert kind == "ascii"
    assert len(tris) == 2


def test_missing_file_exits_cleanly(tmp_path):
    """A non-existent path returns exit code 2 with a friendly error, not a traceback."""
    import subprocess
    import sys
    bad = tmp_path / "nope.stl"
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "cad2md.py"), str(bad)],
        capture_output=True, text=True)
    assert r.returncode == 2
    assert "file not found" in r.stderr
    assert "Traceback" not in r.stderr
