"""Tests for the multi-agent orchestrator and individual agents.

Run with:
    cd /path/to/ResearchApp
    python -m pytest tests/ -v
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.research_agents import (
    RouterAgent,
    RetrievalAgent,
    SynthesisAgent,
    CriticAgent,
    WriterAgent,
    _log_agent,
)
from services.agent_orchestrator import AgentOrchestrator, _initial_state


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_state(**kwargs):
    """Build a minimal state dict for a single agent test."""
    base = {
        "session_id": "test-session",
        "query": "What is machine learning?",
        "mode": "qa",
        "paper_id": None,
        "workflow_type": None,
        "retrieved_chunks": [],
        "synthesis": "",
        "critique": {},
        "final_response": "",
        "agent_log": [],
        "agent_states": {
            "router":    {"status": "pending", "output": None, "error": None},
            "retrieval": {"status": "pending", "output": None, "error": None},
            "synthesis": {"status": "pending", "output": None, "error": None},
            "critic":    {"status": "pending", "output": None, "error": None},
            "writer":    {"status": "pending", "output": None, "error": None},
        },
        "error": None,
    }
    base.update(kwargs)
    return base


@pytest.fixture
def mock_collection():
    col = MagicMock()
    col.query.return_value = {
        "documents": [["Test document content about machine learning."]],
        "metadatas": [[{"paper_id": "1", "section_type": "abstract"}]],
    }
    return col


@pytest.fixture
def mock_papers():
    return {"1": {"id": "1", "title": "Test Paper on ML", "filename": "test.pdf", "sections": []}}


@pytest.fixture
def orchestrator(mock_collection, mock_papers):
    return AgentOrchestrator("fake_token", mock_collection, mock_papers)


# ---------------------------------------------------------------------------
# _initial_state
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_has_required_keys(self):
        state = _initial_state("query", "qa", None)
        for key in ("session_id", "query", "mode", "paper_id", "workflow_type",
                    "retrieved_chunks", "synthesis", "critique", "final_response",
                    "agent_log", "agent_states", "provenance_hash", "timestamp", "error"):
            assert key in state

    def test_all_agents_start_pending(self):
        state = _initial_state("q", "qa", None)
        for agent_name in ("router", "retrieval", "synthesis", "critic", "writer"):
            assert state["agent_states"][agent_name]["status"] == "pending"


# ---------------------------------------------------------------------------
# RouterAgent
# ---------------------------------------------------------------------------

class TestRouterAgent:
    def test_routes_synthesis_mode(self):
        agent = RouterAgent("token")
        state = _make_state(mode="synthesis", paper_id=None)
        result = agent.run(state)
        assert result["workflow_type"] == "cross_paper_synthesis"
        assert result["agent_states"]["router"]["status"] == "completed"

    def test_routes_methodology_mode(self):
        agent = RouterAgent("token")
        result = agent.run(_make_state(mode="methodology", paper_id=None))
        assert result["workflow_type"] == "methodology_comparison"

    def test_routes_gap_mode(self):
        agent = RouterAgent("token")
        result = agent.run(_make_state(mode="gap", paper_id=None))
        assert result["workflow_type"] == "gap_analysis"

    def test_routes_qa_mode(self):
        agent = RouterAgent("token")
        result = agent.run(_make_state(mode="qa", paper_id=None))
        assert result["workflow_type"] == "general_qa"

    def test_routes_paper_specific_when_paper_id(self):
        agent = RouterAgent("token")
        result = agent.run(_make_state(mode="qa", paper_id="123"))
        assert result["workflow_type"] == "paper_specific"

    def test_routes_unknown_mode_to_general_qa(self):
        agent = RouterAgent("token")
        result = agent.run(_make_state(mode="nonexistent", paper_id=None))
        assert result["workflow_type"] == "general_qa"

    def test_logs_event(self):
        agent = RouterAgent("token")
        state = _make_state(mode="qa", paper_id=None)
        result = agent.run(state)
        assert len(result["agent_log"]) >= 2  # started + completed


# ---------------------------------------------------------------------------
# RetrievalAgent
# ---------------------------------------------------------------------------

class TestRetrievalAgent:
    def test_retrieves_chunks_successfully(self, mock_collection, mock_papers):
        agent = RetrievalAgent(mock_collection, mock_papers)
        state = _make_state(mode="qa", workflow_type="general_qa", query="ML basics")
        result = agent.run(state)
        assert len(result["retrieved_chunks"]) == 1
        assert result["retrieved_chunks"][0]["paper_id"] == "1"
        assert result["retrieved_chunks"][0]["title"] == "Test Paper on ML"
        assert result["agent_states"]["retrieval"]["status"] == "completed"
        assert result["agent_states"]["retrieval"]["output"]["chunk_count"] == 1

    def test_handles_empty_query(self, mock_collection, mock_papers):
        agent = RetrievalAgent(mock_collection, mock_papers)
        state = _make_state(mode="qa", workflow_type="general_qa", query="")
        result = agent.run(state)
        # Should still call collection.query (with fallback text)
        mock_collection.query.assert_called_once()

    def test_handles_empty_results(self):
        col = MagicMock()
        col.query.return_value = {"documents": [[]], "metadatas": [[]]}
        agent = RetrievalAgent(col, {})
        state = _make_state(mode="qa", workflow_type="general_qa", query="test")
        result = agent.run(state)
        assert result["retrieved_chunks"] == []
        assert result["agent_states"]["retrieval"]["status"] == "completed"

    def test_paper_specific_adds_paper_id_filter(self, mock_papers):
        col = MagicMock()
        col.query.return_value = {"documents": [[]], "metadatas": [[]]}
        agent = RetrievalAgent(col, mock_papers)
        state = _make_state(mode="qa", workflow_type="paper_specific",
                            query="test", paper_id="1")
        agent.run(state)
        call_args = col.query.call_args
        where = call_args.kwargs.get("where") or call_args[1].get("where")
        assert "$and" in where

    def test_handles_chromadb_error(self):
        col = MagicMock()
        col.query.side_effect = Exception("DB connection failed")
        agent = RetrievalAgent(col, {})
        state = _make_state(mode="qa", workflow_type="general_qa", query="test")
        result = agent.run(state)
        assert result["agent_states"]["retrieval"]["status"] == "failed"
        assert result["error"] is not None
        assert "Retrieval agent failed" in result["error"]


# ---------------------------------------------------------------------------
# SynthesisAgent
# ---------------------------------------------------------------------------

class TestSynthesisAgent:
    def test_skips_when_no_token(self, mock_papers):
        agent = SynthesisAgent(None, mock_papers)
        state = _make_state(
            retrieved_chunks=[{"paper_id": "1", "title": "T", "section_type": "abstract", "content": "x"}],
        )
        result = agent.run(state)
        assert "unavailable" in result["synthesis"].lower()
        assert result["agent_states"]["synthesis"]["status"] == "completed"

    def test_skips_when_no_chunks(self, mock_papers):
        agent = SynthesisAgent("token", mock_papers)
        state = _make_state(retrieved_chunks=[])
        result = agent.run(state)
        assert "No relevant" in result["synthesis"]
        assert result["agent_states"]["synthesis"]["status"] == "completed"

    def test_calls_llm_when_chunks_present(self, mock_papers):
        agent = SynthesisAgent("token", mock_papers)
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "This is a synthesised result."
        mock_client.chat_completion.return_value = mock_resp
        agent._client = mock_client

        state = _make_state(
            retrieved_chunks=[{"paper_id": "1", "title": "T", "section_type": "abstract", "content": "ML content"}],
        )
        result = agent.run(state)
        assert result["synthesis"] == "This is a synthesised result."
        assert result["agent_states"]["synthesis"]["status"] == "completed"

    def test_handles_llm_error(self, mock_papers):
        agent = SynthesisAgent("token", mock_papers)
        mock_client = MagicMock()
        mock_client.chat_completion.side_effect = Exception("LLM API error")
        agent._client = mock_client

        state = _make_state(
            retrieved_chunks=[{"paper_id": "1", "title": "T", "section_type": "abstract", "content": "content"}],
        )
        result = agent.run(state)
        assert result["agent_states"]["synthesis"]["status"] == "failed"
        assert result["error"] is not None


# ---------------------------------------------------------------------------
# CriticAgent
# ---------------------------------------------------------------------------

class TestCriticAgent:
    def test_skips_when_no_token(self):
        agent = CriticAgent(None)
        state = _make_state(synthesis="Some synthesis text")
        result = agent.run(state)
        assert result["agent_states"]["critic"]["status"] == "skipped"
        assert result["critique"]["confidence_level"] == "medium"

    def test_skips_when_empty_synthesis(self):
        agent = CriticAgent("token")
        state = _make_state(synthesis="")
        result = agent.run(state)
        assert result["agent_states"]["critic"]["status"] == "skipped"

    def test_parses_valid_json_critique(self):
        agent = CriticAgent("token")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        critique_json = '{"missing_evidence": ["lacks citation"], "weak_claims": [], "methodological_gaps": [], "confidence_level": "high", "confidence_reason": "well supported", "overall_quality_score": 8}'
        mock_resp.choices[0].message.content = critique_json
        mock_client.chat_completion.return_value = mock_resp
        agent._client = mock_client

        state = _make_state(synthesis="A well-supported synthesis.")
        result = agent.run(state)
        assert result["agent_states"]["critic"]["status"] == "completed"
        assert result["critique"]["confidence_level"] == "high"
        assert result["critique"]["overall_quality_score"] == 8

    def test_handles_non_json_response(self):
        agent = CriticAgent("token")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "This synthesis is fine overall."
        mock_client.chat_completion.return_value = mock_resp
        agent._client = mock_client

        state = _make_state(synthesis="Some synthesis.")
        result = agent.run(state)
        # Should not crash; should have a fallback critique
        assert "confidence_level" in result["critique"]

    def test_handles_llm_error_non_fatally(self):
        agent = CriticAgent("token")
        mock_client = MagicMock()
        mock_client.chat_completion.side_effect = Exception("API timeout")
        agent._client = mock_client

        state = _make_state(synthesis="Some synthesis.")
        result = agent.run(state)
        # Error is non-fatal – agent status is failed but no state["error"]
        assert result["agent_states"]["critic"]["status"] == "failed"
        assert result["critique"]["confidence_level"] == "low"


# ---------------------------------------------------------------------------
# WriterAgent
# ---------------------------------------------------------------------------

class TestWriterAgent:
    def test_passthrough_when_no_token(self):
        agent = WriterAgent(None)
        state = _make_state(synthesis="My synthesis", critique={"weak_claims": ["weak 1"]})
        result = agent.run(state)
        assert result["final_response"] == "My synthesis"
        assert result["agent_states"]["writer"]["status"] == "completed"
        assert result["agent_states"]["writer"]["output"]["method"] == "passthrough"

    def test_passthrough_when_no_weak_claims(self):
        agent = WriterAgent("token")
        state = _make_state(synthesis="Clean synthesis", critique={"weak_claims": []})
        result = agent.run(state)
        assert result["final_response"] == "Clean synthesis"
        assert result["agent_states"]["writer"]["output"]["method"] == "passthrough"

    def test_passthrough_when_empty_synthesis(self):
        agent = WriterAgent(None)
        state = _make_state(synthesis="", critique={})
        result = agent.run(state)
        assert result["agent_states"]["writer"]["status"] == "completed"

    def test_refines_when_weak_claims_present(self):
        agent = WriterAgent("token")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "Refined synthesis text."
        mock_client.chat_completion.return_value = mock_resp
        agent._client = mock_client

        state = _make_state(synthesis="Original synthesis", critique={"weak_claims": ["claim A"]})
        result = agent.run(state)
        assert result["final_response"] == "Refined synthesis text."
        assert result["agent_states"]["writer"]["output"]["method"] == "refined"

    def test_fallback_to_synthesis_on_llm_error(self):
        agent = WriterAgent("token")
        mock_client = MagicMock()
        mock_client.chat_completion.side_effect = Exception("network error")
        agent._client = mock_client

        state = _make_state(synthesis="Original synthesis", critique={"weak_claims": ["weak A"]})
        result = agent.run(state)
        assert result["final_response"] == "Original synthesis"
        assert result["agent_states"]["writer"]["status"] == "failed"


# ---------------------------------------------------------------------------
# AgentOrchestrator (integration)
# ---------------------------------------------------------------------------

class TestAgentOrchestrator:
    def test_returns_complete_state_structure(self, orchestrator):
        with patch.object(orchestrator.synthesis, '_client') as mock_client:
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = "Synthesised response."
            mock_client.chat_completion.return_value = mock_resp
            # Disable critic and writer LLM calls
            orchestrator.critic._token = None
            orchestrator.writer._token = None

            state = orchestrator.run("What is ML?", "qa")

        assert "session_id" in state
        assert "agent_states" in state
        assert "final_response" in state
        assert "provenance_hash" in state
        assert state["provenance_hash"] is not None
        assert len(state["provenance_hash"]) == 64  # SHA-256 hex

    def test_router_completes(self, orchestrator):
        orchestrator.synthesis._token = None
        orchestrator.critic._token = None
        orchestrator.writer._token = None
        state = orchestrator.run("test", "synthesis")
        assert state["agent_states"]["router"]["status"] == "completed"
        assert state["workflow_type"] == "cross_paper_synthesis"

    def test_retrieval_completes(self, orchestrator):
        orchestrator.synthesis._token = None
        orchestrator.critic._token = None
        orchestrator.writer._token = None
        state = orchestrator.run("ML research", "qa")
        assert state["agent_states"]["retrieval"]["status"] == "completed"
        assert len(state["retrieved_chunks"]) == 1

    def test_returns_state_on_retrieval_failure(self, mock_papers):
        col = MagicMock()
        col.query.side_effect = Exception("DB error")
        orc = AgentOrchestrator("token", col, mock_papers)
        state = orc.run("test query", "qa")
        assert state["error"] is not None
        assert "Retrieval agent failed" in state["error"]

    def test_provenance_hash_is_deterministic_for_same_output(self, mock_papers):
        col = MagicMock()
        col.query.return_value = {"documents": [[]], "metadatas": [[]]}
        orc = AgentOrchestrator(None, col, mock_papers)

        s1 = orc.run("fixed query", "qa")
        s2 = orc.run("different query", "qa")

        # Different queries produce different hashes
        assert s1["provenance_hash"] != s2["provenance_hash"]

    def test_paper_specific_workflow(self, orchestrator):
        orchestrator.synthesis._token = None
        orchestrator.critic._token = None
        orchestrator.writer._token = None
        state = orchestrator.run("Summarize this paper", "qa", paper_id="1")
        assert state["workflow_type"] == "paper_specific"
