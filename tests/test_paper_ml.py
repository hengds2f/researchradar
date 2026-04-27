"""Tests for services/paper_ml.py and the ML Flask endpoints.

Run with:
    cd /path/to/ResearchApp
    python -m pytest tests/ -v
"""

import json
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.paper_ml import PaperMLService, SECTION_LABELS, _LIMIT_PATTERNS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SECTIONS = [
    {
        "section_type": "abstract",
        "content": "This paper presents a novel approach to neural machine translation.",
    },
    {
        "section_type": "methods",
        "content": "We trained a transformer model on 1M sentence pairs using Adam optimizer.",
    },
    {
        "section_type": "results",
        "content": "Our model achieves a BLEU score of 32.4, surpassing the baseline by 2.1 points.",
    },
    {
        "section_type": "discussion",
        "content": (
            "A key limitation of our study is the small dataset size restricted to English-German pairs. "
            "Future work should address the generalizability of the model to low-resource languages. "
            "The model cannot handle domain-specific terminology effectively."
        ),
    },
]

MOCK_ZERO_SHOT_RESPONSE_LIST = [
    MagicMock(label="methodology", score=0.72),
    MagicMock(label="results", score=0.15),
    MagicMock(label="abstract", score=0.08),
    MagicMock(label="introduction", score=0.03),
    MagicMock(label="discussion", score=0.02),
]


# ---------------------------------------------------------------------------
# Unit tests – PaperMLService
# ---------------------------------------------------------------------------

class TestLimitationPatterns(unittest.TestCase):
    """Verify that _LIMIT_PATTERNS match limitation-indicating phrases."""

    def _any_match(self, text):
        return any(p.search(text) for p in _LIMIT_PATTERNS)

    def test_matches_limitation_keyword(self):
        self.assertTrue(self._any_match("A major limitation of this study is the small sample size."))

    def test_matches_future_work(self):
        self.assertTrue(self._any_match("Future work should explore multi-lingual settings."))

    def test_matches_cannot(self):
        self.assertTrue(self._any_match("The model cannot generalise to out-of-domain text."))

    def test_matches_restricted_to(self):
        self.assertTrue(self._any_match("Results are restricted to English-language corpora only."))

    def test_no_false_positive_on_plain_result(self):
        self.assertFalse(self._any_match("The model achieves state-of-the-art performance on all benchmarks."))


class TestPaperMLServiceInit(unittest.TestCase):
    def test_no_token_gives_unknown_classification(self):
        svc = PaperMLService(hf_token=None)
        result = svc.classify_chunk("Some scientific text about methodology.")
        self.assertEqual(result["label"], "unknown")
        self.assertEqual(result["confidence"], 0.0)

    def test_no_token_gives_empty_summary(self):
        svc = PaperMLService(hf_token=None)
        result = svc.summarize_section("Some results text.", "results")
        self.assertEqual(result, "")

    def test_no_token_pattern_limitations_still_work(self):
        """Pattern-based limitation detection does not need an API token."""
        svc = PaperMLService(hf_token=None)
        lims = svc.detect_limitations(SAMPLE_SECTIONS)
        self.assertGreater(len(lims), 0, "Should detect pattern-based limitations without a token")
        sources = {l["source"] for l in lims}
        self.assertIn("pattern", sources)


class TestClassifyChunk(unittest.TestCase):
    def setUp(self):
        self.svc = PaperMLService(hf_token="fake-token")

    def test_returns_top_label_from_list_response(self):
        with patch.object(
            PaperMLService, "_inference_client", new_callable=PropertyMock
        ) as mock_client_prop:
            mock_client = MagicMock()
            mock_client.zero_shot_classification.return_value = MOCK_ZERO_SHOT_RESPONSE_LIST
            mock_client_prop.return_value = mock_client

            result = self.svc.classify_chunk("We trained a transformer on 1M pairs.")

        self.assertEqual(result["label"], "methodology")
        self.assertAlmostEqual(result["confidence"], 0.72, places=2)
        self.assertIn("methodology", result["all_scores"])

    def test_handles_api_exception_gracefully(self):
        with patch.object(
            PaperMLService, "_inference_client", new_callable=PropertyMock
        ) as mock_client_prop:
            mock_client = MagicMock()
            mock_client.zero_shot_classification.side_effect = Exception("API timeout")
            mock_client_prop.return_value = mock_client

            result = self.svc.classify_chunk("Some text.")

        self.assertEqual(result["label"], "unknown")
        self.assertIn("error", result)

    def test_truncates_long_text(self):
        """Verify that texts longer than 512 chars are accepted without error."""
        long_text = "word " * 300  # 1500 chars
        with patch.object(
            PaperMLService, "_inference_client", new_callable=PropertyMock
        ) as mock_client_prop:
            mock_client = MagicMock()
            mock_client.zero_shot_classification.return_value = MOCK_ZERO_SHOT_RESPONSE_LIST
            mock_client_prop.return_value = mock_client

            result = self.svc.classify_chunk(long_text)

        # Confirm that zero_shot_classification was called with at most 512 chars
        call_args = mock_client.zero_shot_classification.call_args
        self.assertLessEqual(len(call_args[0][0]), 512)
        self.assertEqual(result["label"], "methodology")


class TestDetectLimitations(unittest.TestCase):
    def setUp(self):
        self.svc = PaperMLService(hf_token=None)  # no token – pattern only

    def test_detects_limitation_sentences(self):
        lims = self.svc.detect_limitations(SAMPLE_SECTIONS)
        self.assertGreater(len(lims), 0)

    def test_result_structure(self):
        lims = self.svc.detect_limitations(SAMPLE_SECTIONS)
        for lim in lims:
            self.assertIn("text", lim)
            self.assertIn("source", lim)
            self.assertGreater(len(lim["text"]), 30)

    def test_caps_at_ten(self):
        many_sections = [
            {
                "section_type": "discussion",
                "content": " ".join(
                    [f"Limitation {i}: the dataset cannot handle this case." for i in range(20)]
                ),
            }
        ]
        lims = self.svc.detect_limitations(many_sections)
        self.assertLessEqual(len(lims), 10)

    def test_ignores_non_target_sections(self):
        intro_only = [
            {"section_type": "introduction", "content": "This study has a limitation."},
        ]
        # Introduction is not in target types; pattern matching should skip it
        lims = self.svc.detect_limitations(intro_only)
        self.assertEqual(lims, [])


class TestClassifySections(unittest.TestCase):
    def test_enriches_sections_with_ml_fields(self):
        svc = PaperMLService(hf_token="fake")

        with patch.object(PaperMLService, "classify_chunk") as mock_classify:
            mock_classify.return_value = {
                "label": "methodology",
                "confidence": 0.85,
                "all_scores": {},
            }
            result = svc.classify_sections(SAMPLE_SECTIONS)

        self.assertEqual(len(result), len(SAMPLE_SECTIONS))
        for item in result:
            self.assertIn("ml_label", item)
            self.assertIn("ml_confidence", item)
            self.assertEqual(item["ml_label"], "methodology")

    def test_preserves_original_fields(self):
        svc = PaperMLService(hf_token="fake")
        with patch.object(PaperMLService, "classify_chunk") as mock_classify:
            mock_classify.return_value = {"label": "abstract", "confidence": 0.9, "all_scores": {}}
            result = svc.classify_sections(SAMPLE_SECTIONS)
        for orig, classified in zip(SAMPLE_SECTIONS, result):
            self.assertEqual(classified["section_type"], orig["section_type"])
            self.assertEqual(classified["content"], orig["content"])


class TestAnalyzePaper(unittest.TestCase):
    def test_returns_expected_keys(self):
        svc = PaperMLService(hf_token="fake")
        with patch.object(PaperMLService, "classify_sections") as mock_cls, \
             patch.object(PaperMLService, "detect_limitations") as mock_lim, \
             patch.object(PaperMLService, "summarize_section") as mock_sum:

            mock_cls.return_value = [
                {**s, "ml_label": "methodology", "ml_confidence": 0.8, "ml_all_scores": {}}
                for s in SAMPLE_SECTIONS
            ]
            mock_lim.return_value = [{"text": "Small dataset.", "source": "pattern"}]
            mock_sum.return_value = "A brief summary."

            result = svc.analyze_paper("1", SAMPLE_SECTIONS)

        self.assertIn("paper_id", result)
        self.assertIn("classified_sections", result)
        self.assertIn("limitations", result)
        self.assertIn("section_summaries", result)
        self.assertIn("section_distribution", result)
        self.assertIn("total_sections", result)
        self.assertEqual(result["paper_id"], "1")
        self.assertEqual(result["total_sections"], len(SAMPLE_SECTIONS))

    def test_section_distribution_counts(self):
        svc = PaperMLService(hf_token="fake")
        with patch.object(PaperMLService, "classify_sections") as mock_cls, \
             patch.object(PaperMLService, "detect_limitations") as mock_lim, \
             patch.object(PaperMLService, "summarize_section") as mock_sum:

            mock_cls.return_value = [
                {**SAMPLE_SECTIONS[0], "ml_label": "abstract", "ml_confidence": 0.9, "ml_all_scores": {}},
                {**SAMPLE_SECTIONS[1], "ml_label": "methodology", "ml_confidence": 0.8, "ml_all_scores": {}},
                {**SAMPLE_SECTIONS[2], "ml_label": "methodology", "ml_confidence": 0.7, "ml_all_scores": {}},
                {**SAMPLE_SECTIONS[3], "ml_label": "discussion", "ml_confidence": 0.6, "ml_all_scores": {}},
            ]
            mock_lim.return_value = []
            mock_sum.return_value = ""

            result = svc.analyze_paper("1", SAMPLE_SECTIONS)

        dist = result["section_distribution"]
        self.assertEqual(dist.get("methodology"), 2)
        self.assertEqual(dist.get("abstract"), 1)
        self.assertEqual(dist.get("discussion"), 1)


# ---------------------------------------------------------------------------
# Integration tests – Flask endpoints
# ---------------------------------------------------------------------------

class TestFlaskEndpoints(unittest.TestCase):
    def setUp(self):
        import app as flask_app
        flask_app.app.config["TESTING"] = True
        self.client = flask_app.app.test_client()
        # Reset global state
        flask_app.papers.clear()
        flask_app.collection = flask_app.chroma_client.get_or_create_collection(
            name="test_research_papers"
        )

    def test_list_papers_empty(self):
        res = self.client.get("/api/papers")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data["papers"], [])

    def test_paper_not_found_returns_404(self):
        res = self.client.post("/api/paper/999/ml-analysis")
        self.assertEqual(res.status_code, 404)

    def test_limitations_not_found_returns_404(self):
        res = self.client.get("/api/paper/999/limitations")
        self.assertEqual(res.status_code, 404)

    def test_sections_not_found_returns_404(self):
        res = self.client.get("/api/paper/999/sections")
        self.assertEqual(res.status_code, 404)

    def test_ml_analysis_returns_cached_result(self):
        import app as flask_app
        flask_app.papers["42"] = {
            "id": "42",
            "title": "Test Paper",
            "filename": "test.pdf",
            "chunk_types": ["abstract"],
            "sections": SAMPLE_SECTIONS,
            "ml_analysis": {
                "paper_id": "42",
                "classified_sections": [],
                "limitations": [{"text": "Small dataset.", "source": "pattern"}],
                "section_summaries": {},
                "section_distribution": {"abstract": 1},
                "total_sections": 1,
            },
        }

        res = self.client.post("/api/paper/42/ml-analysis")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data["paper_id"], "42")
        self.assertEqual(len(data["limitations"]), 1)

    def test_limitations_endpoint_uses_pattern_fallback(self):
        import app as flask_app
        flask_app.papers["43"] = {
            "id": "43",
            "title": "Pattern Test",
            "filename": "test.pdf",
            "chunk_types": ["discussion"],
            "sections": SAMPLE_SECTIONS,
        }

        res = self.client.get("/api/paper/43/limitations")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertIn("limitations", data)
        self.assertGreater(len(data["limitations"]), 0)

    def test_sections_endpoint_raw_fallback(self):
        import app as flask_app
        flask_app.papers["44"] = {
            "id": "44",
            "title": "Sections Test",
            "filename": "test.pdf",
            "chunk_types": ["abstract", "methods"],
            "sections": SAMPLE_SECTIONS,
        }

        res = self.client.get("/api/paper/44/sections")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertIn("sections", data)
        self.assertIn("section_distribution", data)
        self.assertGreater(len(data["sections"]), 0)

    def test_list_papers_after_inject(self):
        import app as flask_app
        flask_app.papers["50"] = {
            "id": "50",
            "title": "Another Paper",
            "filename": "another.pdf",
            "chunk_types": ["abstract"],
            "sections": [],
        }

        res = self.client.get("/api/papers")
        data = json.loads(res.data)
        ids = [p["id"] for p in data["papers"]]
        self.assertIn("50", ids)
        # sections key must NOT be serialised in list_papers
        for p in data["papers"]:
            self.assertNotIn("sections", p)


if __name__ == "__main__":
    unittest.main()
