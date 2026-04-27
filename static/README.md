# Static — Front-End (Browser) Code

This folder contains everything the browser loads. There is no build step or bundler — the files are served directly by Flask.

---

## File Overview

| File | Role |
|---|---|
| `index.html` | The single HTML page. Defines the layout, navigation tabs, and every panel the user sees. |
| `app.js` | All browser-side logic — uploading files, calling the API, rendering results, updating the UI. |
| `styles.css` | All visual styling — colours, layout, animations, and component-specific styles. |

---

## `index.html` — The Page Shell

The app is a **single-page application (SPA)**: there is only one HTML file. Different "views" are just `<section>` elements that are shown or hidden by JavaScript.

### Five views (tabs)

| Tab / Section ID | What the user sees |
|---|---|
| `#synthesis-view` | Upload zone on the left, AI query panel on the right. The default landing view. |
| `#cluster-view` | An interactive D3.js force-directed graph showing papers grouped by semantic similarity. |
| `#analysis-view` | Section classification table, confidence bars, a horizontal bar chart, detected limitations, and section summaries for one paper at a time. |
| `#agents-view` | Agent Workflow — a query form on the left and a live pipeline visualiser with five step-dots (Router → Retrieval → Synthesis → Critic → Writer). The right panel shows the critique badge, quality score, and final response. |
| `#provenance-view` | Provenance Ledger — select a paper to see its full hash-chain history as a vertical timeline of cards. |

### External libraries loaded
- **D3.js v7** (`https://d3js.org/d3.v7.min.js`) — used for the clustering force graph and the section distribution bar chart.
- **marked.js** (`https://cdn.jsdelivr.net/npm/marked/marked.min.js`) — converts Markdown text returned by the AI into formatted HTML.

---

## `app.js` — Interaction Logic

The entire file is wrapped in a single `document.addEventListener('DOMContentLoaded', ...)` callback, which means it runs once the page has fully loaded.

### Key sections inside `app.js`

#### Navigation
Clicking a nav button calls `activateView(navButton, section)`, which removes the `active` class from all buttons, hides all sections, then shows the selected one.

#### File Upload
- Clicking the upload zone (the "+" box) triggers the hidden `<input type="file">`.
- Dragging a file onto the zone also works.
- On file selection, a `FormData` object is built and sent to `POST /api/upload`.
- The paper list on the left updates in real time with the new paper title and its detected sections.

#### AI Query (Synthesis tab)
- The "Generate Insights" button sends the query text and selected mode to `POST /api/query`.
- The response (Markdown text) is rendered into the result panel using `marked.parse()`.

#### D3 Clustering
- On first visit to the Clustering tab, `GET /api/clustering` is called.
- The returned nodes and links are drawn as a draggable force-directed graph using D3.js.

#### Paper Analysis
- The paper dropdown is populated from `GET /api/papers`.
- "Run ML Analysis" calls `POST /api/paper/<id>/ml-analysis`.
- Results are rendered as a section table (with confidence bars) and a D3 horizontal bar chart.

#### Agent Workflow
- "Run Agent Workflow" calls `POST /api/research/agent-run`.
- While waiting, the five pipeline step-dots show a pulsing animation.
- On response, each dot updates to green (completed), red (failed), or grey (skipped).
- The critique panel shows a confidence badge (`high`/`medium`/`low`), quality score, and colour-coded weakness tags.
- The final answer is rendered as Markdown.

#### Provenance Ledger
- "Load Provenance" calls `GET /api/provenance/<paperId>`.
- A chain integrity indicator shows either a green "✓ Chain Intact" or red "✗ Chain Compromised".
- Each event in the chain is displayed as a card with content hash, record hash, optional tx hash, and optional IPFS CID.

---

## `styles.css` — Visual Design

The stylesheet is organised into sections, in order:

1. **CSS variables** — colour palette, glass effect background, border colours
2. **Reset & base** — box-sizing, body, font
3. **Animated background blobs** — the subtle colour blobs floating behind the page
4. **Navbar** — sticky header with logo and nav buttons
5. **Layout** — `.container`, `.two-col-layout`, `.glass-panel`, `.col`
6. **Upload zone** — drag-and-drop area with hover state
7. **Paper list** — uploaded papers sidebar
8. **Query area** — form controls, textarea, select dropdowns
9. **Buttons** — `.btn-primary` with hover/active states
10. **Result panel** — Markdown output area, loading spinner
11. **D3 graph** — canvas sizing, node/link colours
12. **Paper Analysis** — section rows, confidence bars, chart container, badges
13. **Agent pipeline** — step dots with `pending / running / completed / failed / skipped` states, pulse animation
14. **Agent critique panel** — confidence badge colours (`high` = green, `medium` = amber, `low` = red), weakness tags
15. **Provenance** — chain status indicator, timeline cards colour-coded by event type
16. **Utility** — `.hidden`, `.empty-state`, `.markdown-body` Markdown typography

---

## No Build Step Required

Unlike many modern front-end projects, this app uses **no framework, no bundler, and no transpiler**. If you edit a `.css` or `.js` file, just refresh the browser. The changes take effect immediately.
