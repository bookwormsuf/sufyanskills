---
name: link-pass
description: Scan recently changed second-brain notes for entity mentions that should be [[wikilinks]], propose them for approval, and flag repeatedly mentioned entities that have no note yet. Use when the user says '/link-pass', 'run a link pass', 'fix my wikilinks', 'find missing links', 'what notes am I missing', or at the end of a session when notes were written or edited and the user wants the vault's links kept healthy. Also suggest it after /review-session when new notes mention existing people or projects as plain text.
---

# Link Pass

Keep the vault's wikilink graph healthy. Notes mention people, projects, and topics as plain text all the time; every unlinked mention is invisible to backlink greps and to Claude following links. This pass finds those mentions in recently changed files and proposes fixes. It never edits without approval.

This skill assumes an Obsidian-style vault with `people/`, `projects/`, `learnings/`, and `notes/` folders.

**Vault root:** takes a `--vault` argument pointing at the vault. Defaults to the current working directory, so running it from inside the vault needs no argument.

## Step 1: Run the scanner

`scripts/find_candidates.py` does the mechanical half: it enumerates every note that exists, works out which files changed since the last pass, masks the regions where a link would be wrong (code blocks, inline code, frontmatter, URLs, existing links), and reports each unlinked mention with a line number and a ready-to-apply replacement line. It takes a couple of seconds, where reading the files yourself takes minutes.

```bash
cd /path/to/your/vault
python3 /path/to/link-pass/scripts/find_candidates.py --vault .
```

Useful flags: `--vault <path>` to point at a vault other than the current directory, `--files a.md b.md` to scan specific files, `--all` for the whole vault, `--no-orphans` to skip the notes-waiting-to-exist search.

The JSON it returns has:

- `first_run` — true when no state file existed, meaning it fell back to the last 20 commits. Tell the user, and offer `--all` if they'd rather sweep everything.
- `files_scanned` — scope is `notes/`, `people/`, `projects/`, `learnings/`, minus archives and minus chronological logs (`STATUS.md`, `SESSION_LOG.md`, `INDEX.md`). Logs are dated build records; nobody follows a link out of one, and their length makes them generate noise by the dozen.
- `candidates` — each with `file`, `line`, `matched_text`, `target`, `current_line`, `replacement_line`, and `first_name_only`.
- `orphans` — recurring proper nouns with no note, with the file count behind each.

If `candidates` and `orphans` are both empty, say the vault is clean and stop.

## Step 2: Judge the candidates

The script is deliberately mechanical, so it finds real mentions but cannot tell whether a link is *worth making*. That judgement is yours, and it's the whole reason a human-facing proposal step exists. Read each candidate's `current_line` and drop the ones where:

- The mention is a common word that happens to match a note title. `Visual Design` as a heading about the general skill is not a link to `visual-design.md`.
- The link adds nothing a reader would follow. A passing mention in a list of seven names is weaker than a sentence about that person's work.
- `first_name_only` is true and the surrounding text makes you doubt it's that person. The script only offers a first name when exactly one person in the vault owns it, but context still wins.
- The note is about the entity itself, so linking is circular.

Mark anything you're unsure about as uncertain rather than proposing it confidently. A wrong link is worse than a missing one, because it quietly corrupts the graph the whole vault depends on.

## Step 3: Judge the orphans

An orphan is a proper noun that keeps appearing with no note behind it. High file counts are the strong signal; something in 30 files is clearly part of your working vocabulary. Discard orphans that are third-party products you only mention in passing, and keep the ones carrying real information you'd want to find later.

## Step 4: Propose, approve, apply

Present one proposal list before touching anything:

```markdown
## Link proposals

### notes/weekly-sync-2026-09-04.md
1. "Alex" → [[alex|Alex]] (line 12)
2. "the Project Atlas research" → [[project-atlas-research|Project Atlas research]] (line 30) — uncertain, confirm

### projects/intern-scoping.md
3. "Priya" → [[design-attachee-priya|Priya]] (line 8)

## Notes waiting to exist
- **Dialkit** — mentioned in 4 files (list them). Create projects/dialkit.md?
```

Let the user approve all, pick numbers, or skip. Apply only approved edits with the Edit tool, using the scanner's `replacement_line` verbatim so nothing but the linked mention changes.

Use that line rather than composing the link yourself, because the safe form is not always the obvious one. Inside a markdown table the pipe is a column separator, so a piped link has to escape it as `[[alex\|Alex]]`; write the unescaped version and the row silently gains a column and the table breaks. The scanner already knows which lines are table rows.

## Step 5: Verify the edits

Applying an edit and reporting success is not evidence the edit was right. Run the verifier on every file you touched, before updating state and before telling the user you're done:

```bash
python3 /path/to/link-pass/scripts/verify_edits.py --vault . --files <each file you edited>
```

It re-reads each file and checks what a wikilink can silently break: table column counts against their header, `[[` matched by `]]`, bare pipes inside table rows, and whether every link target resolves to a real note. Where a file is tracked by git it diffs findings against the committed version, so only damage *this pass introduced* is reported. Exit status is 1 when something new is wrong.

If it reports a problem, fix it before continuing. Do not update the state file: the next run should re-cover those files. Tell the user what broke and what you did about it, because a maintenance tool that quietly damages notes is worse than no tool.

`--all` audits the whole vault instead of the changed files, and `--all-findings` includes pre-existing problems. That combination is a useful occasional health check; dangling links it surfaces are usually notes waiting to exist rather than mistakes, so report them, don't fix them.

## Step 6: Update state

Once verification passes, write the current HEAD hash and date:

```bash
echo "$(git rev-parse HEAD) $(date +%F)" > .claude/link-pass-state
```

Don't update state if the scan failed, was aborted, or the verifier found new damage; the next run should re-cover the same files.

## Report

End with a short summary: files scanned, links added, notes suggested, and that verification passed. If zero proposals came up, that's a healthy vault; say so, don't invent work.
