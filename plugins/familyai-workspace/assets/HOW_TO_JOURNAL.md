# HOW TO JOURNAL

This is the single source of truth for making and recording a journal entry. Follow every step exactly. The steps are written so even a small/simple model can follow them without guessing.

A correct journal action = **two things, every time**:
1. Write ONE entry file into `entries/`.
2. Add ONE line for it at the TOP of the list in `JOURNAL.md`.

If you do only one of the two, the entry is broken. Do both.

---

## Step 1 — When to journal
Write an entry at the end of **every session that did real work** (built, fixed, configured, researched, decided, shipped). Never skip because "nothing major happened" — every working session gets exactly one entry.

## Step 2 — The entry filename
Format (use EXACTLY this):

```
YYYY_MM_DD_HR24_MI_Subject.md
```

- `YYYY` = 4-digit year, `MM` = 2-digit month, `DD` = 2-digit day.
- `HR24` = 2-digit hour in 24-hour time (00–23), `MI` = 2-digit minute (00–59).
- Separator between every part is a single underscore `_`.
- `Subject` = 1–5 words describing the session, each word `Title_Case`, joined by underscores.
- The file ends in `.md`.

If you do not know the time, use `00_00` (midnight). Never leave the time out.

**Correct examples:**
- `2026_06_26_12_45_Roast_Skill_Install.md`
- `2026_06_19_00_00_Hermes_Desktop_Sync.md`  (time unknown → `00_00`)

**Wrong (never do these):**
- `2026-06-19-hermes-desktop-sync.md`  (dashes, lowercase, no time)
- `2026_06_14_System_Prompt_Fix.md`  (missing the `HR_MI` time fields)

The filename must match this exact pattern: `^\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_.+\.md$`

## Step 3 — Where the entry file goes
Put the entry file in the `entries/` subfolder:

```
$AI/Journal/entries/<your-filename>.md
```

NEVER put the entry file in the Journal root. Only `entries/` holds entries.

## Step 4 — What goes inside the entry file
Use exactly this template (4 sections). Keep it short — 10–20 lines, a log not an essay. Write plainly, for a human reading it weeks later.

```markdown
# <YYYY-MM-DD> — <Subject in words>

## What we did
<2-4 sentences: what the session set out to do and the main work.>

## What shipped
- <thing created/changed> — <one line>
- ...

## Decisions / constraints
- <any notable decision, rule, or discovery — or "none">

## Deferred / open
- <anything not finished or needing follow-up — or "none">
```

## Step 5 — Add the index line to JOURNAL.md (MANDATORY)
Open `$AI/Journal/JOURNAL.md`. Find the `## Entries` heading. Insert ONE new line **directly under `## Entries`, at the very TOP of the list** (newest first):

```
- [[Journal/entries/<filename-without-.md>]] — <one-line summary>
```

Rules for this line:
- Use the Obsidian wikilink form `[[Journal/entries/<name>]]` — include the `Journal/entries/` path, do NOT include the `.md` extension.
- Do NOT use markdown-link form `[name](name.md)`.
- Newest at the TOP. Do NOT append at the bottom.
- Exactly ONE line per entry. Never add a second line for the same file.

**Example line:**
```
- [[./entries/2026_06_26_12_45_Roast_Skill_Install]] — Installed /roast skill after SkillSpector security audit.
```

## Step 6 — Self-check before you finish
Confirm all of these are true. If any is false, fix it now:
- [ ] The entry file is inside `entries/` (not the Journal root).
- [ ] The filename matches `^\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_.+\.md$`.
- [ ] Exactly ONE new line was added to `JOURNAL.md`, directly under `## Entries`, at the top.
- [ ] That line uses `[[Journal/entries/<name>]]` (wikilink, no `.md`) and has a one-line summary after ` — `.
- [ ] You did both: the file AND the index line.

## Never
- Never write the entry in the Journal root.
- Never use markdown-link form in the index.
- Never append at the bottom of `JOURNAL.md`.
- Never leave `JOURNAL.md` un-updated after writing an entry.
- Never edit the four governing files (`CLAUDE.md`, `AGENT.md`, `HOW_TO_JOURNAL.md`, `JOURNAL.md` header) as if they were entries — they are not journaled.
