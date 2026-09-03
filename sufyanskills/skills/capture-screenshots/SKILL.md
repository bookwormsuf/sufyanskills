---
name: capture-screenshots
description: Capture screenshots of a running prototype or web app using Playwright MCP, then save locally, upload to Figma, or embed in a markdown file. Use when the user says 'take screenshots', 'capture screenshots', 'screenshot the prototype', 'capture sprint', 'visual changelog', 'screenshot this for the PRD', 'record what the UI looks like', or mentions documenting prototype state for UTs, portfolio, PRDs, or design review. Also use when the user finishes a sprint or feature and wants to save the current state of the UI. Covers any web app on localhost or a URL.
---

# Capture Screenshots

Takes screenshots of a running web app using Playwright MCP tools, then saves them locally, uploads to Figma, or embeds references in a markdown file. Works with any web app on any URL.

## Arguments (all optional)

| Arg | Example | Default |
|-----|---------|---------|
| `--url <url>` | `http://localhost:5173` | Ask the user |
| `--output <path>` | `./screenshots/sprint-28` | Ask the user |
| `--figma <url>` | Figma file URL | Skip Figma upload |
| `--page <name>` | `"UT Round 1"` | Required if `--figma` used |
| `--label <text>` | `"Sprint 28 - Guided flow"` | Date + description |
| `--md <path>` | `./prd/README.md` | Skip markdown embedding |
| `--no-figma` | | Save locally only |

Example: `/capture-screenshots --url http://localhost:5173/admin/form/abc123 --output ./prd/screenshots --md ./prd/README.md`

## Phase 0: Preflight checks

Check each prerequisite in order. If any fails, tell the user exactly what to fix and stop.

### Check 1: Playwright MCP is available

Look for `mcp__playwright__browser_navigate` in your available tools.

**If not available:** Say "Playwright MCP is not connected. Start it in a separate terminal tab: `npm exec @playwright/mcp@latest`" and stop.

**If the tool exists but returns "Browser is already in use":** This means a previous session left a browser open. Do NOT kill Playwright processes. Instead, say: "The Playwright browser is locked by another session. Please restart the Playwright MCP server: kill the process in the terminal tab running it, then start it again with `npm exec @playwright/mcp@latest`."

This distinction matters. Killing MCP processes from the CLI removes the tools entirely and forces a fallback to fragile scripts. Always ask the user to restart the server instead.

### Check 2: The target URL is reachable

Call `mcp__playwright__browser_navigate` with the target URL.

**If it fails:** Say "Can't reach {url}. Is the dev server running?" and stop.

**If it loads a login page:** Playwright MCP opens a fresh Chromium instance with no saved cookies or sessions. Your existing Chrome login will NOT carry over. Say: "The app needs login. Playwright opened a new browser window with no saved sessions. Please log in using THAT browser window (not your regular Chrome), then tell me when you're ready." Wait for the user to confirm before continuing.

### Check 3: Destination

If the user hasn't specified where screenshots should go, ask:

"Where should I save the screenshots?"
- A local folder (provide path)
- Upload to Figma (provide Figma file URL and page name)
- Embed in a markdown file (provide .md file path)
- Any combination of the above

## Phase 1: Capture screenshots

### Viewport

Before capturing, set viewport to **1440x900** using `mcp__playwright__browser_resize` so screenshots are consistent across sessions.

### Naming

Number screenshots sequentially with zero-padded prefixes: `01-`, `02-`, etc. Use kebab-case descriptions: `01-intro-screen.png`, `02-guided-step1.png`.

### Multi-URL navigation

The user may want screenshots from different pages or routes within the same session (e.g. workflow tab, then settings page, then preview). Navigate freely between URLs using `browser_navigate` during the session. The browser session and cookies persist across navigations, so the user doesn't need to re-authenticate.

### Mode A: User-directed capture

Use this when the user describes specific screens or states to capture (e.g. "screenshot the intro screen, the guided flow, and the preview").

For each requested state:

1. **Snapshot first.** Call `mcp__playwright__browser_snapshot` to see the current accessibility tree. This shows you what elements exist and their `ref` IDs.
2. **Navigate using refs.** Use `mcp__playwright__browser_click` with the `ref` from the snapshot. Never guess at selectors or text content without snapshotting first.
3. **Wait for the UI to settle.** Call `mcp__playwright__browser_wait_for` with expected text, or wait 1-2 seconds for animations.
4. **Screenshot.** Call `mcp__playwright__browser_take_screenshot` and save with a descriptive filename.

**If navigation fails** (element not found, expected text doesn't appear): screenshot whatever is visible, log a warning, and continue to the next state. Don't abort the sequence. Report failures at the end.

**The snapshot-first rule is critical.** The most common failure mode is clicking elements by guessed text or selector without checking what's actually on the page. The accessibility snapshot tells you exactly what's there. Use it before every click.

#### Sequential flows

Some captures require navigating through a multi-step flow (e.g. a wizard with Continue buttons at each stage). For these:

- **Snapshot after every click.** The DOM changes at each stage. A ref that was valid before the click is stale afterward. Always re-snapshot to get fresh refs.
- **Verify advancement by content, not by click success.** A click on "Continue" might succeed but the UI might not advance (e.g. validation error). After clicking, snapshot again and check that new content appeared (a new section, different heading, changed text).
- **Same button text at every stage is normal.** When multiple stages use "Continue", don't try to find all Continue buttons at once. Snapshot, click the one visible Continue, snapshot again, repeat.
- **Screenshot at each meaningful state**, not just the final one. If the user asked for "screenshot the guided flow", that means each stage of the flow, not just the last screen.

### Mode B: Interactive capture

Use this when the user wants to navigate manually, or when the UI states are too complex to describe upfront.

1. Say: "I'll screenshot whatever you navigate to. Browse to each state you want to capture and say `capture` with a short description (e.g. 'capture intro screen'). Say `done` when finished."
2. On each `capture`:
   - `mcp__playwright__browser_take_screenshot`
   - Save as `{NN}-{description}.png`
   - Confirm: "Captured screenshot {N}: {description}."
3. On `done`, proceed to Phase 2.

## Phase 2: Save to destination

### Local folder

1. Create the output directory if it doesn't exist.
2. Screenshots are already saved during Phase 1. Confirm the path to the user.
3. List all captured files.

### Markdown embedding

If a `--md` target file was specified:

1. Read the target markdown file.
2. For each screenshot, find existing `<!-- Screenshot: {name} -->` placeholders and replace them with image references:
   ```markdown
   ![{description}](screenshots/{filename})
   ```
3. If no placeholders exist, append an image gallery at the `## Screenshots` heading if one exists, or at the end of the file.
4. Use relative paths from the markdown file to the screenshots folder.

### Figma upload

**Important: Before calling `mcp__figma__use_figma`, you MUST invoke the `/figma-use` skill first.** This is a mandatory prerequisite for the Figma MCP. Skipping it causes hard-to-debug failures.

**Step 1 - Create a frame for the screenshots:**

Use `mcp__figma__use_figma` on the target Figma file to:
- Find the page matching the `--page` argument
- Calculate Y position: find the lowest existing frame on the page, add 200px gap below it. If empty, start at Y=0.
- Create a parent frame named with the label (or `{date} - Screenshots`)
  - Horizontal auto-layout
  - Spacing: 40px between children
  - Padding: 40px
- Add a text node as the first child with the label
- Create child image frames (1440x900 each), one per screenshot, named after the screen

**Step 2 - Upload screenshots:**

For each screenshot:
1. Call `mcp__figma__upload_assets` with `count: 1`. The `nodeId` parameter does NOT reliably auto-apply the image fill.
2. Save the `imageHash` from the upload response.
3. After all uploads complete, call `mcp__figma__use_figma` to manually apply image fills:
   ```js
   node.fills = [{ type: 'IMAGE', scaleMode: 'FILL', imageHash: '<hash>' }];
   ```

Upload in parallel for speed. Collect all imageHashes, then apply them in a single `use_figma` call.

## Phase 3: Report

Print a summary:
```
Screenshots captured - {date}
  Total: {N} screenshots
  Saved to: {path}
  {Markdown: {md file} (if embedded)}
  {Figma page: {page name} (if uploaded)}

Files:
  1. {filename} - {description}
  2. {filename} - {description}
  ...
```

## Error handling

| Error | Response |
|-------|----------|
| Playwright MCP not available | "Start it: `npm exec @playwright/mcp@latest`" |
| Browser locked ("already in use") | "Restart Playwright MCP in its terminal tab. Do not kill processes from here." |
| URL not reachable | "Can't reach {url}. Is the dev server running?" |
| Login required | "Playwright opened a fresh browser. Log in using THAT window, not your regular Chrome. Tell me when ready." |
| Element not found during nav | Snapshot current state, log warning, continue |
| Figma auth failed | "Figma MCP auth failed. Re-authenticate and try again." |
| Upload fails | Log which screenshot failed, continue with rest, report at end |

## What NOT to do

These are failure modes learned from real sessions. They waste significant time.

1. **Never kill Playwright MCP processes.** This removes the MCP tools entirely. You lose `browser_navigate`, `browser_click`, `browser_snapshot`, and `browser_take_screenshot`. Ask the user to restart the server instead.

2. **Never fall back to Playwright scripts.** Writing standalone Node.js scripts with `require('playwright')` or `require('@playwright/test')` introduces a cascade of problems: missing packages, missing bundled browsers, no auth cookies, blind selectors. The MCP tools are the only reliable approach.

3. **Never click without snapshotting first.** `getByText('Workflow')` might match a paragraph, not a button. `browser_snapshot` shows you the actual DOM with clickable refs.

4. **Never clear localStorage to "reset" state.** This destroys the user's prototype data. If you need a clean state, ask the user to set it up.
