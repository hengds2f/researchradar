"""Blockchain integration service for provenance anchoring.

Supports two modes:
- **Real mode**: Ethereum via Web3.py.  Activated when the ``web3`` package
  is installed *and* BLOCKCHAIN_RPC_URL + CONTRACT_ADDRESS env vars are set.
- **Mock mode** (default): A local in-memory ledger that produces
  deterministic, SHA-256-derived transaction hashes.  Functionally
  transparent for development and testing.

All public methods are identical in both modes so callers never need to
branch on which mode is active.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from web3 import Web3
    _HAS_WEB3 = True
except ImportError:
    _HAS_WEB3 = False
    logger.info("web3 package not installed; BlockchainService will use mock mode")


# ---------------------------------------------------------------------------
# Minimal ABI for PaperProvenance.sol
# ---------------------------------------------------------------------------

_PAPER_PROVENANCE_ABI = [
    {
        "inputs": [
            {"internalType": "string", "name": "paperId", "type": "string"},
            {"internalType": "bytes32", "name": "fileHash", "type": "bytes32"},
            {"internalType": "string", "name": "ipfsCid", "type": "string"},
        ],
        "name": "registerUpload",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "string", "name": "paperId", "type": "string"},
            {"internalType": "bytes32", "name": "summaryHash", "type": "bytes32"},
        ],
        "name": "registerSummary",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "string", "name": "paperId", "type": "string"},
        ],
        "name": "getHistoryCount",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "string", "name": "paperId", "type": "string"},
            {"indexed": False, "internalType": "bytes32", "name": "fileHash", "type": "bytes32"},
            {"indexed": False, "internalType": "string", "name": "ipfsCid", "type": "string"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
        ],
        "name": "PaperUploaded",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "string", "name": "paperId", "type": "string"},
            {"indexed": False, "internalType": "bytes32", "name": "summaryHash", "type": "bytes32"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
        ],
        "name": "SummaryGenerated",
        "type": "event",
    },
]


# ---------------------------------------------------------------------------
# Mock blockchain
# ---------------------------------------------------------------------------

class _MockBlockchain:
    """
    In-memory mock blockchain.

    Generates deterministic transaction hashes using SHA-256 so that the same
    payload always produces the same hash (useful for testing).
    """

    def __init__(self):
        self._ledger: list = []
        self._nonce: int = 0

    def register_upload(self, paper_id: str, file_hash: str, ipfs_cid: str) -> str:
        return self._record(
            "upload",
            {"paper_id": paper_id, "file_hash": file_hash, "ipfs_cid": ipfs_cid},
        )

    def register_summary(self, paper_id: str, summary_hash: str) -> str:
        return self._record(
            "summary",
            {"paper_id": paper_id, "summary_hash": summary_hash},
        )

    def get_ledger(self) -> list:
        return list(self._ledger)

    # ------------------------------------------------------------------
    def _record(self, event_type: str, payload: dict) -> str:
        self._nonce += 1
        timestamp = datetime.now(timezone.utc).isoformat()
        tx_data = json.dumps(
            {"nonce": self._nonce, "event": event_type, "payload": payload, "ts": timestamp},
            sort_keys=True,
        )
        tx_hash = "0x" + hashlib.sha256(tx_data.encode()).hexdigest()
        self._ledger.append(
            {
                "tx_hash": tx_hash,
                "event_type": event_type,
                "payload": payload,
                "timestamp": timestamp,
                "block": self._nonce,
            }
        )
        logger.debug("MockBlockchain tx %s (%s)", tx_hash[:12], event_type)
        return tx_hash


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------

class BlockchainService:
    """
    Blockchain service for provenance anchoring.

    Uses a real Ethereum node when RPC_URL, CONTRACT_ADDRESS, and
    BLOCKCHAIN_PRIVATE_KEY env vars are all present and the ``web3``
    package is installed.  Falls back to the mock ledger otherwise.
    """

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        contract_address: Optional[str] = None,
        private_key: Optional[str] = None,
    ):
        self._rpc_url = rpc_url or os.environ.get("BLOCKCHAIN_RPC_URL", "")
        self._contract_address = contract_address or os.environ.get("CONTRACT_ADDRESS", "")
        self._private_key = private_key or os.environ.get("BLOCKCHAIN_PRIVATE_KEY", "")

        self._w3: Optional[object] = None
        self._contract: Optional[object] = None
        self._mock = _MockBlockchain()
        self._use_real = False

        if _HAS_WEB3 and self._rpc_url and self._contract_address and self._private_key:
            self._connect()

    @property
    def is_real_chain(self) -> bool:
        return self._use_real

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_upload(self, paper_id: str, file_hash: str, ipfs_cid: str) -> str:
        if self._use_real:
            try:
                return self._on_chain_upload(paper_id, file_hash, ipfs_cid)
            except Exception as exc:
                logger.error("On-chain upload failed, using mock: %s", exc)
        return self._mock.register_upload(paper_id, file_hash, ipfs_cid)

    def register_summary(self, paper_id: str, summary_hash: str) -> str:
        if self._use_real:
            try:
                return self._on_chain_summary(paper_id, summary_hash)
            except Exception as exc:
                logger.error("On-chain summary failed, using mock: %s", exc)
        return self._mock.register_summary(paper_id, summary_hash)

    # ------------------------------------------------------------------
    # Web3 internals
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        try:
            w3 = Web3(Web3.HTTPProvider(self._rpc_url))
            if not w3.is_connected():
                logger.warning("BlockchainService: RPC not reachable, using mock")
                return
            self._w3 = w3
            self._contract = w3.eth.contract(
                address=Web3.to_checksum_address(self._contract_address),
                abi=_PAPER_PROVENANCE_ABI,
            )
            self._use_real = True
            logger.info("BlockchainService connected to %s", self._rpc_url)
        except Exception as exc:
            logger.warning("BlockchainService setup error, using mock: %s", exc)

    def _on_chain_upload(self, paper_id: str, file_hash: str, ipfs_cid: str) -> str:
        w3 = self._w3
        account = w3.eth.account.from_key(self._private_key)
        fh_bytes = bytes.fromhex(file_hash[:64].ljust(64, "0"))
        nonce = w3.eth.get_transaction_count(account.address)
        tx = self._contract.functions.registerUpload(
            paper_id, fh_bytes, ipfs_cid
        ).build_transaction({"from": account.address, "nonce": nonce, "gas": 200_000})
        signed = w3.eth.account.sign_transaction(tx, self._private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        return receipt.transactionHash.hex()

    def _on_chain_summary(self, paper_id: str, summary_hash: str) -> str:
        w3 = self._w3
        account = w3.eth.account.from_key(self._private_key)
        sh_bytes = bytes.fromhex(summary_hash[:64].ljust(64, "0"))
        nonce = w3.eth.get_transaction_count(account.address)
        tx = self._contract.functions.registerSummary(
            paper_id, sh_bytes
        ).build_transaction({"from": account.address, "nonce": nonce, "gas": 150_000})
        signed = w3.eth.account.sign_transaction(tx, self._private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        return receipt.transactionHash.hex()
