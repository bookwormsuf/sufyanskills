#!/usr/bin/env python3
"""Find candidate wikilink sites in a second-brain vault.

The mechanical half of a link pass: enumerate the notes that exist, mask the
regions where a link would be wrong (code, frontmatter, URLs, existing links),
and report every unlinked mention with its line number and a ready-to-apply
replacement line. Judging which candidates are real is left to the caller.

Usage:
    python3 find_candidates.py                     # changed files, auto-detected
    python3 find_candidates.py --files a.md b.md   # specific files
    python3 find_candidates.py --all               # every knowledge file
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

KNOWLEDGE_DIRS = ["notes", "people", "projects", "learnings"]

# Terms that are everywhere in this vault and carry no linking value on their own.
STOPWORDS = {
    "claude", "figma", "react", "github", "slack", "notion", "google",
    "typescript", "javascript", "python", "css", "html", "api", "prd", "ut",
    "singapore", "chrome", "storybook",
    "the", "this", "that", "and", "but", "for", "with", "from", "what", "when",
    "next", "steps", "current", "state", "changes", "decisions", "summary",
    "note", "notes", "status", "plan", "phase", "sprint", "design", "product",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}

# Filenames that are structural, not subjects. A note called plan.md is "the plan
# for that project", so linking the word "plan" anywhere in prose is always wrong.
GENERIC_BASENAMES = {
    "readme", "index", "skill", "skills", "plan", "plans", "profile", "context",
    "decisions", "status", "inbox", "examples", "references", "reference",
    "screener", "brief", "implementation", "handover", "handoff", "prd", "adr",
    "notes", "note", "summary", "overview", "template", "draft", "spec",
    "changelog", "roadmap", "glossary", "todo", "active", "done", "archive",
    "dashboard", "connections", "memory", "resumes", "guide", "process",
    # structural folders that exist in projects/ but name no subject
    "docs", "assets", "images", "scripts", "src", "public", "data", "evals",
    "agents", "screenshots", "components", "develop", "design", "build",
}

# Chronological logs. Same reasoning as SESSION_LOG: nobody follows a link out of
# a dated build log, and their length makes them generate noise by the dozen.
LOG_FILENAMES = {"STATUS.md", "SESSION_LOG.md", "INDEX.md", "CHANGELOG.md"}


def run(cmd, cwd):
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, shell=isinstance(cmd, str)
    ).stdout


def changed_files(vault):
    """Files touched since the last recorded pass, plus the working tree."""
    state = os.path.join(vault, ".claude", "link-pass-state")
    last = None
    if os.path.exists(state):
        with open(state) as f:
            parts = f.read().split()
            if parts:
                last = parts[0]
    base = last or "HEAD~20"
    # A base that does not exist makes git print nothing, which would read as a
    # clean vault instead of a failed scan. Fall back to the first commit.
    if not run(f"git rev-parse --verify --quiet {base}^{{commit}}", vault).strip():
        base = run("git rev-list --max-parents=0 HEAD", vault).split()[0]
    dirs = " ".join(KNOWLEDGE_DIRS)
    out = run(f"git diff --name-only {base} HEAD -- {dirs}", vault)
    files = set(out.split())
    for line in run(f"git status --porcelain -- {dirs}", vault).splitlines():
        if len(line) > 3:
            files.add(line[3:].strip().strip('"'))
    return sorted(f for f in files if in_scope(f)), (last is None)


def in_scope(rel):
    if not rel.endswith(".md"):
        return False
    if "/archive/" in rel or rel.startswith("archive/"):
        return False
    if os.path.basename(rel) in LOG_FILENAMES:
        return False
    return rel.split("/")[0] in KNOWLEDGE_DIRS


def all_files(vault):
    found = []
    for d in KNOWLEDGE_DIRS:
        root = os.path.join(vault, d)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x != "archive"]
            for fn in filenames:
                if fn.endswith(".md"):
                    found.append(os.path.relpath(os.path.join(dirpath, fn), vault))
    return sorted(found)


def surface_forms(slug):
    """Human spellings a kebab-case filename might appear as in prose.

    Structural filenames are dropped here: a single generic word like "plan" or
    "profile" names a file's role inside a project, never a subject you'd link to.
    """
    low = slug.lower()
    if low in GENERIC_BASENAMES or low in STOPWORDS:
        return set()
    words = slug.split("-")
    if len(words) == 1 and low in GENERIC_BASENAMES:
        return set()
    forms = {slug.replace("-", " ")}
    # proj-2492-empty-states -> keep the whole thing only; ticket slugs are not prose
    if not re.match(r"^[a-z]+-\d+", slug):
        forms.add(" ".join(w.capitalize() for w in words))
    return {f for f in forms if len(f) > 3}


def build_entities(vault):
    """Map lowercase surface form -> {'target': slug, 'kind': folder}."""
    entities = {}
    first_names = defaultdict(list)

    for rel in all_files(vault):
        folder = rel.split("/")[0]
        base = os.path.basename(rel)[:-3]
        slug = base
        # projects/foo/README.md is addressed as the folder name
        if base.lower() in ("readme", "index") and "/" in rel:
            slug = rel.split("/")[-2]
        for form in surface_forms(slug):
            entities.setdefault(form.lower(), {"target": slug, "kind": folder, "path": rel})
        if folder == "people":
            first = slug.split("-")[0]
            if len(first) > 2:
                first_names[first].append(slug)

    # Project folders are link targets, but only when they hold notes. Asset
    # folders (screenshots/, images/) share the same shape and would otherwise
    # turn every filename in them into a phantom entity.
    proj = os.path.join(vault, "projects")
    for dirpath, dirnames, _ in os.walk(proj):
        dirnames[:] = [d for d in dirnames if d != "archive"]
        for d in dirnames:
            full = os.path.join(dirpath, d)
            if not any(fn.endswith(".md") for fn in os.listdir(full)):
                continue
            for form in surface_forms(d):
                entities.setdefault(
                    form.lower(),
                    {"target": d, "kind": "projects",
                     "path": os.path.relpath(os.path.join(dirpath, d), vault)},
                )

    # frontmatter aliases
    for rel in all_files(vault):
        try:
            with open(os.path.join(vault, rel), encoding="utf-8") as f:
                head = f.read(2000)
        except OSError:
            continue
        m = re.search(r"^aliases:\s*\[(.*?)\]", head, re.M)
        if m:
            slug = os.path.basename(rel)[:-3]
            for alias in m.group(1).split(","):
                alias = alias.strip().strip("\"'")
                if len(alias) > 2:
                    entities[alias.lower()] = {"target": slug, "kind": rel.split("/")[0], "path": rel}

    # a first name is linkable only when exactly one person owns it
    for first, owners in first_names.items():
        if len(owners) == 1 and first not in STOPWORDS:
            entities.setdefault(first, {"target": owners[0], "kind": "people",
                                        "path": f"people/{owners[0]}.md"})
    return entities


def mask(text):
    """Blank out regions where inserting a link would be wrong, keeping offsets."""
    out = list(text)

    def blank(start, end):
        for i in range(start, min(end, len(out))):
            if out[i] != "\n":
                out[i] = " "

    # frontmatter
    fm = re.match(r"^---\n.*?\n---\n", text, re.S)
    if fm:
        blank(0, fm.end())
    patterns = [
        r"^(?:```|~~~).*?^(?:```|~~~)",   # fenced code
        r"`[^`\n]+`",                      # inline code
        r"\[\[[^\]]*\]\]",                 # existing wikilinks
        r"\[[^\]]*\]\([^)]*\)",            # markdown links
        r"https?://\S+",                   # bare URLs
        r"^\s{4,}\S.*$",                   # indented code
        r"<!--.*?-->",                     # html comments
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.S | re.M):
            blank(m.start(), m.end())
    return "".join(out)


def is_table_row(line):
    """A markdown table row: starts with a pipe and holds at least one more."""
    s = line.strip()
    return s.startswith("|") and s.count("|") >= 2


def find_in_file(vault, rel, entities):
    path = os.path.join(vault, rel)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    masked = mask(text)
    lines = text.split("\n")
    masked_lines = masked.split("\n")
    self_slug = os.path.basename(rel)[:-3]

    # Targets this file already links to. Masking hides existing links from the
    # scanner, so without this the pass would propose the *second* mention on the
    # next run, then the third, never converging on "one link per file".
    # rstrip the backslash so an escaped table link, [[alex\|Alex]], still counts.
    already = {m.group(1).strip().rstrip("\\").strip().lower()
               for m in re.finditer(r"\[\[([^\]|#]+)", text)}

    hits = []
    seen = set()
    for form, ent in entities.items():
        if ent["target"] == self_slug or ent["path"] == rel:
            continue
        if ent["target"] in seen or ent["target"].lower() in already:
            continue
        pat = re.compile(r"\b" + re.escape(form) + r"\b", re.I)
        for idx, mline in enumerate(masked_lines):
            m = pat.search(mline)
            if not m:
                continue
            actual = lines[idx][m.start():m.end()]
            # Every linkable entity here is a proper noun (a person, project, or
            # tool). A lowercase match is the same word used as an ordinary noun,
            # so linking it would be wrong.
            if not actual[:1].isupper():
                continue
            if actual.lower() in STOPWORDS or actual.lower() in GENERIC_BASENAMES:
                continue
            target = ent["target"]
            # Only a byte-identical match can drop the pipe. "Zul" linked as
            # [[zul]] would render lowercase and quietly reword the sentence.
            if actual == target:
                link = f"[[{target}]]"
            else:
                # Inside a table the pipe is a column separator, so an unescaped
                # piped link silently splits the row into an extra column.
                sep = "\\|" if is_table_row(lines[idx]) else "|"
                link = f"[[{target}{sep}{actual}]]"
            hits.append({
                "file": rel,
                "line": idx + 1,
                "matched_text": actual,
                "target": target,
                "target_path": ent["path"],
                "current_line": lines[idx],
                "replacement_line": lines[idx][:m.start()] + link + lines[idx][m.end():],
                "first_name_only": " " not in form and ent["kind"] == "people",
            })
            seen.add(target)
            break
    return hits


def looks_like_a_name(phrase, preceding):
    """Is this phrase plausibly a proper noun rather than a sentence opener?

    English capitalises the first word of every sentence, heading and bullet, so
    position is the main signal separating "Nothing" from "Camunda". A phrase in
    one of those positions only counts when its own shape marks it as a name:
    several capitalised words, internal capitals, or an acronym.
    """
    words = phrase.split()
    strong_shape = (
        len(words) > 1
        or re.search(r"[a-z][A-Z]", phrase)          # CamelCase
        or (phrase.isupper() and len(phrase) >= 3)   # acronym
    )
    at_start = not preceding.strip() or preceding.rstrip()[-1:] in ".!?:|#*-–—>"
    return strong_shape if at_start else True


def orphan_candidates(vault, files, entities):
    """Recurring proper nouns with no note of their own."""
    counts = defaultdict(set)
    for rel in files:
        try:
            with open(os.path.join(vault, rel), encoding="utf-8") as f:
                text = mask(f.read())
        except OSError:
            continue
        for m in re.finditer(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2})\b", text):
            phrase = m.group(1).strip()
            low = phrase.lower()
            if low in STOPWORDS or low in entities or low in GENERIC_BASENAMES:
                continue
            if len(phrase) < 4 or phrase.rstrip("s").lower() in STOPWORDS:
                continue
            if any(w.lower() in STOPWORDS for w in phrase.split()):
                continue
            line_start = text.rfind("\n", 0, m.start()) + 1
            if not looks_like_a_name(phrase, text[line_start:m.start()]):
                continue
            counts[phrase].add(rel)

    shortlist = {p for p, seen in counts.items() if len(seen) >= 2}
    if not shortlist:
        return []

    # One pass over the vault, checking every shortlisted phrase per file, so the
    # cost stays linear in vault size rather than phrases times files.
    corpus = []
    for rel in all_files(vault):
        try:
            with open(os.path.join(vault, rel), encoding="utf-8") as f:
                corpus.append((rel, f.read()))
        except OSError:
            continue

    results = []
    for phrase in shortlist:
        exact = re.compile(r"\b" + re.escape(phrase) + r"\b")
        lower = re.compile(r"\b" + re.escape(phrase.lower()) + r"\b")
        hits, upper_n, lower_n = [], 0, 0
        for rel, body in corpus:
            if exact.search(body):
                hits.append(rel)
            upper_n += len(exact.findall(body))
            lower_n += len(lower.findall(body))
        if len(hits) < 3:
            continue
        # A name keeps its capital wherever it appears. A common word used as a
        # heading or UI label ("Preview", "Step") shows up lowercase far more
        # often, which is what separates the two here.
        if lower_n > upper_n * 0.25:
            continue
        results.append({"phrase": phrase, "file_count": len(hits),
                        "files": sorted(hits)[:8]})
    results.sort(key=lambda r: -r["file_count"])
    return results[:10]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.getcwd())
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--all", action="store_true")
    # The orphan search re-reads the whole vault and costs about three quarters
    # of the runtime, for a list that changes slowly. Off by default; run it
    # deliberately when you want the "notes waiting to exist" sweep.
    ap.add_argument("--orphans", action="store_true",
                    help="also hunt recurring proper nouns that have no note")
    ap.add_argument("--no-orphans", action="store_true",
                    help=argparse.SUPPRESS)  # accepted and ignored; now the default
    args = ap.parse_args()

    vault = os.path.abspath(args.vault)
    first_run = False
    if args.all:
        files = [f for f in all_files(vault) if in_scope(f)]
    elif args.files:
        files = [f for f in args.files if in_scope(f)]
    else:
        files, first_run = changed_files(vault)

    if not files:
        print(json.dumps({"first_run": first_run, "files_scanned": [],
                          "candidates": [], "orphans": [],
                          "orphan_search": "skipped (no files to scan)",
                          "message": "No changed files. Nothing to scan."}, indent=2))
        return

    entities = build_entities(vault)
    candidates = []
    for rel in files:
        candidates.extend(find_in_file(vault, rel, entities))

    orphans = orphan_candidates(vault, files, entities) if args.orphans else []

    print(json.dumps({
        "first_run": first_run,
        "entity_count": len(entities),
        "files_scanned": files,
        "candidates": candidates,
        "orphans": orphans,
        "orphan_search": "ran" if args.orphans else "skipped (pass --orphans to run it)",
    }, indent=2))


if __name__ == "__main__":
    main()
