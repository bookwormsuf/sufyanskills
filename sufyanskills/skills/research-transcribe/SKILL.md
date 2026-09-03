---
name: research-transcribe
description: "Convert raw interview transcripts into formatted markdown for qualitative research. Creates participant folder, converts to table format with row numbers, and sets up for coding. Use when: 'transcribe P3', 'add transcript for P2', 'process this interview', or user pastes raw transcript text with SPEAKER_XX format."
---

# Research Transcribe Skill

Converts raw interview transcripts into the standard markdown format used in qualitative research repos.

## Performance Guidelines (IMPORTANT)

Based on benchmarking across 7 transcripts:

| Approach | Speed | When to use |
|----------|-------|-------------|
| **Direct Write** | ~0.1s/utterance | DEFAULT for all transcripts |
| **Python script** | ~0.3s/utterance | Only if direct write fails |
| **Subagent** | ~1.3s/utterance | NEVER USE - 10-13x slower |

**NEVER delegate transcript parsing to a subagent.** Parse inline and write directly.

## When to Use

- User says "transcribe P3" or "/transcribe P3"
- User pastes raw transcript and mentions a participant number
- User says "add transcript for participant 2"
- User shares a transcript file and wants it processed

## Input Format

Raw transcript with speaker labels:

```
SPEAKER_00: First thing they said.
SPEAKER_01: Response here.
SPEAKER_00: Another utterance that might be
quite long and span multiple ideas.
```

Also supports markdown format (`**SPEAKER_00**:`).

## Transcript Fidelity

Transcribe exactly what was said. Do not correct grammar, fix phrasing, or clean up the transcript in any way. If something sounds garbled, mark it with `[?audio]` but do not guess at what was meant. Always ask the user before making any edits to transcript content. The raw words are research data, not prose to be polished.

## Output

Creates `participants/P#/transcript.md` with:

1. **Details header** (to be filled in manually)
2. **Markdown table** in one of two formats:

### Standard format (interviews, concept testing)
Columns: #, Speaker, Utterance, Code 1, Code 2, Notes

### UT format (usability testing)
Columns: #, Speaker, Utterance, Issue, Confidence, MM, Notes

Where:
- **Issue** = usability issue codes (C- confusion, E- error)
- **Confidence** = High/Medium/Low (only when Issue has a value)
- **MM** = qualitative analysis codes (MM- mental model, EXP- expectation, R- rating)
- **Notes** = enrichment only ([?UI] flags, intervention context, positive observations)

### Format detection

Check `method/analysis-plan.md` in the repo. If it exists and defines a transcript column structure, use that format. Otherwise default to standard format. UT repos will have an analysis plan specifying the UT format.

## Workflow

### Step 1: Identify the Research Repo

Check which research repo is active. Look for:
- A repo path the user names or provides
- The current working directory, if it looks like a research repo (has a `method/` or `participants/` folder)

After identifying the repo, check for `method/analysis-plan.md` to determine transcript format (standard vs UT). If no analysis plan exists, use standard format.

### Step 2: Get Participant Number

If not provided, ask: "Which participant number? (e.g., P1, P2)"

### Step 3: Get Transcript Content

If not provided, ask user to paste the raw transcript or provide a file path.

### Step 4: Parse and Write Directly (NO SUBAGENT)

**Do this inline in main context. Do NOT delegate to a subagent.**

1. Identify speakers first (who is interviewer vs participant)
2. Split transcript by speaker turns (lines starting with `SPEAKER_` or `**SPEAKER_`)
3. Assign sequential row numbers starting at 1
4. Clean up speaker labels, map to I (Interviewer) or P (Participant)
5. Escape pipe characters: `|` → `\|`
6. Write directly to file using the Write tool

**Fallback only if direct write fails:** Use a Python script via Bash:
```python
import re
# Parse SPEAKER_XX: lines, output markdown table rows
# Write directly to file (don't return to main context)
```

### Step 5: Create Output File

1. Create participant folder if it doesn't exist: `participants/P#/`
2. Write `participants/P#/transcript.md` directly (single Write call) with:

**Standard format:**
```markdown
# P# Transcript

## Details

**Participant:** [Name], [Role], [Agency]
**Date:** YYYY-MM-DD
**Duration:** XX min
**Referred by:** [Source]

---

## Transcript

| # | Speaker | Utterance | Code 1 | Code 2 | Notes |
|---|---------|-----------|--------|--------|-------|
| 1 | SPEAKER_00 | First utterance... | | | |
| 2 | SPEAKER_01 | Response... | | | |
```

**UT format** (when `method/analysis-plan.md` specifies it):
```markdown
# P# Transcript

## Details

**Participant:** P#
**Segment:** [Segment]
**Date:** YYYY-MM-DD
**Duration:** XX min
**Recording:**

## Speaker Mapping

- I = Interviewer
- P = Participant

---

## Transcript

| # | Speaker | Utterance | Issue | Confidence | MM | Notes |
|---|---------|-----------|-------|------------|----|----- -|
| 1 | SPEAKER_00 | First utterance... | | | | |
| 2 | SPEAKER_01 | Response... | | | | |
```

Note the UT format differences: no participant name (privacy), segment field, speaker mapping section, and 4 coding columns instead of 3.

### Step 6: Update Index (with retry)

If the repo has `participants/INDEX.md`:
1. Read the current INDEX.md
2. Update the participant's row with segment, order shown, transcript [x]
3. If edit fails with "file modified since read" error, re-read and retry once

### Step 7: Confirm

After creating:
1. Confirm file location and utterance count
2. Skip verification (direct write is reliable, verification adds tool calls without catching issues)
3. Remind user to fill in summary and code using `method/codebook.md`

## Parsing Rules

### Speaker Detection
- Lines starting with `SPEAKER_` followed by digits
- Lines starting with `**SPEAKER_` (markdown bold)
- Speaker label ends at first `: ` (colon-space)

### Speaker Mapping
Identify who is who BEFORE parsing:
- Listen for names mentioned ("Thanks for joining us, Sarah")
- Check who asks questions vs answers (interviewer asks, participant answers)
- Map to simple labels: I (Interviewer), P (Participant), O (Observer)
- Note: SPEAKER_00 is NOT always the interviewer

### Utterance Extraction
- Everything after the first `: ` is the utterance
- Multi-line utterances: if next line doesn't start with SPEAKER_, append to current utterance
- Preserve line breaks within utterances as spaces
- After collecting a full speaker turn, split into individual sentences. Each sentence gets its own row with the same speaker label. Split on sentence-ending punctuation (. ? !) followed by a space or end of string. This makes coding more precise because each row contains one thought rather than a whole paragraph. Keep short standalone sentences (like "Yeah." or "Okay.") as their own rows.

### Edge Cases
- Empty utterances: skip the row
- Very long utterances: keep full text, don't truncate
- Special characters: escape pipe `|` as `\|` for markdown tables
- Quotes in utterances: keep as-is
- Filler repetition: skip rows that are just "yeah yeah yeah" artifacts from transcription

### Common Transcription Fixes (project-specific term fixes, e.g. a product name the transcriber mishears)
- Listen for near-homophones of the product name and correct them consistently (e.g. a product called "Formflow" might get transcribed as "form flow" or "form full")
- Watch for acronyms or internal terms that get misheard as similar-sounding words, and fix them consistently once you know the correct term
- Mark garbled audio with `[?audio]` - don't guess

## Examples

### Standard format

**Input:**
```
SPEAKER_00: So tell me about your typical day.
SPEAKER_01: Well, I usually start by checking emails. Then I download the CSV from the form builder and open it in Excel.
SPEAKER_00: And what do you do with that data?
SPEAKER_01: I clean it up, remove duplicates, and then send it to my supervisor for review.
```

**Output:**
```markdown
| # | Speaker | Utterance | Code 1 | Code 2 | Notes |
|---|---------|-----------|--------|--------|-------|
| 1 | I | So tell me about your typical day. | | | |
| 2 | P | Well, I usually start by checking emails. | | | |
| 3 | P | Then I download the CSV from the form builder and open it in Excel. | | | |
| 4 | I | And what do you do with that data? | | | |
| 5 | P | I clean it up, remove duplicates, and then send it to my supervisor for review. | | | |
```

### UT format

Same input, but repo has `method/analysis-plan.md` with UT column structure:

**Output:**
```markdown
| # | Speaker | Utterance | Issue | Confidence | MM | Notes |
|---|---------|-----------|-------|------------|----|-------|
| 1 | I | So tell me about your typical day. | | | | |
| 2 | P | Well, I usually start by checking emails. | | | | |
| 3 | P | Then I download the CSV from the form builder and open it in Excel. | | | | |
| 4 | I | And what do you do with that data? | | | | |
| 5 | P | I clean it up, remove duplicates, and then send it to my supervisor for review. | | | | |
```

## Quick Reference

| Command | Action |
|---------|--------|
| `/transcribe P3` | Process transcript for participant 3 |
| `/transcribe` | Will ask for participant number |
| Paste transcript + "P2" | Process pasted text as P2 |
