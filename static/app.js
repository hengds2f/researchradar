document.addEventListener('DOMContentLoaded', () => {
    // Nav logic
    const navSynthesis = document.getElementById('nav-synthesis');
    const navCluster = document.getElementById('nav-cluster');
    const navAnalysis = document.getElementById('nav-analysis');
    const navAgents = document.getElementById('nav-agents');
    const navProvenance = document.getElementById('nav-provenance');
    const viewSynthesis = document.getElementById('synthesis-view');
    const viewCluster = document.getElementById('cluster-view');
    const viewAnalysis = document.getElementById('analysis-view');
    const viewAgents = document.getElementById('agents-view');
    const viewProvenance = document.getElementById('provenance-view');

    const allNavBtns = [navSynthesis, navCluster, navAnalysis, navAgents, navProvenance];
    const allViews = [viewSynthesis, viewCluster, viewAnalysis, viewAgents, viewProvenance];

    function activateView(activeNav, activeView) {
        allNavBtns.forEach(b => b.classList.remove('active'));
        allViews.forEach(v => v.classList.add('hidden'));
        activeNav.classList.add('active');
        activeView.classList.remove('hidden');
    }

    navSynthesis.addEventListener('click', () => activateView(navSynthesis, viewSynthesis));

    navCluster.addEventListener('click', () => {
        activateView(navCluster, viewCluster);
        renderD3Clustering();
    });

    navAnalysis.addEventListener('click', () => {
        activateView(navAnalysis, viewAnalysis);
        refreshPaperSelector();
    });

    navAgents.addEventListener('click', () => {
        activateView(navAgents, viewAgents);
        refreshAgentPaperSelector();
    });

    navProvenance.addEventListener('click', () => {
        activateView(navProvenance, viewProvenance);
        refreshProvenancePaperSelector();
    });

    // Upload logic
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const paperList = document.getElementById('paper-list');

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });

    function handleFiles(files) {
        if (!files.length) return;
        
        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            if (files[i].type === 'application/pdf' || files[i].type === 'text/plain') {
                formData.append('file', files[i]);
            }
        }

        if (!formData.has('file')) {
            alert('Please upload PDF files only.');
            return;
        }

        dropZone.querySelector('p').textContent = 'Uploading and Parsing...';

        fetch('/api/upload', {
            method: 'POST',
            body: formData
        })
        .then(async res => {
            if (!res.ok) {
                const errText = await res.text();
                throw new Error(errText);
            }
            return res.json();
        })
        .then(data => {
            if (data.papers) {
                updatePaperList(data.papers);
                dropZone.querySelector('p').textContent = 'Drag & drop more PDFs here, or click to browse';
            }
        })
        .catch(err => {
            console.error('Upload failed', err);
            dropZone.querySelector('p').textContent = 'Upload failed: ' + String(err).substring(0, 50);
        });
    }

    let allPapers = [];
    function updatePaperList(papers) {
        allPapers = [...allPapers, ...papers];
        paperList.innerHTML = '';
        const uniquePapers = [...new Map(allPapers.map(item => [item['title'], item])).values()];
        allPapers = uniquePapers;

        if (allPapers.length === 0) {
            paperList.innerHTML = '<li class="empty-state">No papers uploaded yet.</li>';
            return;
        }

        allPapers.forEach(p => {
            const li = document.createElement('li');
            const chunkStr = p.chunk_types ? p.chunk_types.join(', ') : 'abstract, methods, results, discussion';
            li.innerHTML = `<div><strong>${p.title}</strong><br><span style="font-size: 0.75rem; color: #94a3b8;">Extracted Sections: ${chunkStr}</span></div>`;
            paperList.appendChild(li);
        });
    }

    // Query Logic
    const btnSubmit = document.getElementById('btn-submit');
    const queryMode = document.getElementById('query-mode');
    const queryInput = document.getElementById('query-input');
    const resultContent = document.getElementById('result-content');
    const loadingSpinner = document.getElementById('loading-spinner');

    btnSubmit.addEventListener('click', async () => {
        const mode = queryMode.value;
        const query = queryInput.value;
        
        resultContent.innerHTML = '';
        loadingSpinner.classList.remove('hidden');
        resultContent.classList.add('hidden');

        try {
            const res = await fetch('/api/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode, query })
            });
            
            if (!res.ok) {
                const errText = await res.text();
                throw new Error("HTTP " + res.status + " " + errText);
            }
            
            const data = await res.json();
            
            loadingSpinner.classList.add('hidden');
            resultContent.classList.remove('hidden');
            
            if (data.response) {
                resultContent.innerHTML = marked.parse(data.response);
            } else {
                resultContent.innerHTML = '<div class="empty-state">No response generated.</div>';
            }
            
        } catch (err) {
            loadingSpinner.classList.add('hidden');
            resultContent.classList.remove('hidden');
            resultContent.innerHTML = '<div class="empty-state">Error generating insights: ' + String(err).substring(0, 500) + '</div>';
        }
    });

    // D3 variables
    let d3Rendered = false;

    async function renderD3Clustering() {
        if (d3Rendered) return;
        
        const container = document.getElementById('d3-container');
        container.innerHTML = '<div style="padding: 2rem; color: #94a3b8;">Loading cluster map...</div>';
        
        try {
            const res = await fetch('/api/clustering');
            const data = await res.json();
            
            if (!data.nodes || data.nodes.length === 0) {
                container.innerHTML = '<div style="padding: 2rem; color: #94a3b8;">Not enough papers uploaded to cluster yet.</div>';
                return;
            }

            container.innerHTML = '';
            
            const width = container.clientWidth;
            const height = container.clientHeight || 500;
            
            const color = d3.scaleOrdinal(d3.schemePaired);

            const simulation = d3.forceSimulation(data.nodes)
                .force("link", d3.forceLink(data.links).id(d => d.id).distance(100))
                .force("charge", d3.forceManyBody().strength(-300))
                .force("center", d3.forceCenter(width / 2, height / 2));

            const svg = d3.select("#d3-container")
                .append("svg")
                .attr("width", width)
                .attr("height", height);

            const link = svg.append("g")
                .attr("class", "links")
                .selectAll("line")
                .data(data.links)
                .enter().append("line")
                .attr("class", "link")
                .attr("stroke-width", d => Math.sqrt(d.value) * 5);

            const node = svg.append("g")
                .attr("class", "nodes")
                .selectAll("g")
                .data(data.nodes)
                .enter().append("g")
                .call(d3.drag()
                    .on("start", dragstarted)
                    .on("drag", dragged)
                    .on("end", dragended));

            node.append("circle")
                .attr("r", 10)
                .attr("fill", d => color(d.group));

            node.append("text")
                .attr("dx", 15)
                .attr("dy", ".35em")
                .text(d => d.title);

            node.append("title")
                .text(d => d.title);

            simulation.on("tick", () => {
                link
                    .attr("x1", d => d.source.x)
                    .attr("y1", d => d.source.y)
                    .attr("x2", d => d.target.x)
                    .attr("y2", d => d.target.y);

                node
                    .attr("transform", d => `translate(${d.x},${d.y})`);
            });

            function dragstarted(event, d) {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            }

            function dragged(event, d) {
                d.fx = event.x;
                d.fy = event.y;
            }

            function dragended(event, d) {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            }

            d3Rendered = true;

        } catch (e) {
            container.innerHTML = '<div style="padding: 2rem; color: #94a3b8;">Failed to load cluster map.</div>';
            console.error(e);
        }
    }

    // -----------------------------------------------------------------------
    // Paper Analysis View
    // -----------------------------------------------------------------------

    const analysisPaperSelect = document.getElementById('analysis-paper-select');
    const btnRunAnalysis = document.getElementById('btn-run-analysis');
    const analysisLoading = document.getElementById('analysis-loading');
    const sectionsTable = document.getElementById('sections-table');
    const limitationsPanel = document.getElementById('limitations-panel');
    const limitationsList = document.getElementById('limitations-list');
    const summariesPanel = document.getElementById('summaries-panel');
    const summariesContent = document.getElementById('summaries-content');
    const chartEmpty = document.getElementById('chart-empty');

    async function refreshPaperSelector() {
        try {
            const res = await fetch('/api/papers');
            const data = await res.json();
            const papers = data.papers || [];

            analysisPaperSelect.innerHTML = papers.length
                ? '<option value="">-- Select a paper --</option>'
                : '<option value="">-- Upload a paper first --</option>';

            papers.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.title;
                analysisPaperSelect.appendChild(opt);
            });
        } catch (e) {
            console.error('Failed to fetch papers list', e);
        }
    }

    analysisPaperSelect.addEventListener('change', () => {
        btnRunAnalysis.disabled = !analysisPaperSelect.value;
    });

    btnRunAnalysis.addEventListener('click', async () => {
        const paperId = analysisPaperSelect.value;
        if (!paperId) return;

        sectionsTable.innerHTML = '';
        limitationsPanel.classList.add('hidden');
        summariesPanel.classList.add('hidden');
        chartEmpty.style.display = 'block';
        document.getElementById('section-chart').innerHTML = '';
        analysisLoading.classList.remove('hidden');
        btnRunAnalysis.disabled = true;

        try {
            const res = await fetch(`/api/paper/${paperId}/ml-analysis`, { method: 'POST' });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || 'ML analysis failed');
            }
            const data = await res.json();

            analysisLoading.classList.add('hidden');

            renderSectionsTable(data.classified_sections || []);

            if (data.section_distribution && Object.keys(data.section_distribution).length) {
                chartEmpty.style.display = 'none';
                renderSectionDistributionChart(data.section_distribution);
            }

            if (data.limitations && data.limitations.length) {
                limitationsList.innerHTML = '';
                data.limitations.forEach(lim => {
                    const li = document.createElement('li');
                    li.className = 'limitation-item';
                    const badge = lim.source === 'llm' ? '<span class="badge badge-llm">LLM</span>' : '<span class="badge badge-pattern">Pattern</span>';
                    li.innerHTML = `${badge}<span>${escapeHtml(lim.text)}</span>`;
                    limitationsList.appendChild(li);
                });
                limitationsPanel.classList.remove('hidden');
            }

            const summaries = data.section_summaries || {};
            if (Object.keys(summaries).length) {
                summariesContent.innerHTML = '';
                Object.entries(summaries).forEach(([sectionType, summary]) => {
                    if (!summary) return;
                    const div = document.createElement('div');
                    div.className = 'summary-block';
                    div.innerHTML = `<strong class="summary-label">${capitalise(sectionType)}</strong><p>${escapeHtml(summary)}</p>`;
                    summariesContent.appendChild(div);
                });
                summariesPanel.classList.remove('hidden');
            }

        } catch (err) {
            analysisLoading.classList.add('hidden');
            sectionsTable.innerHTML = `<div class="empty-state" style="color:#f87171;">Error: ${escapeHtml(String(err).substring(0, 300))}</div>`;
        } finally {
            btnRunAnalysis.disabled = false;
        }
    });

    function renderSectionsTable(sections) {
        if (!sections.length) {
            sectionsTable.innerHTML = '<div class="empty-state">No sections found.</div>';
            return;
        }

        const rows = sections.map(s => {
            const conf = s.ml_confidence != null ? (s.ml_confidence * 100).toFixed(1) : '—';
            const confWidth = s.ml_confidence ? Math.round(s.ml_confidence * 100) : 0;
            const mlLabel = s.ml_label || '—';
            const rawLabel = s.section_type || '—';

            return `
            <div class="section-row">
                <div class="section-meta">
                    <span class="tag tag-raw">${escapeHtml(rawLabel)}</span>
                    <span class="tag tag-ml">${escapeHtml(mlLabel)}</span>
                </div>
                <div class="confidence-bar-wrap">
                    <div class="confidence-bar" style="width:${confWidth}%"></div>
                    <span class="confidence-label">${conf}%</span>
                </div>
                <p class="section-preview">${escapeHtml((s.content_preview || '').substring(0, 120))}…</p>
            </div>`;
        }).join('');

        sectionsTable.innerHTML = `<div class="sections-list">${rows}</div>`;
    }

    function renderSectionDistributionChart(distribution) {
        const container = document.getElementById('section-chart');
        container.innerHTML = '';

        const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
        const margin = { top: 10, right: 20, bottom: 30, left: 110 };
        const width = (container.clientWidth || 360) - margin.left - margin.right;
        const height = Math.max(entries.length * 36, 120) - margin.top - margin.bottom;

        const color = d3.scaleOrdinal()
            .domain(entries.map(d => d[0]))
            .range(['#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#ec4899']);

        const svg = d3.select('#section-chart')
            .append('svg')
            .attr('width', width + margin.left + margin.right)
            .attr('height', height + margin.top + margin.bottom)
            .append('g')
            .attr('transform', `translate(${margin.left},${margin.top})`);

        const x = d3.scaleLinear()
            .domain([0, d3.max(entries, d => d[1]) + 1])
            .range([0, width]);

        const y = d3.scaleBand()
            .domain(entries.map(d => d[0]))
            .range([0, height])
            .padding(0.25);

        svg.selectAll('.bar')
            .data(entries)
            .enter()
            .append('rect')
            .attr('class', 'bar')
            .attr('x', 0)
            .attr('y', d => y(d[0]))
            .attr('width', d => x(d[1]))
            .attr('height', y.bandwidth())
            .attr('fill', d => color(d[0]))
            .attr('rx', 4);

        svg.selectAll('.bar-label')
            .data(entries)
            .enter()
            .append('text')
            .attr('class', 'bar-label')
            .attr('x', d => x(d[1]) + 6)
            .attr('y', d => y(d[0]) + y.bandwidth() / 2)
            .attr('dy', '0.35em')
            .attr('fill', '#94a3b8')
            .attr('font-size', '12px')
            .text(d => d[1]);

        svg.append('g')
            .call(d3.axisLeft(y).tickSize(0))
            .selectAll('text')
            .attr('fill', '#cbd5e1')
            .attr('font-size', '12px');

        svg.select('.domain').remove();
    }

    // -----------------------------------------------------------------------
    // Agent Workflow View
    // -----------------------------------------------------------------------

    const agentPaperSelect = document.getElementById('agent-paper-select');
    const agentMode = document.getElementById('agent-mode');
    const agentQuery = document.getElementById('agent-query');
    const btnAgentRun = document.getElementById('btn-agent-run');
    const agentLoading = document.getElementById('agent-loading');
    const agentResult = document.getElementById('agent-result');
    const agentCritiquePanel = document.getElementById('agent-critique-panel');
    const critiqueConfidenceBadge = document.getElementById('critique-confidence-badge');
    const critiqueScore = document.getElementById('critique-score');
    const critiqueProvenance = document.getElementById('critique-provenance');
    const critiqueDetails = document.getElementById('critique-details');

    async function refreshAgentPaperSelector() {
        try {
            const res = await fetch('/api/papers');
            const data = await res.json();
            const papers = data.papers || [];
            agentPaperSelect.innerHTML = '<option value="">All papers (cross-paper)</option>';
            papers.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.title;
                agentPaperSelect.appendChild(opt);
            });
        } catch (e) {
            console.error('Failed to fetch papers for agent selector', e);
        }
    }

    function resetPipeline() {
        document.querySelectorAll('.pipeline-step').forEach(step => {
            step.dataset.status = 'pending';
            step.querySelector('.step-status').textContent = 'pending';
            step.querySelector('.step-dot').className = 'step-dot';
        });
    }

    function updatePipelineStep(agentName, status, extra) {
        const step = document.querySelector(`.pipeline-step[data-agent="${agentName}"]`);
        if (!step) return;
        step.dataset.status = status;
        const dot = step.querySelector('.step-dot');
        const statusEl = step.querySelector('.step-status');
        dot.className = `step-dot step-dot-${status}`;
        let label = status;
        if (extra) label += ` — ${extra}`;
        statusEl.textContent = label;
    }

    function renderPipelineFromState(agentStates) {
        if (!agentStates) return;
        Object.entries(agentStates).forEach(([agent, info]) => {
            let extra = '';
            if (info.output) {
                if (info.output.workflow_type) extra = info.output.workflow_type;
                else if (info.output.chunk_count !== undefined) extra = `${info.output.chunk_count} chunks`;
                else if (info.output.confidence_level) extra = info.output.confidence_level;
                else if (info.output.method) extra = info.output.method;
            }
            updatePipelineStep(agent, info.status, extra);
        });
    }

    btnAgentRun.addEventListener('click', async () => {
        const query = agentQuery.value.trim();
        if (!query) { agentQuery.focus(); return; }

        const mode = agentMode.value;
        const paperId = agentPaperSelect.value || null;

        agentResult.innerHTML = '';
        agentCritiquePanel.classList.add('hidden');
        agentLoading.classList.remove('hidden');
        btnAgentRun.disabled = true;
        resetPipeline();

        try {
            const res = await fetch('/api/research/agent-run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, mode, paper_id: paperId }),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || `HTTP ${res.status}`);
            }

            const state = await res.json();

            agentLoading.classList.add('hidden');
            renderPipelineFromState(state.agent_states);

            // Render critique panel
            const critique = state.critique || {};
            const confLevel = critique.confidence_level || 'unknown';
            critiqueConfidenceBadge.textContent = `Confidence: ${confLevel}`;
            critiqueConfidenceBadge.className = `confidence-badge confidence-${confLevel}`;
            critiqueScore.textContent = `Quality: ${critique.overall_quality_score || '—'}/10`;
            critiqueProvenance.textContent = state.provenance_hash
                ? `🔒 ${state.provenance_hash.substring(0, 12)}…`
                : '';
            critiqueProvenance.title = state.provenance_hash || '';

            const details = [];
            (critique.weak_claims || []).forEach(w =>
                details.push(`<span class="critique-tag tag-weak">⚠ ${escapeHtml(w)}</span>`));
            (critique.missing_evidence || []).forEach(m =>
                details.push(`<span class="critique-tag tag-missing">📋 ${escapeHtml(m)}</span>`));
            (critique.methodological_gaps || []).forEach(g =>
                details.push(`<span class="critique-tag tag-gap">🔬 ${escapeHtml(g)}</span>`));
            critiqueDetails.innerHTML = details.join('');
            agentCritiquePanel.classList.remove('hidden');

            // Render final response
            const response = state.final_response || state.synthesis || 'No response generated.';
            if (state.error) {
                agentResult.innerHTML = `<div class="empty-state" style="color:#f87171;">Error: ${escapeHtml(state.error)}</div>`;
            } else {
                agentResult.innerHTML = marked.parse(response);
            }

        } catch (err) {
            agentLoading.classList.add('hidden');
            agentResult.innerHTML = `<div class="empty-state" style="color:#f87171;">Error: ${escapeHtml(String(err))}</div>`;
        } finally {
            btnAgentRun.disabled = false;
        }
    });

    // -----------------------------------------------------------------------
    // Provenance View
    // -----------------------------------------------------------------------

    const provenancePaperSelect = document.getElementById('provenance-paper-select');
    const btnLoadProvenance = document.getElementById('btn-load-provenance');
    const chainStatus = document.getElementById('chain-status');
    const chainIndicator = document.getElementById('chain-indicator');
    const chainValidLabel = document.getElementById('chain-valid-label');
    const chainMessage = document.getElementById('chain-message');
    const chainModeBadge = document.getElementById('chain-mode-badge');
    const chainIpfsBadge = document.getElementById('chain-ipfs-badge');
    const chainRecordCount = document.getElementById('chain-record-count');
    const provenanceLoading = document.getElementById('provenance-loading');
    const provenanceTimeline = document.getElementById('provenance-timeline');

    async function refreshProvenancePaperSelector() {
        try {
            const res = await fetch('/api/papers');
            const data = await res.json();
            const papers = data.papers || [];
            provenancePaperSelect.innerHTML = papers.length
                ? '<option value="">-- Select a paper --</option>'
                : '<option value="">-- Upload a paper first --</option>';
            papers.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.title;
                provenancePaperSelect.appendChild(opt);
            });
            btnLoadProvenance.disabled = !papers.length;
        } catch (e) {
            console.error('Failed to refresh provenance selector', e);
        }
    }

    provenancePaperSelect.addEventListener('change', () => {
        btnLoadProvenance.disabled = !provenancePaperSelect.value;
    });

    btnLoadProvenance.addEventListener('click', async () => {
        const paperId = provenancePaperSelect.value;
        if (!paperId) return;

        provenanceLoading.classList.remove('hidden');
        provenanceTimeline.innerHTML = '';
        chainStatus.classList.add('hidden');

        try {
            const res = await fetch(`/api/provenance/${paperId}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            provenanceLoading.classList.add('hidden');

            // Chain status
            const cv = data.chain_verification || {};
            const isValid = cv.valid !== false;
            chainIndicator.className = `chain-status-indicator ${isValid ? 'chain-valid' : 'chain-invalid'}`;
            chainValidLabel.textContent = isValid ? '✓ Chain Intact' : '✗ Chain Compromised';
            chainMessage.textContent = cv.message || '';
            chainModeBadge.textContent = `Blockchain: ${data.blockchain_mode || 'mock'}`;
            chainIpfsBadge.textContent = `IPFS: ${data.ipfs_enabled ? 'enabled' : 'mock'}`;
            chainRecordCount.textContent = `${cv.record_count || 0} record(s)`;
            chainStatus.classList.remove('hidden');

            // Timeline
            const records = data.records || [];
            if (!records.length) {
                provenanceTimeline.innerHTML = '<div class="empty-state">No provenance records found for this paper.</div>';
                return;
            }

            provenanceTimeline.innerHTML = '';
            records.forEach((rec, idx) => {
                const card = document.createElement('div');
                card.className = `provenance-card provenance-${rec.record_type}`;

                const typeIcon = { upload: '📄', summary: '📝', agent_output: '🤖' }[rec.record_type] || '📌';
                const shortHash = rec.content_hash ? rec.content_hash.substring(0, 16) + '…' : '—';
                const shortRecord = rec.record_hash ? rec.record_hash.substring(0, 16) + '…' : '—';
                const txHash = rec.tx_hash ? rec.tx_hash.substring(0, 16) + '…' : null;
                const ipfsCid = rec.ipfs_cid || null;
                const ts = rec.timestamp ? new Date(rec.timestamp).toLocaleString() : '—';
                const meta = rec.metadata || {};

                let metaHtml = '';
                if (meta.filename) metaHtml += `<span class="prov-meta-item">File: ${escapeHtml(meta.filename)}</span>`;
                if (meta.agent_session_id) metaHtml += `<span class="prov-meta-item">Session: ${escapeHtml(meta.agent_session_id.substring(0,8))}…</span>`;
                if (meta.mode) metaHtml += `<span class="prov-meta-item">Mode: ${escapeHtml(meta.mode)}</span>`;
                if (meta.confidence) metaHtml += `<span class="prov-meta-item">Confidence: ${escapeHtml(meta.confidence)}</span>`;
                if (meta.quality_score != null) metaHtml += `<span class="prov-meta-item">Quality: ${meta.quality_score}/10</span>`;

                card.innerHTML = `
                    <div class="prov-card-header">
                        <span class="prov-type-icon">${typeIcon}</span>
                        <span class="prov-type-label">${capitalise(rec.record_type.replace('_', ' '))}</span>
                        <span class="prov-timestamp">${ts}</span>
                    </div>
                    <div class="prov-card-body">
                        <div class="prov-hash-row">
                            <span class="prov-hash-label">Content Hash</span>
                            <code class="prov-hash" title="${rec.content_hash}">${shortHash}</code>
                        </div>
                        <div class="prov-hash-row">
                            <span class="prov-hash-label">Record Hash</span>
                            <code class="prov-hash" title="${rec.record_hash}">${shortRecord}</code>
                        </div>
                        ${txHash ? `<div class="prov-hash-row">
                            <span class="prov-hash-label">Tx Hash</span>
                            <code class="prov-hash prov-tx" title="${rec.tx_hash}">${txHash}</code>
                        </div>` : ''}
                        ${ipfsCid ? `<div class="prov-hash-row">
                            <span class="prov-hash-label">IPFS CID</span>
                            <code class="prov-hash prov-ipfs" title="${ipfsCid}">${ipfsCid.substring(0, 20)}…</code>
                        </div>` : ''}
                        ${metaHtml ? `<div class="prov-meta">${metaHtml}</div>` : ''}
                    </div>
                `;
                provenanceTimeline.appendChild(card);
            });

        } catch (err) {
            provenanceLoading.classList.add('hidden');
            provenanceTimeline.innerHTML = `<div class="empty-state" style="color:#f87171;">Error: ${escapeHtml(String(err))}</div>`;
        }
    });

    // Utility helpers
    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function capitalise(str) {
        return str.charAt(0).toUpperCase() + str.slice(1);
    }
});

    navCluster.addEventListener('click', () => {
        activateView(navCluster, viewCluster);
        renderD3Clustering();
    });

    navAnalysis.addEventListener('click', () => {
        activateView(navAnalysis, viewAnalysis);
        refreshPaperSelector();
    });

    // Upload logic
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const paperList = document.getElementById('paper-list');

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });

    function handleFiles(files) {
        if (!files.length) return;
        
        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            if (files[i].type === 'application/pdf' || files[i].type === 'text/plain') {
                formData.append('file', files[i]);
            }
        }

        if (!formData.has('file')) {
            alert('Please upload PDF files only.');
            return;
        }

        dropZone.querySelector('p').textContent = 'Uploading and Parsing...';

        fetch('/api/upload', {
            method: 'POST',
            body: formData
        })
        .then(async res => {
            if (!res.ok) {
                const errText = await res.text();
                throw new Error(errText);
            }
            return res.json();
        })
        .then(data => {
            if (data.papers) {
                updatePaperList(data.papers);
                dropZone.querySelector('p').textContent = 'Drag & drop more PDFs here, or click to browse';
            }
        })
        .catch(err => {
            console.error('Upload failed', err);
            // Show the first 50 chars of the error to the user to help debug
            dropZone.querySelector('p').textContent = 'Upload failed: ' + String(err).substring(0, 50);
        });
    }

    let allPapers = [];
    function updatePaperList(papers) {
        allPapers = [...allPapers, ...papers];
        paperList.innerHTML = '';
        const uniquePapers = [...new Map(allPapers.map(item => [item['title'], item])).values()];
        allPapers = uniquePapers;

        if (allPapers.length === 0) {
            paperList.innerHTML = '<li class="empty-state">No papers uploaded yet.</li>';
            return;
        }

        allPapers.forEach(p => {
            const li = document.createElement('li');
            const chunkStr = p.chunk_types ? p.chunk_types.join(', ') : 'abstract, methods, results, discussion';
            li.innerHTML = `<div><strong>${p.title}</strong><br><span style="font-size: 0.75rem; color: #94a3b8;">Extracted Sections: ${chunkStr}</span></div>`;
            paperList.appendChild(li);
        });
    }

    // Query Logic
    const btnSubmit = document.getElementById('btn-submit');
    const queryMode = document.getElementById('query-mode');
    const queryInput = document.getElementById('query-input');
    const resultContent = document.getElementById('result-content');
    const loadingSpinner = document.getElementById('loading-spinner');

    btnSubmit.addEventListener('click', async () => {
        const mode = queryMode.value;
        const query = queryInput.value;
        
        resultContent.innerHTML = '';
        loadingSpinner.classList.remove('hidden');
        resultContent.classList.add('hidden');

        try {
            const res = await fetch('/api/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode, query })
            });
            
            if (!res.ok) {
                const errText = await res.text();
                throw new Error("HTTP " + res.status + " " + errText);
            }
            
            const data = await res.json();
            
            loadingSpinner.classList.add('hidden');
            resultContent.classList.remove('hidden');
            
            if (data.response) {
                resultContent.innerHTML = marked.parse(data.response);
            } else {
                resultContent.innerHTML = '<div class="empty-state">No response generated.</div>';
            }
            
        } catch (err) {
            loadingSpinner.classList.add('hidden');
            resultContent.classList.remove('hidden');
            resultContent.innerHTML = '<div class="empty-state">Error generating insights: ' + String(err).substring(0, 500) + '</div>';
        }
    });

    // D3 variables
    let d3Rendered = false;

    async function renderD3Clustering() {
        if (d3Rendered) return;
        
        const container = document.getElementById('d3-container');
        container.innerHTML = '<div style="padding: 2rem; color: #94a3b8;">Loading cluster map...</div>';
        
        try {
            const res = await fetch('/api/clustering');
            const data = await res.json();
            
            if (!data.nodes || data.nodes.length === 0) {
                container.innerHTML = '<div style="padding: 2rem; color: #94a3b8;">Not enough papers uploaded to cluster yet.</div>';
                return;
            }

            container.innerHTML = '';
            
            // Render Graph
            const width = container.clientWidth;
            const height = container.clientHeight || 500;
            
            const color = d3.scaleOrdinal(d3.schemePaired);

            const simulation = d3.forceSimulation(data.nodes)
                .force("link", d3.forceLink(data.links).id(d => d.id).distance(100))
                .force("charge", d3.forceManyBody().strength(-300))
                .force("center", d3.forceCenter(width / 2, height / 2));

            const svg = d3.select("#d3-container")
                .append("svg")
                .attr("width", width)
                .attr("height", height);

            const link = svg.append("g")
                .attr("class", "links")
                .selectAll("line")
                .data(data.links)
                .enter().append("line")
                .attr("class", "link")
                .attr("stroke-width", d => Math.sqrt(d.value) * 5);

            const node = svg.append("g")
                .attr("class", "nodes")
                .selectAll("g")
                .data(data.nodes)
                .enter().append("g")
                .call(d3.drag()
                    .on("start", dragstarted)
                    .on("drag", dragged)
                    .on("end", dragended));

            node.append("circle")
                .attr("r", 10)
                .attr("fill", d => color(d.group));

            node.append("text")
                .attr("dx", 15)
                .attr("dy", ".35em")
                .text(d => d.title);

            node.append("title")
                .text(d => d.title);

            simulation.on("tick", () => {
                link
                    .attr("x1", d => d.source.x)
                    .attr("y1", d => d.source.y)
                    .attr("x2", d => d.target.x)
                    .attr("y2", d => d.target.y);

                node
                    .attr("transform", d => `translate(${d.x},${d.y})`);
            });

            function dragstarted(event, d) {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            }

            function dragged(event, d) {
                d.fx = event.x;
                d.fy = event.y;
            }

            function dragended(event, d) {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            }

            d3Rendered = true;

        } catch (e) {
            container.innerHTML = '<div style="padding: 2rem; color: #94a3b8;">Failed to load cluster map.</div>';
            console.error(e);
        }
    }

    // -----------------------------------------------------------------------
    // Paper Analysis View
    // -----------------------------------------------------------------------

    const analysisPaperSelect = document.getElementById('analysis-paper-select');
    const btnRunAnalysis = document.getElementById('btn-run-analysis');
    const analysisLoading = document.getElementById('analysis-loading');
    const sectionsTable = document.getElementById('sections-table');
    const limitationsPanel = document.getElementById('limitations-panel');
    const limitationsList = document.getElementById('limitations-list');
    const summariesPanel = document.getElementById('summaries-panel');
    const summariesContent = document.getElementById('summaries-content');
    const chartEmpty = document.getElementById('chart-empty');

    // Populate the paper dropdown from /api/papers
    async function refreshPaperSelector() {
        try {
            const res = await fetch('/api/papers');
            const data = await res.json();
            const papers = data.papers || [];

            analysisPaperSelect.innerHTML = papers.length
                ? '<option value="">-- Select a paper --</option>'
                : '<option value="">-- Upload a paper first --</option>';

            papers.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.title;
                analysisPaperSelect.appendChild(opt);
            });
        } catch (e) {
            console.error('Failed to fetch papers list', e);
        }
    }

    analysisPaperSelect.addEventListener('change', () => {
        btnRunAnalysis.disabled = !analysisPaperSelect.value;
    });

    btnRunAnalysis.addEventListener('click', async () => {
        const paperId = analysisPaperSelect.value;
        if (!paperId) return;

        // Reset UI
        sectionsTable.innerHTML = '';
        limitationsPanel.classList.add('hidden');
        summariesPanel.classList.add('hidden');
        chartEmpty.style.display = 'block';
        document.getElementById('section-chart').innerHTML = '';
        analysisLoading.classList.remove('hidden');
        btnRunAnalysis.disabled = true;

        try {
            const res = await fetch(`/api/paper/${paperId}/ml-analysis`, { method: 'POST' });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || 'ML analysis failed');
            }
            const data = await res.json();

            analysisLoading.classList.add('hidden');

            // Render section classification table
            renderSectionsTable(data.classified_sections || []);

            // Render D3 bar chart for section distribution
            if (data.section_distribution && Object.keys(data.section_distribution).length) {
                chartEmpty.style.display = 'none';
                renderSectionDistributionChart(data.section_distribution);
            }

            // Render limitations
            if (data.limitations && data.limitations.length) {
                limitationsList.innerHTML = '';
                data.limitations.forEach(lim => {
                    const li = document.createElement('li');
                    li.className = 'limitation-item';
                    const badge = lim.source === 'llm' ? '<span class="badge badge-llm">LLM</span>' : '<span class="badge badge-pattern">Pattern</span>';
                    li.innerHTML = `${badge}<span>${escapeHtml(lim.text)}</span>`;
                    limitationsList.appendChild(li);
                });
                limitationsPanel.classList.remove('hidden');
            }

            // Render section summaries
            const summaries = data.section_summaries || {};
            if (Object.keys(summaries).length) {
                summariesContent.innerHTML = '';
                Object.entries(summaries).forEach(([sectionType, summary]) => {
                    if (!summary) return;
                    const div = document.createElement('div');
                    div.className = 'summary-block';
                    div.innerHTML = `<strong class="summary-label">${capitalise(sectionType)}</strong><p>${escapeHtml(summary)}</p>`;
                    summariesContent.appendChild(div);
                });
                summariesPanel.classList.remove('hidden');
            }

        } catch (err) {
            analysisLoading.classList.add('hidden');
            sectionsTable.innerHTML = `<div class="empty-state" style="color:#f87171;">Error: ${escapeHtml(String(err).substring(0, 300))}</div>`;
        } finally {
            btnRunAnalysis.disabled = false;
        }
    });

    function renderSectionsTable(sections) {
        if (!sections.length) {
            sectionsTable.innerHTML = '<div class="empty-state">No sections found.</div>';
            return;
        }

        const rows = sections.map(s => {
            const conf = s.ml_confidence != null ? (s.ml_confidence * 100).toFixed(1) : '—';
            const confWidth = s.ml_confidence ? Math.round(s.ml_confidence * 100) : 0;
            const mlLabel = s.ml_label || '—';
            const rawLabel = s.section_type || '—';

            return `
            <div class="section-row">
                <div class="section-meta">
                    <span class="tag tag-raw">${escapeHtml(rawLabel)}</span>
                    <span class="tag tag-ml">${escapeHtml(mlLabel)}</span>
                </div>
                <div class="confidence-bar-wrap">
                    <div class="confidence-bar" style="width:${confWidth}%"></div>
                    <span class="confidence-label">${conf}%</span>
                </div>
                <p class="section-preview">${escapeHtml((s.content_preview || '').substring(0, 120))}…</p>
            </div>`;
        }).join('');

        sectionsTable.innerHTML = `<div class="sections-list">${rows}</div>`;
    }

    function renderSectionDistributionChart(distribution) {
        const container = document.getElementById('section-chart');
        container.innerHTML = '';

        const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
        const margin = { top: 10, right: 20, bottom: 30, left: 110 };
        const width = (container.clientWidth || 360) - margin.left - margin.right;
        const height = Math.max(entries.length * 36, 120) - margin.top - margin.bottom;

        const color = d3.scaleOrdinal()
            .domain(entries.map(d => d[0]))
            .range(['#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#ec4899']);

        const svg = d3.select('#section-chart')
            .append('svg')
            .attr('width', width + margin.left + margin.right)
            .attr('height', height + margin.top + margin.bottom)
            .append('g')
            .attr('transform', `translate(${margin.left},${margin.top})`);

        const x = d3.scaleLinear()
            .domain([0, d3.max(entries, d => d[1]) + 1])
            .range([0, width]);

        const y = d3.scaleBand()
            .domain(entries.map(d => d[0]))
            .range([0, height])
            .padding(0.25);

        // Bars
        svg.selectAll('.bar')
            .data(entries)
            .enter()
            .append('rect')
            .attr('class', 'bar')
            .attr('x', 0)
            .attr('y', d => y(d[0]))
            .attr('width', d => x(d[1]))
            .attr('height', y.bandwidth())
            .attr('fill', d => color(d[0]))
            .attr('rx', 4);

        // Value labels
        svg.selectAll('.bar-label')
            .data(entries)
            .enter()
            .append('text')
            .attr('class', 'bar-label')
            .attr('x', d => x(d[1]) + 6)
            .attr('y', d => y(d[0]) + y.bandwidth() / 2)
            .attr('dy', '0.35em')
            .attr('fill', '#94a3b8')
            .attr('font-size', '12px')
            .text(d => d[1]);

        // Y axis
        svg.append('g')
            .call(d3.axisLeft(y).tickSize(0))
            .selectAll('text')
            .attr('fill', '#cbd5e1')
            .attr('font-size', '12px');

        svg.select('.domain').remove();
    }

    // Utility helpers
    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function capitalise(str) {
        return str.charAt(0).toUpperCase() + str.slice(1);
    }
});
