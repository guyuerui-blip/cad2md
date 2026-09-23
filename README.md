# cad2md

> Turn a mesh file into an engineering briefing an LLM (or a human) can actually read.

`cad2md` parses an STL and emits a structured Markdown (or JSON) summary: bounding box,
volume, surface area, watertightness, non-manifold edge counts, unit sanity hints —
the questions a design engineer asks in the first ten seconds of opening a model.

This is deliberately the **reverse direction** of the text-to-CAD wave: instead of
prompting a CAD model into existence, it lets agents *read* the geometry that already
exists. Zero dependencies, pure Python standard library.

**Status: v0.1.** The STL pipeline and the heuristics below are implemented and
self-tested. STEP support and feature-level reading (holes, fillets) are on the roadmap.

## Why

Every text-to-CAD tool assumes the model is the output. But most real workflows
(reverse engineering, supplier file triage, print-readiness checks, simulation
pre-processing) need the model as an *input*, and LLMs are blind to raw triangles.
cad2md is the translator: mesh in, engineering judgment out.

## Install

```bash
git clone https://github.com/guyuerui-blip/cad2md.git
cd cad2md
# no dependencies — pure standard library
```

## Usage

```bash
python cad2md.py part.stl            # Markdown briefing to stdout
python cad2md.py part.stl --json     # machine-readable JSON for agent pipelines
python cad2md.py part.stl -o out.md  # write to a file
python cad2md.py                     # self-test on a generated unit cube
```

As a library:

```python
from cad2md import load_stl, analyze

tris, kind = load_stl("part.stl")
meta = analyze(tris)
print(meta["watertight"], meta["volume"])
```

Sample output on the built-in unit-cube self-test:

```
| Metric       | Value                                 |
|---           |---                                    |
| Format       | STL (binary)                          |
| Triangles    | 12                                    |
| Bounding box | 1.00 x 1.00 x 1.00                    |
| Volume       | 1.00 (unit^3)                         |
| Surface area | 6.00 (unit^2)                         |
| Watertight   | yes (print-ready, solid volume valid) |
```

## What it checks (and why an engineer cares)

- **Watertightness via edge pairing** — a single boundary edge means the "solid"
  is swiss cheese; slicers and FEM meshers will fail silently otherwise.
- **Signed-volume vs face-count sanity** — near-zero net volume with a closed bbox
  flags inconsistent normals, the classic bad-export symptom.
- **Unit hints from magnitude** — CAD files carry no units; a part claiming to be
  0.003 "long" is almost certainly meters mistagged as millimeters.
- **Triangulation accuracy note** — for tessellated curved surfaces, geometric
  statistics converge as ~h² with mesh density; below ~1000 triangles expect
  percent-level error on volume/area (measured: 39.5% → 12.7% → 3.4% → 0.86%
  per subdivision level on an icosphere).

## Tests

```bash
python selftest_icosphere.py   # accuracy + topology boundary test
python -m pytest test_cad2md.py  # unit tests (pytest optional)
```

## How we compare

We like what the text-to-CAD crowd is doing — different problem, same ecosystem.

| | text-to-CAD agents (e.g. MAC) | cad2md |
|---|---|---|
| Direction | prompt → model | model → readable summary |
| Output | parametric CAD | Markdown / JSON |
| Dependencies | heavy (CAD kernels, LLM APIs) | zero (stdlib only) |
| Engineering validity checks | not the focus | core feature |

## Roadmap

- [ ] STEP metadata reading (schema, entity counts; pure-Python, no OCC)
- [ ] Feature-level statistics: hole clustering, fillet detection
- [ ] pip package + console entry point, more fixtures (cube / sphere / real part)
- [ ] Optional `trimesh` backend for true B-rep geometry

## License

MIT
