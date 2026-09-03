---
name: explore-ui
description: "Generate multiple interactive UI options for a feature so you can compare and pick the best approach before implementing. Use when the user says '/explore-ui', 'explore options for', 'show me different ways to', 'prototype options', 'compare UI approaches', 'what are the options for this UI', or wants to see multiple interaction patterns side-by-side before committing to one. Also use when the user is unsure which UI pattern fits best and wants to see alternatives. Do NOT use for building a single known component (use /prototype instead) or for non-UI work."
---

# Explore UI

Adapted from an Anthropic demo skill.

Generate N interactive HTML demos of different approaches to a UI feature. Compare them side-by-side. Pick the best one. Stop there.

This skill is about exploration and decision-making, not implementation. You produce throwaway demos that help the user choose an interaction pattern. Implementation happens separately.

## Workflow

### Step 1: Understand the feature

Read the user's request. Identify:
- **What feature** they want to explore (e.g., "autocomplete for the search bar")
- **How many options** they want (default: 3, respect any number they give)
- **Any constraints** they mention (e.g., "accessible", "mobile-first", "match our existing dropdown style")
- **Research request** — only search the web if the user explicitly asks (e.g., "look at how Linear does it", "research existing patterns"). Don't research by default.

### Step 2: Capture visual context from Storybook

The HTML demos need to look like they belong in the actual product. Reading source code is not enough for this. You need to see the rendered components.

**If the project has a Storybook:**

1. Check if Storybook is already running at `localhost:6006`. Use Playwright to navigate there.
2. If it's not running, start it:
   - Check `package.json` for a storybook script and run it
   - Wait for it to be ready (poll `localhost:6006` until it responds)
3. Use Playwright to browse stories related to the feature you're exploring. Take screenshots of:
   - Components that will appear in your demos (buttons, inputs, cards, modals, etc.)
   - The overall visual language (colors, spacing, border radii, typography)
4. Extract the design tokens you see: primary colors, font family, border radius values, spacing rhythm, shadow style.

**If no Storybook exists**, fall back to reading the codebase's frontend code (theme files, component files). Keep it to 5-6 file reads max.

**Use what you capture.** The HTML demos must use the same colors, fonts, border radii, and spacing you saw in Storybook. Match the product's visual feel, not generic web defaults. This is the whole point of this step. If your demos don't look like they belong in the app, this step failed.

### Step 3: Plan the variations

Before generating any HTML, write out a brief plan listing each option:

```
Option 1: [Name] — [One sentence describing the interaction pattern]
Option 2: [Name] — [One sentence describing the interaction pattern]
Option 3: [Name] — [One sentence describing the interaction pattern]
```

Each option should represent a **meaningfully different interaction pattern**, not just visual restyling of the same approach. If the feature genuinely only has 2 distinct approaches, generate 2. Don't pad with filler.

Show this plan to the user and wait for confirmation before generating. They may want to steer a specific direction or swap one out.

### Step 4: Generate the HTML demos

Generate all options in parallel using subagents. Each option is a **self-contained HTML file** that:
- Opens directly in a browser with zero build step
- Is fully interactive with realistic dummy data
- Uses CDN links for any libraries needed (Tailwind, Alpine.js, vanilla JS, etc.)
- Approximates the app's visual feel based on what you learned in Step 2 (colors, fonts, spacing)
- Is a working mini-app, not a static mockup

**File location:** Save all files to `.explore-ui/<feature-name>/` in the project directory.
```
.explore-ui/
  autocomplete/
    option-1-typeahead.html
    option-2-command-palette.html
    option-3-inline-ghost.html
    compare.html
```

Name each file descriptively: `option-<N>-<short-name>.html`.

**Important:** Check that `.explore-ui/` is in the project's `.gitignore`. If not, add it.

### Step 5: Build the comparison page

Generate `compare.html` in the same directory. This is the primary review interface. Auto-open it in the browser when done.

The comparison page has:

**Navigation:**
- One tab per option (labeled with option name), showing a full-size iframe of that option
- An "All" tab showing all options in a side-by-side grid of iframes
- Active tab is visually distinct

**Ranking panel:**
- Collapsible panel (collapsed by default, toggle button visible)
- Contains Claude's ranking of all options: #1 through #N
- Each ranking entry has: option name, 1-2 sentence summary of the approach, key trade-offs (pros and cons)
- The recommended option is marked clearly
- Panel should not obscure the previews when expanded (sidebar or overlay)

**Styling:**
- The comparison page itself should be minimal and tool-like (dark toolbar, neutral colors)
- It's a review tool, not part of the product
- Iframes should be large enough to actually interact with the demos
- "All" tab grid: 2 columns for 2-3 options, 3 columns for 4-6 options

**Template structure:**
```html
<!DOCTYPE html>
<html>
<head>
  <title>Explore UI: [Feature Name]</title>
  <style>
    /* Dark, neutral toolbar styling */
    /* Tab navigation */
    /* Iframe container — full viewport height minus tabs */
    /* Side-by-side grid for "All" tab */
    /* Collapsible ranking panel */
  </style>
</head>
<body>
  <nav id="tabs">
    <!-- One tab per option + "All" tab -->
  </nav>
  <div id="ranking-panel">
    <!-- Claude's ranking, collapsible -->
  </div>
  <div id="preview-area">
    <!-- Iframes, one per option. Show/hide based on active tab -->
    <!-- "All" view: grid of all iframes -->
  </div>
  <script>
    // Tab switching logic
    // Ranking panel toggle
    // Auto-resize iframes
  </script>
</body>
</html>
```

After generating, open the comparison page:
```bash
open .explore-ui/<feature-name>/compare.html
```

### Step 6: Present and wait

Tell the user the comparison page is open. Briefly summarize your recommendation:

> "I generated 3 options. My recommendation is **Option 2 (Command Palette)** because [reason]. But Option 1 has [trade-off worth considering]. The comparison page is open — click through each tab to try them out. The ranking panel has full trade-offs.
>
> Which option do you want to go with? You can also ask me to tweak any option or combine approaches."

**Then stop.** Wait for the user to pick. Do not start implementing anything.

### Step 7: Handle follow-ups

The user may:
- **Pick an option** — Acknowledge the choice. Skill is done. The user will decide next steps.
- **Ask for a tweak** — e.g., "Make option 2's dropdown wider." Regenerate just that HTML file and refresh the comparison page.
- **Ask for a mashup** — e.g., "Combine the search from option 1 with the layout of option 3." Generate a new option HTML file, add it to the comparison page.
- **Ask for more options** — Generate additional options and add them.
- **Rerun entirely** — Start over from Step 3.

For tweaks and mashups, update only the affected files. Don't regenerate everything.

## What this skill does NOT do

- **Implement in the codebase.** This skill stops at option selection. Implementation is a separate step.
- **Generate production code.** The HTML demos are throwaway exploration tools.
- **Auto-research.** Only searches the web if the user explicitly asks.
- **Force iteration.** The user can pick immediately or request changes. Don't prompt "want to tweak anything?" every time.

## Tips for good options

- Each option should be something you could genuinely argue is the best approach. No strawmen.
- Name options by their interaction pattern, not "Option A/B/C." Names like "Typeahead Dropdown" vs "Command Palette" vs "Inline Ghost Text" make comparison meaningful.
- Dummy data should feel real. Names, dates, amounts that match the product domain.
- If the codebase uses a specific framework (React, Vue), the HTML demos don't need to use it. Vanilla JS or Alpine.js is fine for throwaway exploration. The point is feeling the interaction, not matching the tech stack.
- **Match the product's visual language.** Use the exact colors, fonts, border radii, and spacing you captured from Storybook. Generic-looking demos make it hard to evaluate how the feature will actually feel in the product. If the app uses Inter with 4px border radius and blue-600 primary, your demos should too.
