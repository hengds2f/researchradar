// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title PaperProvenance
 * @notice Immutable on-chain registry for academic paper provenance events.
 *
 * Design principles:
 *  - Only hashes and small metadata are stored on-chain (no raw content).
 *  - Large artifacts (PDFs, full text) are stored off-chain on IPFS; only
 *    the CID is anchored here.
 *  - A simple whitelist prevents arbitrary addresses from spamming records.
 *    The contract owner can add/remove authorised recorders.
 */
contract PaperProvenance {

    // -----------------------------------------------------------------------
    // Types
    // -----------------------------------------------------------------------

    enum EventType { Upload, Summary, Revision, AgentOutput }

    struct ProvenanceRecord {
        string    paperId;
        bytes32   contentHash;  // SHA-256 of the relevant content
        string    ipfsCid;      // CID of off-chain artefact (may be empty)
        EventType eventType;
        address   recorder;
        uint256   blockTimestamp;
    }

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------

    address public owner;

    /// @dev paperId => ordered list of provenance records
    mapping(string => ProvenanceRecord[]) private _history;

    /// @dev contentHash => already registered (prevents duplicates for uploads)
    mapping(bytes32 => bool) public registeredHashes;

    /// @dev authorised recorders (owner is always authorised)
    mapping(address => bool) public authorised;

    // -----------------------------------------------------------------------
    // Events
    // -----------------------------------------------------------------------

    event PaperUploaded(
        string  indexed paperId,
        bytes32         contentHash,
        string          ipfsCid,
        uint256         timestamp
    );

    event SummaryGenerated(
        string  indexed paperId,
        bytes32         summaryHash,
        uint256         timestamp
    );

    event RevisionRecorded(
        string  indexed paperId,
        bytes32         revisionHash,
        uint256         timestamp
    );

    event AgentOutputRecorded(
        string  indexed paperId,
        bytes32         outputHash,
        uint256         timestamp
    );

    event RecorderAdded(address indexed recorder);
    event RecorderRemoved(address indexed recorder);

    // -----------------------------------------------------------------------
    // Modifiers
    // -----------------------------------------------------------------------

    modifier onlyOwner() {
        require(msg.sender == owner, "PaperProvenance: not owner");
        _;
    }

    modifier onlyAuthorised() {
        require(
            msg.sender == owner || authorised[msg.sender],
            "PaperProvenance: not authorised"
        );
        _;
    }

    // -----------------------------------------------------------------------
    // Constructor
    // -----------------------------------------------------------------------

    constructor() {
        owner = msg.sender;
    }

    // -----------------------------------------------------------------------
    // Access control
    // -----------------------------------------------------------------------

    function addRecorder(address recorder) external onlyOwner {
        authorised[recorder] = true;
        emit RecorderAdded(recorder);
    }

    function removeRecorder(address recorder) external onlyOwner {
        authorised[recorder] = false;
        emit RecorderRemoved(recorder);
    }

    // -----------------------------------------------------------------------
    // Registration functions
    // -----------------------------------------------------------------------

    /**
     * @notice Register a paper upload.
     * @param paperId   Application-level paper identifier.
     * @param fileHash  SHA-256 hash of the extracted text content.
     * @param ipfsCid   IPFS CID of the stored artefact (empty string if none).
     */
    function registerUpload(
        string  calldata paperId,
        bytes32          fileHash,
        string  calldata ipfsCid
    ) external onlyAuthorised {
        require(!registeredHashes[fileHash], "PaperProvenance: hash already registered");
        registeredHashes[fileHash] = true;

        _history[paperId].push(ProvenanceRecord({
            paperId:        paperId,
            contentHash:    fileHash,
            ipfsCid:        ipfsCid,
            eventType:      EventType.Upload,
            recorder:       msg.sender,
            blockTimestamp: block.timestamp
        }));

        emit PaperUploaded(paperId, fileHash, ipfsCid, block.timestamp);
    }

    /**
     * @notice Register a generated summary.
     * @param paperId     Application-level paper identifier.
     * @param summaryHash SHA-256 hash of the summary text.
     */
    function registerSummary(
        string  calldata paperId,
        bytes32          summaryHash
    ) external onlyAuthorised {
        _history[paperId].push(ProvenanceRecord({
            paperId:        paperId,
            contentHash:    summaryHash,
            ipfsCid:        "",
            eventType:      EventType.Summary,
            recorder:       msg.sender,
            blockTimestamp: block.timestamp
        }));

        emit SummaryGenerated(paperId, summaryHash, block.timestamp);
    }

    /**
     * @notice Register an agent-workflow output.
     * @param paperId    Application-level paper identifier.
     * @param outputHash SHA-256 hash of the serialised agent output.
     */
    function registerAgentOutput(
        string  calldata paperId,
        bytes32          outputHash
    ) external onlyAuthorised {
        _history[paperId].push(ProvenanceRecord({
            paperId:        paperId,
            contentHash:    outputHash,
            ipfsCid:        "",
            eventType:      EventType.AgentOutput,
            recorder:       msg.sender,
            blockTimestamp: block.timestamp
        }));

        emit AgentOutputRecorded(paperId, outputHash, block.timestamp);
    }

    // -----------------------------------------------------------------------
    // View functions
    // -----------------------------------------------------------------------

    /// @notice Return all provenance records for a paper.
    function getHistory(string calldata paperId)
        external
        view
        returns (ProvenanceRecord[] memory)
    {
        return _history[paperId];
    }

    /// @notice Return the number of provenance records for a paper.
    function getHistoryCount(string calldata paperId)
        external
        view
        returns (uint256)
    {
        return _history[paperId].length;
    }

    /// @notice Check whether a specific content hash has been registered.
    function isRegistered(bytes32 contentHash) external view returns (bool) {
        return registeredHashes[contentHash];
    }
}
