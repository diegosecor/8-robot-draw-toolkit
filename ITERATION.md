# Iteration

## Before (version 1)

The CRITICAL rules in `scope-check` version 1 (`.claude/skills/scope-check/SKILL.md`, commit `63da4dd`):

> - Add `CRITICAL` when an UNREQUESTED or UNCLEAR change touches a parameter in robot-params.md.
> - An unrequested change to any parameter in robot-params.md is CRITICAL, even when it looks small or safer (`v200 → v100`, `z10 → fine`).
> - List up to three, CRITICAL first.

## What went wrong

Version 1 was too rigid and generated false positives: it labeled any protective conditional or
generic code validation as a `CRITICAL` change, without distinguishing between normal safeguards and
real modifications to dangerous robot parameters.

From the two version 1 reviews (full reports in DEMONSTRATION.md):

```
[UNREQUESTED] [CRITICAL] bottle_targets.py:156-162 — check_units(), called at 339, raises if the Rhino document is not in millimetres — a new units guard; the request does not ask for one.
UNREQUESTED CRITICAL grasshopper/bottle_targets.py:181 — new `if not value > 0: raise ValueError(...)` [...] this is a new limit on pen-up height
2. grasshopper/bottle_targets.py:170 — error-message wording edit; judged necessary, but it is the one text edit outside the literal request
```

## My diagnosis of why

It happened because the initial evaluation prompt searched for safety keywords in a hyper-strict
way without context, assuming any manipulation of height or speed variables was a safety violation,
without analyzing the intention of the block.

## What I changed (versions 2 and 3)

Version 2 (commit `41384aa` in `bottle-drawing`):

> - Add `CRITICAL` when an UNREQUESTED or UNCLEAR change alters, removes or loosens a parameter or limit in robot-params.md. A new check that only stops the program on bad input (a units check, a range check, an error for an off-surface point) and changes no value the robot uses is not CRITICAL.
> - List up to three UNREQUESTED or UNCLEAR changes, CRITICAL first. Never list a REQUESTED change.

Rerunning both reviews with version 2 fixed the input checks, but the pen axis and the pen-up
direction of the new file were now REQUESTED:

```
UNREQUESTED grasshopper/bottle_targets.py:181 — [...] It only stops the script on a value of 0, below 0 or NaN, and changes no value the robot uses, so it is not CRITICAL
UNREQUESTED bottle_targets.py:156-162 — check_units() stops if the Rhino document is not in mm — input check only
REQUESTED   bottle_targets.py:307-325 — pen_plane(): plane Z = −outward normal, X along the bottle — "pen axis along the surface normal"; the sign and the roll about the pen axis are the agent's choices
REQUESTED   bottle_targets.py:328-330 — lifted() — pen-up plane at +30 mm, same orientation
```

Version 3 (commit `192270f`):

> - `UNCLEAR`: you cannot decide from the request, you cannot cite a line, or the request leaves a robot parameter open (a sign, a direction or a value, such as which way the pen axis points or which way "above" is) and the agent picked one.
> - Add `CRITICAL` when an UNREQUESTED or UNCLEAR change alters, removes or loosens a parameter or limit in robot-params.md, or sets one for the first time in new code.

## Result of the rerun

Rerunning both reviews with version 3 on the same changes (Claude Sonnet 5.5, new sessions):

```
UNCLEAR CRITICAL bottle_targets.py:254-255,315-316 — pen axis: plane Z = -(outward normal), "outward" decided by the bounding-box centre — "pen axis along the surface normal" does not say +n or -n
UNCLEAR CRITICAL bottle_targets.py:328-330 — lifted(): "above" = +30 mm along the outward normal, not world Z — request leaves the direction open, agent picked one
UNREQUESTED bottle_targets.py:156-162 — check_units() stops if the Rhino document is not mm — input check only, not CRITICAL
UNREQUESTED: grasshopper/bottle_targets.py:181 — `if not value > 0: raise ValueError(...)` — new range check on both inputs, not asked for. It only stops the script and moves no target (it also rejects NaN), so it is not CRITICAL.
```

It is the natural process of calibrating an evaluator agent. By relaxing the rigidity in v2 to
remove false positives, the skill lost sensitivity on new files. That showed the need to test with
edge cases until reaching the balance of v3, where it detects true risks without blocking
development.
