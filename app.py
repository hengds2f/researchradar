import os
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
import PyPDF2
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import json

app = Flask(__name__, static_folder='static')
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# In-memory "database"
papers = {}
paper_chunks = []

def extract_sections(text):
    sections = []
    current_section = 'introduction'
    current_content = []
    
    lines = text.split('\n')
    for line in lines:
        l_upper = line.strip().upper()
        if 'ABSTRACT' in l_upper and len(l_upper) < 20:
            if current_content:
                sections.append({'section_type': current_section, 'content': '\n'.join(current_content).strip()})
            current_section = 'abstract'
            current_content = []
        elif ('METHOD' in l_upper or 'METHODOLOGY' in l_upper) and len(l_upper) < 20:
            if current_content:
                sections.append({'section_type': current_section, 'content': '\n'.join(current_content).strip()})
            current_section = 'methods'
            current_content = []
        elif 'RESULT' in l_upper and len(l_upper) < 20:
            if current_content:
                sections.append({'section_type': current_section, 'content': '\n'.join(current_content).strip()})
            current_section = 'results'
            current_content = []
        elif 'DISCUSSION' in l_upper and len(l_upper) < 20:
            if current_content:
                sections.append({'section_type': current_section, 'content': '\n'.join(current_content).strip()})
            current_section = 'discussion'
            current_content = []
        else:
            current_content.append(line)
            
    if current_content:
        sections.append({'section_type': current_section, 'content': '\n'.join(current_content).strip()})
        
    filtered = [s for s in sections if len(s['content']) > 50]
    
    # Fallback if heuristic failed entirely
    if len(filtered) < 2:
        words = text.split()
        if len(words) > 100:
            q = len(words) // 4
            return [
                {'section_type': 'abstract', 'content': ' '.join(words[:q])},
                {'section_type': 'methods', 'content': ' '.join(words[q:q*2])},
                {'section_type': 'results', 'content': ' '.join(words[q*2:q*3])},
                {'section_type': 'discussion', 'content': ' '.join(words[q*3:])}
            ]
        else:
            return [{'section_type': 'abstract', 'content': text}]
            
    return filtered

def compute_embeddings():
    if not paper_chunks:
        return
    texts = [c['content'] for c in paper_chunks]
    vectorizer = TfidfVectorizer(stop_words='english', max_features=1536)
    tfidf_matrix = vectorizer.fit_transform(texts)
    
    for i, c in enumerate(paper_chunks):
        c['embedding'] = tfidf_matrix[i].toarray()[0]
        
    # Compute paper level embeddings for clustering
    paper_ids = list(papers.keys())
    for pid in paper_ids:
        p_chunks = [c['embedding'] for c in paper_chunks if c['paper_id'] == pid and 'embedding' in c]
        if p_chunks:
            papers[pid]['embedding'] = np.mean(p_chunks, axis=0)

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
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Parse text
            text = ""
            if filename.endswith('.pdf'):
                with open(filepath, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
            else:
                with open(filepath, 'r', encoding='utf-8') as f:
                    text = f.read()
                        
            # Store paper
            paper_id = str(len(papers) + 1)
            papers[paper_id] = {
                'id': paper_id,
                'title': filename.replace('.pdf', ''),
                'filename': filename
            }
            uploaded_papers.append(papers[paper_id])
            
            # Extract chunks
            sections = extract_sections(text)
            for s in sections:
                paper_chunks.append({
                    'id': str(len(paper_chunks) + 1),
                    'paper_id': paper_id,
                    'section_type': s['section_type'],
                    'content': s['content']
                })
                
    compute_embeddings()
    return jsonify({'message': 'Successfully processed', 'papers': uploaded_papers})


def mock_llm_synthesise(mode, query, retrieved):
    if not retrieved:
        return "No relevant information found in the uploaded corpus."
        
    sources = "\n\n".join([f"[{c['paper_id']} - {c['section_type']}]: {c['content'][:200]}..." for c in retrieved])
    
    # Format a fake response trying to look like what an LLM would do.
    response = ""
    if mode == 'synthesis':
        response = f"**Synthesis Report**\n\nBased on your query '{query}', here are the common findings synthesized across the results:\n\n"
        response += "The papers primarily indicate consistent patterns in the data, concluding that the measured phenomena have strong positive correlations overall.\n\n"
        response += "**Sources:**\n" + sources
    elif mode == 'methodology':
        response = f"**Methodology Comparison Table**\n\n| Paper | Method Approach | Key Characteristics |\n|---|---|---|\n"
        for r in retrieved[:3]:
            response += f"| Paper {r['paper_id']} | Empirical study | {r['content'][:50]}... |\n"
        response += "\n\n**Sources:**\n" + sources
    elif mode == 'gap':
        response = f"**Research Gap Analysis**\n\nBased on the discussions in the provided papers:\n\n- The majority of papers note temporal limitations.\n- Several studies highlight the need for larger sample sizes.\n\n"
        response += "**Sources:**\n" + sources
    else: # qna
        response = f"**Answer**\n\nRegarding your question '{query}', the extracted content suggests standard findings typical in this field of research.\n\n"
        response += "**Sources:**\n" + sources
    return response

@app.route('/api/query', methods=['POST'])
def query_papers():
    data = request.json
    mode = data.get('mode', 'qa') # synthesis, methodology, gap, qa
    query_text = data.get('query', '')
    
    # 1. Filter by section type like Supabase filter
    valid_sections = ['abstract', 'introduction', 'methods', 'results', 'discussion']
    if mode == 'synthesis':
        valid_sections = ['abstract', 'results']
    elif mode == 'methodology':
        valid_sections = ['methods']
    elif mode == 'gap':
        valid_sections = ['discussion']
        
    filtered_chunks = [c for c in paper_chunks if c['section_type'] in valid_sections]
    
    if not filtered_chunks:
        return jsonify({'response': "No sections matching the query mode were found. Please upload papers first or check chunks."})
        
    # 2. Mock vector search: TF-IDF similarity with the query. 
    # If no query is provided (e.g. general synthesize all), just return all top filtered chunks.
    if query_text.strip():
        # Fit vectorizer on filtered chunks + query to get similarities
        texts = [c['content'] for c in filtered_chunks] + [query_text]
        vectorizer = TfidfVectorizer(stop_words='english')
        try:
            tfidf_matrix = vectorizer.fit_transform(texts)
            sims = cosine_similarity(tfidf_matrix[-1:], tfidf_matrix[:-1]).flatten()
            
            top_k_indices = sims.argsort()[-5:][::-1] # top 5
            retrieved = [filtered_chunks[i] for i in top_k_indices if sims[i] > 0]
        except ValueError:
            # fallback if tfidf fails due to empty vocab
            retrieved = filtered_chunks[:5]
    else:
        retrieved = filtered_chunks[:5]
        
    # 3. Pass to mock LLM
    response_text = mock_llm_synthesise(mode, query_text, retrieved)
    
    return jsonify({'response': response_text, 'chunks': retrieved})

@app.route('/api/clustering', methods=['GET'])
def clustering_data():
    if not papers:
        return jsonify({"nodes": [], "links": []})
        
    nodes = []
    vector_list = []
    pid_list = []
    
    for pid, p in papers.items():
        if 'embedding' in p:
            nodes.append({"id": pid, "title": p['title'], "group": 1})
            vector_list.append(p['embedding'])
            pid_list.append(pid)
            
    links = []
    if len(vector_list) > 1:
        sim_matrix = cosine_similarity(vector_list)
        for i in range(len(vector_list)):
            for j in range(i+1, len(vector_list)):
                if sim_matrix[i][j] > 0.1: # threshold edge
                    links.append({
                        "source": pid_list[i],
                        "target": pid_list[j],
                        "value": float(sim_matrix[i][j])
                    })
                    
    return jsonify({"nodes": nodes, "links": links})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7860)
