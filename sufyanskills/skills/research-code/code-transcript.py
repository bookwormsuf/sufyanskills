#!/usr/bin/env python3
"""
Pre-code transcript using pattern matching.
Reduces AI workload by auto-coding obvious rows.

Usage:
    python code-transcript.py /path/to/participants/P4/transcript.md [--apply]

Without --apply: Shows what would be coded (dry run)
With --apply: Edits the transcript file directly
"""

import re
import json
import sys
from pathlib import Path

# Load patterns from same directory as script
SCRIPT_DIR = Path(__file__).parent
PATTERNS_FILE = SCRIPT_DIR / "patterns.json"


def load_patterns():
    """Load pattern matching rules."""
    with open(PATTERNS_FILE) as f:
        return json.load(f)


def parse_transcript_table(content: str) -> tuple[str, list[dict], str]:
    """
    Parse markdown table into rows.
    Returns: (header_section, rows, footer_section)
    """
    lines = content.split('\n')

    # Find table start (header row with | # |)
    table_start = None
    for i, line in enumerate(lines):
        if re.match(r'\|\s*#\s*\|.*Speaker.*Utterance', line):
            table_start = i
            break

    if table_start is None:
        raise ValueError("Could not find transcript table")

    header_section = '\n'.join(lines[:table_start])

    # Parse table rows (skip header and separator)
    rows = []
    table_end = table_start

    for i, line in enumerate(lines[table_start:], start=table_start):
        if not line.strip().startswith('|'):
            table_end = i
            break

        # Skip header and separator rows
        if i == table_start or '---' in line:
            continue

        # Parse row
        parts = [p.strip() for p in line.split('|')[1:-1]]  # Remove empty first/last
        if len(parts) >= 6:
            rows.append({
                'line_num': i,
                'row_num': parts[0],
                'speaker': parts[1],
                'utterance': parts[2],
                'code_1': parts[3],
                'code_2': parts[4],
                'notes': parts[5],
                'original_line': line
            })
        table_end = i + 1

    footer_section = '\n'.join(lines[table_end:])

    return header_section, rows, footer_section


def match_patterns(utterance: str, patterns: dict) -> dict:
    """
    Apply all patterns to an utterance.
    Returns dict with suggested codes and flags.
    """
    result = {
        'suggested_code_1': None,
        'suggested_code_2': None,
        'flags': [],
        'is_filler': False,
        'confidence': 0,
        'matches': []
    }

    text = utterance.lower()

    # Check for fillers first
    for pattern in patterns.get('filler_utterances', {}).get('patterns', []):
        if re.match(pattern['regex'], utterance, re.IGNORECASE):
            result['is_filler'] = True
            result['flags'].append('filler')
            return result

    # Check for garbled audio
    for pattern in patterns.get('garbled_audio', {}).get('patterns', []):
        if re.search(pattern['regex'], utterance):
            result['flags'].append(pattern['flag'])
            result['matches'].append(f"garbled: {pattern['name']}")

    # Check tool mentions (high confidence)
    for pattern in patterns.get('tool_mentions', {}).get('patterns', []):
        if re.search(pattern['regex'], utterance, re.IGNORECASE):
            if not result['suggested_code_1']:
                result['suggested_code_1'] = pattern['suggests_code']
                result['confidence'] = 0.9
            elif not result['suggested_code_2']:
                result['suggested_code_2'] = pattern['suggests_code']
            result['matches'].append(f"tool: {pattern['name']}")

    # Check keyword hints (medium confidence)
    for pattern in patterns.get('keyword_hints', {}).get('patterns', []):
        for keyword in pattern['keywords']:
            if keyword.lower() in text:
                conf = pattern.get('confidence', 0.6)
                if not result['suggested_code_1']:
                    result['suggested_code_1'] = pattern['suggests_code']
                    result['confidence'] = conf
                elif not result['suggested_code_2'] and result['suggested_code_1'] != pattern['suggests_code']:
                    result['suggested_code_2'] = pattern['suggests_code']
                result['matches'].append(f"keyword: {keyword}")
                break  # Only match first keyword per pattern

    # Check quotable signals
    for pattern in patterns.get('quotable_signals', {}).get('patterns', []):
        for keyword in pattern['keywords']:
            if keyword.lower() in text:
                result['flags'].append('maybe_quotable')
                result['matches'].append(f"quotable: {keyword}")
                break

    return result


def format_row(row: dict, code_1: str = '', code_2: str = '', notes: str = '') -> str:
    """Format a row back to markdown table format."""
    return f"| {row['row_num']} | {row['speaker']} | {row['utterance']} | {code_1} | {code_2} | {notes} |"


def process_transcript(transcript_path: str, apply: bool = False) -> dict:
    """
    Process transcript with pattern matching.
    Returns stats about what was coded.
    """
    path = Path(transcript_path)
    content = path.read_text()
    patterns = load_patterns()

    header, rows, footer = parse_transcript_table(content)

    stats = {
        'total_rows': len(rows),
        'already_coded': 0,
        'auto_coded': 0,
        'fillers_skipped': 0,
        'needs_ai': 0,
        'flagged_audio': 0,
        'maybe_quotable': 0,
        'auto_coded_rows': [],
        'needs_ai_rows': [],
        'quotable_candidates': []
    }

    new_lines = []

    for row in rows:
        # Skip if already coded
        if row['code_1'].strip():
            stats['already_coded'] += 1
            new_lines.append(row['original_line'])
            continue

        # Apply pattern matching
        result = match_patterns(row['utterance'], patterns)

        if result['is_filler']:
            stats['fillers_skipped'] += 1
            new_lines.append(row['original_line'])  # Leave uncoded
            continue

        if '[?audio]' in result['flags']:
            stats['flagged_audio'] += 1

        if 'maybe_quotable' in result['flags']:
            stats['maybe_quotable'] += 1
            stats['quotable_candidates'].append({
                'row': row['row_num'],
                'utterance': row['utterance'][:80] + '...' if len(row['utterance']) > 80 else row['utterance']
            })

        # Determine if we can auto-code
        if result['suggested_code_1'] and result['confidence'] >= 0.7:
            stats['auto_coded'] += 1
            stats['auto_coded_rows'].append({
                'row': row['row_num'],
                'code': result['suggested_code_1'],
                'matches': result['matches']
            })

            new_line = format_row(
                row,
                code_1=result['suggested_code_1'],
                code_2=result['suggested_code_2'] or '',
                notes=row['notes']
            )
            new_lines.append(new_line)
        else:
            stats['needs_ai'] += 1
            if result['matches']:
                stats['needs_ai_rows'].append({
                    'row': row['row_num'],
                    'hints': result['matches'],
                    'suggested': result['suggested_code_1']
                })
            new_lines.append(row['original_line'])

    # Reconstruct file
    # Find table header lines
    table_header_lines = []
    for line in content.split('\n'):
        if re.match(r'\|\s*#\s*\|', line):
            table_header_lines.append(line)
        elif '---' in line and '|' in line and table_header_lines:
            table_header_lines.append(line)
            break

    new_content = header + '\n' + '\n'.join(table_header_lines) + '\n' + '\n'.join(new_lines) + '\n' + footer

    if apply:
        path.write_text(new_content)
        stats['applied'] = True
    else:
        stats['applied'] = False

    return stats


def print_report(stats: dict):
    """Print a summary report."""
    print("\n" + "=" * 60)
    print("TRANSCRIPT PRE-CODING REPORT")
    print("=" * 60)

    print(f"\nTotal rows: {stats['total_rows']}")
    print(f"Already coded: {stats['already_coded']}")
    print(f"Fillers skipped: {stats['fillers_skipped']}")
    print(f"Flagged audio issues: {stats['flagged_audio']}")
    print()

    pct_auto = (stats['auto_coded'] / max(1, stats['total_rows'] - stats['already_coded'] - stats['fillers_skipped'])) * 100
    print(f"Auto-coded (high confidence): {stats['auto_coded']} ({pct_auto:.0f}%)")
    print(f"Needs AI review: {stats['needs_ai']}")

    if stats['auto_coded_rows']:
        print("\n── Auto-coded rows ──────────────────────────")
        for item in stats['auto_coded_rows'][:15]:  # Show first 15
            print(f"  Row {item['row']}: {item['code']} ({', '.join(item['matches'])})")
        if len(stats['auto_coded_rows']) > 15:
            print(f"  ... and {len(stats['auto_coded_rows']) - 15} more")

    if stats['needs_ai_rows']:
        print("\n── Rows with hints (for AI) ─────────────────")
        for item in stats['needs_ai_rows'][:10]:
            hints = ', '.join(item['hints'])
            print(f"  Row {item['row']}: suggests {item['suggested'] or 'unclear'} ({hints})")
        if len(stats['needs_ai_rows']) > 10:
            print(f"  ... and {len(stats['needs_ai_rows']) - 10} more")

    if stats['quotable_candidates']:
        print("\n── Possible quotables ───────────────────────")
        for item in stats['quotable_candidates'][:5]:
            print(f"  Row {item['row']}: \"{item['utterance']}\"")

    print("\n" + "=" * 60)
    if stats['applied']:
        print("Changes APPLIED to transcript.")
    else:
        print("DRY RUN - no changes made. Use --apply to write changes.")
    print("=" * 60 + "\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    transcript_path = sys.argv[1]
    apply = '--apply' in sys.argv

    if not Path(transcript_path).exists():
        print(f"Error: File not found: {transcript_path}")
        sys.exit(1)

    try:
        stats = process_transcript(transcript_path, apply=apply)
        print_report(stats)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
