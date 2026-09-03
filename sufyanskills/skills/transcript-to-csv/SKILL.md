---
name: transcript-to-csv
description: "Convert interview/UX research transcripts into CSV files for qualitative coding analysis. Use when the user has a transcript with SPEAKER_XX: utterance format (markdown or plain text) and wants to create a spreadsheet for coding, tagging, or analysis. Triggers on: 'convert transcript to csv', 'parse transcript', 'create coding sheet from transcript', 'transcript for qualitative analysis', interview transcripts, UX research sessions."
---

# Transcript to CSV Skill

Converts interview transcripts into CSV format suitable for qualitative content analysis and coding.

## Input Formats Supported

**Markdown format:**
```
**SPEAKER_00**: This is what they said.
**SPEAKER_01**: And this is the response.
```

**Plain text format:**
```
SPEAKER_00: This is what they said.
SPEAKER_01: And this is the response.
```

## Output Format

CSV with these columns:
- `#` - Sequential utterance number (1, 2, 3...)
- `Speaker` - Speaker identifier (SPEAKER_00, SPEAKER_01, etc.)
- `Utterance` - The spoken text
- `Code 1` - Empty column for primary coding
- `Code 2` - Empty column for secondary coding
- `Notes` - Empty column for analyst notes

## How to Convert

### Option 1: Use the bundled script (recommended for large files)

```bash
cd /path/to/transcript/folder
bash scripts/parse-transcript.sh transcript.md output.csv
# scripts/parse-transcript.sh is resolved relative to this skill's folder
```

### Option 2: One-liner for markdown transcripts

```bash
echo '#,Speaker,Utterance,Code 1,Code 2,Notes' > output.csv && \
grep '^\*\*SPEAKER' transcript.md | \
awk -F': ' 'BEGIN{n=1} {
  speaker=$1;
  gsub(/\*\*/,"",speaker);
  utterance=$0;
  sub(/^[^:]+: /,"",utterance);
  gsub(/"/, "\"\"", utterance);
  print n","speaker",\""utterance"\",,,";
  n++
}' >> output.csv
```

### Option 3: One-liner for plain text transcripts

```bash
echo '#,Speaker,Utterance,Code 1,Code 2,Notes' > output.csv && \
grep '^SPEAKER' transcript.txt | \
awk -F': ' 'BEGIN{n=1} {
  speaker=$1;
  utterance=$0;
  sub(/^[^:]+: /,"",utterance);
  gsub(/"/, "\"\"", utterance);
  print n","speaker",\""utterance"\",,,";
  n++
}' >> output.csv
```

## Script Explanation

The parsing script does the following:

1. **`grep '^\*\*SPEAKER'`** - Find lines starting with `**SPEAKER` (markdown) or `SPEAKER` (plain text)
2. **`awk -F': '`** - Split each line on `: ` (colon-space)
3. **`gsub(/\*\*/,"",speaker)`** - Remove `**` markdown formatting from speaker name
4. **`sub(/^[^:]+: /,"",utterance)`** - Extract utterance text (everything after the first colon-space)
5. **`gsub(/"/, "\"\"", utterance)`** - Escape quotes by doubling them (CSV standard)
6. **Output** - Format as numbered CSV row with empty coding columns

## Workflow Tips

1. **Naming convention**: Use `P1-YYYY-MM-DD.csv` format for participant files
2. **Folder structure**: Keep transcript.md, summary.md, and the CSV in the same participant folder
3. **After conversion**: Open in Excel/Sheets to add codes in the empty columns
