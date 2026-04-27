"""Provenance tracking service.

Maintains a tamper-evident linked hash chain for paper uploads, summaries,
and agent-generated outputs.  Each record embeds the hash of the previous
record so that any retroactive modification to the chain is detectable.

Optional anchoring on an Ethereum-compatible blockchain and optional IPFS
storage are delegated to BlockchainService and IPFSService respectively.
Both dependencies are optional; the service degrades gracefully when they
are unavailable.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ProvenanceService:
    """
    Build and verify a per-paper tamper-evident provenance chain.

    Parameters
    ----------
    blockchain_service :
        Optional BlockchainService instance.  When provided, every record
        is anchored on-chain (or on the mock ledger).
    ipfs_service :
        Optional IPFSService instance.  When provided, upload content is
        pinned to IPFS and the CID is stored in the record.
    """

    def __init__(self, blockchain_service=None, ipfs_service=None):
        # {paper_id: [record_dict, ...]}
        self._records: dict = {}
        # Global hash chain head; starts with a well-known genesis string
        self._chain_head: str = "genesis"
        self._blockchain = blockchain_service
        self._ipfs = ipfs_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_upload(
        self,
        paper_id: str,
        filename: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Record a paper-upload provenance event."""
        content_hash = _sha256(content)

        ipfs_cid = ""
        if self._ipfs:
            try:
                ipfs_cid = self._ipfs.pin_content(content[:4_096], filename)
            except Exception as exc:
                logger.warning("IPFS pin failed for %s: %s", filename, exc)

        record = self._build_record(
            paper_id=paper_id,
            record_type="upload",
            content_hash=content_hash,
            ipfs_cid=ipfs_cid,
            metadata={
                "filename": filename,
                "filename_hash": _sha256(filename),
                **(metadata or {}),
            },
        )

        if self._blockchain:
            try:
                tx = self._blockchain.register_upload(paper_id, content_hash, ipfs_cid)
                record["tx_hash"] = tx
            except Exception as exc:
                logger.warning("Blockchain anchor failed for %s: %s", paper_id, exc)

        self._store(paper_id, record)
        return record

    def register_summary(
        self,
        paper_id: str,
        summary_text: str,
        agent_session_id: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Record a summary-generation provenance event."""
        summary_hash = _sha256(summary_text)

        record = self._build_record(
            paper_id=paper_id,
            record_type="summary",
            content_hash=summary_hash,
            ipfs_cid="",
            metadata={
                "agent_session_id": agent_session_id,
                "summary_length": len(summary_text),
                **(metadata or {}),
            },
        )

        if self._blockchain:
            try:
                tx = self._blockchain.register_summary(paper_id, summary_hash)
                record["tx_hash"] = tx
            except Exception as exc:
                logger.warning("Blockchain anchor failed for summary %s: %s", paper_id, exc)

        self._store(paper_id, record)
        return record

    def register_agent_output(
        self,
        paper_id: str,
        session_id: str,
        agent_state: dict,
    ) -> dict:
        """Record a complete agent-workflow output provenance event."""
        canonical = json.dumps(
            {
                "session_id": agent_state.get("session_id"),
                "query": agent_state.get("query", ""),
                "final_response": agent_state.get("final_response", ""),
            },
            sort_keys=True,
        )
        output_hash = _sha256(canonical)

        record = self._build_record(
            paper_id=paper_id,
            record_type="agent_output",
            content_hash=output_hash,
            ipfs_cid="",
            metadata={
                "agent_session_id": session_id,
                "mode": agent_state.get("mode"),
                "workflow_type": agent_state.get("workflow_type"),
                "confidence": agent_state.get("critique", {}).get("confidence_level"),
                "quality_score": agent_state.get("critique", {}).get("overall_quality_score"),
            },
        )

        self._store(paper_id, record)
        return record

    def get_history(self, paper_id: str) -> list:
        """Return all provenance records for a paper (oldest first)."""
        return list(self._records.get(paper_id, []))

    def get_all(self) -> dict:
        """Return a shallow copy of the full in-memory store."""
        return {pid: list(records) for pid, records in self._records.items()}

    def verify_chain(self, paper_id: str) -> dict:
        """
        Verify the integrity of the hash chain for a specific paper.

        Returns a dict with keys: ``valid``, ``message``, ``record_count``.
        """
        records = self._records.get(paper_id, [])
        if not records:
            return {"valid": True, "message": "No records to verify", "record_count": 0}

        for i, rec in enumerate(records):
            prev = records[i - 1]["record_hash"] if i > 0 else "genesis"
            expected = _sha256(
                f"{prev}:{rec['record_id']}:{rec['content_hash']}:{rec['timestamp']}"
            )
            if expected != rec["record_hash"]:
                return {
                    "valid": False,
                    "message": f"Chain broken at record index {i} (id={rec['record_id']})",
                    "record_count": len(records),
                }

        return {
            "valid": True,
            "message": "Chain integrity verified",
            "record_count": len(records),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_record(
        self,
        paper_id: str,
        record_type: str,
        content_hash: str,
        ipfs_cid: str,
        metadata: dict,
    ) -> dict:
        record_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # Link to the previous record in the global chain
        prev_hash = self._chain_head
        record_hash = _sha256(
            f"{prev_hash}:{record_id}:{content_hash}:{timestamp}"
        )
        self._chain_head = record_hash

        return {
            "record_id": record_id,
            "paper_id": paper_id,
            "record_type": record_type,
            "content_hash": content_hash,
            "ipfs_cid": ipfs_cid,
            "tx_hash": None,
            "metadata": metadata,
            "timestamp": timestamp,
            "record_hash": record_hash,
            "prev_hash": prev_hash,
        }

    def _store(self, paper_id: str, record: dict) -> None:
        self._records.setdefault(paper_id, []).append(record)
        logger.info(
            "Provenance: %s [%s] stored for paper %s",
            record["record_type"],
            record["record_id"][:8],
            paper_id,
        )
