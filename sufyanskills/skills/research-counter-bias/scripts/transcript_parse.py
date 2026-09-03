"""Shared parsing for research study repos (transcripts + checklists).

Why this exists as its own module: both research-coverage and
research-counter-bias need to read the same transcript tables and the same
checklist sources (analysis-plan.md for UT studies, research-plan.md for
standard studies). Keeping one copy per skill (kept byte-identical on
purpose) avoids a shared-package dependency while guaranteeing both skills
agree on what a "row" and a "checklist item" are. If you change parsing
behavior here, copy the file into the sibling skill's scripts/ dir too.

Standard library only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Study root / mode detection
# ---------------------------------------------------------------------------

def find_study_root(path: str | Path) -> Path:
    """Walk up from path until a directory containing participants/ is found.

    Why: callers may be handed a subdirectory (e.g. a participant folder) or
    the study root itself. Rather than requiring the caller to know which,
    we walk up so the CLI tools are forgiving about what path they're given.
    """
    p = Path(path).resolve()
    candidates = [p] + list(p.parents)
    for candidate in candidates:
        if (candidate / "participants").is_dir():
            return candidate
    raise FileNotFoundError(
        f"Could not find a study root (a directory containing participants/) "
        f"starting from {p}"
    )


def method_dir(root: Path) -> Path | None:
    """Return root/method if it exists, else root/approach, else None.

    Why: different studies use one name or the other for the same role
    (protocol + codebook + plan documents). Callers should not have to know
    which one a given study picked.
    """
    m = root / "method"
    if m.is_dir():
        return m
    a = root / "approach"
    if a.is_dir():
        return a
    return None


def detect_mode(root: Path) -> str:
    """Return "ut" or "standard".

    UT mode requires BOTH:
    - an analysis-plan.md in method/ or approach/
    - at least one transcript whose table header contains Issue, Confidence,
      and MM columns

    Why both checks: analysis-plan.md alone isn't proof the transcripts were
    actually coded in UT style (a study could keep an old plan file around),
    and the header alone isn't proof the study intends UT-style analysis.
    Requiring both matches the spec's mode-detection rule exactly.
    """
    mdir = method_dir(root)
    has_analysis_plan = bool(mdir and (mdir / "analysis-plan.md").exists())
    if not has_analysis_plan:
        return "standard"

    for _name, tpath in list_participants(root):
        try:
            lines = tpath.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        headers = _find_table_headers(lines)
        if headers is None:
            continue
        header_set = {h.strip() for h in headers}
        if {"Issue", "Confidence", "MM"}.issubset(header_set):
            return "ut"
    return "standard"


# ---------------------------------------------------------------------------
# Participant listing (natural sort)
# ---------------------------------------------------------------------------

def _natural_key(name: str):
    """Split a participant folder name into text/number chunks for sorting.

    Why: plain string sort puts P10 before P2. Participant folders also have
    non-numeric suffixes (P1A, P1-shared, P4-paired), so the key must fall
    back to plain string comparison for the non-digit remainder.
    """
    parts = re.split(r"(\d+)", name)
    return [int(part) if part.isdigit() else part for part in parts]


def list_participants(root: Path) -> list[tuple[str, Path]]:
    """Return sorted (participant_name, transcript_path) pairs.

    Only participants with an actual transcript.md are included, since a
    participant folder can exist (e.g. mid-transcription) without one yet.
    """
    participants_dir = root / "participants"
    if not participants_dir.is_dir():
        return []
    results = []
    for child in participants_dir.iterdir():
        if not child.is_dir():
            continue
        transcript = child / "transcript.md"
        if transcript.exists():
            results.append((child.name, transcript))
    results.sort(key=lambda pair: _natural_key(pair[0]))
    return results


# ---------------------------------------------------------------------------
# Generic markdown table parsing
# ---------------------------------------------------------------------------

_SEPARATOR_RE = re.compile(r"^\|?[\s:|-]+\|?$")


def _is_separator_row(line: str) -> bool:
    """A markdown table separator row is only dashes, colons, pipes, spaces.

    Why a dedicated check: separator rows in the wild have ragged spacing
    (e.g. "|---|---------|-----------|-------|------------|----|----- --|")
    and must never be mistaken for a data row.
    """
    stripped = line.strip()
    if "-" not in stripped:
        return False
    return bool(_SEPARATOR_RE.match(stripped))


def _split_table_row(line: str) -> list[str]:
    """Split one markdown table row into cell strings.

    Handles a leading/trailing pipe and does not attempt to un-escape
    anything: per the spec, pipes inside utterance text are escaped or
    simply absent, so a naive split on "|" is sufficient.
    """
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def parse_md_table(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """Parse the first markdown table found in lines.

    Returns (headers, rows) where rows are lists of cell strings (the
    separator row is skipped, and non-table lines before/after are ignored).
    Returns ([], []) if no table is found.

    This is used both for transcript tables and for the small tables in
    checklist source files (Session Phases, Participants, rq-map), so it
    deliberately does not know anything about column meaning.
    """
    headers: list[str] = []
    rows: list[list[str]] = []
    in_table = False
    header_seen = False

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if in_table:
                # Table has ended (blank line or prose after it).
                break
            continue

        if not header_seen:
            headers = _split_table_row(stripped)
            header_seen = True
            in_table = True
            continue

        if _is_separator_row(stripped):
            continue

        rows.append(_split_table_row(stripped))

    return headers, rows


def _find_table_headers(lines: list[str]) -> list[str] | None:
    """Cheap peek at just the header row of the first table in lines."""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|"):
            return _split_table_row(stripped)
    return None


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------

def parse_transcript(path: Path) -> dict:
    """Parse one transcript.md into columns + structured rows.

    Why "codes" is computed generically (every column after Utterance except
    Notes/Confidence) rather than hardcoding Issue/MM/Code 1/Code 2: the two
    known layouts (UT and standard) use different column names for the same
    role, and a future layout might add another. Treating "not Notes, not
    Confidence, comes after Utterance" as the definition of a code column
    means new layouts work without a parser change.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Only look at the table under "## Transcript" if that heading exists;
    # otherwise fall back to the first table in the file.
    transcript_idx = None
    for i, line in enumerate(lines):
        if line.strip().lower() == "## transcript":
            transcript_idx = i
            break
    table_lines = lines[transcript_idx:] if transcript_idx is not None else lines

    headers, raw_rows = parse_md_table(table_lines)

    try:
        utterance_idx = headers.index("Utterance")
    except ValueError:
        utterance_idx = 2  # best-effort fallback: # | Speaker | Utterance | ...

    n_idx = 0
    speaker_idx = 1 if len(headers) > 1 else None

    notes_idx = headers.index("Notes") if "Notes" in headers else None
    confidence_idx = headers.index("Confidence") if "Confidence" in headers else None

    code_indices = [
        i for i in range(utterance_idx + 1, len(headers))
        if i != notes_idx and i != confidence_idx
    ]

    rows = []
    for raw in raw_rows:
        def cell(idx):
            return raw[idx].strip() if idx is not None and idx < len(raw) else ""

        n = cell(n_idx)
        speaker = cell(speaker_idx)
        utterance = cell(utterance_idx)
        codes = [c for c in (cell(i) for i in code_indices) if c]

        row = {
            "n": n,
            "speaker": speaker,
            "utterance": utterance,
            "codes": codes,
        }
        if notes_idx is not None:
            row["notes"] = cell(notes_idx)
        if confidence_idx is not None:
            row["confidence"] = cell(confidence_idx)
        rows.append(row)

    return {
        "participant": path.parent.name,
        "path": path,
        "columns": headers,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Checklist loading
# ---------------------------------------------------------------------------

def _find_section(lines: list[str], heading_pattern: re.Pattern) -> list[str] | None:
    """Return the lines belonging to the first section matching a heading regex.

    A section runs from a matching "## " (or "### ") heading up to (but not
    including) the next heading of the same or higher level.
    """
    start = None
    level = None
    for i, line in enumerate(lines):
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m and heading_pattern.match(m.group(2).strip()):
            start = i
            level = len(m.group(1))
            break
    if start is None:
        return None

    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = re.match(r"^(#{2,3})\s+", lines[j])
        if m and len(m.group(1)) <= level:
            end = j
            break
    return lines[start:end]


def _load_ut_checklist(mdir: Path) -> list[dict]:
    """Read Session Phases table from analysis-plan.md into PH1..PHn items."""
    analysis_plan = mdir / "analysis-plan.md"
    lines = analysis_plan.read_text(encoding="utf-8").splitlines()

    section = _find_section(lines, re.compile(r"^Session Phases"))
    if section is None:
        return []

    headers, rows = parse_md_table(section)
    try:
        phase_idx = headers.index("Phase")
    except ValueError:
        phase_idx = 0
    try:
        track_idx = headers.index("What to track")
    except ValueError:
        track_idx = len(headers) - 1

    items = []
    for i, row in enumerate(rows, start=1):
        label = row[phase_idx].strip() if phase_idx < len(row) else ""
        detail = row[track_idx].strip() if track_idx < len(row) else ""
        if not label:
            continue
        items.append({"id": f"PH{i}", "label": label, "detail": detail})
    return items


def _extract_bold(text: str) -> str:
    """Strip a leading/trailing markdown bold marker, if present."""
    m = re.match(r"^\*\*(.+?)\*\*$", text.strip())
    return m.group(1).strip() if m else text.strip()


def _load_standard_checklist(mdir: Path) -> list[dict]:
    """Read Research Question(s) from research-plan.md into RQ1..RQn items.

    The primary question (a single bolded sentence, or the first paragraph
    of the section if not bolded) becomes RQ1. A "### Secondary Questions"
    subsection, if present, holds a numbered list that becomes RQ2..RQn.
    """
    research_plan = mdir / "research-plan.md"
    lines = research_plan.read_text(encoding="utf-8").splitlines()

    section = _find_section(
        lines, re.compile(r"^Research Questions?$", re.IGNORECASE)
    )
    if section is None:
        return []

    items = []

    # Primary question: first non-blank, non-heading line in the section.
    primary_text = None
    secondary_start = None
    for i, line in enumerate(section):
        stripped = line.strip()
        if i == 0:
            continue  # the heading itself
        if re.match(r"^###\s+Secondary Questions", stripped, re.IGNORECASE):
            secondary_start = i
            break
        if stripped and primary_text is None:
            primary_text = stripped

    if primary_text:
        items.append({
            "id": "RQ1",
            "label": _extract_bold(primary_text),
            "detail": "",
        })

    if secondary_start is not None:
        for line in section[secondary_start + 1:]:
            stripped = line.strip()
            m = re.match(r"^\d+[.)]\s+(.*)$", stripped)
            if not m:
                if stripped.startswith("-"):
                    m = re.match(r"^-\s+(.*)$", stripped)
                if not m:
                    continue
            label = m.group(1).strip()
            if label:
                items.append({
                    "id": f"RQ{len(items) + 1}",
                    "label": _extract_bold(label),
                    "detail": "",
                })

    return items


def max_row_number(rows: list[dict]) -> int | None:
    """Return the highest leading integer among a transcript's row numbers.

    Row numbers are kept as strings elsewhere because a value like "147a"
    can appear, but phase-map validation needs a plain integer to compare
    against, so this extracts just the leading digits.
    """
    best = None
    for row in rows:
        m = re.match(r"^(\d+)", row["n"])
        if m:
            val = int(m.group(1))
            if best is None or val > best:
                best = val
    return best


# ---------------------------------------------------------------------------
# UT phase map (phase-map.md)
# ---------------------------------------------------------------------------

def _parse_phase_cell(raw: str) -> tuple[str, object]:
    """Classify one phase-map cell.

    Returns (kind, value):
    - ("dash", None) for "-": the phase did not happen.
    - ("range", (start, end)) for a single "N-M": an explicit boundary, used
      when a session ran phases out of the declared order and a bare start
      (which relies on "until the next phase" to find its end) cannot
      express that.
    - ("ranges", [(start, end), ...]) for a comma-separated list of "N-M"
      ranges: a phase can be non-contiguous (a session ran debrief, then
      handover, then went back to debrief), so one range is not always
      enough to hold it.
    - ("bare", start) for a plain "N": kept for backward compatibility with
      maps written before ranges existed, and still the simplest form when
      a study did run phases in order.
    - ("invalid", raw) for anything else, including a comma-separated list
      that mixes bare numbers with ranges (a bare number's end depends on
      "the next phase", which is not a coherent idea inside a multi-range
      cell, so every item in a multi-item cell must be an explicit range).
    """
    if raw == "-":
        return ("dash", None)
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    if not tokens:
        return ("invalid", raw)

    parsed_tokens: list[tuple[str, object]] = []
    for token in tokens:
        m_range = re.match(r"^(\d+)-(\d+)$", token)
        if m_range:
            parsed_tokens.append(("range", (int(m_range.group(1)), int(m_range.group(2)))))
        elif token.isdigit():
            parsed_tokens.append(("bare", int(token)))
        else:
            return ("invalid", raw)

    if len(parsed_tokens) == 1:
        return parsed_tokens[0]
    if all(kind == "range" for kind, _value in parsed_tokens):
        return ("ranges", [value for _kind, value in parsed_tokens])
    return ("invalid", raw)


def _ranges_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def load_phase_map(root: Path, checklist: list[dict],
                    last_rows: dict[str, int],
                    map_path: Path | None = None) -> dict[str, dict[str, list[tuple[int, int]] | None]]:
    """Parse a phase-map.md into {participant: {phase_id: (start, end) or None}}.

    Defaults to <method_dir>/phase-map.md; pass map_path to point at a
    different file (e.g. a disposable test fixture in a temp dir, so real
    study repos and their disposable copies never need a phase-map.md
    written into them just to exercise this function).

    Each cell holds one of three things:
    - "-": that phase did not happen for that participant. Kept distinct
      from a phase that happened but produced no coded rows, because the
      two mean different things for a coverage report (one is "we never
      got there", the other is "we got there and found nothing to code").
    - "N-M": an explicit row range. Needed because a session can run its
      phases out of the declared order (a handover task before the debrief
      ratings, say), and a table that only records where a phase starts has
      no way to say where it ends except "the next phase's start", which
      breaks the moment phases are not in order.
    - "N": a bare start. Its end is "the next bare-start phase's start
      minus one", which only means something if bare-start phases are in
      increasing order, so that ordering is still enforced for them. This
      form exists so maps written before ranges did stay valid.

    A participant may mix bare starts and explicit ranges. The bare ones
    are resolved into ranges using only each other's order (ranges do not
    participate in that ordering, since they are exactly the escape hatch
    for phases that are out of order). The result is then checked for
    overlaps against every other range for that participant, bare-derived
    or explicit, since two phases claiming the same row would double count
    it.

    Why validation is strict rather than tolerant: a coverage report built
    on a bad phase map (an out-of-order start treated as in-order, a range
    past the end of the transcript, two phases silently sharing rows) would
    look exactly like a real report while being wrong in a way nobody would
    notice without re-deriving the boundaries by hand. All of that is
    checked here, once, so the coverage computation itself never has to
    guess.

    Raises FileNotFoundError if phase-map.md itself is missing, and
    ValueError (with every problem found, not just the first) if it exists
    but fails validation.
    """
    mdir = method_dir(root)
    expected_path = map_path if map_path is not None else (mdir or root) / "phase-map.md"
    if not expected_path.exists():
        raise FileNotFoundError(str(expected_path))

    lines = expected_path.read_text(encoding="utf-8").splitlines()
    headers, rows = parse_md_table(lines)

    if not headers or headers[0] != "Participant":
        raise ValueError(
            f"{expected_path}: expected the first column to be 'Participant', "
            f"found headers {headers}"
        )

    phase_ids = [item["id"] for item in checklist]
    missing_cols = [pid for pid in phase_ids if pid not in headers]
    if missing_cols:
        raise ValueError(
            f"{expected_path}: missing column(s) for phase(s) {missing_cols} "
            f"(checklist has {phase_ids}, table has {headers})"
        )

    errors: list[str] = []
    result: dict[str, dict[str, list[tuple[int, int]] | None]] = {}
    seen_participants: set[str] = set()

    for raw_row in rows:
        cell_map = dict(zip(headers, raw_row))
        participant = cell_map.get("Participant", "").strip()
        if not participant:
            continue
        seen_participants.add(participant)

        if participant not in last_rows:
            errors.append(
                f"{expected_path}: participant {participant!r} has a row in "
                f"the phase map but no transcript.md was found for them"
            )
            continue

        last_row = last_rows[participant]
        parsed: dict[str, tuple[str, object]] = {}
        for pid in phase_ids:
            raw = cell_map.get(pid, "").strip()
            if raw == "":
                errors.append(
                    f"{expected_path}: {participant} has no value for {pid} "
                    f"(use a row number, a 'start-end' range, or '-' if that "
                    f"phase did not happen)"
                )
                continue
            kind, value = _parse_phase_cell(raw)
            if kind == "invalid":
                errors.append(
                    f"{expected_path}: {participant} {pid} has a value that is "
                    f"neither a row number, a 'start-end' range, a comma-separated list of ranges, nor '-': {raw!r}"
                )
                continue
            parsed[pid] = (kind, value)

        # Validate explicit ranges on their own terms: end not before start,
        # end within the transcript. A "ranges" cell is just several of
        # these, so both kinds go through the same per-range checks.
        for pid, (kind, value) in parsed.items():
            if kind == "range":
                range_list = [value]
            elif kind == "ranges":
                range_list = value
            else:
                continue
            for start, end in range_list:
                if end < start:
                    errors.append(
                        f"{expected_path}: {participant} {pid} range {start}-{end} "
                        f"ends before it starts"
                    )
                if end > last_row:
                    errors.append(
                        f"{expected_path}: {participant} {pid} range {start}-{end} "
                        f"ends beyond that participant's last transcript row ({last_row})"
                    )

        # Validate bare starts against the transcript, and against each
        # other in phase-id order (their only source of an end row).
        bare_pids = [pid for pid in phase_ids if parsed.get(pid, (None,))[0] == "bare"]
        prev_val = None
        prev_pid = None
        for pid in bare_pids:
            val = parsed[pid][1]
            if val > last_row:
                errors.append(
                    f"{expected_path}: {participant} {pid} start row {val} is "
                    f"beyond that participant's last transcript row ({last_row})"
                )
            if prev_val is not None and val <= prev_val:
                errors.append(
                    f"{expected_path}: {participant} phase starts are not "
                    f"increasing ({prev_pid}={prev_val}, {pid}={val}); use an "
                    f"explicit 'start-end' range for phases that run out of order"
                )
            prev_val = val
            prev_pid = pid

        if errors:
            # Downstream range math assumes validated inputs; skip building
            # ranges for a participant that already failed validation.
            continue

        # Resolve bare starts into ranges using only bare-to-bare order.
        # Every phase ends up holding a LIST of (start, end) pairs (or
        # None), even a bare or single-range phase with exactly one, so
        # downstream code never has to branch on how a phase's boundary
        # was written.
        ranges: dict[str, list[tuple[int, int]] | None] = {}
        for pid, (kind, value) in parsed.items():
            if kind == "dash":
                ranges[pid] = None
            elif kind == "range":
                ranges[pid] = [value]
            elif kind == "ranges":
                ranges[pid] = value
        for idx, pid in enumerate(bare_pids):
            start = parsed[pid][1]
            end = parsed[bare_pids[idx + 1]][1] - 1 if idx + 1 < len(bare_pids) else last_row
            ranges[pid] = [(start, end)]
        for pid in phase_ids:
            ranges.setdefault(pid, None)

        # Overlap check across every range of every phase for this
        # participant, bare-derived or explicit, single or one of several
        # in a "ranges" cell: a row can only ever belong to one phase, so
        # any two ranges sharing a row (even two ranges of the SAME phase)
        # are an error.
        present = [
            (pid, rng)
            for pid, range_list in ranges.items() if range_list is not None
            for rng in range_list
        ]
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                pid_a, rng_a = present[i]
                pid_b, rng_b = present[j]
                if _ranges_overlap(rng_a, rng_b):
                    errors.append(
                        f"{expected_path}: {participant} {pid_a} ({rng_a[0]}-{rng_a[1]}) "
                        f"overlaps {pid_b} ({rng_b[0]}-{rng_b[1]})"
                    )

        result[participant] = ranges

    for participant in last_rows:
        if participant not in seen_participants:
            errors.append(
                f"{expected_path}: transcript for {participant!r} has no "
                f"row in the phase map"
            )

    if errors:
        raise ValueError(
            "Phase map validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    return result


# ---------------------------------------------------------------------------
# Standard-mode codebook categories (codebook.md)
# ---------------------------------------------------------------------------

def load_codebook_categories(root: Path) -> dict[str, list[str]]:
    """Read codebook.md's "###" category headings into {category: [codes]}.

    Why this lives here rather than in coverage.py: it reads the same kind
    of document (a plan/reference file under method_dir) with the same
    section + table parsing helpers as the checklist loaders above, so it
    belongs next to them rather than duplicating _find_section elsewhere.

    Each category is a "###" heading; the codes belonging to it are read
    from the "Code" column of the first table under that heading. A
    codebook with no "###" headings returns an empty dict (nothing to
    resolve categories against, callers fall back to explicit-code-only
    matching).
    """
    mdir = method_dir(root)
    if mdir is None:
        return {}
    codebook_path = mdir / "codebook.md"
    if not codebook_path.exists():
        return {}

    lines = codebook_path.read_text(encoding="utf-8").splitlines()

    categories: dict[str, list[str]] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    def flush():
        if current_name is None:
            return
        headers, rows = parse_md_table(current_lines)
        if "Code" not in headers:
            categories[current_name] = []
            return
        code_idx = headers.index("Code")
        codes = [row[code_idx].strip() for row in rows if code_idx < len(row) and row[code_idx].strip()]
        categories[current_name] = codes

    for line in lines:
        m = re.match(r"^###\s+(.*)$", line.strip())
        if m:
            flush()
            current_name = m.group(1).strip()
            current_lines = []
            continue
        if re.match(r"^##\s+", line.strip()):
            # A "##" heading (not "###") ends the current category section.
            flush()
            current_name = None
            current_lines = []
            continue
        if current_name is not None:
            current_lines.append(line)

    flush()
    return categories


def load_checklist(root: Path) -> list[dict]:
    """Return the study's declared checklist as a list of {id, label, detail}.

    Why IDs are invented here rather than read from the source files: the
    source documents (analysis-plan.md's phase table, research-plan.md's
    question list) carry no ID scheme of their own. Assigning PH1..PHn /
    RQ1..RQn deterministically (in document order) gives coverage.py stable
    identifiers to key off, as long as the source document isn't reordered.
    """
    mdir = method_dir(root)
    if mdir is None:
        return []
    mode = detect_mode(root)
    if mode == "ut":
        return _load_ut_checklist(mdir)
    return _load_standard_checklist(mdir)


# ---------------------------------------------------------------------------
# CLI (debugging entry point)
# ---------------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: python3 transcript_parse.py <study-root>", file=sys.stderr)
        return 2

    root = find_study_root(argv[0])
    mode = detect_mode(root)
    participants = list_participants(root)
    checklist = load_checklist(root)

    print(f"Study root: {root}")
    print(f"Mode: {mode}")
    print(f"Method dir: {method_dir(root)}")
    print(f"Participants ({len(participants)}): {[name for name, _ in participants]}")
    print()

    for name, tpath in participants:
        parsed = parse_transcript(tpath)
        print(f"{name}: {len(parsed['rows'])} rows, columns={parsed['columns']}")

    print()
    print(f"Checklist ({len(checklist)} items):")
    for item in checklist:
        print(f"  {item['id']}: {item['label']!r} -- {item['detail']!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
