import os
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
import PyPDF2
import numpy as np
import re

# AI Integration
import chromadb
from huggingface_hub import InferenceClient

app = Flask(__name__, static_folder='static')

# Environment configuration
HF_TOKEN = os.environ.get("HF_TOKEN")

if not HF_TOKEN:
    print("Warning: Missing HF_TOKEN environment variable. LLM Synthesis will fail.")

# Initialize ChromaDB (Local In-Memory Vector Database)
chroma_client = chromadb.Client()
collection = chroma_client.get_or_create_collection(name="research_papers")

papers = {}

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
                'title': filename.replace('.pdf', ''),
                'filename': filename,
                'chunk_types': chunk_types
            }
            uploaded_papers.append(papers[paper_id])
            
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
    if not retrieved_chunks:
        return "No relevant information found in the uploaded corpus."
        
    context = ""
    for i, c in enumerate(retrieved_chunks):
        context += f"\n\n--- Source [{i+1}] (Paper ID: {c['paper_id']} - Section: {c['section_type']}) ---\n"
        context += c['content'][:2500] 

    if mode == 'synthesis':
        system_prompt = "You are a research synthesis assistant. Compare the provided sources and summarize the common findings. Explicitly cite the source paper IDs in your response."
    elif mode == 'methodology':
        system_prompt = "You are a research assistant. Compare the methodologies of the provided sources. Output a Markdown table comparing their approaches and key characteristics."
    elif mode == 'gap':
        system_prompt = "You are a research assistant analysing academic papers. Discuss the limitations and research gaps mentioned in the provided text."
    else: 
        system_prompt = "You are a knowledgeable academic assistant. Answer the user's question using the provided source context. Cite Paper IDs."

    # Use Hugging Face API for completion
    try:
        hf_client = InferenceClient(model="meta-llama/Meta-Llama-3-8B-Instruct", token=HF_TOKEN)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuery: {query}"}
        ]
        
        response = hf_client.chat_completion(
            messages=messages,
            max_tokens=800,
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
    return jsonify({"nodes": [], "links": []})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7860)
