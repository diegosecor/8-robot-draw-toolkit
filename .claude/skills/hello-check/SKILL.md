---
name: hello-check
description: Trivial test skill that proves the agent loaded the skills in this repository. Use only when the user says "check hello" or invokes /hello-check. Makes the reply start with the word ORBIT.
---

# Hello Check

This skill exists only to confirm that skills in `.claude/skills/` are being read.

## What to do

1. Start your reply with the exact word `ORBIT` (uppercase, the very first word, nothing before it).
2. Then write one short sentence confirming that the `hello-check` skill was loaded from `.claude/skills/hello-check/SKILL.md`.
3. Do nothing else: do not read, create or edit files, and do not run commands.

## Rules

- Do not apply this skill to any message other than "check hello" or `/hello-check`.
