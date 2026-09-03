---
name: research-counter-bias
description: Stress-test qualitative research findings by hunting for evidence that contradicts them, using fresh subagents that read blinded transcripts so they cannot anchor on the existing codes. Use this whenever the user wants to challenge, pressure-test, sanity-check, or find holes in research themes, findings, an issue log, or a synthesis; whenever they ask "is this finding real", "does the data actually support this", "what am I missing", "am I seeing what I want to see", or "how confident should I be in this theme"; and whenever they are about to present or hand over research conclusions and want them checked first. Also use it to verify frequency claims like "4 of 5 participants" against the transcripts. Works with UT studies and interview studies that follow the participants/P#/transcript.md convention.
---

# Counter-Bias Pass

Coding a transcript makes you fluent in your own story. By the time themes exist, every reread of the data tends to confirm them, because you already know what you are looking for and the codes tell you where to look. This skill exists to break that loop. It sends fresh readers at the raw words with one job: find what does not fit.

Two things make it work, and both are easy to lose:

**The readers must be blind to the codes.** Transcripts in these repos are coded in place, so the code columns sit right next to the utterances. An agent that can see `C-entry-point-unclear` in the Issue column will read the surrounding rows as evidence for confusion. So the transcripts get stripped to `#`, `Speaker`, and `Utterance` before anyone reads them.

**The readers must not know each other's work, or yours.** One fresh agent per claim, each given only the blinded transcripts and the single claim it is testing. No codebook, no synthesis, no other agent's findings. An agent asked to critique reasoning it can see will reconstruct and defend that reasoning.

## Mode detection

Same rule as `research-code`, so the two skills agree about what kind of study this is.

Look for `analysis-plan.md` in `method/` or `approach/`. If it exists and the transcript table has `Issue`, `Confidence`, and `MM` columns, this is a **UT study**. Otherwise it is a **standard study** (interviews, concept tests) with `Code 1` and `Code 2` columns.

The scripts detect this on their own. Run `python3 scripts/transcript_parse.py <study-root>` to see what it decided, along with participant and row counts. Do that first if anything downstream looks wrong.

## Step 1: Gather the claims

A claim is a statement the research is currently making. Pull them from wherever the study records its conclusions:

- **UT studies**: the issue log in `SYNTHESIS.md`, grouped by severity. These are gold for this pass because they already carry counts like `4/5 participants`, which are checkable.
- **Standard studies**: the core findings or theme sections in `SYNTHESIS.md` or `SYNTHESIS-working-doc.md`.
- **No synthesis yet**: derive candidate claims from code frequency across transcripts. A code appearing in four of six participants is an implicit claim.
- **User named them**: use theirs, and do not add your own.

Write each claim as a **falsifiable statement**, not a topic. This matters more than it looks. "Autosave" gives an agent nothing to disprove, so it will summarise. "Users expect their work to save automatically and are surprised when it does not" can be checked against a specific row.

Show the user the claim list before spending agents on it. A misworded claim wastes the whole pass, and they will spot a bad wording instantly.

## Step 2: Audit the claims against what they cite

Do this before building anything or spending any reading agents. It is cheap, it is arithmetic, and it often ends the run: a miscount is a bigger finding than a nuanced contradiction, and it changes which claims are worth testing at all.

The order matters for a practical reason. An earlier version of this skill built the blind copies first, then audited, then stopped because the audit found problems. The blinding was wasted work, and the run reported success having never used the skill's main mechanism.

Check all of these. They are all things a stated claim can get wrong without anyone noticing:

**Does the count hold?** Grep the codes behind the claim and count distinct participants. Watch the unit: one transcript folder can hold two people in a paired session, so folders are not participants.

**Is the denominator real?** A claim of `3/5` measured against five people, two of whom never encountered the thing, is really `3/3` with two unobserved. That is a much stronger signal than `3/5` suggests, and it is reported as a weaker one. Check whether every participant in the denominator has rows for the relevant phase.

**Does the cited row say what the claim needs?** Read it. A quote can be verbatim and still be the wrong evidence, for instance if the row is coded for a different confusion than the one the claim is about.

**Is the cited order real?** When a claim asserts that one thing happened before another, compare the row numbers. This is a ten second check and it has caught a load-bearing causal claim stated backwards.

**Is the attributed speaker right?** In paired sessions, find the interviewer's turn naming each person and check which side of it the row falls on. A flipped attribution can invert a finding while every quote stays accurate.

**Is a number stated or inferred?** A rating coded as `4` where the row contains no numeral is a coder's reading, not the participant's answer. Say which, and recompute any average without the inferred cells so the user can see whether the headline moves.

**Do the cited codes exist?** Grep every code name in the registry against the transcripts. A code with a registry entry and zero hits is a phantom, and any count built by grepping registry names silently returns zero for it.

Watch for the near miss here, because it is easy to wave through: a phantom often exists in the transcripts under a **different name**. Finding a similarly named code on the same row is not a match, it is a rename, and it means the registry and the transcripts disagree. Report it as drift rather than treating the registry entry as satisfied.

**Do sections agree with each other?** A synthesis that says "every participant" in one section and lists a counterexample in its own table two sections later has contradicted itself, and both statements will be quoted.

### Before you report any of it, verify it

Every mismatch you report sends the user back to their data. A wrong one costs them more than a missed one, so re-check each finding against the transcript before it goes in the report, and drop the ones you cannot stand behind. Say how many you checked and how many held.

If the audit finds problems, stop here and show the user. Do not build blind copies or spawn readers yet. The claim wordings will change once these are resolved, and testing a wording that is about to change burns the pass.

## Step 3: Build blind copies

Only once the claims are settled.

```bash
python3 scripts/blind_transcripts.py <study-root> --out <scratch>/blind
```

This writes one file per participant with only `#`, `Speaker`, `Utterance`, plus a `manifest.json` of row counts.

Interviewer rows stay in. Do not strip them, even though `research-code` tells you never to code them. Here they carry the information that decides a verdict: whether a participant was ever asked about the topic. A participant who was asked and said something different is evidence against the claim. A participant who was never asked is not evidence at all, and quietly counting them as agreement is one of the most common ways a thin finding looks solid.

## Step 4: One fresh agent per claim

Spawn them in parallel, one per claim. Each gets only the blind directory path and its own claim.

**Budget the claims before you spawn.** Each reading agent reads every transcript in full, which on a four-transcript study costs roughly 120k tokens. A measured run came to about 480k for three claims plus the canary pass. That is fine for the three or four claims a readout actually rests on, and wasteful as a sweep across a whole issue log.

So pick the claims that would change a decision if they turned out to be wrong: the ones going into a handover, the ones a severity rating depends on, the ones someone is quoting. Tell the user the count and the rough cost before spending it, and if they want the whole log tested, do it in batches so they can stop after the first batch tells them something.

Use this prompt shape. The parts that matter are the refusal to ask for supporting evidence, and the explicit permission to find nothing:

```
You are checking one claim against interview transcripts.

CLAIM: "<the falsifiable statement>"

Transcripts are in <blind-dir>. Each file is one participant, as a table of
row number, speaker, utterance. Speaker I is the interviewer, P is the
participant, O and O2 are observers.

Read every participant file in full.

Your only job is to find evidence that does NOT fit the claim. Specifically:

1. Rows where a participant says something that contradicts the claim.
2. Rows where a participant was asked about this topic and answered in a way
   the claim does not predict. Look at the interviewer's questions to find
   where the topic came up.
3. Participants who were never asked about this topic at all. Say so per
   participant, and cite the closest the interviewer got.

Do not collect evidence that supports the claim. Others are doing that and it
is not what this pass is for.

Report every finding as: participant, row number, and the utterance quoted
word for word. A finding without a quote and a row number cannot be checked,
so it is not usable.

Finding no contradictions is a real and useful answer. If the data genuinely
fits the claim, say that plainly. Do not stretch a weak row into a
contradiction to have something to report.
```

That last paragraph is not politeness. An agent told to find problems will find problems, and invented contradictions are worse than none, because they send the user back to the recordings to chase something that was never said.

## Step 5: Prove the pass can actually fail

A counter-bias pass that reports "no contradictions found" is worthless unless you know it would have caught one. So plant one and watch.

Write a canary file with one fabricated utterance per claim, each a flat contradiction phrased in that participant's own register:

```json
[
  {"participant": "P3", "after_row": "147", "speaker": "P",
   "utterance": "Honestly I would rather it never saved on its own. I want to press save myself every time."}
]
```

Then build a separate canary copy and rerun the same agent prompt against it:

```bash
python3 scripts/blind_transcripts.py <study-root> --out <scratch>/canary --canary canaries.json
```

The script renumbers rows in the canary copy so the planted row cannot be spotted by its numbering, and writes `canary_answers.json` with where each one landed. Because the numbers have shifted, **row numbers from a canary run must never appear in the findings report.** The canary run tests the method. The real run produces the findings.

Then check the result honestly:

- Canary caught: report the claim's verdict as trustworthy.
- Canary missed: say so, and mark that claim's verdict as unverified. Do not report a clean bill of health from a check you just watched fail to notice a flat contradiction sitting in the data.

A missed canary usually means the claim wording was too vague to test, or the transcripts are long enough that the reader skimmed. Rewording the claim more sharply fixes it more often than rerunning does.

## Step 6: Report

### First, check exposure

Before anyone counts as contradicting a claim, confirm they actually encountered the thing the claim is about. This step was added because the pass got it wrong without it.

On a real run, a claim about a prototype feature was tested across four transcripts, and two participants were counted as contradicting it. Their session never included the prototype task at all. Their transcript jumps from the warm-up straight to the debrief, so their comments were recollection, not reaction. Counting them as counter-evidence inflated the verdict and pointed at the wrong conclusion.

So sort participants into four buckets, not three:

```
Not exposed:     never encountered the thing the claim is about
Never asked:     exposed, but the topic never came up
Contradicted by: exposed, asked, and said something that does not fit
Consistent with: exposed, asked, did not contradict
```

Only the last two are evidence about the claim. The first two are evidence about the study.

The blind transcripts are enough to check exposure, because a session that skipped a task has no rows for it. When a transcript jumps from one phase to a later one, say so, and put those participants in "not exposed" whatever they said afterwards.

### Then write the verdict

Say **consistent with**, not **supports**. A participant who was asked and did not contradict the claim has not endorsed it. Writing "supports" turns silence into agreement, which is the exact bias this pass exists to catch, and it would be odd to reintroduce it in the summary line.

Do not present the buckets as a score. A count of contradictions is not a refutation tally, and formatting it like one invites reading "contradicted by 3" as though the claim lost a vote. Three people contradicting a claim about their own experience may mean the claim is wrong, or that it was always about a narrower group than it was written for. Say which you think it is, and say what the claim would have to be narrowed to in order to survive.

One dissenter against five is a finding about that dissenter. Report it as that. This is the single easiest place for the pass to overcorrect: having spent the whole run hunting for contradictions, the summary tends to treat every one it found as decisive.

Use this structure:

```markdown
# Counter-Bias Pass: <study name>

Blinded transcripts: <n> participants, <n> rows
Claims tested: <n>
Canary validation: <n> of <n> caught

## Claim 1: <the claim as tested>

**Stated in synthesis as:** <original wording and count, if any>
**Count check:** <matches, or the real count>
**Verdict:** consistent with <n>, contradicted by <n>, never asked <n>
**Canary:** caught at P3 row 148 / MISSED, verdict unverified

### Contradicting evidence
| Participant | Row | Quote |
|---|---|---|
| P2 | 47 | "..." |

### Never asked
| Participant | Closest the interviewer got |
|---|---|
| P4 | row 92, "..." |

## Summary
| Claim | Consistent | Contradicted | Never asked | Canary |
|---|---|---|---|---|
```

Lead the summary with claims whose verdicts changed, not with the ones that survived. The user already believes the surviving ones.

## What this pass cannot do

Be straight with the user about the limits, because a false sense of rigour is worse than none:

- It finds contradictions **in what was said**. A topic nobody raised and the interviewer never asked about stays invisible. That gap is `research-coverage`'s job.
- It cannot tell a participant being polite from a participant agreeing.
- Blinding removes the codes, not the wording of the claim. A leading claim still leads.

## Common ways this goes wrong

**Reusing an agent that has already seen the codes.** The single most likely failure, and it silently turns the pass into confirmation. Each claim gets a genuinely new agent, given only the blind path.

**Testing a topic instead of a claim.** Produces a summary of what people said about the topic, which reads useful and checks nothing.

**Stripping interviewer rows.** Loses the ability to tell "never asked" from "asked and disagreed", which is most of the value.

**Citing canary-run row numbers.** They are renumbered, so they point at the wrong utterances in the real transcript.

**Reporting one participant's contradiction as if it sinks a claim.** One dissenting voice against five is a finding about that participant, and worth a line, but it is not a refutation. Say which it is.

## Files this skill uses

| Path | Role |
|---|---|
| `participants/P*/transcript.md` | Source, read only, never written |
| `SYNTHESIS.md` or `SYNTHESIS-working-doc.md` | Where claims come from |
| `method/analysis-plan.md` | Mode detection, code registry for count checks |
| `scripts/blind_transcripts.py` | Strips coding columns, optionally plants canaries |
| `scripts/transcript_parse.py` | Shared parser, runnable alone to debug mode detection |

This skill never writes to a study repo. Findings go wherever the user asks, and the default is to show them in the conversation first, because a verdict that changes a finding is something they will want to argue with before it lands in a file.

## Related

- `research-code` applies codes to transcripts. Run it before this.
- `research-coverage` finds research questions with no evidence at all. That is the blind spot this skill cannot see, so the two are worth running together.
