---
name: research-coverage
description: Check which of a study's research questions or session phases actually have coded evidence behind them, and flag the ones that have none. Use this whenever the user asks what they are missing, whether they have enough data, whether they can stop recruiting, if a question went unanswered, "did we answer everything", "what gaps are left", "is this study done", or wants to know whether a finding rests on a single participant. Also use it before writing a synthesis, before a research handover or readout, and when deciding whether another round of sessions is needed. Works with UT studies (checks session phases) and interview studies (checks research questions) that follow the participants/P#/transcript.md convention.
---

# Coverage Gap Check

This answers one question with arithmetic instead of judgement: which of the things this study set out to learn have no coded evidence behind them?

It is deliberately dumb. A question either has rows coded against it or it does not. There is no confidence score, no partial credit, and no prose about whether the evidence feels sufficient. That is the point. Softer versions of this check tend to conclude that everything is mostly covered, which is the one answer that makes it useless.

## The link that has to exist first

Nothing in these repos records what a coded row is evidence *for*. Codebooks list codes, definitions, and examples. UT registries group codes by prefix, which groups by kind of finding. Neither says which question a code answers.

So there is nothing to compute against until that link is written down once, with the user's approval. After it exists, every run is set arithmetic.

The two study types need genuinely different links, because they declare different intentions:

| Mode | Checklist comes from | Item ids | Link file |
|---|---|---|---|
| Standard | `research-plan.md`, primary plus secondary questions | `RQ1`, `RQ2`, ... | `rq-map.md` |
| UT | `analysis-plan.md`, the `## Session Phases` table | `PH1`, `PH2`, ... | `phase-map.md` |

### When the declared checklist is too thin to be useful

Some plans declare a single broad research question. A one-item checklist can only ever return "all covered" or "nothing covered", which tells the user almost nothing, and reporting "no gaps" from it is close to meaningless.

When that happens, do not just report the vacuous result. The study's **operational** questions are the must-ask questions in `discussion-guide.md`, marked in bold by the guide's own convention (`**Bold** = Must-ask`). Those are what the sessions were actually built to answer, and they make a checklist with real structure.

Offer to derive the checklist from them, get approval, and record the derived list alongside the map so the run is repeatable. Say clearly in the report that the checklist was derived from the guide rather than declared in the plan, because that is a different claim about the study.

Then suggest the plan be updated to declare those questions properly. A coverage check cannot find gaps against a question nobody wrote down, so a thin plan quietly disables the check.

Be straight with the user about the trade: **after the link exists the check is fully mechanical, and its trustworthiness reduces entirely to whether the link is right.** That is a good deal, because both link files are short enough to read and correct by hand, which is not true of a synthesis.

## Mode detection

Same rule as `research-code`, so both skills agree about the study type. `analysis-plan.md` in `method/` or `approach/`, plus `Issue`, `Confidence`, and `MM` columns in the transcript table, means **UT study**. Otherwise **standard study**.

Neither source file has an id scheme, so the parser assigns ids by order. They are stable as long as nobody reorders the source, and the report always prints the full label beside the id so a shifted id is obvious.

Run this first to see what was detected:

```bash
python3 scripts/transcript_parse.py <study-root>
```

## Step 1a: UT studies, build the phase map

Session phases are **temporal**. They describe when in the session something happened. Codes are **thematic**, and a `MM-` code can turn up in any phase. So there is no correct mapping from codes to phases, and trying to build one produces a confident wrong answer.

What a phase actually needs is its row range, per participant:

```markdown
| Participant | PH1 | PH2 | PH3 | PH4 | PH5 | PH6 |
|-------------|-----|-----|-----|-----|-----|-----|
| P1          | 1   | 95  | 150 | 480 | 560 | 640 |
| P2          | 1   | 78  | 130 | 390 | 445 | 470 |
| P3          | 1   | 60  | 118 | -   | 400 | 430 |
```

Each cell is the first row of that phase. A phase runs until the next one starts, and the last runs to the participant's final row. A cell of `-` means the phase never happened for that participant, which is a legitimate entry and gets reported separately from a phase that happened and produced no codes. Those two look identical in a summary and mean completely different things, so the check keeps them apart.

Propose boundaries by reading the interviewer rows for the transition questions. The discussion guide sections named in `analysis-plan.md` tell you what to look for. Six boundaries per participant is a short review, and getting one wrong shifts coverage between two adjacent phases rather than corrupting the whole picture.

Save to `<method-or-approach>/phase-map.md`.

## Step 1b: Standard studies, build the code map

Here codes really are the right unit, and there are usually few enough to handle.

Map at the **category** level, using the `###` headings already in the codebook, and add a per-code row only where a code does not follow its category:

```markdown
| Code | Answers |
|------|---------|
| Trust & Comfort | RQ1 |
| Boundaries & Red Lines | RQ1, RQ2 |
| Government Service Experience | RQ2 |
| Initial reaction | - |
```

A code inherits its category's mapping unless there is a row naming that exact code, which wins. Categories keep this to about six rows instead of one per code.

`-` means the code answers no declared question. That is a legitimate entry, not a gap. Codes marked `-` are often the interesting ones, because they are findings the study was not looking for.

Save to `<method-or-approach>/rq-map.md`.

## Both: stop for approval

Do not run the check on an unreviewed link file and present the output as fact. A wrong mapping or a misplaced boundary produces a precise, confident, wrong answer, which is worse than no answer. Show the table and ask the user to correct it.

This is the only step in the skill that involves judgement, so it is the only step that deserves their attention. Everything after it is arithmetic.

If the link file is missing, `coverage.py` exits 3 and names the path it expected. It will not guess.

## Step 2: Run the check

```bash
python3 scripts/coverage.py <study-root>
```

Exit codes make this usable as a real gate rather than something to read past:

| Code | Meaning |
|---|---|
| 0 | Every item has evidence and every participant is coded |
| 1 | At least one item has no evidence |
| 3 | No link file, build it first |
| 4 | A participant has no codes at all, so the result is not trustworthy |

Exit 4 exists because of the worst output this check can produce. On a three-participant study where one transcript was never coded, an earlier version reported no gaps and exited 0. The coverage was real, but it was computed over two thirds of the data, and nothing in the output said so. "No gaps" from a partly coded study is not a finding about the research, it is a finding about the coding.

So check coding completeness before you read anything else. The report prints it as its own section: rows and coded rows per participant. A participant sitting at zero means stop and code them, not recruit more people.

Add `--json` for machine-readable output, or `--map PATH` to point somewhere else.

The report sections each answer a different question:

- **Coverage table**: every item, its evidence, and `covered` or `GAP`. In UT mode this includes a per-participant breakdown, because "PH5 covered" can hide "only P1 got that far".
- **Gaps**: zero coded rows. This is the answer to "what did we not learn".
- **Not run** (UT only): phases marked `-` for some participants. Not a gap in the data, a gap in the sessions.
- **Thin coverage**: all evidence comes from one participant. Not a gap, but a finding resting on a single voice, worth knowing before it goes into a readout as a pattern.
- **Dead codes**: mapped but used in zero rows. Usually a code that was planned and never emerged, which is a small finding about the study's assumptions.
- **Unmapped codes**: used in transcripts but absent from the map. These need a decision, not a fix. Either the map missed one or a finding came from outside the plan, so present them as a question rather than an error.

In standard mode the report also names which rule matched each code, category or explicit, so a surprising result is traceable to the rule that caused it.

## Step 3: Watch it fail before trusting it

A coverage check reporting full coverage has told you either that the study is complete or that the check is broken, and the output looks the same either way. So make it fail on purpose:

```bash
python3 scripts/coverage.py <study-root> --selftest
```

It takes the real data, picks the item with the most evidence, drops that evidence, and confirms the item now reports `GAP`. It also confirms an unrelated item is still `covered`, so you know it suppressed one thing rather than blanking everything. In UT mode it suppresses by phase range; in standard mode by mapped codes.

Nothing is written and no files are touched. The coverage computation is a pure function over parsed rows, so the selftest just calls it with a filtered list.

Run this the first time you use the check on a study, and again after editing a link file. If it fails, the check is not measuring what it claims and its output should not be reported.

If it cannot run because nothing is covered, it exits 2 and says so. Report that too: a study where no item has any evidence usually means the link file does not match the codes or rows actually in use, not that no coding has happened.

## Report format

```markdown
# Coverage: <study name>

Mode: <ut|standard>
Participants: <n>
Coded rows: <n>
Selftest: PASS

## Gaps
<items with zero coded rows, or "none">

## Not run
<UT only: phases that did not happen, by participant, or "none">

## Thin coverage
<items resting on one participant, or "none">

## Coverage
| ID | Item | Evidence | Participants | Status |
|---|---|---|---|---|

## Dead codes
## Unmapped codes
```

Lead with the gaps. A full coverage table is reassuring to read and is not what the user asked for.

## Step 4: Ask what the arithmetic cannot

The check is set arithmetic over coded rows, so there is a whole class of gap it will never see, and it will report a clean result while that gap sits in the data. Do not stop at the table. After the numbers, look at these by hand and put them in the report:

**Sort the gaps by what would actually close them.** This is the step that answers the question users are really asking, and the arithmetic cannot do it:

- Gaps **coding** would close: a transcript exists and nobody has coded it.
- Gaps **more sessions** would close: the topic was never raised with anyone.
- Gaps **only different recruitment** would close: the people you spoke to are not positioned to answer.

Name at least one gap in the third category, or say plainly that there are none. That category is the one this check is blind to, and it is the only one where "do I need another round" is genuinely yes.

**Does the sample fit the question?** This is how you find the third category. A study can have full coverage of a question its participants cannot answer from experience. Read how they talk about the topic: first person ("I would feel") means lived experience, third person ("people who might need this would feel") means they are imagining someone else. If a question asks how people in a situation feel, and every participant is speculating about that situation from outside it, the question is not covered no matter how many rows sit against it.

This is not hypothetical. On a real run, a study whose only research question was how citizens feel about AI in services that directly involve them came back with full coverage. Not one participant had used the service the central scenario was about, and they answered it in the third person throughout. The check reported no gaps, correctly by its own definition, and the honest answer was that another round was needed with different screening criteria.

**Is anything single-source that reads as a pattern?** The check flags this, but flagging is not enough. Say which participant carries it and whether they are unusual in a way that matters for that specific point.

**Would coding the uncoded transcripts change the picture?** When a participant is uncoded, skim their raw transcript against the thin items and say which ones their material would likely lift. That turns "code P3" into a prediction the user can check, which is more useful than an instruction.

None of this is mechanical, and that is the point. The check exists so nobody has to eyeball the countable things, which frees the attention for these.

## When not to use this skill

Worth being straight about, because reaching for a tool that is worse than reading is a bad trade.

On a study small enough to read in one sitting, three or four transcripts of a few hundred rows, reading it beats running this check. Someone holding the whole study at once will spot the sampling problem, the miscoded category, and the thin theme, and will not need a map file to do it. This was tested, and unassisted reading found more than the check did on a three-participant study.

What this skill actually buys you:

- **Repeatability.** The map is committed, so the same run gives the same answer, and a disagreement about coverage becomes a disagreement about a specific table row.
- **A real gate.** Exit codes mean this can block a synthesis or a handover rather than being a document someone skims.
- **Scale.** It keeps working when there are more transcripts than fit in one context, which is where reading stops being an option.

Reach for it for those. On a small study, read the transcripts and use `research-counter-bias` on the themes instead.

## What counts as evidence

Worth stating plainly, because the check is only as meaningful as this definition.

In standard mode a row counts when it carries a code the map links to that question. In UT mode a row counts when it falls inside that phase's range for a participant and carries any code at all.

That is the whole definition. The check does not read the utterance, does not weigh how strong a row is, and does not care whether the participant sounded certain.

So `covered` means **somebody said something coded here**, not that the question is answered well. Depth is a judgement call and this skill deliberately does not make it. Use `research-counter-bias` to test whether the evidence holds up.

## Limits

- It checks against the study's **declared** intentions. A question nobody thought to ask is invisible, because it is missing from the plan too.
- Ids are positional, so reordering questions or phases in the source reshuffles them. The label always prints beside the id for this reason.
- Codes must be spelled consistently. A typo becomes an unmapped code, which is why that section exists rather than being quietly dropped.
- Partly coded studies show gaps that are really unfinished coding. Check how many transcripts carry codes before reading a gap as a research finding, and say which it is.
- A phase boundary off by a few rows moves evidence between neighbouring phases. Worth knowing when two adjacent phases sit near the line between covered and gap.

## Files this skill uses

| Path | Role |
|---|---|
| `participants/P*/transcript.md` | Source of coded rows, read only |
| `method/research-plan.md` or `approach/research-plan.md` | Research questions, standard mode |
| `method/analysis-plan.md` | Session phases, UT mode |
| `method/codebook.md` or `approach/codebook.md` | Codes and categories for the map |
| `method/rq-map.md` | Code to question map, standard mode |
| `method/phase-map.md` | Per-participant phase row ranges, UT mode |
| `scripts/coverage.py` | The check, with `--selftest` |
| `scripts/transcript_parse.py` | Shared parser, runnable alone to debug detection |

The link file is the only thing written into a study repo, and only with the user's approval.

## Related

- `research-code` applies the codes. Coverage is meaningless before it has run.
- `research-counter-bias` tests whether covered items are covered *well*. Coverage finds silence, counter-bias finds contradiction, and a study wants both.
