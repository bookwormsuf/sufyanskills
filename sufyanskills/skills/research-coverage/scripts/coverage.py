"""Check whether a study's declared checklist (research questions or UT
session phases) actually has coded evidence behind it.

Why this exists: a codebook can grow organically during coding, and it is
easy to end up with codes that answer no declared question, or declared
questions that quietly never got any evidence. This script does a plain set
difference between "what the study says it wants to learn" and "what got
coded", so a human (or a CI-style check) can see the gap without re-reading
every transcript.

The two modes use genuinely different mechanics, not just different labels:

- Standard mode maps CODES (thematic tags) to research questions, because a
  code answering a question is a real, checkable relationship.
- UT mode maps PHASES (temporal segments of the session) to rows by ROW
  NUMBER RANGE, not by code. A UT codebook's codes (especially MM- mental
  model codes) recur across every phase of a session, so no code-to-phase
  table could ever be correct. What differs by phase is *when* a row was
  said, not *what* it was coded as, so coverage in UT mode is a range
  membership check against a human-drawn phase boundary map.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from transcript_parse import (
    detect_mode,
    find_study_root,
    list_participants,
    load_checklist,
    load_codebook_categories,
    load_phase_map,
    max_row_number,
    method_dir,
    parse_md_table,
    parse_transcript,
)


# ---------------------------------------------------------------------------
# Data loading (shared by both modes)
# ---------------------------------------------------------------------------

def load_all_rows(root: Path) -> list[tuple[str, dict]]:
    """Read every transcript in the study into a flat (participant, row) list."""
    all_rows = []
    for name, tpath in list_participants(root):
        parsed = parse_transcript(tpath)
        for row in parsed["rows"]:
            all_rows.append((name, row))
    return all_rows


def load_last_rows(root: Path) -> dict[str, int]:
    """Return {participant: highest row number in their transcript}."""
    last_rows = {}
    for name, tpath in list_participants(root):
        parsed = parse_transcript(tpath)
        last = max_row_number(parsed["rows"])
        if last is not None:
            last_rows[name] = last
    return last_rows


def row_number(row: dict) -> int | None:
    """Extract the leading integer from a row's # cell, or None if absent."""
    m = re.match(r"^(\d+)", row["n"])
    return int(m.group(1)) if m else None


def distinct_row_keys(pairs: list[tuple[str, dict]]) -> set[tuple[str, str]]:
    """Return the set of distinct (participant, row_number_string) keys.

    This is the single definition of "how many distinct rows" used
    everywhere a row count gets reported. Standard mode has two code
    columns, so a row coded on both Code 1 and Code 2 can appear twice in
    a naive list built by iterating per-code usage; routing every row
    count through this function is what keeps "how many rows" from
    disagreeing with itself between the coverage table, the completeness
    table, and the selftest output.
    """
    return {(p, r["n"]) for p, r in pairs}


def count_coded_rows(all_rows: list[tuple[str, dict]]) -> int:
    """Count distinct rows that carry at least one code.

    The report's one authoritative "total coded rows" figure. Every other
    row count in the report (a checklist item's rows, a mutation's
    suppressed-row count) is a subset of this and must never exceed it;
    see the assertions in compute_coverage_standard, compute_coverage_ut,
    and the mutation suite.
    """
    return len(distinct_row_keys([(p, r) for p, r in all_rows if r["codes"]]))


# ---------------------------------------------------------------------------
# Coding completeness (shared by both modes)
# ---------------------------------------------------------------------------

def compute_coding_completeness(all_rows: list[tuple[str, dict]]) -> list[dict]:
    """Count data rows and coded rows per participant.

    Why this exists: a coverage report is a comparison between a checklist
    and coded evidence, but it says nothing about whether every participant
    was actually coded. A participant with zero coded rows contributes
    nothing either way, a phase or question can look fully covered purely
    on the strength of the other participants, and a plain gap-free report
    would look identical to a report where a third of the study was never
    touched. This function makes that visible unconditionally, not just
    when something looks wrong.

    Participant order follows the order rows were loaded in (i.e. the same
    natural participant order as list_participants), since all_rows is
    built one participant's rows at a time.
    """
    by_participant: dict[str, list[tuple[str, dict]]] = {}
    for participant, row in all_rows:
        by_participant.setdefault(participant, []).append((participant, row))

    result = []
    for participant, pairs in by_participant.items():
        data_rows = len(pairs)
        coded_rows = count_coded_rows(pairs)
        pct = round((coded_rows / data_rows * 100), 1) if data_rows else 0.0
        result.append({
            "participant": participant,
            "data_rows": data_rows,
            "coded_rows": coded_rows,
            "pct_coded": pct,
        })
    return result


def uncoded_participants(completeness: list[dict]) -> list[str]:
    """Participants with zero coded rows: the signal that makes a report untrustworthy."""
    return [c["participant"] for c in completeness if c["coded_rows"] == 0]


def render_coding_completeness(completeness: list[dict]) -> str:
    lines = ["## Coding completeness"]
    lines.append("| Participant | Data rows | Coded rows | Percent coded |")
    lines.append("|--------------|-----------|------------|----------------|")
    for c in completeness:
        lines.append(
            f"| {c['participant']} | {c['data_rows']} | {c['coded_rows']} | {c['pct_coded']}% |"
        )
    return "\n".join(lines)


def exit_code_and_reason(items: list[dict], uncoded: list[str]) -> tuple[int, str]:
    """Decide the final exit code and its printed reason.

    Precedence (highest first): 3 (no map, handled earlier and never reaches
    here), 4 (incomplete coding), 1 (gaps), 0 (clean). Incomplete coding
    outranks a plain gap because a gap on a partly-coded study cannot be
    trusted to mean "no evidence exists" instead of "nobody coded it yet".
    """
    has_gap = any(item["status"] == "GAP" for item in items)
    if uncoded:
        return 4, (
            f"Exit 4: zero coded rows for {', '.join(uncoded)}. "
            "Coverage result is not trustworthy until they are coded."
        )
    if has_gap:
        gap_count = sum(1 for item in items if item["status"] == "GAP")
        return 1, f"Exit 1: {gap_count} checklist item(s) have no coded evidence."
    return 0, "Exit 0: every checklist item has evidence and every participant is coded."


def checklist_size_note(checklist: list[dict]) -> str | None:
    """Warn when a checklist is too small for coverage to say much.

    With fewer than 2 items, coverage can only ever come back as "all
    covered" or "nothing covered": there is no item-to-item contrast to
    learn from, so the report is technically correct but carries almost no
    information. Callers should print this in every run, not only inside
    --selftest, since a one-item study's normal run is exactly where this
    matters most.
    """
    if len(checklist) < 2:
        return (
            f"NOTE: this study's checklist has only {len(checklist)} item(s). "
            "With fewer than 2 items, coverage can only report 'all covered' "
            "or 'nothing covered', so this check carries little information "
            "beyond that binary."
        )
    return None


# ---------------------------------------------------------------------------
# UT mode: phase ranges + coverage
# ---------------------------------------------------------------------------

def compute_coverage_ut(checklist: list[dict], phase_map: dict[str, dict[str, list[tuple[int, int]] | None]],
                         last_rows: dict[str, int],
                         all_rows: list[tuple[str, dict]]) -> dict:
    """Compute UT-mode coverage: coded rows per phase, bucketed by row range.

    phase_map holds already-resolved, already-validated ranges (a list of
    (start, end) pairs per phase per participant, or None if that phase did
    not happen), produced by transcript_parse.load_phase_map. This function
    does no boundary resolution of its own: a phase can legitimately be
    non-contiguous (a session ran debrief, then handover, then went back to
    debrief), so "the range" for a phase is really "the union of its
    ranges", and that union is exactly what load_phase_map already built.

    Pure function: takes the already-parsed phase map and row list, touches
    no filesystem, so --selftest can call it again with rows filtered out,
    or with the phase map itself perturbed, and nothing else needs to change.
    """
    phase_ids = [item["id"] for item in checklist]

    # phase_id -> participant -> count of coded rows
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for participant, row in all_rows:
        if not row["codes"]:
            continue
        n = row_number(row)
        if n is None:
            continue
        participant_ranges = phase_map.get(participant)
        if not participant_ranges:
            continue
        for pid, ranges in participant_ranges.items():
            if ranges is None:
                continue
            if any(start <= n <= end for start, end in ranges):
                counts[pid][participant] += 1
                break  # a row belongs to at most one phase; ranges never overlap

    total_coded = count_coded_rows(all_rows)

    items = []
    for entry in checklist:
        pid = entry["id"]
        per_participant = dict(counts.get(pid, {}))
        participants_covered = sorted(per_participant)
        participants_not_run = sorted(
            p for p, participant_ranges in phase_map.items()
            if participant_ranges.get(pid) is None
        )
        total_rows = sum(per_participant.values())
        assert total_rows <= total_coded, (
            f"{pid}: rows_count {total_rows} exceeds total coded rows {total_coded}, "
            "which should be impossible since a row can belong to at most one phase"
        )
        items.append({
            "id": pid,
            "label": entry["label"],
            "rows": total_rows,
            "participants_covered": participants_covered,
            "rows_by_participant": per_participant,
            "participants_not_run": participants_not_run,
            "status": "covered" if total_rows > 0 else "GAP",
        })

    return {"items": items}


def render_markdown_ut(result: dict, uncoded: list[str], unassigned: dict[str, int]) -> str:
    lines = []
    lines.append("| ID | Phase | Rows | Participants covered | Not run | Status |")
    lines.append("|----|-------|------|-----------------------|---------|--------|")
    for item in result["items"]:
        covered = ", ".join(item["participants_covered"]) if item["participants_covered"] else "-"
        not_run = ", ".join(item["participants_not_run"]) if item["participants_not_run"] else "-"
        lines.append(
            f"| {item['id']} | {item['label']} | {item['rows']} | {covered} | "
            f"{not_run} | {item['status']} |"
        )

    lines.append("")
    lines.append("## Per-participant breakdown")
    lines.append("A phase can show as covered while only one participant carried it. This spells that out.")
    for item in result["items"]:
        if not item["rows_by_participant"]:
            continue
        breakdown = ", ".join(f"{p}={n}" for p, n in sorted(item["rows_by_participant"].items()))
        lines.append(f"- {item['id']} ({item['label']}): {breakdown}")

    lines.append("")
    lines.append("## Gaps")
    if uncoded:
        lines.append(
            f"WARNING: zero coded rows for {', '.join(uncoded)}. Any gap listed "
            "(or NOT listed) below may reflect unfinished coding rather than a real "
            "absence of evidence. Treat this report as incomplete, not clean."
        )
    gaps = [i for i in result["items"] if i["status"] == "GAP"]
    if gaps:
        for item in gaps:
            lines.append(f"- {item['id']}: {item['label']} (no coded rows in any participant's range for this phase)")
    else:
        lines.append("None. Every phase has at least one coded row from some participant.")

    lines.append("")
    lines.append("## Thin coverage")
    lines.append("Phases backed by only one participant. A single voice may be carrying this finding.")
    thin = [i for i in result["items"] if i["status"] == "covered" and len(i["participants_covered"]) == 1]
    if thin:
        for item in thin:
            lines.append(f"- {item['id']}: {item['label']} (only {item['participants_covered'][0]})")
    else:
        lines.append("None.")

    lines.append("")
    lines.append("## Not run")
    lines.append("Phase map cells marked '-': this phase did not happen for that participant. "
                  "Kept separate from a GAP, which means the phase happened but produced no coded rows.")
    any_not_run = False
    for item in result["items"]:
        if item["participants_not_run"]:
            any_not_run = True
            lines.append(f"- {item['id']}: {item['label']} not run for {', '.join(item['participants_not_run'])}")
    if not any_not_run:
        lines.append("None. Every phase was run for every participant.")

    lines.append("")
    lines.append("## Unassigned rows")
    lines.append("Rows that fall in no phase range at all. Not an error: scenario setup "
                  "and small talk legitimately sit between phases. A large count is worth a "
                  "look, since a boundary typo can orphan rows the same way.")
    for participant in sorted(unassigned):
        lines.append(f"- {participant}: {unassigned[participant]} unassigned row(s)")

    return "\n".join(lines)


def compute_unassigned_rows(phase_map: dict[str, dict[str, list[tuple[int, int]] | None]],
                             last_rows: dict[str, int]) -> dict[str, int]:
    """Count, per participant, how many transcript rows fall in no phase range.

    Not an error: scenario setup, small talk, and other in-between moments
    legitimately sit outside any declared phase. But a boundary typo can
    orphan a large block of rows the same way a real gap would, so the
    count is surfaced unconditionally rather than silently absorbed.
    """
    unassigned = {}
    for participant, last_row in last_rows.items():
        covered_rows: set[int] = set()
        for ranges in phase_map.get(participant, {}).values():
            if ranges is None:
                continue
            for start, end in ranges:
                covered_rows.update(range(start, end + 1))
        unassigned[participant] = last_row - len(covered_rows & set(range(1, last_row + 1)))
    return unassigned


# ---------------------------------------------------------------------------
# Standard mode: rq-map.md (codes and/or categories) + coverage
# ---------------------------------------------------------------------------

def load_map(map_path: Path) -> dict[str, list[str]]:
    """Parse rq-map.md into {code_or_category: [checklist_id, ...]}.

    An entry mapped to "-" answers no declared question and is stored as an
    empty list, which is meaningfully different from "not in the map at
    all" (that's an unmapped code, handled separately). The Code column may
    hold either an individual code or a codebook category name; which one
    it is gets resolved against the codebook by resolve_standard_map.
    """
    lines = map_path.read_text(encoding="utf-8").splitlines()
    headers, rows = parse_md_table(lines)
    try:
        code_idx = headers.index("Code")
        answers_idx = headers.index("Answers")
    except ValueError as exc:
        raise ValueError(
            f"{map_path} does not look like a Code/Answers table "
            f"(found headers: {headers})"
        ) from exc

    mapping: dict[str, list[str]] = {}
    for row in rows:
        if len(row) <= max(code_idx, answers_idx):
            continue
        key = row[code_idx].strip()
        answers_raw = row[answers_idx].strip()
        if not key:
            continue
        if answers_raw == "-":
            mapping[key] = []
        else:
            mapping[key] = [a.strip() for a in answers_raw.split(",") if a.strip()]
    return mapping


def resolve_standard_map(map_entries: dict[str, list[str]], categories: dict[str, list[str]]):
    """Split rq-map.md entries into category rules and explicit code rules.

    An entry's key must be either a known codebook category name or a known
    codebook code. Anything else is very likely a typo (a category name
    that doesn't exist), and typos here fail silently unless we check: a
    mistyped category maps nothing, and nothing downstream would notice.

    Returns (category_rules, explicit_rules, errors). errors is a list of
    strings for keys that matched neither; callers should treat any
    non-empty errors list as fatal.
    """
    category_names = set(categories)
    all_known_codes = {code for codes in categories.values() for code in codes}

    category_rules: dict[str, list[str]] = {}
    explicit_rules: dict[str, list[str]] = {}
    errors: list[str] = []

    for key, ids in map_entries.items():
        if key in category_names:
            category_rules[key] = ids
        elif key in all_known_codes:
            explicit_rules[key] = ids
        else:
            errors.append(
                f"'{key}' matches neither a codebook category nor a known code"
            )

    return category_rules, explicit_rules, errors


def build_code_to_category(categories: dict[str, list[str]]) -> dict[str, str]:
    mapping = {}
    for category, codes in categories.items():
        for code in codes:
            mapping[code] = category
    return mapping


def resolve_code(code: str, category_rules: dict, explicit_rules: dict,
                  code_to_category: dict) -> tuple[list[str] | None, str | None]:
    """Resolve one used code to (checklist_ids, rule_name).

    An explicit per-code entry always wins over its category, since a
    specific override is more informative than the general case. Returns
    (None, None) if nothing in the map matches this code at all.
    """
    if code in explicit_rules:
        return explicit_rules[code], "explicit"
    category = code_to_category.get(code)
    if category is not None and category in category_rules:
        return category_rules[category], "category"
    return None, None


def compute_coverage_standard(checklist: list[dict], category_rules: dict, explicit_rules: dict,
                               categories: dict, all_rows: list[tuple[str, dict]]) -> dict:
    """Compute standard-mode coverage with category-then-explicit resolution.

    Pure function over already-parsed inputs, so --selftest can re-run it
    on a filtered row list with no file access and no mocking.
    """
    code_to_category = build_code_to_category(categories)

    # code -> list of (participant, row) uses
    code_uses: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for participant, row in all_rows:
        for code in row["codes"]:
            code_uses[code].append((participant, row))

    # checklist id -> list of (code, rule) that resolve to it
    id_to_codes: dict[str, list[tuple[str, str]]] = defaultdict(list)
    resolution_log = []  # (code, rule, ids) for every used code, for the report
    unmapped_codes = []

    for code in sorted(code_uses):
        ids, rule = resolve_code(code, category_rules, explicit_rules, code_to_category)
        if rule is None:
            unmapped_codes.append(code)
            continue
        resolution_log.append((code, rule, ids))
        for cid in ids:
            id_to_codes[cid].append((code, rule))

    total_coded = count_coded_rows(all_rows)

    items = []
    for entry in checklist:
        cid = entry["id"]
        contributing = id_to_codes.get(cid, [])
        codes_for_id = [code for code, _rule in contributing]
        uses = []
        for code, _rule in contributing:
            uses.extend(code_uses.get(code, []))
        # "uses" holds one entry per (code, row) application, so a row coded
        # on two codes that both map to this item appears twice here. Rows
        # is the distinct-row count; code_applications is that raw tally,
        # kept as a separate labeled figure rather than replacing rows,
        # since "how many rows say this" and "how many code applications
        # exist" are different questions.
        row_keys = distinct_row_keys(uses)
        participants = sorted({p for p, _key in row_keys})
        rows_count = len(row_keys)
        assert rows_count <= total_coded, (
            f"{cid}: rows_count {rows_count} exceeds total coded rows {total_coded}, "
            "which should be impossible since every counted row is coded by definition"
        )
        items.append({
            "id": cid,
            "label": entry["label"],
            "mapped_codes": sorted(set(codes_for_id)),
            "rows": rows_count,
            "code_applications": len(uses),
            "participants": participants,
            "status": "covered" if rows_count > 0 else "GAP",
        })

    # Dead entries: a category rule is dead if none of ITS codebook codes
    # were used anywhere; an explicit rule is dead if that exact code was
    # never used. "-" entries (ids == []) count too, since they can still
    # be dead relative to actual usage.
    dead_entries = []
    for category, ids in category_rules.items():
        codes_in_category = categories.get(category, [])
        used = any(code_uses.get(code) for code in codes_in_category)
        if not used:
            dead_entries.append(f"category:{category}")
    for code, ids in explicit_rules.items():
        if not code_uses.get(code):
            dead_entries.append(f"code:{code}")

    return {
        "items": items,
        "dead_entries": sorted(dead_entries),
        "unmapped_codes": sorted(unmapped_codes),
        "resolution_log": resolution_log,
    }


def render_markdown_standard(result: dict, uncoded: list[str]) -> str:
    lines = []
    lines.append(
        "| ID | Checklist item | Mapped codes | Rows | Code applications | Participants | Status |"
    )
    lines.append("|----|----------------|--------------|------|--------------------|---------------|--------|")
    for item in result["items"]:
        codes = ", ".join(item["mapped_codes"]) if item["mapped_codes"] else "(none)"
        participants = ", ".join(item["participants"]) if item["participants"] else "-"
        lines.append(
            f"| {item['id']} | {item['label']} | {codes} | {item['rows']} | "
            f"{item['code_applications']} | {participants} | {item['status']} |"
        )
    lines.append("")
    lines.append("Rows counts distinct transcript rows. Code applications counts each mapped "
                  "code application separately, so a row coded on two mapped codes (Code 1 and "
                  "Code 2 both mapping here) contributes 1 to Rows and 2 to Code applications.")

    lines.append("")
    lines.append("## Mapping resolution")
    lines.append("Which rule matched each used code, so a surprising result is traceable.")
    if result["resolution_log"]:
        for code, rule, ids in result["resolution_log"]:
            target = ", ".join(ids) if ids else "(answers nothing declared)"
            lines.append(f"- {code}: matched by {rule}, answers {target}")
    else:
        lines.append("No used code matched any map entry.")

    lines.append("")
    lines.append("## Gaps")
    if uncoded:
        lines.append(
            f"WARNING: zero coded rows for {', '.join(uncoded)}. Any gap listed "
            "(or NOT listed) below may reflect unfinished coding rather than a real "
            "absence of evidence. Treat this report as incomplete, not clean."
        )
    gaps = [i for i in result["items"] if i["status"] == "GAP"]
    if gaps:
        for item in gaps:
            lines.append(f"- {item['id']}: {item['label']} (no coded rows)")
    else:
        lines.append("None. Every checklist item has at least one coded row.")

    lines.append("")
    lines.append("## Thin coverage")
    lines.append("Items backed by only one participant. A single voice may be carrying this finding.")
    thin = [i for i in result["items"] if i["status"] == "covered" and len(i["participants"]) == 1]
    if thin:
        for item in thin:
            lines.append(f"- {item['id']}: {item['label']} (only {item['participants'][0]})")
    else:
        lines.append("None.")

    lines.append("")
    lines.append("## Dead codes")
    lines.append("Map entries (category or explicit code) with zero uses in the transcripts.")
    if result["dead_entries"]:
        for entry in result["dead_entries"]:
            lines.append(f"- {entry}")
    else:
        lines.append("None.")

    lines.append("")
    lines.append("## Unmapped codes")
    lines.append("Codes used in transcripts but matched by neither an explicit entry nor their "
                  "category. Each needs a decision: add it to the map, or confirm it is a "
                  "finding outside the declared plan.")
    if result["unmapped_codes"]:
        for code in result["unmapped_codes"]:
            lines.append(f"- {code}")
    else:
        lines.append("None.")

    return "\n".join(lines)


def find_code_for_id(target_id: str, category_rules: dict, explicit_rules: dict,
                      categories: dict) -> str | None:
    """Find any code that resolves to target_id, for injecting synthetic evidence."""
    for code, ids in explicit_rules.items():
        if target_id in ids:
            return code
    for category, ids in category_rules.items():
        if target_id in ids and categories.get(category):
            return categories[category][0]
    return None


def find_any_mappable_code_and_id(category_rules: dict, explicit_rules: dict,
                                   categories: dict) -> tuple[str, str] | tuple[None, None]:
    """Find a (code, checklist_id) pair to inject, for the uncoded-participant branch of mutation 3.

    Returning the target id (not just the code) matters: the mutation's
    caught/missed signal must be read back through compute(), the same
    pluggable function the negative control swaps for a stub, so a fake
    backend that ignores its inputs cannot pass this mutation just because
    something else in the script (coding completeness bookkeeping) still
    noticed the injected row.
    """
    for code, ids in explicit_rules.items():
        if ids:
            return code, ids[0]
    for category, ids in category_rules.items():
        if ids and categories.get(category):
            return categories[category][0], ids[0]
    return None, None


# ---------------------------------------------------------------------------
# Mutation-based selftest
#
# Why this replaced a single suppress-and-check selftest: that older
# version only ever proved the computation responds to ONE kind of change.
# A run against a deliberately broken phase map still printed clean PASS
# lines, because nothing in that selftest exercised validation, injection,
# or the paths the real data never happens to hit (like thin coverage).
# This suite runs a fixed menu of mutations, each with a specific expected
# direction of change, and proves ITSELF trustworthy by running the same
# menu against a stub that ignores its inputs: if the stub "passes" any
# mutation, the suite is broken and its result on the real backend is void.
# ---------------------------------------------------------------------------

def _mutation(name: str, expectation: str, status: str, detail: str = "") -> dict:
    return {"name": name, "expectation": expectation, "status": status, "detail": detail}


def render_mutation_table(rows: list[dict]) -> str:
    lines = ["| Mutation | Expectation | Result |", "|----------|-------------|--------|"]
    for r in rows:
        lines.append(f"| {r['name']} | {r['expectation']} | {r['status']} |")
    details = [r for r in rows if r["detail"]]
    if details:
        lines.append("")
        lines.append("Details:")
        for r in details:
            lines.append(f"- {r['name']}: {r['detail']}")
    return "\n".join(lines)


def _stub_compute(rows, checklist, ctx) -> list[dict]:
    """A deliberately broken backend: ignores every input, reports all clean.

    This exists only to prove the mutation suite is capable of failing.
    Every mutation that mutates rows or ctx should come back MISSED against
    this stub, since its output never depends on what it is given.
    """
    return [
        {
            "id": item["id"],
            "label": item["label"],
            "rows": 999,
            "code_applications": 999,
            "mapped_codes": ["STUB-CODE"],
            "participants": ["STUB"],
            "participants_covered": ["STUB"],
            "rows_by_participant": {"STUB": 999},
            "participants_not_run": [],
            "status": "covered",
        }
        for item in checklist
    ]


def _stub_load_phase_map(root, checklist, last_rows, map_path=None):
    """A deliberately broken loader: never validates, always 'succeeds'.

    Used only by the negative control for the UT validation mutations
    (5, 6, 7), which check that a REAL loader raises on bad input. A loader
    that always returns something regardless of what it was given should
    never be able to "catch" those mutations either.
    """
    return {p: {item["id"]: None for item in checklist} for p in last_rows}


# --- standard mode mutations ---

def run_mutations_standard(checklist: list[dict], all_rows: list[tuple[str, dict]],
                            category_rules: dict, explicit_rules: dict, categories: dict,
                            compute_fn=None) -> list[dict]:
    if compute_fn is _stub_compute:
        compute = lambda rows: _stub_compute(rows, checklist, None)
    else:
        compute = lambda rows: compute_coverage_standard(
            checklist, category_rules, explicit_rules, categories, rows)["items"]

    baseline = compute(all_rows)
    total_coded = count_coded_rows(all_rows)
    results = []

    # 1. Suppress the best covered item's evidence.
    covered = [i for i in baseline if i["status"] == "covered"]
    if covered:
        target = max(covered, key=lambda i: i["rows"])
        target_codes = set(target["mapped_codes"])
        # Rows actually affected: those carrying a target code, counted as
        # distinct rows (not once per matching code), so this number can
        # never disagree with the report's own coded-row total.
        affected = distinct_row_keys([(p, r) for p, r in all_rows if set(r["codes"]) & target_codes])
        affected_count = len(affected)
        assert affected_count <= total_coded, (
            f"suppressed row count {affected_count} exceeds total coded rows {total_coded}"
        )
        mutated_rows = [
            (p, {**r, "codes": [c for c in r["codes"] if c not in target_codes]})
            for p, r in all_rows
        ]
        after = compute(mutated_rows)
        after_target = next(i for i in after if i["id"] == target["id"])
        caught = after_target["status"] == "GAP"
        results.append(_mutation(
            "1. suppress best covered item", f"{target['id']} flips to GAP",
            "CAUGHT" if caught else "MISSED",
            f"target={target['id']}, suppressed {affected_count} of {total_coded} coded rows, "
            f"after status={after_target['status']}",
        ))
    else:
        results.append(_mutation("1. suppress best covered item", "flips to GAP", "SKIPPED",
                                  "no covered item exists in the baseline"))

    # 2. Suppress every code everywhere.
    mutated_rows = [(p, {**r, "codes": []}) for p, r in all_rows]
    after = compute(mutated_rows)
    caught = len(after) > 0 and all(i["status"] == "GAP" for i in after)
    results.append(_mutation("2. suppress all codes", "every item flips to GAP",
                              "CAUGHT" if caught else "MISSED",
                              f"suppressed all {total_coded} coded rows, statuses={[i['status'] for i in after]}"))

    # 3. Inject one code into a GAP item, or into an uncoded participant.
    gap_items = [i for i in baseline if i["status"] == "GAP"]
    if gap_items:
        target = gap_items[0]
        inject_code = find_code_for_id(target["id"], category_rules, explicit_rules, categories)
        if inject_code is None:
            results.append(_mutation("3. inject evidence", f"{target['id']} flips to covered",
                                      "SKIPPED", f"no mappable code found for {target['id']}"))
        else:
            mutated_rows = all_rows + [("SYNTHETIC", {"n": "9001", "speaker": "P",
                                                        "utterance": "synthetic", "codes": [inject_code]})]
            after = compute(mutated_rows)
            after_target = next(i for i in after if i["id"] == target["id"])
            caught = after_target["status"] == "covered"
            results.append(_mutation("3. inject evidence", f"{target['id']} flips to covered",
                                      "CAUGHT" if caught else "MISSED",
                                      f"injected {inject_code!r}, after status={after_target['status']}"))
    else:
        completeness = compute_coding_completeness(all_rows)
        uncoded = uncoded_participants(completeness)
        if uncoded:
            participant = uncoded[0]
            inject_code, target_id = find_any_mappable_code_and_id(category_rules, explicit_rules, categories)
            if inject_code is None:
                results.append(_mutation("3. inject evidence", f"{participant} leaves the uncoded list",
                                          "SKIPPED", "no mappable code available to inject"))
            else:
                mutated_rows = all_rows + [(participant, {"n": "9001", "speaker": "P",
                                                            "utterance": "synthetic", "codes": [inject_code]})]
                # Read the signal back through compute(), not through a
                # separate completeness recount, so a stub backend that
                # ignores mutated_rows cannot pass this by accident.
                after = compute(mutated_rows)
                after_target = next(i for i in after if i["id"] == target_id)
                caught = participant in after_target["participants"]
                results.append(_mutation("3. inject evidence", f"{participant} appears in {target_id}'s participants",
                                          "CAUGHT" if caught else "MISSED",
                                          f"injected {inject_code!r} into {participant}, target={target_id}"))
        else:
            results.append(_mutation("3. inject evidence", "a GAP item flips, or an uncoded participant is coded",
                                      "SKIPPED", "no GAP item and no uncoded participant to inject into"))

    # 4. Suppress an item's evidence for all participants but one.
    candidates = [i for i in baseline if i["status"] == "covered" and len(i["participants"]) >= 2]
    if candidates:
        target = candidates[0]
        keep = target["participants"][0]
        target_codes = set(target["mapped_codes"])
        affected = distinct_row_keys([
            (p, r) for p, r in all_rows if p != keep and (set(r["codes"]) & target_codes)
        ])
        affected_count = len(affected)
        assert affected_count <= total_coded, (
            f"suppressed row count {affected_count} exceeds total coded rows {total_coded}"
        )
        mutated_rows = []
        for p, r in all_rows:
            if p != keep and (set(r["codes"]) & target_codes):
                mutated_rows.append((p, {**r, "codes": [c for c in r["codes"] if c not in target_codes]}))
            else:
                mutated_rows.append((p, r))
        after = compute(mutated_rows)
        after_target = next(i for i in after if i["id"] == target["id"])
        caught = (after_target["status"] == "covered"
                  and len(after_target["participants"]) == 1
                  and after_target["participants"][0] == keep)
        results.append(_mutation("4. suppress all but one participant", "thin coverage fires for that item",
                                  "CAUGHT" if caught else "MISSED",
                                  f"target={target['id']}, kept={keep}, suppressed {affected_count} of "
                                  f"{total_coded} coded rows, after participants={after_target['participants']}"))
    else:
        results.append(_mutation("4. suppress all but one participant", "thin coverage fires",
                                  "SKIPPED", "no covered item has evidence from 2+ participants"))

    # 5-8 do not apply to standard mode: there is no row-range map, no
    # per-participant map entry, and mutation 8 is UT-only by definition.
    results.append(_mutation("5. truncate transcript past a map range", "validation error",
                              "SKIPPED", "standard mode has no row-range map to violate"))
    results.append(_mutation("6. remove a participant's transcript", "missing-transcript error",
                              "SKIPPED", "standard mode has no per-participant map entry to miss a transcript for"))
    results.append(_mutation("7. remove a participant's map row", "not-in-map error",
                              "SKIPPED", "standard mode's map has no per-participant rows"))
    results.append(_mutation("8. shift a phase boundary", "counts move between phases",
                              "SKIPPED", "UT mode only, standard mode has no phases"))

    return results


# --- UT mode mutations ---

def run_mutations_ut(checklist: list[dict], all_rows: list[tuple[str, dict]],
                      phase_map: dict, last_rows: dict, root: Path, map_path: Path | None,
                      compute_fn=None, load_phase_map_fn=None) -> list[dict]:
    load_phase_map_fn = load_phase_map_fn or load_phase_map

    def real_compute(rows, pm=None):
        return compute_coverage_ut(checklist, pm if pm is not None else phase_map, last_rows, rows)["items"]

    def stub_compute(rows, pm=None):
        return _stub_compute(rows, checklist, None)

    compute = stub_compute if compute_fn is _stub_compute else real_compute

    baseline = compute(all_rows)
    total_coded = count_coded_rows(all_rows)
    results = []

    def ranges_for(participant, pid):
        return (phase_map.get(participant, {}) or {}).get(pid) or []

    # 1. Suppress the best covered phase's evidence, for every participant.
    covered = [i for i in baseline if i["status"] == "covered"]
    if covered:
        target = max(covered, key=lambda i: i["rows"])

        def in_target(p, r):
            n = row_number(r)
            return n is not None and any(s <= n <= e for s, e in ranges_for(p, target["id"]))

        # Suppressed count must be CODED rows in range, not all rows in
        # range (most of a phase's rows are small talk with no code at
        # all). Counting every in-range row here is exactly the bug that
        # let a suppressed-row count exceed the report's own coded-row
        # total: this is a subset of total_coded by construction, and the
        # assertion below makes that impossible to violate silently.
        affected = distinct_row_keys([(p, r) for p, r in all_rows if in_target(p, r) and r["codes"]])
        affected_count = len(affected)
        assert affected_count <= total_coded, (
            f"suppressed row count {affected_count} exceeds total coded rows {total_coded}"
        )

        mutated_rows = [(p, {**r, "codes": []} if in_target(p, r) else r) for p, r in all_rows]
        after = compute(mutated_rows)
        after_target = next(i for i in after if i["id"] == target["id"])
        caught = after_target["status"] == "GAP"
        results.append(_mutation("1. suppress best covered phase", f"{target['id']} flips to GAP",
                                  "CAUGHT" if caught else "MISSED",
                                  f"target={target['id']}, suppressed {affected_count} of {total_coded} "
                                  f"coded rows, after status={after_target['status']}"))
    else:
        results.append(_mutation("1. suppress best covered phase", "flips to GAP", "SKIPPED",
                                  "no covered phase exists in the baseline"))

    # 2. Suppress every code everywhere.
    mutated_rows = [(p, {**r, "codes": []}) for p, r in all_rows]
    after = compute(mutated_rows)
    caught = len(after) > 0 and all(i["status"] == "GAP" for i in after)
    results.append(_mutation("2. suppress all codes", "every phase flips to GAP",
                              "CAUGHT" if caught else "MISSED",
                              f"suppressed all {total_coded} coded rows, statuses={[i['status'] for i in after]}"))

    # 3. Inject one code into a GAP phase, or into an uncoded participant.
    gap_items = [i for i in baseline if i["status"] == "GAP"]
    if gap_items:
        target = gap_items[0]
        host = next((p for p in phase_map if ranges_for(p, target["id"])), None)
        if host is None:
            results.append(_mutation("3. inject evidence", f"{target['id']} flips to covered",
                                      "SKIPPED", f"no participant has a range for {target['id']}"))
        else:
            start, _end = ranges_for(host, target["id"])[0]
            mutated_rows = all_rows + [(host, {"n": str(start), "speaker": "P",
                                                "utterance": "synthetic", "codes": ["SYNTHETIC-CODE"]})]
            after = compute(mutated_rows)
            after_target = next(i for i in after if i["id"] == target["id"])
            caught = after_target["status"] == "covered"
            results.append(_mutation("3. inject evidence", f"{target['id']} flips to covered",
                                      "CAUGHT" if caught else "MISSED",
                                      f"injected into {host} at row {start}"))
    else:
        completeness = compute_coding_completeness(all_rows)
        uncoded = uncoded_participants(completeness)
        if uncoded:
            participant = uncoded[0]
            phase_ids = [item["id"] for item in checklist]
            host_pid = next((pid for pid in phase_ids if ranges_for(participant, pid)), None)
            if host_pid is None:
                results.append(_mutation("3. inject evidence", f"{participant} appears in a phase's participants",
                                          "SKIPPED", f"{participant} has no phase range at all to inject into"))
            else:
                start, _end = ranges_for(participant, host_pid)[0]
                mutated_rows = all_rows + [(participant, {"n": str(start), "speaker": "P",
                                                            "utterance": "synthetic", "codes": ["SYNTHETIC-CODE"]})]
                # Read the signal back through compute(), not through a
                # separate completeness recount, so a stub backend that
                # ignores mutated_rows cannot pass this by accident.
                after = compute(mutated_rows)
                after_target = next(i for i in after if i["id"] == host_pid)
                caught = participant in after_target["participants_covered"]
                results.append(_mutation("3. inject evidence", f"{participant} appears in {host_pid}'s participants",
                                          "CAUGHT" if caught else "MISSED",
                                          f"injected into {participant} at row {start}, target={host_pid}"))
        else:
            results.append(_mutation("3. inject evidence", "a GAP phase flips, or an uncoded participant is coded",
                                      "SKIPPED", "no GAP phase and no uncoded participant to inject into"))

    # 4. Suppress a phase's evidence for all participants but one.
    candidates = [i for i in baseline if i["status"] == "covered" and len(i["participants_covered"]) >= 2]
    if candidates:
        target = candidates[0]
        keep = target["participants_covered"][0]

        def in_target_for_others(p, r):
            if p == keep:
                return False
            n = row_number(r)
            return n is not None and any(s <= n <= e for s, e in ranges_for(p, target["id"]))

        affected = distinct_row_keys([
            (p, r) for p, r in all_rows if in_target_for_others(p, r) and r["codes"]
        ])
        affected_count = len(affected)
        assert affected_count <= total_coded, (
            f"suppressed row count {affected_count} exceeds total coded rows {total_coded}"
        )

        def strip_for_others(p, r):
            return {**r, "codes": []} if in_target_for_others(p, r) else r

        mutated_rows = [(p, strip_for_others(p, r)) for p, r in all_rows]
        after = compute(mutated_rows)
        after_target = next(i for i in after if i["id"] == target["id"])
        caught = (after_target["status"] == "covered"
                  and len(after_target["participants_covered"]) == 1
                  and after_target["participants_covered"][0] == keep)
        results.append(_mutation("4. suppress all but one participant", "thin coverage fires for that phase",
                                  "CAUGHT" if caught else "MISSED",
                                  f"target={target['id']}, kept={keep}, suppressed {affected_count} of "
                                  f"{total_coded} coded rows, after participants={after_target['participants_covered']}"))
    else:
        results.append(_mutation("4. suppress all but one participant", "thin coverage fires",
                                  "SKIPPED", "no covered phase has evidence from 2+ participants"))

    # 5. Truncate a participant's transcript so a map range now runs past the end.
    truncate_target = None
    for p, phases in phase_map.items():
        for pid, ranges in phases.items():
            if ranges:
                truncate_target = (p, max(e for _s, e in ranges))
                break
        if truncate_target:
            break
    if truncate_target:
        p, some_end = truncate_target
        mutated_last_rows = dict(last_rows)
        mutated_last_rows[p] = max(1, some_end - 5)
        try:
            load_phase_map_fn(root, checklist, mutated_last_rows, map_path=map_path)
            results.append(_mutation("5. truncate transcript past a map range", "validation error",
                                      "MISSED", f"no error raised after truncating {p} to {mutated_last_rows[p]}"))
        except FileNotFoundError:
            results.append(_mutation("5. truncate transcript past a map range", "validation error",
                                      "MISSED", "loader reported file not found instead of a range error"))
        except ValueError as exc:
            caught = "beyond that participant's last transcript row" in str(exc)
            results.append(_mutation("5. truncate transcript past a map range", "validation error",
                                      "CAUGHT" if caught else "MISSED", str(exc)[:200]))
    else:
        results.append(_mutation("5. truncate transcript past a map range", "validation error",
                                  "SKIPPED", "no participant has any range to truncate past"))

    # 6. Remove a participant's transcript (drop them from last_rows, keep them in the map).
    if last_rows:
        p = next(iter(last_rows))
        mutated_last_rows = {k: v for k, v in last_rows.items() if k != p}
        try:
            load_phase_map_fn(root, checklist, mutated_last_rows, map_path=map_path)
            results.append(_mutation("6. remove a participant's transcript", "missing-transcript error",
                                      "MISSED", f"no error raised after dropping {p} from last_rows"))
        except FileNotFoundError:
            results.append(_mutation("6. remove a participant's transcript", "missing-transcript error",
                                      "MISSED", "loader reported file not found instead"))
        except ValueError as exc:
            caught = "no transcript.md was found" in str(exc)
            results.append(_mutation("6. remove a participant's transcript", "missing-transcript error",
                                      "CAUGHT" if caught else "MISSED", str(exc)[:200]))
    else:
        results.append(_mutation("6. remove a participant's transcript", "missing-transcript error",
                                  "SKIPPED", "no participants to remove"))

    # 7. Remove a participant's row from the map file itself.
    if map_path is not None and Path(map_path).exists() and last_rows:
        p = next(iter(last_rows))
        lines = Path(map_path).read_text(encoding="utf-8").splitlines()
        filtered_lines = [line for line in lines if not re.search(rf"\|\s*{re.escape(p)}\s*\|", line)]
        if len(filtered_lines) == len(lines):
            results.append(_mutation("7. remove a participant's map row", "not-in-map error",
                                      "SKIPPED", f"could not locate {p}'s row by text match to remove it"))
        else:
            tmp_dir = Path(tempfile.mkdtemp(prefix="coverage_selftest_"))
            tmp_map = tmp_dir / "phase-map.md"
            tmp_map.write_text("\n".join(filtered_lines) + "\n", encoding="utf-8")
            try:
                load_phase_map_fn(root, checklist, last_rows, map_path=tmp_map)
                results.append(_mutation("7. remove a participant's map row", "not-in-map error",
                                          "MISSED", f"no error raised after removing {p}'s row"))
            except ValueError as exc:
                caught = "has no row in the phase map" in str(exc)
                results.append(_mutation("7. remove a participant's map row", "not-in-map error",
                                          "CAUGHT" if caught else "MISSED", str(exc)[:200]))
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        results.append(_mutation("7. remove a participant's map row", "not-in-map error",
                                  "SKIPPED", "no phase-map.md file available to edit"))

    # 8. Shift one phase boundary by a large amount; counts should move.
    shift_target = None
    for p, phases in phase_map.items():
        for pid, ranges in phases.items():
            if ranges:
                shift_target = (p, pid)
                break
        if shift_target:
            break
    if shift_target:
        p, pid = shift_target
        mutated_map = {part: dict(phases) for part, phases in phase_map.items()}
        old_ranges = mutated_map[p][pid]
        last_row = last_rows.get(p, max(e for _s, e in old_ranges))
        new_ranges = [(s, min(e + 50, last_row)) for s, e in old_ranges]
        mutated_map[p][pid] = new_ranges
        after = real_compute(all_rows, pm=mutated_map) if compute_fn is not _stub_compute else stub_compute(all_rows)
        baseline_row_count = next(i for i in baseline if i["id"] == pid)["rows"]
        after_row_count = next(i for i in after if i["id"] == pid)["rows"]
        caught = after_row_count != baseline_row_count
        results.append(_mutation("8. shift a phase boundary", "counts move between phases",
                                  "CAUGHT" if caught else "MISSED",
                                  f"shifted {p}'s {pid} end by up to 50, rows {baseline_row_count} -> {after_row_count}"))
    else:
        results.append(_mutation("8. shift a phase boundary", "counts move between phases",
                                  "SKIPPED", "no participant has any range to shift"))

    return results


SELFTEST_DISCLAIMER = (
    "This suite proves the computation responds correctly to changes in the data. "
    "It says nothing about whether the map or the phase boundaries are actually "
    "right, and the map is the one input a passing suite has the least power to "
    "check: only mutation 8 varies the boundaries themselves, and even that only "
    "proves the counts move, not that they land where a human would put them. "
    "Only a human reviewing the map and boundaries can confirm they are correct. "
    "A clean selftest is not validation that the boundaries are correct."
)


def run_selftest(mode: str, checklist: list[dict], all_rows: list[tuple[str, dict]],
                  mode_ctx: dict) -> int:
    """Run the mutation suite against the real backend, then against a stub.

    The stub run is the negative control: it proves the suite itself can
    tell a working check apart from a fake one. If the stub 'catches' any
    mutation, something about the suite is broken and the real run's
    result cannot be trusted, regardless of how it looked on its own.
    """
    if mode == "ut":
        real_rows = run_mutations_ut(checklist, all_rows, mode_ctx["phase_map"], mode_ctx["last_rows"],
                                      mode_ctx["root"], mode_ctx["map_path"])
        stub_rows = run_mutations_ut(checklist, all_rows, mode_ctx["phase_map"], mode_ctx["last_rows"],
                                      mode_ctx["root"], mode_ctx["map_path"],
                                      compute_fn=_stub_compute, load_phase_map_fn=_stub_load_phase_map)
    else:
        real_rows = run_mutations_standard(checklist, all_rows, mode_ctx["category_rules"],
                                            mode_ctx["explicit_rules"], mode_ctx["categories"])
        stub_rows = run_mutations_standard(checklist, all_rows, mode_ctx["category_rules"],
                                            mode_ctx["explicit_rules"], mode_ctx["categories"],
                                            compute_fn=_stub_compute)

    print(render_mutation_table(real_rows))
    print()

    applicable_real = [r for r in real_rows if r["status"] != "SKIPPED"]
    all_caught = all(r["status"] == "CAUGHT" for r in applicable_real)
    missed = [r for r in applicable_real if r["status"] != "CAUGHT"]

    applicable_stub = [r for r in stub_rows if r["status"] != "SKIPPED"]
    stub_caught = [r for r in applicable_stub if r["status"] == "CAUGHT"]

    if stub_caught:
        print(f"NEGATIVE CONTROL: FAILED. The stub backend, which ignores its inputs, "
              f"still got marked CAUGHT on {len(stub_caught)} mutation(s): "
              f"{[r['name'] for r in stub_caught]}. The suite cannot tell a real "
              f"check from a fake one, so its result on the real backend is void.")
        print()
        print(SELFTEST_DISCLAIMER)
        return 1

    print(f"NEGATIVE CONTROL: PASSED. The stub backend caught 0 of {len(applicable_stub)} "
          f"applicable mutation(s), confirming the suite can tell a real check from a fake one.")
    print()
    print(SELFTEST_DISCLAIMER)
    print()

    skipped = [r["name"] for r in real_rows if r["status"] == "SKIPPED"]
    if skipped:
        print(f"SKIPPED (not applicable here): {', '.join(skipped)}")

    # Bidirectional requirement: a check hardwired to always report GAP
    # would pass every downward mutation (1, 2). Only the upward one (3,
    # evidence added to a GAP item or an uncoded participant) can catch
    # that, so a suite that never ran an upward mutation has not actually
    # proven the check is responsive, only that it can suppress things.
    by_name = {r["name"]: r for r in real_rows}
    downward_caught = any(
        by_name[name]["status"] == "CAUGHT"
        for name in by_name if name.startswith("1.") or name.startswith("2.")
    )
    upward_result = next((r for r in real_rows if r["name"].startswith("3.")), None)
    upward_caught = upward_result is not None and upward_result["status"] == "CAUGHT"
    bidirectional_met = downward_caught and upward_caught

    if bidirectional_met:
        print("BIDIRECTIONAL CHECK: met. At least one downward mutation (covered -> GAP) "
              "and the upward mutation (GAP -> covered, or uncoded -> coded) were both caught.")
    else:
        reason = "no upward mutation was caught" if not upward_caught else "no downward mutation was caught"
        print(f"BIDIRECTIONAL CHECK: NOT MET ({reason}). A downward-only suite cannot rule out "
              "a check that is hardwired to always report a gap.")
    print()

    if all_caught and bidirectional_met:
        print(f"SELFTEST: PASS. {len(applicable_real)} applicable mutation(s) all caught, "
              f"bidirectional check met, negative control clean.")
        return 0
    elif all_caught:
        print(f"SELFTEST: PARTIAL PASS. {len(applicable_real)} applicable mutation(s) all caught, "
              f"negative control clean, but the bidirectional requirement was not met, so this is "
              f"not reported as a full pass.")
        return 0
    else:
        print(f"SELFTEST: FAIL. Missed: {[r['name'] for r in missed]}")
        return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="coverage.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Compare a study's declared checklist against the coded evidence "
            "that exists. Standard mode maps codes (or codebook categories) to "
            "research questions via rq-map.md. UT mode maps session phases to "
            "row-number ranges via phase-map.md, since UT codes are thematic "
            "and recur across every phase, so no code-to-phase table would "
            "ever be correct."
        ),
        epilog=(
            "Exit codes:\n"
            "  0  every item has evidence and every participant is coded\n"
            "  1  at least one item has no evidence\n"
            "  3  no link file, build it first\n"
            "  4  at least one participant has no codes at all, so the result "
            "is not trustworthy\n"
        ),
    )
    parser.add_argument("study_root", help="Path to the study repo, or any folder inside it")
    parser.add_argument(
        "--map",
        dest="map_path",
        help="Standard mode only: path to the rq-map.md code/category-to-checklist map. "
             "Defaults to <method-or-approach-dir>/rq-map.md. Ignored in UT mode.",
    )
    parser.add_argument(
        "--phase-map",
        dest="phase_map_path",
        help="UT mode only: path to the phase-map.md phase boundary table. "
             "Defaults to <method-or-approach-dir>/phase-map.md. Ignored in "
             "standard mode. Use this to point at a disposable test fixture "
             "instead of writing phase-map.md into a study repo or its copies.",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Run a suite of mutations (suppress evidence, inject evidence, "
             "break validation, shift boundaries) against the real computation "
             "and confirm each is caught, then run the same suite against a "
             "stub that ignores its inputs and confirm it catches nothing "
             "(the negative control). Proves the computation responds to the "
             "data; says nothing about whether the map or boundaries are correct.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of markdown (ignored with --selftest, which "
             "always prints its own PASS/FAIL lines)",
    )
    args = parser.parse_args(argv)

    root = find_study_root(args.study_root)
    mode = detect_mode(root)
    mdir = method_dir(root)
    checklist = load_checklist(root)

    if not checklist:
        print(
            "No checklist items found (no research questions or session "
            "phases could be read from the study's plan documents).",
            file=sys.stderr,
        )
        return 3

    all_rows = load_all_rows(root)
    completeness = compute_coding_completeness(all_rows)
    uncoded = uncoded_participants(completeness)
    size_note = checklist_size_note(checklist)

    if mode == "ut":
        last_rows = load_last_rows(root)
        phase_map_override = Path(args.phase_map_path) if args.phase_map_path else None
        expected_map_path = phase_map_override if phase_map_override else (mdir or root) / "phase-map.md"
        try:
            phase_map = load_phase_map(root, checklist, last_rows, map_path=phase_map_override)
        except FileNotFoundError:
            print(
                f"No phase boundary map found at {expected_map_path}.\n"
                "This script will not guess session phase boundaries. The "
                "calling agent must build phase-map.md first (a markdown "
                "table with a 'Participant' column and one column per phase "
                "id, each cell the first row number of that phase for that "
                "participant, or '-' if it did not happen), then re-run "
                "this check.",
                file=sys.stderr,
            )
            return 3
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 3

        if args.selftest:
            if size_note:
                print(size_note)
                print()
            return run_selftest("ut", checklist, all_rows, {
                "phase_map": phase_map,
                "last_rows": last_rows,
                "root": root,
                "map_path": expected_map_path,
            })

        result = compute_coverage_ut(checklist, phase_map, last_rows, all_rows)
        unassigned = compute_unassigned_rows(phase_map, last_rows)
        exit_code, reason = exit_code_and_reason(result["items"], uncoded)
        if args.json:
            result["coding_completeness"] = completeness
            result["uncoded_participants"] = uncoded
            result["unassigned_rows"] = unassigned
            result["exit_code"] = exit_code
            result["exit_reason"] = reason
            print(json.dumps(result, indent=2))
        else:
            if size_note:
                print(size_note)
                print()
            print(render_coding_completeness(completeness))
            print()
            print(render_markdown_ut(result, uncoded, unassigned))
            print()
            print(reason)
        return exit_code

    # standard mode
    if args.map_path:
        map_path = Path(args.map_path)
    else:
        if mdir is None:
            print(
                "No method/ or approach/ directory found in this study, so "
                "there is nowhere to look for rq-map.md. Pass --map explicitly.",
                file=sys.stderr,
            )
            return 3
        map_path = mdir / "rq-map.md"

    if not map_path.exists():
        print(
            f"No code-to-checklist map found at {map_path}.\n"
            "This script will not invent one. The calling agent must build "
            "rq-map.md first (a markdown table with 'Code' and 'Answers' "
            "columns; each Code cell may be an individual code or a "
            "codebook category name; '-' for entries that answer no "
            "declared question), then re-run this check.",
            file=sys.stderr,
        )
        return 3

    map_entries = load_map(map_path)
    categories = load_codebook_categories(root)
    category_rules, explicit_rules, resolve_errors = resolve_standard_map(map_entries, categories)

    if resolve_errors:
        print(f"{map_path} has entries that do not resolve:", file=sys.stderr)
        for err in resolve_errors:
            print(f"  - {err}", file=sys.stderr)
        return 3

    if args.selftest:
        if size_note:
            print(size_note)
            print()
        return run_selftest("standard", checklist, all_rows, {
            "category_rules": category_rules,
            "explicit_rules": explicit_rules,
            "categories": categories,
        })

    result = compute_coverage_standard(checklist, category_rules, explicit_rules, categories, all_rows)
    exit_code, reason = exit_code_and_reason(result["items"], uncoded)
    if args.json:
        result["coding_completeness"] = completeness
        result["uncoded_participants"] = uncoded
        result["exit_code"] = exit_code
        result["exit_reason"] = reason
        print(json.dumps(result, indent=2))
    else:
        if size_note:
            print(size_note)
            print()
        print(render_coding_completeness(completeness))
        print()
        print(render_markdown_standard(result, uncoded))
        print()
        print(reason)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
