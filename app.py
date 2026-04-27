import os
import logging
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
import PyPDF2
import numpy as np
import re

# AI Integration
import chromadb
from huggingface_hub import InferenceClient

# ML analysis service
from services.paper_ml import PaperMLService

# Multi-agent orchestration
from services.agent_orchestrator import AgentOrchestrator

# Provenance / dApp layer
from services.provenance_service import ProvenanceService
from services.ipfs_service import IPFSService
from services.blockchain_service import BlockchainService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')

# Environment configuration
HF_TOKEN = os.environ.get("HF_TOKEN")
PROVENANCE_ENABLED = os.environ.get("PROVENANCE_ENABLED", "true").lower() != "false"
AGENT_ENABLED = os.environ.get("AGENT_ENABLED", "true").lower() != "false"

if not HF_TOKEN:
    print("Warning: Missing HF_TOKEN environment variable. LLM Synthesis will fail.")

# Initialize ChromaDB (Local In-Memory Vector Database)
chroma_client = chromadb.Client()
collection = chroma_client.get_or_create_collection(name="research_papers")

# Initialize ML analysis service (lazy – no local weights loaded)
ml_service = PaperMLService(HF_TOKEN)

papers = {}

# Initialize provenance services
_ipfs_service = IPFSService()
_blockchain_service = BlockchainService()
provenance_service = ProvenanceService(
    blockchain_service=_blockchain_service if PROVENANCE_ENABLED else None,
    ipfs_service=_ipfs_service if PROVENANCE_ENABLED else None,
)

# Initialize multi-agent orchestrator (passes references to shared state)
agent_orchestrator = AgentOrchestrator(HF_TOKEN, collection, papers)

def extract_sections(text):
    text_clean = text.replace('\n', ' ')
    
    markers = {
        'abstract': re.search(r'\b(abstract|summary)\b', text, re.IGNORECASE),
        'introduction': re.search(r'\b(introduction|background)\b', text, re.IGNORECASE),
        'methods': re.search(r'\b(method|methods|methodology|approach)\b', text, re.IGNORECASE),
        'results': re.search(r'\b(result|results|findings)\b', text, re.IGNORECASE),
        'discussion': re.search(r'\b(discussion|conclusion|conclusions)\b', text, re.IGNORECASE)
    }
    
    valid_markers = [(k, v.start()) for k, v in markers.items() if v]
    valid_markers.sort(key=lambda x: x[1])
    
    if not valid_markers:
        words = text.split()
        if len(words) > 40:
            q = len(words) // 4
            return [
                {'section_type': 'abstract', 'content': ' '.join(words[:q])},
                {'section_type': 'methods', 'content': ' '.join(words[q:q*2])},
                {'section_type': 'results', 'content': ' '.join(words[q*2:q*3])},
                {'section_type': 'discussion', 'content': ' '.join(words[q*3:])}
            ]
        else:
             return [{'section_type': 'abstract', 'content': text}]

    extracted = []
    for i in range(len(valid_markers)):
        start_idx = valid_markers[i][1]
        if i + 1 < len(valid_markers):
            end_idx = valid_markers[i+1][1]
            content = text[start_idx:end_idx].strip()
        else:
            content = text[start_idx:].strip()
            
        if len(content) > 10:
            extracted.append({'section_type': valid_markers[i][0], 'content': content})
            
    types_found = [s['section_type'] for s in extracted]
    if 'methods' not in types_found and len(extracted) > 0:
         extracted.append({'section_type': 'methods', 'content': extracted[0]['content']})
    if 'discussion' not in types_found and len(extracted) > 0:
         extracted.append({'section_type': 'discussion', 'content': extracted[-1]['content']})
            
    return extracted

@app.route('/')
def serve_html():
    return send_from_directory('static', 'index.html')

@app.route('/api/upload', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    files = request.files.getlist('file')
    
    uploaded_papers = []
    
    for file in files:
        if file.filename == '':
            continue
        if file and (file.filename.endswith('.pdf') or file.filename.endswith('.txt')):
            filename = secure_filename(file.filename)
            
            # Parse text directly from memory
            text = ""
            try:
                if filename.endswith('.pdf'):
                    reader = PyPDF2.PdfReader(file.stream)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                else:
                    text = file.read().decode('utf-8')
            except Exception as e:
                print(f"Error parsing {filename}: {e}")
                continue
                        
            # Store Paper Locally
            sections = extract_sections(text)
            chunk_types = list(set([s['section_type'] for s in sections]))
            
            paper_id = str(len(papers) + 1)
            papers[paper_id] = {
                'id': paper_id,
                'title': filename.replace('.pdf', '').replace('.txt', ''),
                'filename': filename,
                'chunk_types': chunk_types,
                'sections': sections,   # stored for ML analysis
            }
            uploaded_papers.append(papers[paper_id])

            # Register provenance for this upload (non-blocking)
            if PROVENANCE_ENABLED:
                try:
                    provenance_service.register_upload(paper_id, filename, text)
                except Exception as prov_exc:
                    logger.warning("Provenance registration failed for %s: %s", paper_id, prov_exc)

            # Inject documents into ChromaDB mapped with section_type metadata
            for i, s in enumerate(sections):
                chunk_id = f"{paper_id}_chunk_{i}"
                collection.add(
                    documents=[s['content']],
                    metadatas=[{"paper_id": paper_id, "section_type": s['section_type']}],
                    ids=[chunk_id]
                )
                
    return jsonify({'message': 'Successfully processed', 'papers': uploaded_papers})


def synthesize_with_llm(mode, query, retrieved_chunks):
    if not HF_TOKEN:
        return "**Authorization Error:** The `HF_TOKEN` environment variable is missing from this Hugging Face Space! Please go to **Settings -> Variables and secrets**, add a secret named specifically `HF_TOKEN` with your account token, and then wait 1 minute for the Space to restart."
        
    if not retrieved_chunks:
        return "No relevant information found in the uploaded corpus."
        
    context = ""
    for i, c in enumerate(retrieved_chunks):
        title = papers.get(c['paper_id'], {}).get('title', 'Unknown Source')
        context += f"\n\n--- Source [{i+1}] (Paper ID: {c['paper_id']} | Title: {title} | Section: {c['section_type']}) ---\n"
        context += c['content'][:2500] 

    if mode == 'synthesis':
        system_prompt = "You are a research synthesis assistant. Compare the provided sources and summarize the common findings."
    elif mode == 'methodology':
        system_prompt = "You are a research assistant. Compare the methodologies of the provided sources. Output a Markdown table comparing their approaches and key characteristics."
    elif mode == 'gap':
        system_prompt = "You are a research assistant analysing academic papers. Discuss the limitations and research gaps mentioned in the provided text."
    else: 
        system_prompt = "You are a knowledgeable academic assistant. Answer the user's question using the provided source context."

    citation_rule = "\n\nCRITICAL INSTRUCTION: You MUST conclude your entire response with a formal 'References' section containing citations for all utilized sources in APA format. You must explicitly use the explicit 'Title' and 'Paper ID' mappings exactly as provided in the Context source blocks."
    system_prompt += citation_rule

    # Use Hugging Face API for completion
    try:
        hf_client = InferenceClient(model="meta-llama/Meta-Llama-3-8B-Instruct", token=HF_TOKEN)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuery: {query}"}
        ]
        
        response = hf_client.chat_completion(
            messages=messages,
            max_tokens=1200,
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"LLM generation failed: {str(e)}"

@app.route('/api/query', methods=['POST'])
def query_papers():
    data = request.json
    mode = data.get('mode', 'qa') 
    query_text = data.get('query', '')
    
    # Map mode to specific section filters strictly using ChromaDB Metadata Filtering rules
    valid_sections = ['abstract', 'introduction', 'methods', 'results', 'discussion']
    if mode == 'synthesis':
        valid_sections = ['abstract', 'results']
    elif mode == 'methodology':
        valid_sections = ['methods']
    elif mode == 'gap':
        valid_sections = ['discussion']
        
    query_target = query_text if query_text.strip() else "general academic discussion"
    
    # Hit ChromaDB filtering native sections
    try:
        results = collection.query(
            query_texts=[query_target],
            n_results=5,
            where={"section_type": {"$in": valid_sections}}
        )
        
        # Unpack ChromaDB generic structure
        retrieved = []
        if results['documents'] and results['documents'][0]:
            for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
                retrieved.append({
                    'paper_id': meta['paper_id'],
                    'section_type': meta['section_type'],
                    'content': doc
                })
    except Exception as e:
        return jsonify({'error': f'ChromaDB vector query failed: {str(e)}'}), 500
        
    if not retrieved:
        return jsonify({'response': "No sections matching the query mode were found. Please check uploaded chunks."})
        
    # Pass to Hugging Face LLM
    response_text = synthesize_with_llm(mode, query_text, retrieved)
    
    return jsonify({'response': response_text, 'chunks': retrieved})

@app.route('/api/clustering', methods=['GET'])
def clustering_data():
    try:
        all_docs = collection.get(include=['embeddings', 'metadatas'])
        
        if not all_docs or not all_docs.get('embeddings') or len(all_docs['embeddings']) < 2:
            return jsonify({"nodes": [], "links": []})
            
        embeddings = np.array(all_docs['embeddings'])
        metadatas = all_docs['metadatas']
        
        nodes = []
        for meta in metadatas:
            paper_id = meta['paper_id']
            title = papers.get(paper_id, {}).get('title', 'Unknown')
            if not any(n['id'] == paper_id for n in nodes):
                nodes.append({
                    "id": paper_id,
                    "title": title[:50] + "..." if len(title) > 50 else title,
                    "group": 1
                })
                
        # Aggregate chunk embeddings to paper level
        paper_embeddings = {}
        for emb, meta in zip(embeddings, metadatas):
            pid = meta['paper_id']
            if pid not in paper_embeddings:
                paper_embeddings[pid] = []
            paper_embeddings[pid].append(emb)
            
        for pid in paper_embeddings:
            paper_embeddings[pid] = np.mean(paper_embeddings[pid], axis=0)
            
        links = []
        p_ids = list(paper_embeddings.keys())
        for i in range(len(p_ids)):
            for j in range(i+1, len(p_ids)):
                v1 = paper_embeddings[p_ids[i]]
                v2 = paper_embeddings[p_ids[j]]
                
                # Compute mathematical Cosine Similarity Density
                sim = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
                
                if sim > 0.65: # Thematic boundary threshold
                    links.append({
                        "source": p_ids[i],
                        "target": p_ids[j],
                        "value": float(sim)
                    })
    
        return jsonify({"nodes": nodes, "links": links})
    except Exception as e:
        print(f"Clustering matrix error: {e}")
        return jsonify({"nodes": [], "links": []})


# ---------------------------------------------------------------------------
# ML analysis routes
# ---------------------------------------------------------------------------

@app.route('/api/papers', methods=['GET'])
def list_papers():
    """Return metadata for all uploaded papers (id, title, chunk_types)."""
    safe = [
        {k: v for k, v in p.items() if k != 'sections'}
        for p in papers.values()
    ]
    return jsonify({'papers': safe})


@app.route('/api/paper/<paper_id>/ml-analysis', methods=['POST'])
def paper_ml_analysis(paper_id):
    """Run full ML analysis (section classification + limitations + summaries).

    Results are cached on the paper dict so repeated calls are instant.
    """
    if paper_id not in papers:
        return jsonify({'error': 'Paper not found'}), 404

    paper = papers[paper_id]

    # Return cached result if already computed
    if 'ml_analysis' in paper:
        return jsonify(paper['ml_analysis'])

    sections = paper.get('sections', [])
    if not sections:
        return jsonify({'error': 'No sections available for this paper'}), 400

    try:
        result = ml_service.analyze_paper(paper_id, sections)
        papers[paper_id]['ml_analysis'] = result
        return jsonify(result)
    except Exception as exc:
        return jsonify({'error': f'ML analysis failed: {str(exc)}'}), 500


@app.route('/api/paper/<paper_id>/limitations', methods=['GET'])
def paper_limitations(paper_id):
    """Return extracted limitation sentences for a paper.

    Uses cached ML analysis when available; otherwise runs pattern detection.
    """
    if paper_id not in papers:
        return jsonify({'error': 'Paper not found'}), 404

    cached = papers[paper_id].get('ml_analysis')
    if cached and 'limitations' in cached:
        return jsonify({'paper_id': paper_id, 'limitations': cached['limitations']})

    sections = papers[paper_id].get('sections', [])
    if not sections:
        return jsonify({'paper_id': paper_id, 'limitations': []})

    limitations = ml_service.detect_limitations(sections)
    return jsonify({'paper_id': paper_id, 'limitations': limitations})


@app.route('/api/paper/<paper_id>/sections', methods=['GET'])
def paper_sections(paper_id):
    """Return section chunks enriched with ML labels when analysis has run."""
    if paper_id not in papers:
        return jsonify({'error': 'Paper not found'}), 404

    paper = papers[paper_id]
    ml_analysis = paper.get('ml_analysis')

    if ml_analysis:
        return jsonify({
            'paper_id': paper_id,
            'sections': ml_analysis.get('classified_sections', []),
            'section_distribution': ml_analysis.get('section_distribution', {}),
        })

    # Fallback: raw sections without ML labels
    sections = paper.get('sections', [])
    dist: dict = {}
    for s in sections:
        st = s.get('section_type', 'unknown')
        dist[st] = dist.get(st, 0) + 1

    return jsonify({
        'paper_id': paper_id,
        'sections': [
            {'section_type': s['section_type'], 'content_preview': s['content'][:200]}
            for s in sections
        ],
        'section_distribution': dist,
    })


# ---------------------------------------------------------------------------
# Multi-agent research workflow endpoints
# ---------------------------------------------------------------------------

@app.route('/api/research/agent-run', methods=['POST'])
def agent_run():
    """Run the multi-agent research workflow.

    Request JSON:
        query   (str, required)   – The research question.
        mode    (str, optional)   – synthesis | methodology | gap | qa (default: qa)
        paper_id (str, optional)  – Restrict retrieval to a specific paper.
    """
    if not AGENT_ENABLED:
        return jsonify({'error': 'Agent workflow is disabled (AGENT_ENABLED=false)'}), 503

    data = request.get_json(silent=True) or {}
    query = (data.get('query') or '').strip()
    mode = data.get('mode', 'qa')
    paper_id = data.get('paper_id') or None

    if not query:
        return jsonify({'error': 'query is required'}), 400

    if paper_id and paper_id not in papers:
        return jsonify({'error': f'paper_id {paper_id!r} not found'}), 404

    try:
        state = agent_orchestrator.run(query, mode, paper_id)
    except Exception as exc:
        logger.error("agent_run failed: %s", exc, exc_info=True)
        return jsonify({'error': f'Agent workflow error: {exc}'}), 500

    # Register provenance for the agent output (non-blocking)
    if PROVENANCE_ENABLED and state.get('final_response'):
        target_id = paper_id or 'general'
        try:
            provenance_service.register_agent_output(
                target_id,
                state.get('session_id', ''),
                state,
            )
        except Exception as prov_exc:
            logger.warning("Provenance registration failed for agent output: %s", prov_exc)

    # Cache latest agent state on the paper when paper-specific
    if paper_id and paper_id in papers:
        papers[paper_id]['latest_agent_state'] = {
            'session_id': state.get('session_id'),
            'query': state.get('query'),
            'mode': state.get('mode'),
            'workflow_type': state.get('workflow_type'),
            'agent_states': state.get('agent_states'),
            'critique': state.get('critique'),
            'provenance_hash': state.get('provenance_hash'),
            'timestamp': state.get('timestamp'),
        }

    return jsonify(state)


@app.route('/api/research/<paper_id>/agent-state', methods=['GET'])
def get_agent_state(paper_id):
    """Return the cached agent state for the most recent run on a paper."""
    if paper_id not in papers:
        return jsonify({'error': 'Paper not found'}), 404

    agent_state = papers[paper_id].get('latest_agent_state')
    return jsonify({'paper_id': paper_id, 'agent_state': agent_state})


# ---------------------------------------------------------------------------
# Provenance endpoints
# ---------------------------------------------------------------------------

@app.route('/api/provenance/register-upload', methods=['POST'])
def provenance_register_upload():
    """Manually trigger provenance registration for an already-uploaded paper."""
    if not PROVENANCE_ENABLED:
        return jsonify({'error': 'Provenance is disabled (PROVENANCE_ENABLED=false)'}), 503

    data = request.get_json(silent=True) or {}
    paper_id = (data.get('paper_id') or '').strip()

    if not paper_id or paper_id not in papers:
        return jsonify({'error': 'Valid paper_id required'}), 400

    paper = papers[paper_id]
    content = ' '.join(s['content'] for s in paper.get('sections', []))

    try:
        record = provenance_service.register_upload(
            paper_id, paper['filename'], content
        )
    except Exception as exc:
        logger.error("provenance_register_upload failed: %s", exc, exc_info=True)
        return jsonify({'error': str(exc)}), 500

    return jsonify(record)


@app.route('/api/provenance/<paper_id>', methods=['GET'])
def get_provenance(paper_id):
    """Return the full provenance history and chain verification for a paper."""
    history = provenance_service.get_history(paper_id)
    verification = provenance_service.verify_chain(paper_id)
    return jsonify({
        'paper_id': paper_id,
        'records': history,
        'chain_verification': verification,
        'blockchain_mode': 'real' if _blockchain_service.is_real_chain else 'mock',
        'ipfs_enabled': _ipfs_service.is_enabled,
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7860)

