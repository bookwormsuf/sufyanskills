"""Produce blinded copies of a study's transcripts (rows and speakers only,
no coding columns), so a fresh agent can read them without being anchored
by whatever codes were already applied.

Why interviewer rows are kept: the interviewer's questions are the only way
to tell "this topic was never asked about" apart from "it was asked about
and the participant said something that didn't get coded". Dropping I/O/O2
rows would erase that distinction, and a fresh reviewer needs it to tell a
real gap from a coding miss.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

from transcript_parse import find_study_root, list_participants, parse_transcript


# ---------------------------------------------------------------------------
# Blind copy generation
# ---------------------------------------------------------------------------

def render_blind_table(rows: list[dict]) -> str:
    """Render rows as a markdown table with only #, Speaker, Utterance."""
    lines = ["| # | Speaker | Utterance |", "|---|---------|-----------|"]
    for row in rows:
        utterance = row["utterance"].replace("|", "\\|")
        lines.append(f"| {row['n']} | {row['speaker']} | {utterance} |")
    return "\n".join(lines)


def write_blind_copy(out_dir: Path, participant: str, rows: list[dict]) -> None:
    content = (
        f"# {participant} (blinded)\n\n"
        "Coding columns removed. Speakers I (interviewer), O and O2 "
        "(observers) are kept deliberately: without the interviewer's "
        "questions there is no way to tell 'never asked about this' apart "
        "from 'asked, and the answer just wasn't coded'.\n\n"
        "## Transcript\n\n"
        f"{render_blind_table(rows)}\n"
    )
    (out_dir / f"{participant}.md").write_text(content, encoding="utf-8")


def speaker_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["speaker"]] = counts.get(row["speaker"], 0) + 1
    return counts


def row_number_range(rows: list[dict]) -> dict:
    """Return the min/max of the numeric part of each row's # cell.

    Row numbers are strings (e.g. "147a" is allowed by the format), so this
    extracts the leading integer for ordering purposes and reports the raw
    string alongside it.
    """
    numeric = []
    for row in rows:
        m = re.match(r"^(\d+)", row["n"])
        if m:
            numeric.append((int(m.group(1)), row["n"]))
    if not numeric:
        return {"min": None, "max": None}
    numeric.sort(key=lambda pair: pair[0])
    return {"min": numeric[0][1], "max": numeric[-1][1]}


# ---------------------------------------------------------------------------
# Canary insertion
# ---------------------------------------------------------------------------

def insert_canaries(rows: list[dict], canaries: list[dict], participant: str,
                     rng: random.Random) -> tuple[list[dict], list[dict]]:
    """Insert canary rows after the given real row number, then renumber.

    Returns (new_rows, answers) where answers records the NEW sequential row
    number each canary landed at, since renumbering is what makes the
    inserted row undetectable by position.
    """
    my_canaries = [c for c in canaries if c["participant"] == participant]
    if not my_canaries:
        return rows, []

    working = list(rows)
    # Insert from the highest after_row down, so earlier insertions don't
    # shift the indices of ones still to be inserted.
    my_canaries_sorted = sorted(
        my_canaries, key=lambda c: str(c["after_row"]), reverse=True
    )

    for canary in my_canaries_sorted:
        after_row = str(canary["after_row"])
        insert_at = None
        for idx, row in enumerate(working):
            if row["n"] == after_row:
                insert_at = idx + 1
                break
        if insert_at is None:
            # Row not found (bad canary spec); append at the end rather than
            # silently dropping it, so the mismatch is visible in the output.
            insert_at = len(working)

        marker = {
            "n": "__canary__",
            "speaker": canary["speaker"],
            "utterance": canary["utterance"],
            "codes": [],
            "_is_canary": True,
        }
        working.insert(insert_at, marker)

    # Renumber sequentially from 1 so the canary is undetectable by gap.
    answers = []
    renumbered = []
    for i, row in enumerate(working, start=1):
        new_row = dict(row)
        new_row["n"] = str(i)
        renumbered.append(new_row)
        if row.get("_is_canary"):
            answers.append({
                "participant": participant,
                "row": str(i),
                "utterance": row["utterance"],
            })

    return renumbered, answers


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="blind_transcripts.py",
        description=(
            "Write coding-free copies of a study's transcripts (# / Speaker "
            "/ Utterance only) so a fresh agent can read them without being "
            "anchored by existing codes. All speakers, including the "
            "interviewer and observers, are kept."
        ),
    )
    parser.add_argument("study_root", help="Path to the study repo, or any folder inside it")
    parser.add_argument("--out", required=True, help="Directory to write blind copies into")
    parser.add_argument(
        "--canary",
        help=(
            "JSON file with a list of planted utterances to validate the "
            "check itself, e.g. "
            '[{"participant": "P3", "after_row": "147", "speaker": "P", "utterance": "..."}]. '
            "Requires --out to contain 'canary' in its basename."
        ),
    )
    parser.add_argument("--seed", type=int, default=None, help="Seed for reproducible canary handling")
    args = parser.parse_args(argv)

    root = find_study_root(args.study_root)
    out_dir = Path(args.out)

    canaries = None
    if args.canary:
        if "canary" not in out_dir.name.lower():
            print(
                "Refusing to run with --canary because --out "
                f"({out_dir}) does not have 'canary' in its basename.\n"
                "This is deliberate: canary runs renumber rows, so their "
                "output must never look like a real findings run. Use "
                "an --out path like './blind-canary-test/'.",
                file=sys.stderr,
            )
            return 2
        canaries = json.loads(Path(args.canary).read_text(encoding="utf-8"))

    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    manifest = {}
    all_answers = []

    for participant, tpath in list_participants(root):
        parsed = parse_transcript(tpath)
        rows = parsed["rows"]

        if canaries:
            rows, answers = insert_canaries(rows, canaries, participant, rng)
            all_answers.extend(answers)

        write_blind_copy(out_dir, participant, rows)

        manifest[participant] = {
            "row_count": len(rows),
            "speaker_counts": speaker_counts(rows),
            "row_range": row_number_range(rows),
        }

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    if canaries:
        (out_dir / "canary_answers.json").write_text(
            json.dumps(all_answers, indent=2), encoding="utf-8"
        )
        print(
            "WARNING: this is a canary run. Row numbers in these blind "
            "copies were renumbered and DO NOT match the real transcripts. "
            "Never cite these row numbers in actual findings. Use this "
            "output only to validate that the counter-bias check works."
        )

    print(f"Wrote {len(manifest)} blind transcript(s) to {out_dir}")
    for participant, info in manifest.items():
        print(f"  {participant}: {info['row_count']} rows, speakers={info['speaker_counts']}")
    if canaries:
        print(f"Planted {len(all_answers)} canary row(s). See {out_dir / 'canary_answers.json'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
