# Services — Back-End Business Logic

This folder contains all the Python modules that power ResearchRadar's intelligence. Each file has a single, well-defined job. Flask (`app.py`) acts as the coordinator and calls into these services as needed.

---

## File-by-File Guide

### `paper_ml.py` — Section Classifier & Summariser

**What it does in plain English:**  
When you upload a paper, this service reads each paragraph and answers three questions:
1. *What kind of section is this?* (Abstract? Methods? Results?) — using a zero-shot AI classifier (`facebook/bart-large-mnli`)
2. *Does this paragraph mention any limitations or caveats?* — using pattern matching plus an LLM fallback
3. *Can you summarise this section in a sentence or two?* — using Meta-Llama-3

**Key class:** `PaperMLService`  
**Triggered by:** the "Run ML Analysis" button in the Paper Analysis tab  
**Falls back gracefully** when the `HF_TOKEN` environment variable is absent — returns empty results rather than crashing.

---

### `research_agents.py` — The Five AI Agents

**What it does in plain English:**  
Defines five specialist AI workers. Each one receives a shared "state" dictionary (think of it as a shared notepad), does its job, writes its output back, and passes the notepad to the next agent.

| Agent | Job |
|---|---|
| **RouterAgent** | Reads the user's query and decides which type of workflow to run (synthesis, methodology comparison, gap analysis, or Q&A). |
| **RetrievalAgent** | Searches the ChromaDB vector database for the most relevant paper paragraphs. Returns up to 6 matching chunks. |
| **SynthesisAgent** | Reads the retrieved paragraphs and writes a structured answer using Meta-Llama-3. |
| **CriticAgent** | Reviews the draft answer and returns a JSON critique: confidence level (high/medium/low), quality score (0–10), weak claims, missing evidence, and methodological gaps. |
| **WriterAgent** | If the Critic flagged weak claims, the Writer rewrites and polishes the final response. Otherwise passes the synthesis through unchanged. |

**Every agent is fault-tolerant:** if the LLM call fails or the token is missing, the agent marks itself as "skipped" and the pipeline continues.

---

### `agent_orchestrator.py` — The Pipeline Runner

**What it does in plain English:**  
This is the traffic controller. It creates the shared state, runs each agent in order (Router → Retrieval → Synthesis → Critic → Writer), handles short-circuits if an early agent fails critically, and computes a final provenance hash so you can verify the output later.

**Key class:** `AgentOrchestrator`  
**Key method:** `run(query, mode, paper_id)` — returns the full state dict which is sent back to the browser as JSON.

```
Router        determines workflow type
   ↓
Retrieval     fetches relevant paragraphs from ChromaDB
   ↓
Synthesis     writes a first-draft answer
   ↓
Critic        scores and critiques the draft
   ↓
Writer        optionally refines weak points
   ↓
Final state   returned to Flask → sent to the browser
```

**Triggered by:** the "Run Agent Workflow" button in the Agent Workflow tab.

---

### `provenance_service.py` — The Tamper-Evident Ledger

**What it does in plain English:**  
Every time you upload a paper or an AI agent produces output, this service creates a "fingerprint" (SHA-256 hash) of the content and links it to the fingerprint of the previous event. This creates a chain — like links in a padlock chain. If anyone edits an old record, its fingerprint changes and the chain breaks, making tampering detectable.

**Three types of records:**
- `upload` — created automatically when you upload a paper
- `summary` — created when an agent produces a synthesis
- `agent_output` — created when a full agent-pipeline run completes

**Key method:** `verify_chain(paper_id)` — checks every link in the chain and returns `valid: true/false` with a message.

**Depends on:** `BlockchainService` and `IPFSService` (both optional).

---

### `ipfs_service.py` — Decentralised File Storage (Optional)

**What it does in plain English:**  
IPFS (InterPlanetary File System) is like a global, decentralised hard drive. When enabled, this service uploads the fingerprinted content of each paper to IPFS via the Pinata pinning service, and stores the resulting "address" (called a CID) in the provenance record.

**Two modes:**
- **Real mode:** requires `PINATA_API_KEY` and `PINATA_SECRET_KEY` environment variables. Calls the Pinata API.
- **Mock mode (default):** produces a deterministic fake CID derived from the content hash. Everything else in the system works identically — you just can't look the CID up on a real IPFS gateway.

---

### `blockchain_service.py` — Ethereum Anchoring (Optional)

**What it does in plain English:**  
Optionally writes provenance hashes onto an Ethereum-compatible blockchain, making them permanent and publicly auditable. A transaction hash is returned and stored in the provenance record.

**Two modes:**
- **Real mode:** requires the `web3` Python package plus `BLOCKCHAIN_RPC_URL`, `CONTRACT_ADDRESS`, and `BLOCKCHAIN_PRIVATE_KEY` environment variables.
- **Mock mode (default):** uses a local in-memory dictionary as a pretend ledger and produces deterministic fake transaction hashes. The provenance chain works fully in mock mode — blockchain is purely an optional extra layer of trust.

**Related contract:** see [`contracts/PaperProvenance.sol`](../contracts/README.md) for the on-chain registry definition.

---

## How the Services Connect

```
app.py (Flask)
    │
    ├── PaperMLService          ← classifies + summarises sections
    │
    ├── AgentOrchestrator
    │       └── research_agents.py  (Router, Retrieval, Synthesis, Critic, Writer)
    │
    └── ProvenanceService
            ├── IPFSService     ← pin content to IPFS (optional)
            └── BlockchainService  ← anchor hash on Ethereum (optional)
```

All services fail gracefully — missing credentials or unavailable APIs produce informative log warnings, not crashes.
