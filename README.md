# sufyanskills

Claude Code skills I built for design and research work, packaged as a plugin marketplace. Each skill is a self-contained SKILL.md (plus scripts where needed) that Claude Code loads automatically when the trigger conditions match.

## Install

```
/plugin marketplace add bookwormsuf/sufyanskills
/plugin install sufyanskills@sufyanskills
```

Manual alternative: copy any skill folder from `sufyanskills/skills/` into `~/.claude/skills/`.

## Prerequisites

Everything runs inside Claude Code. Some skills also need:

- **Playwright MCP** for capture-screenshots and landing-page-prototype (browser screenshots and live style extraction).
- **Figma MCP** only if you want capture-screenshots to upload into Figma. Optional.
- **Mobbin MCP** for mobbin-reference-sweep. Needs a paid Mobbin plan.
- **Python 3** for the research scripts. Standard library only, nothing to install.

fable-orchestrator delegates to three subagents named `search`, `build` and `think` (Haiku, Sonnet, Opus). Their definitions ship with this plugin under `sufyanskills/agents/`, so they are available once the plugin is installed.

## Skills

Two kinds of skill here. Some I have relied on for months across real projects. Others I am still trying, and the guidance for them is thinner. The Maturity column says which is which.

### Research

These follow the qualitative research cycle. Use them in this order. Synthesis itself is not a skill on purpose: finding the "so what" is still the researcher's job.

| Step | Skill | When to use it | Maturity |
|------|-------|----------------|----------|
| 1. Transcribe | research-transcribe | You have a raw transcript (SPEAKER_XX format) and want a clean, row-numbered markdown table in a participant folder. | Relied on |
| 1b. Spreadsheet route | transcript-to-csv | Same input, but you code in a spreadsheet instead of markdown. | Relied on |
| 2. Code | research-code | You have a codebook and want codes applied line by line, with unclear audio flagged and quotable moments marked. Runs transcripts in parallel for bigger studies. | Relied on |
| 3. Check coverage | research-coverage | Before writing a synthesis, or before deciding whether to recruit more. Shows which research questions or session phases have coded evidence behind them and which rest on one participant. | Trying |
| 4. Counter-bias | research-counter-bias | Before presenting findings. Fresh subagents read blinded transcripts and hunt for evidence against each theme, so they cannot anchor on your codes. | Trying |

### Design

| Skill | When to use it | Maturity |
|-------|----------------|----------|
| mobbin-reference-sweep | Collecting references before committing to a direction. Three different sweeps of Mobbin so you get genuinely different directions, not three takes on one idea. | Trying |
| explore-ui | You know the feature but not the interaction pattern. Generates several interactive HTML options side by side. | Trying |
| landing-page-prototype | You have a reference site and a brand brief. Studies the reference forensically (type, colour, layout, hover, motion) and rebuilds its system for your content. | Relied on |
| capture-screenshots | A prototype is running and you want its state recorded: locally, in Figma, or embedded in a PRD or changelog. | Relied on |

### Working

| Skill | When to use it | Maturity |
|-------|----------------|----------|
| fable-orchestrator | Multi-phase work where a top-tier model should plan and cheaper models should do the checkable parts. | Relied on |
| link-pass | Keeping an Obsidian-style vault's wikilinks healthy after a writing session. Assumes people/, projects/, learnings/, notes/ folders. | Trying |

Each skill's SKILL.md lists its exact trigger phrases.

## Credits

explore-ui is adapted from an Anthropic demo skill.

## Licence

MIT. See LICENSE.
