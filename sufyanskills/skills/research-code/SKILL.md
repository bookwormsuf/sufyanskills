---
name: research-code
description: "Code interview transcripts for qualitative research. Apply codes from a codebook, flag unclear audio, mark quotable moments. Use when: '/code P3', '/code-all', 'code the transcript', 'apply codes to P4', 'code all transcripts in parallel', or user wants to analyze interview data against a codebook. For multiple transcripts (3+), suggest parallel mode for faster results. Also handles UT (usability testing) transcripts with issue extraction and mental model coding."
---

# Research Code Skill

Code interview transcripts for qualitative research. Supports two modes:
- **Standard mode**: Apply codes from a codebook (interviews, concept tests)
- **UT mode**: Extract usability issues and mental models (usability tests)

## When to Use

- User says "/code P3" or "code the P3 transcript"
- User has a transcript that needs coding against a codebook
- User wants to analyze interview data
- User shares whiteboard photos from an interview session

## Mode Detection

Check `method/analysis-plan.md` in the repo. If it exists and defines Issue/Confidence/MM/Notes columns, use **UT mode**. Otherwise use **standard mode**.

UT repos have an analysis plan with a code registry, confidence definitions, and a prototype feature glossary. Standard repos have a codebook.

---

## UT Mode (Usability Testing)

For usability test transcripts. Extracts usability issues and mental models instead of applying codebook themes.

### UT Columns

```
| # | Speaker | Utterance | Issue | Confidence | MM | Notes |
```

- **Issue**: `C-` (confusion/friction) or `E-` (error/wrong action)
- **Confidence**: High/Medium/Low. Only when Issue has a value.
  - High: Participant explicitly states confusion or asks a direct question
  - Medium: Hedging language, uncertainty, or wrong action, no explicit confusion
  - Low: Subtle signal, could be thinking aloud
- **MM**: `MM-` (mental model), `EXP-` (expectation mismatch), `R-` (rating)
- **Notes**: Enrichment only: `[?UI]` flags, intervention context, positive observations. No code explanations.

### UT Coding Workflow

**Step 1: Load context**

Read these files before coding:
- `method/analysis-plan.md` (column structure, confidence definitions, code registry, feature glossary)
- The transcript to code
- Any existing coded transcripts (to reuse established codes)

The feature glossary in the analysis plan maps prototype UI elements to participant language. This prevents miscoding utterances about features you don't recognize.

**Step 2: Code the transcript**

For each participant utterance, decide:
1. Is there an issue signal? Create a C- or E- code in Issue column, assign confidence
2. Is there a mental model signal? Create an MM-/EXP- code in MM column
3. Is there a rating? Create an R- code in MM column (e.g. R-confidence-3)
4. Any enrichment? Add to Notes ([?UI] flags, intervention context, positive observations only)

Codes emerge from the data. Check the code registry for existing codes before creating new ones. If a new code is needed, add it to the registry.

**Step 3: Apply codes via script**

Because UT transcripts have many rows to code, use a Python script to apply all codes in one pass rather than editing row by row. Build a dictionary mapping row numbers to their codes, then apply:

```python
codes = {
    76: ("C-terminology-respondent", "High", "", ""),
    82: ("E-thought-done", "High", "", ""),
    # ... all coded rows
}
# Split each line by |, replace last 4 columns, write back
```

**Step 4: Update code registry**

Add any new codes to `method/analysis-plan.md` under the appropriate section (Issue Codes, Mental Model Codes, Expectation Codes, Rating Codes).

**Step 5: Generate verification summary**

Create `participants/P#/verification-summary.md` with:
- All flagged issues grouped by phase (row, snippet, code, confidence, verify?)
- `[?UI]` flags (what needs recording verification)
- Extracted ratings
- Proposed phase completion (unaided / with hint / couldn't complete, with evidence)
- Mental model comparison (pre-task vs post-task)
- Code stats (total coded, issue vs MM, confidence breakdown)

The user verifies Medium/Low confidence items and [?UI] flags against the screen recording, then confirms changes.

**Step 6: After verification**

Once the user confirms:
- Update the transcript with any changes
- Populate the synthesis working doc (issue log, phase completion, ratings, mental model comparison)
- Update the codebook with finalized codes

### UT Parallel Mode

When coding multiple UT transcripts (`/code-all`):

1. Read the analysis plan and existing code registry
2. Spawn one subagent per transcript
3. Each agent codes its transcript, proposes new codes, generates verification summary
4. Consolidate: merge new codes into registry, flag conflicts
5. User verifies each participant's summary against recordings
6. Final update to synthesis working doc with cross-participant data

### Key Differences from Standard Mode

| Aspect | Standard Mode | UT Mode |
|--------|--------------|---------|
| Columns | Code 1, Code 2, Notes | Issue, Confidence, MM, Notes |
| Code source | Pre-built codebook | Emergent from data |
| Confidence | 0-1 score (AI) | High/Medium/Low (human-verified) |
| Verification | Spot-check | Medium/Low items checked against recording |
| Output | Coded transcript + quotables | Coded transcript + verification summary |
| Notes usage | QUOTABLE, [?audio], brief context | [?UI], intervention context, positive observations |
| Feature context | Not needed | Feature glossary required |

---

## Standard Mode (Interviews, Concept Tests)

## What This Skill Does (Plain English)

Imagine you have a 500-row interview transcript. You need to read each row and tag it with themes like "pain point" or "data handoff". Doing this manually takes hours.

This skill automates most of that work:

1. **Quick wins first**: Some tags are obvious. If someone says "the form builder", that's clearly about the form builder tool. If the audio is garbled ("the the the the"), that needs a flag. A computer can spot these patterns instantly without any AI.

2. **AI for the tricky parts**: Some rows need judgment. "It's really frustrating when the data doesn't match" could be "pain point" or "data quality" or both. AI handles these nuanced decisions.

3. **Learn from past work**: If you've already coded P1 and P2, the skill learns from those. "Last time you tagged 'I have to manually enter' as 'Manual data entry', so I'll do the same here."

4. **Human review for uncertainties**: The skill doesn't guess. If it's unsure, it flags the row for you to check. You only review the 10% that actually need your judgment.

## How It Works

### Pre-Check: Is Transcript Already Coded?

Before spawning any coding agent, check if the transcript already has codes:

```bash
grep -E "^\| [0-9]+ \| [IP] \|.*\| [A-Za-z]" participants/P#/transcript.md | wc -l
```

If count > 10, the transcript is likely already coded. Options:
1. **Skip** - Don't spawn agent, report "already coded"
2. **Verify only** - Spawn agent with verification prompt (2-6 tool calls vs 15-22)
3. **Recode** - User explicitly wants fresh coding

This prevents wasted effort on already-coded transcripts.

### Single Transcript Mode

When triggered with `/code P#`, run this sequence:

**Pass 0: Speaker ID + Cleanup** (if not already done)

Before coding, identify speakers and fix transcription. This prevents the #1 error: accidentally coding interviewer questions.

**How to identify speakers:**
- Look at first 20 rows for patterns
- Interviewer typically: asks questions, uses "you/your", shorter utterances, echoes back what was said
- Participant typically: answers questions, uses "I/we/my", longer responses, describes their work
- If session-notes.md exists, check for participant name there

```
Task: Prepare transcript for coding.

1. Read first 20 rows to identify speaker pattern
2. Add speaker mapping to Summary section:
   "SPEAKER_00 = Interviewer"
   "SPEAKER_01 = Participant (name if known from session-notes.md)"
3. Scan for obvious transcription errors (tool names especially: product names, WhatsApp often misheard)
4. Flag garbled audio with [?audio] (repeated words like "the the the", cut-off sentences)

DO NOT code yet. Just prepare.
```

**Pass 1: Pattern Match**

```bash
python3 ~/.claude/skills/research-code/code-transcript.py \
  /path/to/participants/P#/transcript.md --apply
```

This auto-codes obvious rows (tools, keywords) and skips fillers. Takes <1 second.

**Pass 2: AI Coding**

DO NOT read the transcript in main context. Spawn subagent:

```
Task: Code remaining uncoded rows in P# transcript.

Files:
- Transcript: [path]/participants/P#/transcript.md
- Codebook: [path]/method/codebook.md

Rules:
- Only code rows where Code 1 is empty
- Check speaker mapping in Summary — skip interviewer utterances
- Notes column: QUOTABLE only, else empty
- Skip fillers (Yeah, Okay, Got it alone)
- Code analogies/stories ONCE, not per-row
- Propose new codes if pattern appears 3+ times

Edit transcript.md directly. Update Summary section when done.
```

**Pass 3: Return Summary**

Report: rows coded, new codes proposed, quotable rows.

---

### Parallel Mode (Multiple Transcripts)

When coding a full project (P1-P5), use parallel mode for speed:

```
/code-all
```

**Phase 1: Generate Initial Codebook**

If no codebook exists, generate from research plan:

```
Task: Create initial codebook from research plan.

Read: method/research-plan.md (or ask user for research questions)

Generate codebook.md with:
- 10-15 starter codes based on research questions
- Clear definitions
- Example utterances (hypothetical)

This is a starting point, not final.
```

**Phase 2: Parallel First Pass**

Spawn subagents simultaneously (one per transcript). Use this exact prompt for each:

```
Task: Code transcript P# for qualitative research.

Files:
- Transcript: [path]/participants/P#/transcript.md
- Codebook: [path]/method/codebook.md
- Session notes (if exists): [path]/participants/P#/session-notes.md

Step 1: Speaker ID
- Read first 20 rows to identify interviewer vs participant
- Add mapping to Summary: "SPEAKER_00 = Interviewer, SPEAKER_01 = Participant"

Step 2: Code each row
- Apply codes from codebook
- SKIP interviewer utterances (don't code questions)
- SKIP fillers (Yeah, Okay, Got it alone)
- Code analogies/stories ONCE on first row, not every row
- Flag garbled audio with [?audio]
- Mark strong quotes as QUOTABLE in Notes

Step 3: Propose emergent codes (IMPORTANT)
- ACTIVELY look for patterns not in codebook
- If you see a pattern 3+ times, you MUST propose it
- Include: code name, definition, 3+ example rows with quotes
- Common missed patterns: terminology preferences, workaround behaviors, feature requests

Step 4: Self-evaluate your process (fill in rubric below)

Return:
- Speaker mapping used
- Count of rows coded
- List of proposed new codes with examples (or "None - all patterns covered by codebook")
- List of QUOTABLE rows (row number + brief quote)
- Self-evaluation rubric (filled in)

## Self-Evaluation Rubric

| Dimension | Question | Rating (1-5) | Evidence |
|-----------|----------|--------------|----------|
| File reads | How many times read transcript? (1=5+, 5=1-2) | | |
| Edit batching | Row-by-row or batches? (1=row-by-row, 5=10+ rows) | | |
| Codebook use | How many times re-read codebook? (1=5+, 5=0-1) | | |
| Speaker ID | Correctly identified speakers? (1=errors, 5=all correct) | | |
| Interviewer skipping | Avoided coding interviewer? (1=coded many, 5=skipped all) | | |
| Code specificity | Used concept-specific codes when applicable? (1=generic, 5=specific) | | |
| Over-coding | Avoided coding stories repeatedly? (1=every row, 5=once) | | |
| Tool calls | Approximate number of tool calls | | |
| Blockers | What slowed you down? | | Free text |
| Improvement | What would make this faster? | | Free text |
```

Each agent returns: codes applied + emergent codes proposed + self-evaluation.

**Efficiency Tips for Subagents:**
- **Batch edits**: Edit 10+ rows at once, not row-by-row. Fewer tool calls = faster.
- **Read once**: Read codebook once at start, internalize codes.
- **Skip verification**: Don't re-read transcript after coding. Trust your edits.

**Phase 3: Consolidate Codebook**

Merge emergent codes from all agents:
- Dedupe similar codes
- Add definitions
- Check for redundancy with existing codes
- User approves additions

**Phase 4: Parallel Recode**

Spawn 5 subagents again with consolidated codebook:

```
Agent 1: Apply new codes to P1 (rows that match new codes)
Agent 2: Apply new codes to P2
...
```

This ensures codes from P5 get applied to P1.

**Phase 5: Summary**

Report across all transcripts:
- Total rows coded per participant
- Code frequency table
- Quotable rows

## Usage

Basic usage (uses current project's codebook):
```
/code P3
```

For a new project with no codebook:
```
/code P1 --research-plan ./research-plan.md
```

Or just:
```
/code P1
```
And the skill will ask what your research is about.

## What You'll Be Asked to Review

After coding, you'll see something like:

```
Coding complete: 493 rows

Auto-coded (no review needed): 312 rows
AI-coded (high confidence): 156 rows
Needs your review: 25 rows

── Low Confidence Rows ──────────────────────────
Row 145: "It's a bit gray area"
  AI suggested: Data ownership (confidence: 0.4)
  Could also be: Edge cases, Workflow complexity
  → Which code fits best?

Row 289: "We use Claude to help think through"
  AI suggested: AI for analysis (confidence: 0.6)
  → Confirm or change?

── Proposed New Codes ───────────────────────────
"Data centralization" - bringing scattered data together
  Example: "ensure that the data is centralised" (P3:96)
  → Add to codebook? Yes/No

"Tool workaround" - building custom solutions for tool limits
  Example: "I compress the data and throw it to the form builder" (P3:208)
  → Add to codebook? Yes/No

── Quotable Moments ─────────────────────────────
Row 91: "It's just everywhere" (Fragmented data)
Row 475: "Data cleaning... we are doing it manually" (Manual data entry)
  → Mark as QUOTABLE?
```

## Files This Skill Uses

**In your project:**
```
method/codebook.md           # Your codes and definitions
method/coding-examples/      # Learned patterns from past transcripts
participants/P#/transcript.md    # The transcript to code
participants/P#/session-notes.md # Optional context from interview
participants/P#/whiteboard.md    # Optional whiteboard analysis
```

**In the skill (universal):**
```
~/.claude/skills/research-code/
├── SKILL.md                 # This file
└── patterns.json            # Common patterns (garbled audio, tool names)
```

## Confidence Scores Explained

The AI assigns a confidence score (0 to 1) for each code it applies:

| Score | Meaning | Action |
|-------|---------|--------|
| 0.9+ | Very confident | Auto-apply, no review needed |
| 0.7-0.9 | Fairly confident | Auto-apply, spot-check if you want |
| 0.5-0.7 | Uncertain | Shows alternatives, asks you to pick |
| <0.5 | Guessing | Flags for human review |

## Tips

- **Code your first transcript carefully.** It becomes the example for all future transcripts.
- **Review proposed new codes.** The skill suggests codes it thinks are missing. Good codes make future coding faster.
- **Session notes help.** If you have notes from the interview, the skill uses them for context.

## Common Errors to Avoid

These errors were common in past projects and cost significant cleanup time:

| Error | Example | How to avoid |
|-------|---------|--------------|
| Coding interviewer utterances | Interviewer says "So you're frustrated?" → coded as Pain point | Check speaker mapping. Only code participant speech. |
| Overcoding analogies | 13-row story coded 13 times for same code | Code the analogy ONCE on the first row. Skip continuation rows. |
| Transcription errors in tool names | a mis-heard product name should be the correct one | First pass: fix obvious tool name errors before coding. |
| Overly broad codes | "AI for analysis" covers 3 different activities | Split broad codes early. If a code has 30+ instances, it's probably too broad. |
| Coding filler responses | "Yeah", "Okay", "Got it" coded as agreement | Skip standalone fillers. Only code if part of substantive response. |
| Coding incomplete utterances | "So basically, yeah, they..." | If utterance is cut off or garbled, flag [?audio] instead of guessing. |

## Linter Guidance

**Problem:** Linters (Prettier, etc.) reformat markdown tables on every edit, causing delays.

**Solution:** Add transcript files to `.prettierignore`:

```
# In project root .prettierignore
participants/*/transcript.md
```

Or disable format-on-save for these files in your editor.

This saves significant time when editing transcripts.

## Notes Column Rules

**Keep Notes sparse.** Most rows should have empty Notes. This is coding, not synthesis.

**Only use Notes for:**
| Marker | When to use | Example |
|--------|-------------|---------|
| `QUOTABLE` | Strong verbatim worth citing in final report | Row says "It's just everywhere" |
| `[WB]` | Row is cross-referenced in whiteboard.md | Added automatically during whiteboard analysis |
| `[?audio]` | Garbled or unclear transcription | "the the the system" |
| Brief context | Only when meaning is genuinely ambiguous | "Dropbox = Dropbox Sign (e-signatures)" |

**Never use Notes for:**
- Explaining why a code was chosen (that's what the code is for)
- Summarizing the utterance (redundant)
- Adding interpretation or analysis (save for synthesis)
- Listing alternative codes considered

**Test:** If you're writing more than 5 words in Notes, you're probably over-explaining.

## How Pattern Matching Works (The "Free" Layer)

Before using AI, the skill scans for obvious patterns. This is instant and costs nothing.

**Garbled audio detection:**
- Repeated characters: "the the the the" → `[?audio]`
- Very short utterances that don't make sense → `[?audio]`
- Repeated words: "Yeah. Yeah. Yeah." → likely filler, low priority

**Tool detection:**
- "the form builder" → suggests `Tool: Form Builder`
- "dashboard" → suggests `Dashboard`
- "WhatsApp", "Telegram", "email" → suggests `Fragmented data`

**Keyword hints:**
- "manual", "by hand" → suggests `Manual data entry`
- "clean", "cleaning" → suggests `Data transformation`
- "centraliz-" → suggests `Data centralization` (new code)

These are suggestions, not final codes. The AI confirms or adjusts based on context.

## Glossary

| Term | Plain English |
|------|---------------|
| Codebook | A list of tags/themes with definitions. Like a legend for your data. |
| Few-shot examples | "Here are 10 examples of how I coded before, do the same." |
| Confidence score | How sure the AI is (0 = guessing, 1 = certain) |
| Pattern matching | Finding text that matches a template (like Ctrl+F but smarter) |
| Cold start | First transcript in a new project, no examples to learn from |

## Whiteboard Analysis (Optional)

If you have whiteboard photos from the session, share them after coding. The skill will create a `whiteboard.md` file that connects what they drew to what they said.

### What It Does

1. **Transcribes** the whiteboard content (text, diagrams, arrows)
2. **Recreates** diagrams in ASCII art so they're searchable and readable
3. **Cross-references** each element to specific transcript rows
4. **Analyzes framing** (what did they draw first? what does that reveal?)
5. **Summarizes** key insights and design implications

### Example Output

```markdown
## Board 1: Data Flow

| Whiteboard Element | Key Transcript Rows | Codes |
|-------------------|---------------------|-------|
| "WA / Emails / Tele" | 90, 91, 94, 95 | Fragmented data |
| "one place, clean" | 96, 97 | Data centralization |
| "Form builder as transport" | 208, 236 | Tool: Form Builder |

### Framing Analysis

**What they drew first:** The ideal state (centralized → clean → insights)
**What this reveals:** They think in terms of desired outcomes, not current pain
```

### Why This Matters

Whiteboards capture how people naturally organize their thinking. Someone might say "data is everywhere" in the transcript, but the whiteboard shows exactly which systems they're referring to. The cross-reference table connects the abstract quote to the concrete diagram.

### Usage

After coding a transcript:
```
Here are the whiteboard photos from that session
[attach images]
```

The skill will:
1. Ask which photos go together (if multiple boards)
2. Generate `participants/P#/whiteboard.md`
3. Link evidence to transcript rows

---

## Efficiency Benchmarks

From a concept-testing study (7 transcripts):

| Scenario | Tool Calls | Notes |
|----------|------------|-------|
| Verification only (already coded) | 2-6 | Just read + confirm |
| Fresh coding (short, <150 rows) | 6-15 | P3, P5 |
| Fresh coding (medium, 300-500 rows) | 15-20 | P1, P2, P7 |
| Fresh coding (long, 600+ rows) | 20-25 | P4 |

**Why parallel subagents work for coding:**
- Each agent reads its own files directly (no context passing)
- Each agent writes codes directly to its own file
- Only summaries return to main context (emergent codes, quotables)
- No large data passes through main context

This is different from transcription, where raw data must flow through main context (10-13x slower with subagents).

---

## Troubleshooting

**"The codes don't match my codebook"**
- Check that `method/codebook.md` exists and is formatted correctly
- The skill reads the codebook at the start of each run

**"Too many rows flagged for review"**
- This happens with the first transcript (no examples yet)
- After you review and confirm, future transcripts will have fewer flags

**"It's applying wrong codes"**
- Check your coding examples in `method/coding-examples/`
- Bad examples lead to bad coding
- You can delete examples and rebuild from your best-coded transcript

**"It missed an obvious code"**
- Add the pattern to the codebook with a clear definition
- Or add a keyword hint (coming soon)
