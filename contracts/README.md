# Contracts — On-Chain Provenance Registry

This folder contains a Solidity smart contract that provides an *optional* on-chain layer of trust for ResearchRadar's provenance system.

> **You do not need this to run ResearchRadar.** The app works fully without it, using an in-memory mock blockchain. This contract is for teams who want publicly auditable, permanently immutable proof of provenance on a live Ethereum (or EVM-compatible) network.

---

## `PaperProvenance.sol` — What Is It?

A **smart contract** is a self-executing program that lives on a blockchain. Once deployed, its code cannot be changed and every interaction is publicly recorded. `PaperProvenance.sol` acts as an immutable public registry: it stores cryptographic fingerprints (hashes) of research papers and AI-generated outputs so that anyone can later verify "this paper existed and was analysed at this exact time, and nothing has been changed since."

---

## What Gets Stored On-Chain?

The contract never stores the actual content of papers — only small cryptographic fingerprints and metadata:

| Field | Type | Description |
|---|---|---|
| `paperId` | text | An ID string (e.g. `"1"`, `"2"`) identifying the paper |
| `contentHash` | 32-byte hash | SHA-256 fingerprint of the paper or AI output |
| `ipfsCid` | text | IPFS address of the full content (optional) |
| `eventType` | enum | One of: `Upload`, `Summary`, `Revision`, `AgentOutput` |
| `recorder` | Ethereum address | Who submitted the record |
| `blockTimestamp` | timestamp | When it was recorded, set by the blockchain itself |

---

## Events (Blockchain Notifications)

Every time a new record is added, the contract emits an **event** — a public notification that external apps can subscribe to:

| Event | When It Fires |
|---|---|
| `PaperUploaded` | A new paper is registered |
| `SummaryGenerated` | An AI summary is recorded |
| `RevisionRecorded` | A paper revision is logged |
| `AgentOutputRecorded` | A multi-agent pipeline result is saved |
| `RecorderAdded` | The owner grants recording permission to an address |
| `RecorderRemoved` | The owner revokes recording permission |

---

## Access Control — Who Can Write Records?

The contract uses a simple whitelist:

- The **owner** (whoever deployed the contract) can always write records.
- The owner can **add** other trusted addresses (e.g. the ResearchRadar server wallet) via `addRecorder()`.
- The owner can **remove** recorders via `removeRecorder()`.
- All other addresses are read-only.

This prevents random wallets from spamming fake provenance records.

---

## Duplicate Prevention

For `Upload` events, the contract checks whether the same content hash has already been registered (`registeredHashes` mapping). If it has, the transaction reverts. This ensures each unique piece of content is registered exactly once.

---

## Solidity Version

```solidity
pragma solidity ^0.8.19;
```

Compatible with Ethereum mainnet and any EVM-compatible chain (Polygon, Arbitrum, Base, etc.).

---

## How To Deploy (Optional)

1. Install [Hardhat](https://hardhat.org/) or [Foundry](https://book.getfoundry.sh/).
2. Compile: `npx hardhat compile` (or `forge build`)
3. Deploy to your chosen network and note the contract address.
4. Set the following environment variables in your ResearchRadar deployment:

```bash
BLOCKCHAIN_RPC_URL=https://your-rpc-endpoint
CONTRACT_ADDRESS=0xYourDeployedContractAddress
BLOCKCHAIN_PRIVATE_KEY=0xYourPrivateKey
```

5. Install the `web3` Python package (commented out in `requirements.txt` by default):
```bash
pip install web3>=6.0.0
```

The `BlockchainService` in `services/blockchain_service.py` will automatically detect these variables and switch from mock mode to real on-chain anchoring.

---

## Without Deployment

If you skip deployment entirely, `BlockchainService` falls back to an in-memory mock ledger that produces deterministic SHA-256-derived fake transaction hashes. The provenance chain in the UI works identically — you just don't get public blockchain immutability.
