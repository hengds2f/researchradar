# 09 · ResearchRadar
**Academic Paper Discovery and Synthesis Assistant**

---

## Problem Statement

Researchers and graduate students spend weeks conducting literature reviews, reading dozens of papers to synthesise findings on a topic. Tools like Google Scholar find papers but don't synthesise or compare methodologies and results across them.

---

## Research-Backed Implementation

Inspired by UC Berkeley MIDS capstone RAG projects and Elicit.org's research assistant, students build a system where users upload a corpus of academic PDFs. The app synthesises findings, compares methodologies, and identifies research gaps across the corpus.

---

## Solution Overview

Users upload a corpus of academic papers. The system parses each paper and chunks by section — Abstract, Methods, Results, and Discussion — storing section-type metadata alongside each embedding in the vector database. This enables targeted retrieval by section, so synthesis queries pull from Results sections while methodology comparisons pull from Methods sections. The LLM generates cross-paper summaries with per-paper attributions.

---

## Key Features

- Section-aware chunking: Abstract / Methods / Results / Discussion tagged separately
- Synthesis mode: "What are the common findings across these papers?"
- Methodology comparison table generation
- Research gap identification prompt
- Citation generation in APA/MLA format from extracted metadata
- Paper clustering by topic using cosine similarity scores

---

## Section-Aware Query Examples

| Query Mode | Supabase Filter | Purpose |
|---|---|---|
| Synthesis | `section_type IN ('abstract','results')` | Cross-paper findings |
| Methodology comparison | `section_type = 'methods'` | Compare approaches |
| Gap analysis | `section_type = 'discussion'` | Find limitations noted |
| Full-paper Q&A | No filter | General questions |

---

## Paper Clustering (Stretch Feature)

Using stored embeddings, compute cosine similarity between paper-level average embeddings and render a 2D cluster plot with D3.js force layout to visually show topic groupings across the uploaded corpus.

---

## Difficulty

🟠 **Advanced** — section-aware chunking, cross-paper synthesis, structured output formatting, and optional D3.js cluster visualisation make this a research-grade engineering challenge.

---

## Domain

Academic Research / Education
