# mobbin-reference-sweep

A Claude skill that collects design references on Mobbin using a three-sweep method, so you end up
with genuinely different directions instead of three versions of the same idea.

## What it does

Most reference hunting goes: search once, find the conventional answer, stop. You get three
screenshots of the same concept and call it exploration.

This searches the same problem three different ways:

1. **In-industry** — who solves this for people like ours? Finds the convention you'd be breaking.
2. **Out-of-industry** — who solves this same job somewhere completely different? Finds mechanisms
   that aren't conventional in your category yet.
3. **Metaphor** — what else is this a kind of? Finds structural reframes. This is the one that
   produces real range, and the one everyone skips.

It also picks the right search unit for the grain of your problem (a flow question can't be answered
by screenshots of single screens), and applies a breadth test at the end: *if you changed your mind
about the winner, would any of the others still be on the table?* If not, you made variations.

Output is a shareable artifact with the screens, the exact query used for each sweep, and a summary
of the distinct directions.

## Install

Copy the folder into your skills directory:

```bash
cp -r mobbin-reference-sweep ~/.claude/skills/
```

Then start a new Claude Code session. Check it registered with `/` — you should see
`mobbin-reference-sweep` in the list.

## Requirements

- **Mobbin MCP** connected, which needs a paid Mobbin plan. Setup: https://docs.mobbin.com/mcp/introduction
- **curl** — already on macOS and Linux. Used to download screen images.
- **Python 3** — already on macOS and Linux. No pip packages needed.

If the Mobbin MCP isn't available, the skill says so and offers to run the same three sweeps as web
searches instead. The method is worth more than the tool and transfers to any source.

## Usage

Just ask for references in whatever way is natural:

- "find me references for how apps handle picking a time slot"
- "how do other products do list-to-detail on mobile?"
- "I need inspiration for a filtering UI"
- "search Mobbin for pricing pages"

You don't need to name the skill or mention Mobbin.

## What's in here

```
mobbin-reference-sweep/
├── SKILL.md                      the workflow, loaded when the skill triggers
├── README.md                     this file
├── references/
│   └── query-patterns.md         how to write each sweep's query, with worked examples
└── scripts/
    └── build_artifact.py         builds the shareable HTML from the search results
```

## Notes for anyone modifying this

**There is no industry filter in the Mobbin MCP.** In the web app you'd toggle industry between
sweeps 1 and 2. Through the MCP you only get a natural-language query, so the sweeps are three
*query rewrites*, not three filter settings. That constraint is the whole reason
`references/query-patterns.md` exists.

**Platform is a required parameter with no "both" option.** That turns out to be useful rather than
annoying — searching the other platform is a legitimate out-of-context move when the job transfers,
since a task done under a thumb on a 390px screen has different pressures than the same task with a
mouse.

**`build_artifact.py` uses curl rather than Python's urllib on purpose.** Python on macOS often
ships without usable root certificates and raises `CERTIFICATE_VERIFY_FAILED` on valid URLs. curl is
everywhere and needs no install, which matters when people install this by copying a folder.

**Images are embedded as data URIs, not linked.** Two reasons: artifacts block remote images under
their content security policy, and Mobbin's `image_url` values are short-lived links. Embedding is
what keeps the artifact readable a month later.
