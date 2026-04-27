"""Scientific paper ML analysis service.

Uses the HuggingFace Inference API for:
  - Zero-shot section classification (facebook/bart-large-mnli acting as a
    SciBERT-style scientific-text classifier via NLI)
  - Limitation detection (regex pattern matching + Llama-3 LLM fallback)
  - Per-section abstractive summarization (Llama-3)

All inference calls are lazy-evaluated, cached on the paper dict, and fail
gracefully when the HF token is absent or the API is unavailable.
"""

import re
import json
from typing import Optional

from huggingface_hub import InferenceClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SECTION_LABELS = [
    "abstract",
    "introduction",
    "related work",
    "methodology",
    "results",
    "discussion",
    "conclusion",
]

# Sentence-level patterns that signal methodological limitations
_LIMIT_PATTERNS = [
    re.compile(
        r"\b(limitation|limitations|shortcoming|shortcomings|constraint|constraints"
        r"|drawback|drawbacks|weakness|weaknesses|caveat|caveats)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(future work|future research|further research|further study"
        r"|open question|open problem|remains to be)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(does not|cannot|unable to|failed to|lack of|lacking"
        r"|insufficient|not considered|not addressed|not captured)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(only limited|limited to|restricted to|small sample|small dataset"
        r"|single domain|narrow|generalisability|generalizability)\b",
        re.IGNORECASE,
    ),
]

# Models used via HF Inference API (no local weights required)
CLASSIFIER_MODEL = "facebook/bart-large-mnli"
LLM_MODEL = "meta-llama/Meta-Llama-3-8B-Instruct"


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class PaperMLService:
    """Orchestrates ML analysis of academic paper sections."""

    def __init__(self, hf_token: Optional[str]):
        self._token = hf_token
        self._client: Optional[InferenceClient] = None

    @property
    def _inference_client(self) -> InferenceClient:
        if self._client is None:
            self._client = InferenceClient(token=self._token)
        return self._client

    # ------------------------------------------------------------------
    # Section classification
    # ------------------------------------------------------------------

    def classify_chunk(self, text: str) -> dict:
        """Zero-shot classify one text chunk into a scientific paper section.

        Uses bart-large-mnli (NLI-based zero-shot) which generalises well to
        scientific vocabulary – a practical proxy for a fine-tuned SciBERT
        classifier when no labelled training set is available in this Space.

        Returns a dict with keys: label, confidence, all_scores, [error].
        Falls back to {'label': 'unknown', 'confidence': 0.0} on any error.
        """
        if not self._token:
            return {"label": "unknown", "confidence": 0.0, "all_scores": {}}

        try:
            result = self._inference_client.zero_shot_classification(
                text[:512],
                labels=SECTION_LABELS,
                model=CLASSIFIER_MODEL,
            )
            # huggingface_hub >= 0.20 returns a ZeroShotClassificationOutput
            # with .labels / .scores; older versions return List[ClassificationOutput]
            if isinstance(result, list):
                top = result[0]
                return {
                    "label": top.label,
                    "confidence": round(float(top.score), 4),
                    "all_scores": {r.label: round(float(r.score), 4) for r in result},
                }
            labels = result.labels
            scores = result.scores
            return {
                "label": labels[0],
                "confidence": round(float(scores[0]), 4),
                "all_scores": {l: round(float(s), 4) for l, s in zip(labels, scores)},
            }
        except Exception as exc:
            return {
                "label": "unknown",
                "confidence": 0.0,
                "all_scores": {},
                "error": str(exc),
            }

    def classify_sections(self, sections: list) -> list:
        """Return the sections list enriched with ml_label and ml_confidence."""
        classified = []
        for s in sections:
            cls = self.classify_chunk(s.get("content", ""))
            classified.append(
                {
                    **s,
                    "ml_label": cls["label"],
                    "ml_confidence": cls["confidence"],
                    "ml_all_scores": cls.get("all_scores", {}),
                }
            )
        return classified

    # ------------------------------------------------------------------
    # Limitation detection
    # ------------------------------------------------------------------

    def detect_limitations(self, sections: list) -> list:
        """Extract limitation sentences in two stages.

        Stage 1 – Fast regex scan over discussion/conclusion/results chunks.
        Stage 2 – LLM extraction used only when pattern matching yields nothing.

        Returns a list of dicts: [{text, source}, ...] capped at 10 items.
        """
        limitations = []

        target_types = {"discussion", "conclusion", "results"}
        for s in sections:
            if s.get("section_type") not in target_types:
                continue
            sentences = re.split(r"(?<=[.!?])\s+", s.get("content", ""))
            for sent in sentences:
                if any(p.search(sent) for p in _LIMIT_PATTERNS):
                    clean = sent.strip()
                    if len(clean) > 30:
                        limitations.append({"text": clean, "source": "pattern"})

        # LLM fallback when pattern matching found nothing
        if not limitations and self._token:
            limitations = self._llm_extract_limitations(sections)

        return limitations[:10]

    def _llm_extract_limitations(self, sections: list) -> list:
        """Use Llama-3 to extract limitations from relevant paper sections."""
        parts = []
        for s in sections:
            if s.get("section_type") in ("discussion", "conclusion", "results"):
                parts.append(s.get("content", "")[:800])
        if not parts:
            return []

        context = "\n\n".join(parts[:3])
        try:
            resp = self._inference_client.chat_completion(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a research analyst. Extract the key methodological "
                            "limitations and constraints from the paper text. Return ONLY "
                            "a JSON array of strings, each string being one limitation "
                            "sentence. Maximum 5 items. No extra explanation."
                        ),
                    },
                    {"role": "user", "content": f"Text:\n{context}"},
                ],
                max_tokens=400,
                temperature=0.1,
            )
            raw = resp.choices[0].message.content.strip()
            try:
                items = json.loads(raw)
                if isinstance(items, list):
                    return [{"text": str(x), "source": "llm"} for x in items if x]
            except json.JSONDecodeError:
                pass
            return [{"text": raw[:400], "source": "llm"}]
        except Exception as exc:
            return [{"text": f"LLM extraction error: {exc}", "source": "error"}]

    # ------------------------------------------------------------------
    # Section summarization
    # ------------------------------------------------------------------

    def summarize_section(self, text: str, section_type: str) -> str:
        """Abstractive 2-3 sentence summary for one section via Llama-3."""
        if not self._token or not text.strip():
            return ""
        try:
            resp = self._inference_client.chat_completion(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"You are a research assistant. Summarise the "
                            f"{section_type} section of this academic paper "
                            f"in 2-3 concise sentences."
                        ),
                    },
                    {"role": "user", "content": text[:2000]},
                ],
                max_tokens=200,
                temperature=0.2,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            return f"Summary unavailable: {exc}"

    # ------------------------------------------------------------------
    # Full analysis pipeline
    # ------------------------------------------------------------------

    def analyze_paper(self, paper_id: str, sections: list) -> dict:
        """Run the full ML analysis pipeline on one paper.

        Steps:
          1. Classify each section chunk with zero-shot NLI.
          2. Detect limitation sentences (pattern + LLM).
          3. Generate abstractive summaries for abstract / results / discussion.
          4. Compute section label distribution.

        Returns a serialisable dict safe to JSON-encode and store in `papers`.
        """
        classified = self.classify_sections(sections)
        limitations = self.detect_limitations(sections)

        # Summarise priority sections (one summary per section type)
        section_summaries: dict = {}
        priority = {"abstract", "results", "discussion"}
        for s in classified:
            st = s.get("section_type", "")
            if st in priority and st not in section_summaries:
                section_summaries[st] = self.summarize_section(
                    s.get("content", ""), st
                )

        # Section label distribution (using ML labels)
        dist: dict = {}
        for s in classified:
            label = s.get("ml_label") or s.get("section_type", "unknown")
            dist[label] = dist.get(label, 0) + 1

        return {
            "paper_id": paper_id,
            "classified_sections": [
                {
                    "section_type": s.get("section_type"),
                    "ml_label": s.get("ml_label"),
                    "ml_confidence": s.get("ml_confidence"),
                    "ml_all_scores": s.get("ml_all_scores", {}),
                    "content_preview": s.get("content", "")[:200],
                }
                for s in classified
            ],
            "limitations": limitations,
            "section_summaries": section_summaries,
            "section_distribution": dist,
            "total_sections": len(classified),
        }
