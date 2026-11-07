# Demonstration

## The real task

To project 2D drawing strokes onto the doubly curved geometry of the bottle, calculating the
positions (targets) and tool orientations (TCP) in 6 degrees of freedom so that the ABB IRB 120
robot keeps the pen perpendicular to the surface at all times.

When I tested it in Rhino: the mathematical projection of the vectors and planes onto the curved
surface worked correctly. The target planes were oriented with the bottle's normal, respecting the
lift heights (clearance) and the parameterized spacing, without intersections or strange rotations.

Setup of both runs:

- Work repository: `bottle-drawing`, a local git repository for this project.
- Doing session: a new Claude Code session with Claude Opus 5.5 and the `robot-draw-toolkit` MCP server.
- Checking session: a separate new Claude Code session with Claude Sonnet 5.5, running `/scope-check`.
- The doing sessions left their changes uncommitted. After each review, the result was committed
  from my coordinating Claude Code session (`43f5e3a` and `32cf5f3`), not by the doing agent.
- The sessions were started from that coordinating session and could read a shared notes folder;
  the checking sessions saw short notes left by the doing sessions.

## Run 1

### Doing session (the agent calls the MCP tool)

Request:

> Use the search_robot_papers tool to find how other projects map a 2D drawing onto a curved surface and orient the pen. Then write grasshopper/bottle_targets.py, a GHPython script for Grasshopper with Robot Components. Inputs: a list of 2D stroke curves and the bottle surface. Outputs: one target plane per sample point with the pen axis along the surface normal, and pen-up planes 30 mm above the first and last point of each stroke. Cite the sources you used in comments. Do not commit.

Tool calls (`mcp__robot-draw-toolkit__search_robot_papers`, 7 queries):

```
mapping a 2D drawing onto a 3D curved surface (k=8)
pen tool orientation along the surface normal (k=8)
pen up approach and retract height between strokes (k=6)
Robot Components Robot Target plane input tool plane orientation (k=6)
pen frame z-axis opposite surface normal, x-axis along stroke tangent direction (k=6)
surface parameterization UV coordinates sample points along stroke (k=6)
tooldata tframe z direction of tool coordinate system pointing out of tool (k=4)
```

First tool result (trimmed):

```
Top 8 passages for "mapping a 2D drawing onto a 3D curved surface", grouped by source (5 sources; index holds 3493 passages).

## Robotic drawing on a 3D object
Authors: Amin Haddadi | Year: 2020 | Type: paper | Venue: Diploma thesis, TU Wien
- [#1, score 0.750] p. 69: "2D pattern onto the 3D object surface, the surface is parameterized. [...] a least-squares conformal mapping approach is used to flatten the surface. [...]"

## Distortion-free Robotic Surface-drawing using Conformal Mapping
Authors: Daeun Song, Young J. Kim | Year: 2019 | Type: paper | Venue: IEEE ICRA 2019
- [#2, score 0.749] pp. 3-4: "2D drawing during mapping from a 2D digital vector-drawing to a robotic drawing on a 3D surface by minimizing the angle distortion of local geometry. [...]"
```

Result: a new file, `grasshopper/bottle_targets.py` (380 lines), citing Liu et al. 2020,
Song/Park/Kim 2023 (SSK), Song and Kim 2019, Haddadi 2020 and Jin et al. 2023 in its comments.

### Checking session (scope-check, separate session with a fresh context)

Prompt: `/scope-check The original request was: "<the request above>"` (skill version 1).

Report (trimmed to the CRITICAL lines and the summary):

```
[UNREQUESTED] [CRITICAL] bottle_targets.py:118 — EDGE_TOL_MM = 0.01, an OffSurface error (121-122, 356-359) that stops the script when a point lands past an open edge, and an arc-length clamp min(max(s, 0.0), total) at 290 — a new limit and clamp behavior (units and limits); the request asks for none.
[UNREQUESTED] [CRITICAL] bottle_targets.py:156-162 — check_units(), called at 339, raises if the Rhino document is not in millimetres — a new units guard; the request does not ask for one.
[UNCLEAR] [CRITICAL] bottle_targets.py:316 — plane Z = −(outward normal), pointing into the glass, with X fixed along the bottle rather than along the stroke — the request says "along the surface normal" with no sign and no in-plane rotation.
[UNCLEAR] [CRITICAL] bottle_targets.py:328-330 — lifted() moves the pen-up plane 30 mm along the outward surface normal, not world +Z — the request says only "above", so the direction is the agent's reading.

Totals: 8 REQUESTED, 5 UNREQUESTED, 3 UNCLEAR, 4 CRITICAL
Riskiest changes:
1. grasshopper/bottle_targets.py:316 — pen Z axis points into the glass (−normal) and X is fixed along the bottle; if the Robot Tool plane is defined the other way, every target is flipped
2. grasshopper/bottle_targets.py:328 — pen-up lifts along the surface normal, not world Z; "above" is the agent's interpretation
3. grasshopper/bottle_targets.py:156 — unrequested units guard (mm only), plus unrequested edge-error and clamp logic at 118/286-290
```

### What the checker caught, and whether I agree

Yes, completely. The original prompt did not specify the orientation of the normal vector of the
tool's Z axis or the approach/exit vector. The agent making that decision on its own represents a
risk in robotics (it can cause singularities or end-effector collisions), so it was correct for
the reviewer to flag it.

## Run 2

### Doing session (the agent calls the MCP tool)

Request:

> Use the search_robot_papers tool to check how other robotic drawing projects lift the pen between strokes. Then, in grasshopper/bottle_targets.py, turn the pen-up distance and the sample spacing into component inputs (defaults 30 mm and 2 mm) instead of constants. Do not change anything else and do not commit.

Tool calls (`mcp__robot-draw-toolkit__search_robot_papers`, 5 queries):

```
lift the pen between strokes, pen-up height, retract before moving to next stroke (k=8)
pen approaches along surface normal, offset distance from curved surface when not drawing (k=6)
pen up and pen down motion, hover height, move to start of next stroke without touching canvas (k=8)
safe plane height above the drawing surface for travel moves between strokes (k=6)
travel distance between strokes, minimize pen lifts, stroke ordering (k=6)
```

First tool result (trimmed):

```
Top 8 passages for "lift the pen between strokes, pen-up height, retract before moving to next stroke", grouped by source (5 sources; index holds 3493 passages).

## A Semi-automatic Oriental Ink Painting Framework for Robotic Drawing from 3D Models
Authors: Hao Jin et al. | Year: 2023 | Type: paper | Venue: IEEE Robotics and Automation Letters
- [#2, score 0.632] pp. 7-8: "of stroke drawing results with various descent of brush height hi. [...]"
```

Result: `PEN_UP_MM` and `SAMPLE_STEP_MM` became the optional inputs `pen_up_mm` and
`sample_step_mm` (43 lines added, 19 removed in `grasshopper/bottle_targets.py`).

### Checking session (scope-check, separate session with a fresh context)

Prompt: `/scope-check The original request was: "<the request above>"` (skill version 1).

Report (trimmed to the unrequested line and the summary):

```
UNREQUESTED CRITICAL grasshopper/bottle_targets.py:181 — new `if not value > 0: raise ValueError(...)` (through :182, documented at :26) — rejects 0, negative and NaN for pen_up_mm and sample_step_mm; the request asked only for inputs with defaults, and this is a new limit on pen-up height

Totals: 13 REQUESTED, 1 UNREQUESTED, 0 UNCLEAR, 1 CRITICAL
Riskiest changes:
1. grasshopper/bottle_targets.py:181 — unrequested ≤0/NaN check on the pen-up distance and sample spacing (also described at :26); with the defaults it changes nothing, it only rejects values
2. grasshopper/bottle_targets.py:170 — error-message wording edit; judged necessary, but it is the one text edit outside the literal request
```

### What the checker caught, and whether I agree

Yes. Although the validation was technically positive, any unrequested modification (UNREQUESTED)
to control logic or input parameters must be flagged. In Grasshopper/RAPID environments, an extra
parameter can break connectors or downstream data flows. Marking it CRITICAL was exaggerated.
