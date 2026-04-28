---
title: ResearchRadar
emoji: 🦉
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# ResearchRadar

ResearchRadar is an AI-powered Academic Paper Discovery and Synthesis Assistant. You upload research papers (PDF or plain text), and the app reads them, understands their structure, and lets you ask questions, compare findings, and trace the full history of every analysis — all through a clean web interface.

---

## What Does It Do?

| Feature | Plain-English Description |
|---|---|
| **Paper Upload** | Drop in a PDF or `.txt` file. The app splits it into sections (Abstract, Methods, Results, etc.) automatically. |
| **AI Synthesis** | Ask "What are the common findings?" and get a written answer with citations, powered by Meta-Llama-3. |
| **Methodology Comparison** | Get a Markdown table comparing how each paper approached its research. |
| **Research Gap Analysis** | The AI identifies limitations and open questions across your papers. |
| **Section Classifier** | Each paragraph is labelled with its scientific section type and a confidence score. |
| **Agent Workflow** | A five-step AI pipeline (Router → Retrieval → Synthesis → Critic → Writer) refines every answer before it reaches you. |
| **Provenance Ledger** | Every upload and AI output is stamped with a tamper-evident SHA-256 hash chain so you can verify nothing was changed. |
| **Clustering Map** | Papers are projected into 2-D using UMAP (or PCA fallback) and grouped with HDBSCAN (or KMeans fallback), then rendered as an interactive Plotly scatter map. Hover, click, filter, and highlight clusters. Falls back to TF-IDF vectors when sentence-transformer embeddings are unavailable. |

---

## How It Works — Big Picture

```
You (browser)
    │
    │  drag-drop PDF / ask a question
    ▼
Flask Web Server  (app.py)
    │
    ├── ChromaDB (vector database)  ←── stores paragraph embeddings for fast search
    │
    ├── PaperMLService              ←── classifies sections, detects limitations, summarises
    │
    ├── ClusteringService           ←── UMAP/PCA + HDBSCAN/KMeans, SHA-256 content cache
    │
    ├── AgentOrchestrator           ←── 5-agent AI pipeline
    │       Router → Retrieval → Synthesis → Critic → Writer
    │
    └── ProvenanceService           ←── tamper-evident hash chain
            ├── IPFSService         ←── optional decentralised file storage (Pinata)
            └── BlockchainService   ←── optional Ethereum anchoring (Web3.py)
```

The frontend is a single HTML page (`static/index.html`) with five tabs. Everything communicates with the server through a small REST API.

---

## Project Structure

```
ResearchRadar/
│
├── app.py                  # Main web server — all API routes live here
│
├── services/               # Back-end business logic
│   ├── paper_ml.py         # Section classification & summarisation
│   ├── clustering_service.py  # 2-D semantic map: UMAP/PCA + HDBSCAN/KMeans + cache
│   ├── research_agents.py  # Individual AI agent implementations
│   ├── agent_orchestrator.py  # Runs the 5-agent pipeline
│   ├── provenance_service.py  # Hash-chain provenance tracking
│   ├── ipfs_service.py     # IPFS via Pinata (optional)
│   └── blockchain_service.py  # Ethereum anchoring (optional)
│
├── contracts/
│   └── PaperProvenance.sol # Solidity smart contract (optional on-chain registry)
│
├── static/                 # Front-end (HTML + CSS + JavaScript)
│   ├── index.html          # Single-page app shell
│   ├── app.js              # All browser interaction logic
│   └── styles.css          # Visual styling
│
├── tests/                  # Automated tests (69 total)
│   ├── test_paper_ml.py
│   ├── test_agent_orchestrator.py
│   └── test_provenance_service.py
│
├── Dockerfile              # Container definition for Hugging Face Spaces
└── requirements.txt        # Python package dependencies
```

---

## Running Locally

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set your Hugging Face token
The AI features (synthesis, section classification, summarisation) call the
Hugging Face Inference API. You need a free token from https://huggingface.co/settings/tokens.

```bash
export HF_TOKEN=hf_your_token_here
```

### 3. Start the server
```bash
python app.py
# Open http://localhost:7860 in your browser
```

### 4. Run tests
```bash
python -m pytest tests/ -v
```

---

## Optional Features

These are disabled by default and need extra credentials:

| Feature | Environment Variable(s) | What It Does |
|---|---|---|
| Real IPFS storage | `PINATA_API_KEY`, `PINATA_SECRET_KEY` | Pins paper content to IPFS via Pinata |
| Ethereum anchoring | `BLOCKCHAIN_RPC_URL`, `CONTRACT_ADDRESS`, `BLOCKCHAIN_PRIVATE_KEY` | Anchors provenance hashes on-chain |
| Disable provenance | `PROVENANCE_ENABLED=false` | Turns off the hash chain entirely |
| Disable agents | `AGENT_ENABLED=false` | Turns off the multi-agent pipeline |

Without these, the app uses safe in-memory mocks automatically — no configuration needed to get started.

---

## Deploying to Hugging Face Spaces

This app is deployed at: **https://huggingface.co/spaces/hengds2f/researchradar**

The `Dockerfile` at the project root handles everything. Hugging Face Spaces builds it automatically on every `git push`.

To set your `HF_TOKEN` so the AI works inside the Space:
1. Go to the Space → **Settings → Variables and secrets**
2. Add a secret named `HF_TOKEN` with your token value
3. Wait ~1 minute for the Space to restart

---

## API Reference

| Method | Path | What It Does |
|---|---|---|
| `POST` | `/api/upload` | Upload one or more PDFs / text files |
| `POST` | `/api/query` | Ask a question across all uploaded papers |
| `GET` | `/api/papers` | List all uploaded papers |
| `GET` | `/api/clustering` | Compute and return the 2-D semantic map (points, clusters, stats, method) |
| `POST` | `/api/paper/<id>/ml-analysis` | Run section classification on one paper |
| `POST` | `/api/research/agent-run` | Run the full 5-agent workflow |
| `GET` | `/api/research/<id>/agent-state` | Get the last agent run result for a paper |
| `GET` | `/api/provenance/<id>` | Get provenance history + chain verification |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Web framework | Python / Flask 3 |
| Vector database | ChromaDB (in-memory) |
| AI models | Meta-Llama-3-8B-Instruct, facebook/bart-large-mnli (via HF Inference API) |
| Clustering | scikit-learn (TF-IDF / KMeans / TruncatedSVD), umap-learn (UMAP), hdbscan (HDBSCAN) |
| Frontend | HTML5, Vanilla JS, Plotly.js 2.32, D3.js v7, marked.js |
| Provenance | SHA-256 linked hash chain |
| Optional IPFS | Pinata API |
| Optional blockchain | Web3.py + Solidity (^0.8.19) |
| Containerisation | Docker |
| Hosting | Hugging Face Spaces |
