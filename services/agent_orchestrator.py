"""Multi-agent research workflow orchestrator.

Implements a LangGraph-style stateful pipeline:
  Router → Retrieval → Synthesis → Critic → Writer

State is a plain dict passed between agents. Each agent mutates only its
own fields and never overwrites fields owned by other agents.
"""

import uuid
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from services.research_agents import (
    RouterAgent,
    RetrievalAgent,
    SynthesisAgent,
    CriticAgent,
    WriterAgent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State factory
# ---------------------------------------------------------------------------

def _initial_state(query: str, mode: str, paper_id: Optional[str]) -> dict:
    return {
        "session_id": str(uuid.uuid4()),
        "query": query,
        "mode": mode,
        "paper_id": paper_id,
        "workflow_type": None,
        "retrieved_chunks": [],
        "synthesis": "",
        "critique": {},
        "final_response": "",
        "agent_log": [],
        "agent_states": {
            "router": {"status": "pending", "output": None, "error": None},
            "retrieval": {"status": "pending", "output": None, "error": None},
            "synthesis": {"status": "pending", "output": None, "error": None},
            "critic": {"status": "pending", "output": None, "error": None},
            "writer": {"status": "pending", "output": None, "error": None},
        },
        "provenance_hash": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "iterations": 0,
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class AgentOrchestrator:
    """
    Orchestrates the multi-agent research workflow.

    Parameters
    ----------
    hf_token : str | None
        Hugging Face API token forwarded to all LLM-backed agents.
    chroma_collection :
        ChromaDB collection instance shared with the Flask app.
    papers_store : dict
        The module-level ``papers`` dict from app.py (passed by reference).
    """

    def __init__(
        self,
        hf_token: Optional[str],
        chroma_collection,
        papers_store: dict,
    ):
        self.router = RouterAgent(hf_token)
        self.retrieval = RetrievalAgent(chroma_collection, papers_store)
        self.synthesis = SynthesisAgent(hf_token, papers_store)
        self.critic = CriticAgent(hf_token)
        self.writer = WriterAgent(hf_token)

    def run(
        self,
        query: str,
        mode: str,
        paper_id: Optional[str] = None,
    ) -> dict:
        """
        Execute the full agent pipeline and return the final state.

        The pipeline is:
            router → retrieval → synthesis → critic → writer

        A failure in the router or retrieval sets ``state["error"]`` and
        short-circuits the pipeline. Critic / writer failures are non-fatal
        and degrade gracefully (passthrough of prior stage output).
        """
        state = _initial_state(query, mode, paper_id)

        try:
            state = self.router.run(state)
            if state.get("error"):
                return self._finalize(state)

            state = self.retrieval.run(state)
            if state.get("error"):
                return self._finalize(state)

            state = self.synthesis.run(state)
            if state.get("error"):
                return self._finalize(state)

            # Critic failure is non-fatal – state already has fallback critique
            state = self.critic.run(state)

            # Writer failure falls back to raw synthesis
            state = self.writer.run(state)

        except Exception as exc:
            logger.error("Unexpected orchestrator error: %s", exc, exc_info=True)
            state["error"] = f"Orchestrator error: {exc}"
            if not state.get("final_response"):
                state["final_response"] = state.get("synthesis", "")

        return self._finalize(state)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _finalize(self, state: dict) -> dict:
        """Attach a provenance hash and return the completed state."""
        state["provenance_hash"] = self._hash_state(state)
        return state

    @staticmethod
    def _hash_state(state: dict) -> str:
        content = (
            f"{state['session_id']}:"
            f"{state['query']}:"
            f"{state.get('final_response', '')}"
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
