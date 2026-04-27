"""Tests for the provenance, IPFS, and blockchain services.

Run with:
    cd /path/to/ResearchApp
    python -m pytest tests/ -v
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.provenance_service import ProvenanceService, _sha256
from services.ipfs_service import IPFSService
from services.blockchain_service import BlockchainService, _MockBlockchain


# ---------------------------------------------------------------------------
# ProvenanceService
# ---------------------------------------------------------------------------

class TestProvenanceService:
    def setup_method(self):
        self.svc = ProvenanceService()

    # ------------------------------------------------------------------
    def test_register_upload_returns_record(self):
        rec = self.svc.register_upload("p1", "paper.pdf", "full text content here")
        assert rec["paper_id"] == "p1"
        assert rec["record_type"] == "upload"
        assert rec["content_hash"] == _sha256("full text content here")
        assert rec["record_hash"] is not None
        assert rec["prev_hash"] == "genesis"

    def test_register_upload_stores_record(self):
        self.svc.register_upload("p1", "paper.pdf", "content")
        history = self.svc.get_history("p1")
        assert len(history) == 1
        assert history[0]["record_type"] == "upload"

    def test_register_summary_returns_record(self):
        rec = self.svc.register_summary("p1", "This is the summary.", "session-123")
        assert rec["record_type"] == "summary"
        assert rec["content_hash"] == _sha256("This is the summary.")
        assert rec["metadata"]["agent_session_id"] == "session-123"

    def test_register_agent_output_returns_record(self):
        agent_state = {
            "session_id": "abc-123",
            "query": "test query",
            "final_response": "agent response",
            "mode": "qa",
            "workflow_type": "general_qa",
            "critique": {"confidence_level": "high", "overall_quality_score": 8},
        }
        rec = self.svc.register_agent_output("p1", "abc-123", agent_state)
        assert rec["record_type"] == "agent_output"
        assert rec["metadata"]["mode"] == "qa"
        assert rec["metadata"]["confidence"] == "high"

    # ------------------------------------------------------------------
    def test_get_history_returns_ordered_records(self):
        self.svc.register_upload("p1", "file.pdf", "content1")
        self.svc.register_summary("p1", "summary text", "sess1")
        history = self.svc.get_history("p1")
        assert len(history) == 2
        assert history[0]["record_type"] == "upload"
        assert history[1]["record_type"] == "summary"

    def test_get_history_empty_for_unknown_paper(self):
        assert self.svc.get_history("nonexistent") == []

    def test_multiple_papers_isolated(self):
        self.svc.register_upload("p1", "a.pdf", "content A")
        self.svc.register_upload("p2", "b.pdf", "content B")
        assert len(self.svc.get_history("p1")) == 1
        assert len(self.svc.get_history("p2")) == 1

    # ------------------------------------------------------------------
    def test_verify_chain_empty_paper(self):
        result = self.svc.verify_chain("p_empty")
        assert result["valid"] is True
        assert result["record_count"] == 0

    def test_verify_chain_single_record(self):
        self.svc.register_upload("p1", "file.pdf", "text")
        result = self.svc.verify_chain("p1")
        assert result["valid"] is True
        assert result["record_count"] == 1

    def test_verify_chain_multiple_records(self):
        self.svc.register_upload("p1", "file.pdf", "text")
        self.svc.register_summary("p1", "summary", "sess")
        self.svc.register_agent_output("p1", "sess", {"session_id": "sess", "query": "q", "final_response": "r", "mode": "qa", "workflow_type": "x", "critique": {}})
        result = self.svc.verify_chain("p1")
        assert result["valid"] is True
        assert result["record_count"] == 3

    def test_verify_chain_detects_tampering(self):
        self.svc.register_upload("p1", "file.pdf", "original text")
        self.svc.register_summary("p1", "summary text", "sess")
        # Tamper with the first record's content hash
        self.svc._records["p1"][0]["content_hash"] = "tampered_hash"
        result = self.svc.verify_chain("p1")
        assert result["valid"] is False
        assert "Chain broken" in result["message"]

    # ------------------------------------------------------------------
    def test_hash_chain_links_across_papers(self):
        self.svc.register_upload("p1", "a.pdf", "content A")
        self.svc.register_upload("p2", "b.pdf", "content B")
        # Second record's prev_hash should equal first record's record_hash
        r1 = self.svc.get_history("p1")[0]
        r2 = self.svc.get_history("p2")[0]
        assert r2["prev_hash"] == r1["record_hash"]

    # ------------------------------------------------------------------
    def test_blockchain_called_on_upload(self):
        mock_bc = MagicMock()
        mock_bc.register_upload.return_value = "0xabc123"
        svc = ProvenanceService(blockchain_service=mock_bc)
        rec = svc.register_upload("p1", "file.pdf", "content")
        mock_bc.register_upload.assert_called_once()
        assert rec["tx_hash"] == "0xabc123"

    def test_blockchain_called_on_summary(self):
        mock_bc = MagicMock()
        mock_bc.register_summary.return_value = "0xdef456"
        svc = ProvenanceService(blockchain_service=mock_bc)
        svc.register_upload("p1", "file.pdf", "c")  # need upload first
        rec = svc.register_summary("p1", "summary", "sess")
        mock_bc.register_summary.assert_called_once()
        assert rec["tx_hash"] == "0xdef456"

    def test_blockchain_failure_is_non_fatal(self):
        mock_bc = MagicMock()
        mock_bc.register_upload.side_effect = Exception("RPC error")
        svc = ProvenanceService(blockchain_service=mock_bc)
        # Should not raise
        rec = svc.register_upload("p1", "file.pdf", "content")
        assert rec["tx_hash"] is None

    def test_ipfs_called_on_upload(self):
        mock_ipfs = MagicMock()
        mock_ipfs.pin_content.return_value = "QmFakeCID123"
        svc = ProvenanceService(ipfs_service=mock_ipfs)
        rec = svc.register_upload("p1", "file.pdf", "content to pin")
        mock_ipfs.pin_content.assert_called_once()
        assert rec["ipfs_cid"] == "QmFakeCID123"

    def test_ipfs_failure_is_non_fatal(self):
        mock_ipfs = MagicMock()
        mock_ipfs.pin_content.side_effect = Exception("IPFS timeout")
        svc = ProvenanceService(ipfs_service=mock_ipfs)
        # Should not raise
        rec = svc.register_upload("p1", "file.pdf", "content")
        assert rec["ipfs_cid"] == ""


# ---------------------------------------------------------------------------
# IPFSService
# ---------------------------------------------------------------------------

class TestIPFSService:
    def test_mock_mode_when_no_credentials(self):
        svc = IPFSService(pinata_api_key=None, pinata_secret=None)
        assert not svc.is_enabled

    def test_mock_cid_is_deterministic(self):
        svc = IPFSService()
        cid1 = svc.pin_content("same content")
        cid2 = svc.pin_content("same content")
        assert cid1 == cid2
        assert cid1.startswith("mock_Qm")

    def test_mock_cid_differs_for_different_content(self):
        svc = IPFSService()
        cid1 = svc.pin_content("content A")
        cid2 = svc.pin_content("content B")
        assert cid1 != cid2

    def test_gateway_url_for_real_cid(self):
        svc = IPFSService()
        url = svc.gateway_url("QmRealCID")
        assert "ipfs.io/ipfs/QmRealCID" in url

    def test_gateway_url_for_mock_cid(self):
        svc = IPFSService()
        url = svc.gateway_url("mock_QmABC")
        assert "#mock-ipfs" in url

    def test_pinata_api_called_when_credentials_set(self):
        with patch("services.ipfs_service._HAS_REQUESTS", True):
            with patch("services.ipfs_service.requests") as mock_requests:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"IpfsHash": "QmRealCID"}
                mock_resp.raise_for_status = MagicMock()
                mock_requests.post.return_value = mock_resp

                svc = IPFSService(pinata_api_key="key", pinata_secret="secret")
                cid = svc.pin_content("content", "test.txt")
                assert cid == "QmRealCID"
                mock_requests.post.assert_called_once()

    def test_falls_back_to_mock_on_pinata_error(self):
        with patch("services.ipfs_service._HAS_REQUESTS", True):
            with patch("services.ipfs_service.requests") as mock_requests:
                mock_requests.post.side_effect = Exception("network error")
                svc = IPFSService(pinata_api_key="key", pinata_secret="secret")
                cid = svc.pin_content("content")
                assert cid.startswith("mock_Qm")


# ---------------------------------------------------------------------------
# BlockchainService (mock mode)
# ---------------------------------------------------------------------------

class TestMockBlockchain:
    def test_register_upload_returns_tx_hash(self):
        bc = _MockBlockchain()
        tx = bc.register_upload("p1", "abc123", "QmCID")
        assert tx.startswith("0x")
        assert len(tx) == 66  # "0x" + 64 hex chars

    def test_register_summary_returns_tx_hash(self):
        bc = _MockBlockchain()
        tx = bc.register_summary("p1", "def456")
        assert tx.startswith("0x")

    def test_different_payloads_produce_different_hashes(self):
        bc = _MockBlockchain()
        tx1 = bc.register_upload("p1", "hash1", "cid1")
        tx2 = bc.register_upload("p2", "hash2", "cid2")
        assert tx1 != tx2

    def test_ledger_records_events(self):
        bc = _MockBlockchain()
        bc.register_upload("p1", "hash1", "cid1")
        bc.register_summary("p1", "hash2")
        ledger = bc.get_ledger()
        assert len(ledger) == 2
        assert ledger[0]["event_type"] == "upload"
        assert ledger[1]["event_type"] == "summary"


class TestBlockchainService:
    def test_defaults_to_mock_mode_without_web3(self):
        svc = BlockchainService(rpc_url=None, contract_address=None, private_key=None)
        assert not svc.is_real_chain

    def test_register_upload_returns_hash_in_mock_mode(self):
        svc = BlockchainService()
        tx = svc.register_upload("p1", "a" * 64, "QmCID")
        assert tx.startswith("0x")

    def test_register_summary_returns_hash_in_mock_mode(self):
        svc = BlockchainService()
        tx = svc.register_summary("p1", "b" * 64)
        assert tx.startswith("0x")

    def test_falls_back_to_mock_when_web3_not_available(self):
        with patch("services.blockchain_service._HAS_WEB3", False):
            svc = BlockchainService(
                rpc_url="http://localhost:8545",
                contract_address="0x" + "1" * 40,
                private_key="0x" + "a" * 64,
            )
            assert not svc.is_real_chain
            tx = svc.register_upload("p1", "hash", "cid")
            assert tx.startswith("0x")


# ---------------------------------------------------------------------------
# _sha256 helper
# ---------------------------------------------------------------------------

class TestSha256Helper:
    def test_known_value(self):
        # SHA-256 of empty string
        result = _sha256("")
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_consistent(self):
        assert _sha256("hello") == _sha256("hello")

    def test_different_inputs(self):
        assert _sha256("a") != _sha256("b")
