#!/usr/bin/env python3
"""Check that a link pass did not damage the files it edited.

Applying an edit and reporting success is not evidence the edit was right. This
re-reads each touched file and checks the things a wikilink can silently break:
table column counts, link syntax, and whether targets resolve to real notes.

Where a file is tracked by git, findings are compared against the committed
version so only *new* damage is reported. Pre-existing quirks in a note are the
author's business, not this pass's.

Usage:
    python3 verify_edits.py --files notes/a.md projects/b.md
    python3 verify_edits.py            # every file changed in the working tree

Exit status is 1 when new damage is found, so a caller can gate on it.
"""

import argparse
import json
import os
import re
import subprocess
import sys

KNOWLEDGE_DIRS = ["notes", "people", "projects", "learnings"]


def run(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=True)
    return p.stdout, p.returncode


def strip_inline_code(line):
    return re.sub(r"`[^`]*`", lambda m: " " * len(m.group(0)), line)


def column_count(line):
    """Columns in a markdown table row, ignoring escaped pipes and code spans."""
    s = strip_inline_code(line)
    s = s.replace("\\|", "\x00")          # an escaped pipe is content, not a border
    return s.count("|")


def table_problems(text):
    """Rows whose column count disagrees with their table's header."""
    problems = []
    lines = text.split("\n")
    header_cols = None
    header_line = None
    in_code = False
    for i, line in enumerate(lines, 1):
        if re.match(r"^\s*(```|~~~)", line):
            in_code = not in_code
            continue
        if in_code:
            continue
        stripped = line.strip()
        is_row = stripped.startswith("|") and stripped.count("|") >= 2
        if not is_row:
            header_cols = None
            continue
        cols = column_count(line)
        if header_cols is None:
            header_cols = cols
            header_line = i
            continue
        # the ---|--- separator may legitimately differ in padding, not in count
        if cols != header_cols:
            problems.append({
                "kind": "table_columns",
                "line": i,
                "detail": f"row has {cols} column borders, header on line "
                          f"{header_line} has {header_cols}",
                "text": line.strip()[:160],
            })
    return problems


def link_problems(text, vault, rel):
    problems = []
    lines = text.split("\n")
    in_code = False
    for i, line in enumerate(lines, 1):
        if re.match(r"^\s*(```|~~~)", line):
            in_code = not in_code
            continue
        if in_code:
            continue
        scan = strip_inline_code(line)
        is_row = scan.strip().startswith("|") and scan.strip().count("|") >= 2

        if scan.count("[[") != scan.count("]]"):
            problems.append({"kind": "unbalanced_link", "line": i,
                             "detail": "[[ and ]] counts differ",
                             "text": line.strip()[:160]})

        for m in re.finditer(r"\[\[([^\]]*)\]\]", scan):
            body = m.group(1)
            if is_row and re.search(r"(?<!\\)\|", body):
                problems.append({
                    "kind": "unescaped_pipe_in_table",
                    "line": i,
                    "detail": f"[[{body}]] uses a bare pipe inside a table row; "
                              f"it must be written \\| or the row gains a column",
                    "text": line.strip()[:160],
                })
            # The target ends at the first pipe, escaped or not: both [[a|B]] and
            # [[a\|B]] point at a.
            target = re.split(r"\\?\|", body)[0].strip().rstrip("\\").strip()
            target = target.split("#")[0].strip()
            if target and not resolves(vault, target):
                problems.append({
                    "kind": "dangling_link", "line": i,
                    "detail": f"[[{target}]] does not match any note or folder",
                    "text": line.strip()[:160],
                })
    return problems


_resolve_cache = {}


def resolves(vault, target):
    key = target.lower()
    if key in _resolve_cache:
        return _resolve_cache[key]
    found = False
    for d in KNOWLEDGE_DIRS:
        root = os.path.join(vault, d)
        for dirpath, dirnames, filenames in os.walk(root):
            names = {f[:-3].lower() for f in filenames if f.endswith(".md")}
            if key in names or key in {x.lower() for x in dirnames}:
                found = True
                break
        if found:
            break
    _resolve_cache[key] = found
    return found


def signature(p):
    """Identify a problem by kind and text, so shifted line numbers still match."""
    return (p["kind"], p["text"])


def check(vault, rel):
    path = os.path.join(vault, rel)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return [{"kind": "unreadable", "line": 0, "detail": str(e), "text": ""}]
    return table_problems(text) + link_problems(text, vault, rel)


def baseline(vault, rel):
    """Problems already present in the committed version, if there is one."""
    out, code = run(f"git show HEAD:{rel!r}".replace("'", '"'), vault)
    if code != 0:
        return set()
    tmp = os.path.join(vault, ".git", "link-pass-baseline.md")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(out)
        probs = table_problems(out) + link_problems(out, vault, rel)
        return {signature(p) for p in probs}
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.getcwd())
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--all-findings", action="store_true",
                    help="report pre-existing problems too, not just new ones")
    ap.add_argument("--all", action="store_true",
                    help="audit every knowledge file, not just changed ones")
    args = ap.parse_args()

    vault = os.path.abspath(args.vault)
    files = args.files
    if args.all:
        files = []
        for d in KNOWLEDGE_DIRS:
            for dirpath, dirnames, filenames in os.walk(os.path.join(vault, d)):
                dirnames[:] = [x for x in dirnames if x != "archive"]
                files += [os.path.relpath(os.path.join(dirpath, fn), vault)
                          for fn in filenames if fn.endswith(".md")]
        files.sort()
    if not files:
        out, _ = run("git status --porcelain -- " + " ".join(KNOWLEDGE_DIRS), vault)
        files = [l[3:].strip().strip('"') for l in out.splitlines()
                 if len(l) > 3 and l[3:].strip().endswith(".md")]

    report = {"files_checked": files, "new_problems": [], "pre_existing": 0}
    for rel in files:
        found = check(vault, rel)
        if not found:
            continue
        known = set() if args.all_findings else baseline(vault, rel)
        for p in found:
            p = dict(p, file=rel)
            if signature(p) in known:
                report["pre_existing"] += 1
            else:
                report["new_problems"].append(p)

    print(json.dumps(report, indent=2))
    sys.exit(1 if report["new_problems"] else 0)


if __name__ == "__main__":
    main()
