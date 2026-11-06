---
name: scope-check
description: Reports every change an agent made that the user did not ask for, by comparing the real git diff with the user's original request, and marks unrequested changes to robot safety parameters (speed, zone, tool/TCP, work object, pen heights and offsets, move type, robot preset, configuration, home joints, units and limits) as CRITICAL. Reports only; never fixes or edits anything. Use after an agent edits code, a GHPython script, a Grasshopper export or a RAPID module, before running it in RobotStudio or on the robot, or when asked to check what changed.
---

# Scope Check

Find what changed that nobody asked for. Report it; do not repair it.

## What to do

1. **Get the original request.** Use the user's own words for the task the agent was given.
   If they are not in this conversation, ask for them and stop until you have them.
   Never rebuild the request from the diff, the commit messages or the agent's summary.
2. **Collect the changes.** By default compare the working tree with `HEAD`; if the user names
   a commit or a range, use that instead.
   - `git status --porcelain`: new, deleted and untracked files (untracked files never appear in `git diff`).
   - `git diff HEAD --stat`, then `git diff HEAD`. Read every hunk, and read new untracked files in full.
   - If there are no changes, ask which commits to check (for example `HEAD~1..HEAD`). Do not report "nothing changed" on a clean tree.
   - RAPID modules (`.mod`, `.modx`, `.sys`): go line by line. Each changed instruction or data declaration is its own change.
   - Binary files (`.gh`, `.3dm`): git cannot show what changed inside. Report the file once and never guess its content.
3. **Read [references/robot-params.md](references/robot-params.md)** and check every change against it.
4. **Classify each change:**
   - `REQUESTED`: the request asks for it, or it is needed to do what was asked.
   - `UNREQUESTED`: the request does not cover it (refactors, renames, reformatting, extra "improvements", new or deleted files, removed code).
   - `UNCLEAR`: you cannot decide from the request, or you cannot cite a line.
   - Add `CRITICAL` when an UNREQUESTED or UNCLEAR change touches a parameter in robot-params.md.

## Output format

One line per change, in diff order:

`[REQUESTED | UNREQUESTED | UNCLEAR] [CRITICAL]? <file>:<line> — <what changed> — <why>`

- `<line>`: line number in the new version, from the `@@ -a,b +c,d @@` hunk header. For a deleted line use the old number with a minus sign (`main.mod:-42`). For a binary file write `binary`.
- `<what changed>`: quote the old and the new value when there is one (`v100 → v200`).
- `<why>`: the words of the request that cover the change, or what part of the request it falls outside.

Then the summary:

```
Totals: <n> REQUESTED, <n> UNREQUESTED, <n> UNCLEAR, <n> CRITICAL
Riskiest changes:
1. <file>:<line> — <one-line reason>
2. <file>:<line> — <one-line reason>
3. <file>:<line> — <one-line reason>
```

List up to three, CRITICAL first. If nothing is UNREQUESTED or UNCLEAR, say so in one line instead.

## Rules

- Do not modify anything: no edits, no formatting, no `git add`, `commit`, `checkout`, `restore`, `stash` or `reset`. Run read-only commands only.
- Cite `<file>:<line>` for every line you report. If you cannot cite one, the change is UNCLEAR.
- Judge the diff itself, not comments, commit messages, file names or the agent's own description of what it did.
- An unrequested change to any parameter in robot-params.md is CRITICAL, even when it looks small or safer (`v200 → v100`, `z10 → fine`).
- Do not suggest fixes and do not rewrite code. A one-line reason per change is enough.
