"""IPFS service for decentralized content storage.

Uses the Pinata API when PINATA_API_KEY and PINATA_SECRET_KEY environment
variables are set.  Falls back to a deterministic mock CID otherwise, so the
rest of the system can run without any IPFS credentials.
"""

import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False
    logger.warning("requests package not available; IPFS service will use mock mode")


class IPFSService:
    """
    Upload content to IPFS via the Pinata pinning API.

    When Pinata credentials are absent the service returns a deterministic
    mock CID so dependent code never has to handle a None return value.
    """

    _PIN_JSON_ENDPOINT = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
    _GATEWAY = "https://ipfs.io/ipfs/"

    def __init__(
        self,
        pinata_api_key: Optional[str] = None,
        pinata_secret: Optional[str] = None,
    ):
        self._api_key = pinata_api_key or os.environ.get("PINATA_API_KEY", "")
        self._secret = pinata_secret or os.environ.get("PINATA_SECRET_KEY", "")
        self._enabled = bool(self._api_key and self._secret and _HAS_REQUESTS)

        if not self._enabled:
            logger.info("IPFSService: running in mock mode (no Pinata credentials)")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def pin_content(self, content: str, name: str = "artifact") -> str:
        """
        Pin ``content`` to IPFS and return the CID string.

        Falls back to a deterministic mock CID on any error or when
        Pinata is not configured.
        """
        if not self._enabled:
            return self._mock_cid(content)

        try:
            headers = {
                "pinata_api_key": self._api_key,
                "pinata_secret_api_key": self._secret,
                "Content-Type": "application/json",
            }
            payload = {
                "pinataMetadata": {"name": name[:64]},
                "pinataContent": {"data": content[:10_000]},
            }
            resp = requests.post(
                self._PIN_JSON_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("IpfsHash", self._mock_cid(content))

        except Exception as exc:
            logger.warning("Pinata API error (falling back to mock): %s", exc)
            return self._mock_cid(content)

    def gateway_url(self, cid: str) -> str:
        """Return a public IPFS gateway URL for the given CID."""
        if cid.startswith("mock_"):
            return f"#mock-ipfs/{cid}"
        return f"{self._GATEWAY}{cid}"

    @staticmethod
    def _mock_cid(content: str) -> str:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]
        return f"mock_Qm{digest}"
