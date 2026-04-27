# Tests — Automated Test Suite

ResearchRadar has **96 automated tests** that verify every part of the back-end logic. They run in under 2 seconds and require no API keys or network access (all AI calls are mocked).

---

## Running the Tests

```bash
# From the project root
python -m pytest tests/ -v
```

Add `-q` for a shorter summary, or specify a single file:

```bash
python -m pytest tests/test_paper_ml.py -v
```

---

## Test Files Overview

### `test_paper_ml.py` — 27 tests

Covers `services/paper_ml.py`, the section classifier and summariser.

| Test Class | What It Checks |
|---|---|
| `TestLimitationPatterns` | The regex patterns correctly identify sentences about limitations, future work, and things the system cannot do |
| `TestPaperMLServiceInit` | When no API token is set, the service returns safe empty results rather than crashing |
| `TestClassifyChunk` | Section classification returns the right label, handles API errors gracefully, and truncates very long text |
| `TestDetectLimitations` | Limitation detection finds relevant sentences, ignores irrelevant sections, caps results at 10, and returns the expected data shape |
| `TestClassifySections` | Running classification over a whole paper enriches each section with ML labels while preserving existing fields |
| `TestAnalyzePaper` | The full analysis method returns all expected keys and calculates section distribution counts correctly |
| `TestFlaskEndpoints` | The Flask API endpoints (`/api/papers`, `/api/paper/<id>/ml-analysis`) return the right HTTP status codes and data shapes |

---

### `test_agent_orchestrator.py` — 34 tests

Covers `services/research_agents.py` and `services/agent_orchestrator.py`, the five-agent AI pipeline.

| Test Class | What It Checks |
|---|---|
| `TestInitialState` | The starting state dictionary has all required keys and every agent begins in "pending" status |
| `TestRouterAgent` | Each query mode (synthesis, methodology, gap, Q&A) routes to the correct workflow type; paper-specific queries route correctly; unknown modes fall back to Q&A |
| `TestRetrievalAgent` | Successfully retrieves chunks from ChromaDB; handles empty queries; handles empty results; adds a paper ID filter when searching a specific paper; handles ChromaDB errors without crashing the pipeline |
| `TestSynthesisAgent` | Skips gracefully when no API token or no chunks are available; calls the LLM when chunks are present; handles LLM errors |
| `TestCriticAgent` | Skips when no token or empty synthesis; parses a valid JSON critique from the LLM; handles non-JSON responses; treats LLM errors as non-fatal |
| `TestWriterAgent` | Passes synthesis through unchanged when there are no weak claims or no token; calls the LLM to refine when weak claims are present; falls back to original synthesis on LLM error |
| `TestAgentOrchestrator` | Full pipeline returns the expected state structure; router and retrieval complete successfully; pipeline returns a state even on retrieval failure; provenance hash is deterministic for the same output; paper-specific workflow operates correctly |

---

### `test_provenance_service.py` — 35 tests

Covers `services/provenance_service.py`, `services/ipfs_service.py`, and `services/blockchain_service.py`.

| Test Class | What It Checks |
|---|---|
| `TestSha256Helper` | The `_sha256` helper returns a correct 64-character hex string; identical inputs produce identical hashes; different inputs produce different hashes |
| `TestProvenanceService` | Upload, summary, and agent-output records are created with the correct shape; records are stored per paper; the hash chain links correctly to the previous head; chain verification passes on a valid chain and fails after tampering; IPFS and blockchain calls are made when services are provided; failures in IPFS/blockchain are non-fatal |
| `TestIPFSService` | Mock mode returns a deterministic CID; real mode calls the Pinata API and returns the hash; API errors fall back to mock CID; the gateway URL is correct in both modes |
| `TestMockBlockchain` | The in-memory mock ledger produces transaction hashes; the same input always produces the same hash; different inputs produce different hashes; records are retrievable |
| `TestBlockchainService` | Mock mode is used when env vars are absent; mock mode produces consistent transaction hashes; real mode switches on when web3 is available and env vars are set; connection errors are handled gracefully |

---

## How Tests Avoid Real API Calls

All tests that involve AI models use `unittest.mock.patch` and `MagicMock` to replace the actual Hugging Face `InferenceClient` with a fake object. This means:

- Tests run offline — no internet connection required
- Tests are fast — no waiting for remote API responses
- Tests are deterministic — no flaky failures from rate limits or model changes
- No API token is consumed during testing

---

## Adding New Tests

Tests follow the standard `unittest.TestCase` pattern:

```python
class TestMyFeature(unittest.TestCase):
    def setUp(self):
        # set up shared state before each test
        pass

    def test_something_specific(self):
        result = my_function("input")
        self.assertEqual(result["key"], "expected_value")
```

Place new test files in the `tests/` folder with a `test_` prefix. pytest will discover them automatically.
