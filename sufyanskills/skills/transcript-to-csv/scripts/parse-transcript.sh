#!/bin/bash
# parse-transcript.sh - Convert interview transcripts to CSV for qualitative coding
#
# Usage: parse-transcript.sh <input_file> [output_file]
#
# Supports:
#   - Markdown format: **SPEAKER_XX**: utterance
#   - Plain text format: SPEAKER_XX: utterance
#
# Output CSV columns: #,Speaker,Utterance,Code 1,Code 2,Notes

set -e

INPUT="$1"
OUTPUT="${2:-${INPUT%.*}.csv}"

if [ -z "$INPUT" ]; then
    echo "Usage: parse-transcript.sh <input_file> [output_file]"
    echo ""
    echo "Converts transcript to CSV for qualitative coding."
    echo "If output_file is not specified, uses input filename with .csv extension."
    exit 1
fi

if [ ! -f "$INPUT" ]; then
    echo "Error: File not found: $INPUT"
    exit 1
fi

# Detect format (markdown vs plain text)
if grep -q '^\*\*SPEAKER' "$INPUT"; then
    # Markdown format: **SPEAKER_XX**: text
    PATTERN='^\*\*SPEAKER'
    IS_MARKDOWN=1
else
    # Plain text format: SPEAKER_XX: text
    PATTERN='^SPEAKER'
    IS_MARKDOWN=0
fi

# Write CSV header
echo '#,Speaker,Utterance,Code 1,Code 2,Notes' > "$OUTPUT"

# Parse and convert
if [ "$IS_MARKDOWN" -eq 1 ]; then
    grep "$PATTERN" "$INPUT" | awk -F': ' 'BEGIN{n=1} {
        speaker=$1;
        gsub(/\*\*/,"",speaker);
        utterance=$0;
        sub(/^[^:]+: /,"",utterance);
        gsub(/"/, "\"\"", utterance);
        print n","speaker",\""utterance"\",,,";
        n++
    }' >> "$OUTPUT"
else
    grep "$PATTERN" "$INPUT" | awk -F': ' 'BEGIN{n=1} {
        speaker=$1;
        utterance=$0;
        sub(/^[^:]+: /,"",utterance);
        gsub(/"/, "\"\"", utterance);
        print n","speaker",\""utterance"\",,,";
        n++
    }' >> "$OUTPUT"
fi

# Report result
COUNT=$(wc -l < "$OUTPUT")
COUNT=$((COUNT - 1))  # Subtract header row
echo "Created $OUTPUT with $COUNT utterances"
