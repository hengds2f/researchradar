"""Individual research agent implementations.

Each agent accepts the shared workflow state dict, performs its role, and
returns the updated state. Agents mark themselves as running/completed/failed
in state["agent_states"][agent_name] so the orchestrator and UI can track
progress.
"""

import re
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from huggingface_hub import InferenceClient

logger = logging.getLogger(__name__)

LLM_MODEL = "meta-llama/Meta-Llama-3-8B-Instruct"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_agent(state: dict, agent: str, event: str) -> None:
    state["agent_log"].append({
        "agent": agent,
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Router Agent
# ---------------------------------------------------------------------------

class RouterAgent:
    """Classifies the user query and determines the workflow type."""

    WORKFLOW_MAP = {
        "synthesis": "cross_paper_synthesis",
        "methodology": "methodology_comparison",
        "gap": "gap_analysis",
        "qa": "general_qa",
    }

    def __init__(self, hf_token: Optional[str]):
        self._token = hf_token

    def run(self, state: dict) -> dict:
        agent_name = "router"
        state["agent_states"][agent_name]["status"] = "running"
        _log_agent(state, agent_name, "started")

        try:
            mode = state.get("mode", "qa")
            paper_id = state.get("paper_id")

            if paper_id:
                workflow_type = "paper_specific"
            else:
                workflow_type = self.WORKFLOW_MAP.get(mode, "general_qa")

            state["workflow_type"] = workflow_type
            state["agent_states"][agent_name]["status"] = "completed"
            state["agent_states"][agent_name]["output"] = {
                "workflow_type": workflow_type,
                "mode": mode,
            }
            _log_agent(state, agent_name, f"completed -> workflow={workflow_type}")

        except Exception as exc:
            state["agent_states"][agent_name]["status"] = "failed"
            state["agent_states"][agent_name]["error"] = str(exc)
            state["error"] = f"Router agent failed: {exc}"
            _log_agent(state, agent_name, f"failed: {exc}")

        return state


# ---------------------------------------------------------------------------
# Retrieval Agent
# ---------------------------------------------------------------------------

class RetrievalAgent:
    """Retrieves relevant chunks from ChromaDB based on the workflow type."""

    SECTION_FILTERS = {
        "cross_paper_synthesis": ["abstract", "results"],
        "methodology_comparison": ["methods"],
        "gap_analysis": ["discussion"],
        "general_qa": ["abstract", "introduction", "methods", "results", "discussion"],
        "paper_specific": ["abstract", "introduction", "methods", "results", "discussion"],
        # Legacy mode names
        "synthesis": ["abstract", "results"],
        "methodology": ["methods"],
        "gap": ["discussion"],
        "qa": ["abstract", "introduction", "methods", "results", "discussion"],
    }

    def __init__(self, collection, papers_store: dict):
        self._collection = collection
        self._papers = papers_store

    def run(self, state: dict) -> dict:
        agent_name = "retrieval"
        state["agent_states"][agent_name]["status"] = "running"
        _log_agent(state, agent_name, "started")

        try:
            workflow_type = state.get("workflow_type", "general_qa")
            mode = state.get("mode", "qa")
            query = state.get("query", "")
            paper_id = state.get("paper_id")

            valid_sections = (
                self.SECTION_FILTERS.get(workflow_type)
                or self.SECTION_FILTERS.get(mode)
                or ["abstract", "introduction", "methods", "results", "discussion"]
            )

            query_target = query.strip() or "general academic discussion"
            caller_session_id = state.get("caller_session_id")

            if paper_id and caller_session_id:
                where_filter = {
                    "$and": [
                        {"section_type": {"$in": valid_sections}},
                        {"paper_id": {"$eq": paper_id}},
                        {"session_id": {"$eq": caller_session_id}},
                    ]
                }
            elif paper_id:
                where_filter = {
                    "$and": [
                        {"section_type": {"$in": valid_sections}},
                        {"paper_id": {"$eq": paper_id}},
                    ]
                }
            elif caller_session_id:
                where_filter = {
                    "$and": [
                        {"section_type": {"$in": valid_sections}},
                        {"session_id": {"$eq": caller_session_id}},
                    ]
                }
            else:
                where_filter = {"section_type": {"$in": valid_sections}}

            results = self._collection.query(
                query_texts=[query_target],
                n_results=6,
                where=where_filter,
            )

            retrieved = []
            if results.get("documents") and results["documents"][0]:
                for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                    pid = meta.get("paper_id", "unknown")
                    title = self._papers.get(pid, {}).get("title", "Unknown")
                    retrieved.append({
                        "paper_id": pid,
                        "title": title,
                        "section_type": meta.get("section_type", "unknown"),
                        "content": doc,
                    })

            state["retrieved_chunks"] = retrieved
            state["agent_states"][agent_name]["status"] = "completed"
            state["agent_states"][agent_name]["output"] = {
                "chunk_count": len(retrieved),
                "chunk_ids": [
                    f"{c['paper_id']}_{c['section_type']}" for c in retrieved
                ],
            }
            _log_agent(state, agent_name, f"completed -> {len(retrieved)} chunks retrieved")

        except Exception as exc:
            state["agent_states"][agent_name]["status"] = "failed"
            state["agent_states"][agent_name]["error"] = str(exc)
            state["error"] = f"Retrieval agent failed: {exc}"
            _log_agent(state, agent_name, f"failed: {exc}")

        return state


# ---------------------------------------------------------------------------
# Synthesis Agent
# ---------------------------------------------------------------------------

class SynthesisAgent:
    """Generates a structured synthesis from retrieved chunks."""

    _SYSTEM_PROMPTS = {
        "synthesis": (
            "You are a research synthesis assistant. Analyze the provided sources and "
            "generate a structured synthesis identifying: (1) Common themes, "
            "(2) Key findings, (3) Points of agreement and disagreement. "
            "Be specific and cite sources."
        ),
        "cross_paper_synthesis": (
            "You are a research synthesis assistant. Analyze the provided sources and "
            "generate a structured synthesis identifying: (1) Common themes, "
            "(2) Key findings, (3) Points of agreement and disagreement. "
            "Be specific and cite sources."
        ),
        "methodology": (
            "You are a research methodology expert. Compare the methodologies of the "
            "provided sources. Output a structured Markdown comparison covering: "
            "approach, datasets, evaluation metrics, and key strengths/weaknesses."
        ),
        "methodology_comparison": (
            "You are a research methodology expert. Compare the methodologies of the "
            "provided sources. Output a structured Markdown comparison covering: "
            "approach, datasets, evaluation metrics, and key strengths/weaknesses."
        ),
        "gap": (
            "You are a research gap analyst. Identify limitations and research gaps "
            "in the provided text. Structure your response as: (1) Stated limitations, "
            "(2) Implicit gaps, (3) Suggested future directions."
        ),
        "gap_analysis": (
            "You are a research gap analyst. Identify limitations and research gaps "
            "in the provided text. Structure your response as: (1) Stated limitations, "
            "(2) Implicit gaps, (3) Suggested future directions."
        ),
    }
    _DEFAULT_PROMPT = (
        "You are a knowledgeable academic assistant. Answer the user's question "
        "using the provided source context. Be specific and cite sources."
    )
    _CITATION_RULE = (
        "\n\nCITATION RULE: Conclude with a References section citing all sources "
        "using the paper titles provided in the source blocks."
    )

    def __init__(self, hf_token: Optional[str], papers_store: dict):
        self._token = hf_token
        self._papers = papers_store
        self._client: Optional[InferenceClient] = None

    @property
    def _inference_client(self) -> InferenceClient:
        if self._client is None:
            self._client = InferenceClient(token=self._token)
        return self._client

    def run(self, state: dict) -> dict:
        agent_name = "synthesis"
        state["agent_states"][agent_name]["status"] = "running"
        _log_agent(state, agent_name, "started")

        try:
            chunks = state.get("retrieved_chunks", [])
            query = state.get("query", "")
            mode = state.get("mode", "qa")

            if not chunks:
                state["synthesis"] = (
                    "No relevant sections found for this query. "
                    "Please upload papers first or broaden your query."
                )
                state["agent_states"][agent_name]["status"] = "completed"
                state["agent_states"][agent_name]["output"] = {"synthesis_length": 0}
                _log_agent(state, agent_name, "completed (no chunks)")
                return state

            if not self._token:
                state["synthesis"] = (
                    "Synthesis unavailable: HF_TOKEN is not configured."
                )
                state["agent_states"][agent_name]["status"] = "completed"
                state["agent_states"][agent_name]["output"] = {"synthesis_length": 0}
                _log_agent(state, agent_name, "completed (no token)")
                return state

            context = self._build_context(chunks)
            system_prompt = (
                self._SYSTEM_PROMPTS.get(mode, self._DEFAULT_PROMPT)
                + self._CITATION_RULE
            )

            response = self._inference_client.chat_completion(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Context:\n{context}\n\nQuery: {query}"},
                ],
                max_tokens=1000,
                temperature=0.3,
            )

            synthesis_text = response.choices[0].message.content.strip()
            state["synthesis"] = synthesis_text
            state["agent_states"][agent_name]["status"] = "completed"
            state["agent_states"][agent_name]["output"] = {
                "synthesis_length": len(synthesis_text),
                "sources_used": list({c["paper_id"] for c in chunks}),
            }
            _log_agent(state, agent_name, f"completed -> {len(synthesis_text)} chars")

        except Exception as exc:
            state["agent_states"][agent_name]["status"] = "failed"
            state["agent_states"][agent_name]["error"] = str(exc)
            state["error"] = f"Synthesis agent failed: {exc}"
            _log_agent(state, agent_name, f"failed: {exc}")

        return state

    def _build_context(self, chunks: list) -> str:
        context = ""
        for i, c in enumerate(chunks):
            context += (
                f"\n\n--- Source [{i + 1}] "
                f"(Paper: {c['title']} | Section: {c['section_type']}) ---\n"
            )
            context += c["content"][:2000]
        return context


# ---------------------------------------------------------------------------
# Critic Agent
# ---------------------------------------------------------------------------

class CriticAgent:
    """Evaluates synthesis quality and identifies weaknesses."""

    _CRITIC_PROMPT = (
        "You are a rigorous academic peer reviewer. "
        "Review the following research synthesis and identify:\n"
        "1. Missing evidence or unsupported claims\n"
        "2. Methodological limitations not addressed\n"
        "3. Potential biases or alternative interpretations\n"
        "4. Confidence level (high/medium/low) with justification\n\n"
        "Return ONLY a JSON object with keys:\n"
        "- \"missing_evidence\": list of strings (max 3)\n"
        "- \"weak_claims\": list of strings (max 3)\n"
        "- \"methodological_gaps\": list of strings (max 3)\n"
        "- \"confidence_level\": \"high\"|\"medium\"|\"low\"\n"
        "- \"confidence_reason\": string\n"
        "- \"overall_quality_score\": integer 1-10\n\n"
        "Be concise. No additional explanation outside the JSON."
    )

    def __init__(self, hf_token: Optional[str]):
        self._token = hf_token
        self._client: Optional[InferenceClient] = None

    @property
    def _inference_client(self) -> InferenceClient:
        if self._client is None:
            self._client = InferenceClient(token=self._token)
        return self._client

    def run(self, state: dict) -> dict:
        agent_name = "critic"
        state["agent_states"][agent_name]["status"] = "running"
        _log_agent(state, agent_name, "started")

        synthesis = state.get("synthesis", "")

        if not synthesis or not self._token:
            state["critique"] = {
                "missing_evidence": [],
                "weak_claims": [],
                "methodological_gaps": [],
                "confidence_level": "medium",
                "confidence_reason": "Critic skipped – no synthesis or token",
                "overall_quality_score": 5,
            }
            state["agent_states"][agent_name]["status"] = "skipped"
            _log_agent(state, agent_name, "skipped")
            return state

        try:
            response = self._inference_client.chat_completion(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": self._CRITIC_PROMPT},
                    {
                        "role": "user",
                        "content": f"Synthesis to review:\n{synthesis[:3000]}",
                    },
                ],
                max_tokens=500,
                temperature=0.1,
            )

            raw = response.choices[0].message.content.strip()
            try:
                json_match = re.search(r"\{.*\}", raw, re.DOTALL)
                critique = json.loads(json_match.group() if json_match else raw)
            except (json.JSONDecodeError, AttributeError):
                critique = {
                    "missing_evidence": [],
                    "weak_claims": ["Critic could not parse structured response"],
                    "methodological_gaps": [],
                    "confidence_level": "medium",
                    "confidence_reason": raw[:200],
                    "overall_quality_score": 5,
                }

            state["critique"] = critique
            state["agent_states"][agent_name]["status"] = "completed"
            state["agent_states"][agent_name]["output"] = {
                "confidence_level": critique.get("confidence_level"),
                "quality_score": critique.get("overall_quality_score"),
            }
            _log_agent(
                state,
                agent_name,
                f"completed -> confidence={critique.get('confidence_level')}",
            )

        except Exception as exc:
            # Critic failure is non-fatal; store a minimal critique
            state["critique"] = {
                "missing_evidence": [],
                "weak_claims": [],
                "methodological_gaps": [],
                "confidence_level": "low",
                "confidence_reason": f"Critic error: {exc}",
                "overall_quality_score": 3,
            }
            state["agent_states"][agent_name]["status"] = "failed"
            state["agent_states"][agent_name]["error"] = str(exc)
            _log_agent(state, agent_name, f"failed (non-fatal): {exc}")

        return state


# ---------------------------------------------------------------------------
# Writer Agent
# ---------------------------------------------------------------------------

class WriterAgent:
    """Produces the final polished response, optionally refining the synthesis."""

    _REFINE_PROMPT = (
        "You are an academic writing assistant. Refine the following research "
        "synthesis to address the identified weaknesses. Do NOT add new information "
        "not present in the original synthesis. Keep citations intact. "
        "Maintain academic tone. Return the refined synthesis only."
    )

    def __init__(self, hf_token: Optional[str]):
        self._token = hf_token
        self._client: Optional[InferenceClient] = None

    @property
    def _inference_client(self) -> InferenceClient:
        if self._client is None:
            self._client = InferenceClient(token=self._token)
        return self._client

    def run(self, state: dict) -> dict:
        agent_name = "writer"
        state["agent_states"][agent_name]["status"] = "running"
        _log_agent(state, agent_name, "started")

        try:
            synthesis = state.get("synthesis", "")
            critique = state.get("critique", {})

            if not synthesis:
                state["final_response"] = "No synthesis available."
                state["agent_states"][agent_name]["status"] = "completed"
                state["agent_states"][agent_name]["output"] = {"method": "empty"}
                _log_agent(state, agent_name, "completed (empty synthesis)")
                return state

            weak_claims = critique.get("weak_claims", [])

            # Skip refinement if no token or no weak claims identified
            if not self._token or not weak_claims:
                state["final_response"] = synthesis
                state["agent_states"][agent_name]["status"] = "completed"
                state["agent_states"][agent_name]["output"] = {"method": "passthrough"}
                _log_agent(state, agent_name, "completed (passthrough)")
                return state

            weak_points = "\n".join(f"- {w}" for w in weak_claims[:2])
            user_content = (
                f"Original synthesis:\n{synthesis}\n\n"
                f"Weaknesses to address:\n{weak_points}\n\n"
                "Please provide the refined synthesis."
            )

            response = self._inference_client.chat_completion(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": self._REFINE_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=1200,
                temperature=0.2,
            )

            final = response.choices[0].message.content.strip()
            state["final_response"] = final
            state["agent_states"][agent_name]["status"] = "completed"
            state["agent_states"][agent_name]["output"] = {
                "method": "refined",
                "final_length": len(final),
            }
            _log_agent(state, agent_name, f"completed (refined) -> {len(final)} chars")

        except Exception as exc:
            # Fallback to unrefined synthesis
            state["final_response"] = state.get("synthesis", "")
            state["agent_states"][agent_name]["status"] = "failed"
            state["agent_states"][agent_name]["error"] = str(exc)
            _log_agent(state, agent_name, f"failed (fallback to synthesis): {exc}")

        return state
