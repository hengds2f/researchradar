document.addEventListener('DOMContentLoaded', () => {

    // -----------------------------------------------------------------------
    // Session isolation — one unique ID per browser tab, never shared
    // -----------------------------------------------------------------------
    let sessionId = sessionStorage.getItem('researchSessionId');
    if (!sessionId) {
        sessionId = crypto.randomUUID();
        sessionStorage.setItem('researchSessionId', sessionId);
    }
    function sessionHeaders(extra) {
        return Object.assign({ 'X-Session-ID': sessionId }, extra);
    }

    // -----------------------------------------------------------------------
    // ActivityLog — real-time status feed for each tool
    // -----------------------------------------------------------------------
    class ActivityLog {
        constructor(elementId) {
            this.el = document.getElementById(elementId);
        }

        _time() {
            return new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
        }

        show() { if (this.el) this.el.classList.remove('hidden'); }
        hide() { if (this.el) this.el.classList.add('hidden'); }

        clear() {
            if (this.el) { this.el.innerHTML = ''; this.show(); }
        }

        add(msg, type = 'info') {
            if (!this.el) return null;
            this.show();
            const icons = { info: '🔄', success: '✅', error: '❌', warning: '⚠️', muted: '•' };
            const entry = document.createElement('div');
            entry.className = `log-entry log-${type}`;
            entry.innerHTML = `<span class="log-icon">${icons[type] || '•'}</span><span class="log-time">${this._time()}</span><span class="log-msg">${msg}</span>`;
            this.el.appendChild(entry);
            this.el.scrollTop = this.el.scrollHeight;
            return entry;
        }

        // Replace the last entry instead of adding a new one
        updateLast(msg, type) {
            if (!this.el) return;
            const entries = this.el.querySelectorAll('.log-entry');
            if (!entries.length) { this.add(msg, type); return; }
            const last = entries[entries.length - 1];
            const icons = { info: '🔄', success: '✅', error: '❌', warning: '⚠️', muted: '•' };
            if (type) last.className = `log-entry log-${type}`;
            if (type) last.querySelector('.log-icon').textContent = icons[type] || '•';
            last.querySelector('.log-msg').textContent = msg;
        }
    }

    // Timed progress simulation — shows animated steps while waiting for the API.
    // Returns an array of timeout IDs so they can be cancelled when the API resolves.
    function simulateProgress(log, steps, intervalMs = 1400) {
        const ids = [];
        steps.forEach((step, i) => {
            const id = setTimeout(() => {
                if (i === 0) { log.clear(); log.add(step, 'info'); }
                else         { log.updateLast(steps[i - 1], 'muted'); log.add(step, 'info'); }
            }, i * intervalMs);
            ids.push(id);
        });
        return ids;
    }

    function cancelSimulation(ids) { ids.forEach(id => clearTimeout(id)); }

    // -----------------------------------------------------------------------
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
        clusterMap.render();
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

        const uploadLog = new ActivityLog('upload-log');
        const uploadSteps = [
            'Reading your file and extracting text…',
            'Identifying paper sections (Introduction, Methods, Results…)',
            'Converting text into searchable vectors (embeddings)…',
            'Indexing content into the knowledge base…',
        ];
        const simIds = simulateProgress(uploadLog, uploadSteps, 1200);

        fetch('/api/upload', {
            method: 'POST',
            headers: sessionHeaders(),
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
            cancelSimulation(simIds);
            if (data.papers) {
                uploadLog.updateLast(uploadSteps[uploadSteps.length - 1], 'muted');
                const count = data.papers.length;
                uploadLog.add(`Paper${count > 1 ? 's' : ''} added successfully — ${count} paper${count > 1 ? 's' : ''} now in your knowledge base`, 'success');
                updatePaperList(data.papers);
                clusterMap.reset();
                // Auto-refresh the map if the user is currently viewing it
                if (!viewCluster.classList.contains('hidden')) {
                    clusterMap.render();
                }
                dropZone.querySelector('p').textContent = 'Drag & drop more PDFs here, or click to browse';
            }
        })
        .catch(err => {
            cancelSimulation(simIds);
            uploadLog.add('Upload failed: ' + String(err).substring(0, 100), 'error');
            console.error('Upload failed', err);
            dropZone.querySelector('p').textContent = 'Upload failed: ' + String(err).substring(0, 50);
        });
    }

    let allPapers = [];

    function renderPaperList() {
        paperList.innerHTML = '';
        if (allPapers.length === 0) {
            paperList.innerHTML = '<li class="empty-state">No papers uploaded yet.</li>';
            return;
        }
        allPapers.forEach(p => {
            const li = document.createElement('li');
            li.dataset.paperId = p.id;
            const chunkStr = p.chunk_types ? p.chunk_types.join(', ') : 'abstract, methods, results, discussion';
            li.innerHTML = `
                <div class="paper-list-info">
                    <strong>${escapeHtml(p.title)}</strong><br>
                    <span style="font-size:0.75rem;color:#94a3b8;">Sections: ${escapeHtml(chunkStr)}</span>
                </div>
                <button class="btn-delete-paper" data-id="${p.id}" title="Delete this paper">✕</button>`;
            li.querySelector('.btn-delete-paper').addEventListener('click', () => deletePaper(p.id));
            paperList.appendChild(li);
        });
    }

    function updatePaperList(newPapers) {
        newPapers.forEach(p => {
            if (!allPapers.find(x => x.id === p.id)) allPapers.push(p);
        });
        renderPaperList();
    }

    async function deletePaper(paperId) {
        const uploadLog = new ActivityLog('upload-log');
        try {
            const res = await fetch(`/api/paper/${encodeURIComponent(paperId)}`, {
                method: 'DELETE',
                headers: sessionHeaders(),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || `HTTP ${res.status}`);
            }
            allPapers = allPapers.filter(p => p.id !== paperId);
            renderPaperList();
            clusterMap.reset();
            uploadLog.add('Paper removed from your knowledge base.', 'success');
        } catch (err) {
            uploadLog.add('Failed to delete paper: ' + String(err).substring(0, 100), 'error');
        }
    }

    // New Session button
    const btnNewSession = document.getElementById('btn-new-session');
    btnNewSession.addEventListener('click', async () => {
        if (allPapers.length === 0) return;
        if (!confirm('Clear all uploaded papers and start a new session?')) return;
        const uploadLog = new ActivityLog('upload-log');
        try {
            const res = await fetch('/api/session', {
                method: 'DELETE',
                headers: sessionHeaders(),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || `HTTP ${res.status}`);
            }
            // Generate a fresh session ID
            sessionId = crypto.randomUUID();
            sessionStorage.setItem('researchSessionId', sessionId);
            allPapers = [];
            renderPaperList();
            clusterMap.reset();
            uploadLog.add('Session cleared — all papers removed. You can now upload new papers.', 'success');
            // Reset result area
            resultContent.innerHTML = '<div class="empty-state">Query results will appear here.</div>';
            resultContent.classList.remove('hidden');
            loadingSpinner.classList.add('hidden');
        } catch (err) {
            uploadLog.add('Failed to clear session: ' + String(err).substring(0, 100), 'error');
        }
    });

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

        const queryLog = new ActivityLog('query-log');
        const modeLabels = {
            synthesis: 'Synthesis — combining findings across all papers',
            methodology: 'Methodology Comparison — comparing how studies were conducted',
            gap: 'Research Gap Analysis — identifying unanswered questions',
            qa: 'General Q&A — searching for a direct answer',
        };
        const querySteps = [
            `Starting analysis in ${modeLabels[mode] || mode} mode…`,
            'Searching your knowledge base for relevant passages…',
            'Retrieving the most informative sections…',
            'Sending evidence to the AI to draft a response…',
            'Generating your answer — almost there…',
        ];
        const simIds = simulateProgress(queryLog, querySteps, 1300);

        try {
            const res = await fetch('/api/query', {
                method: 'POST',
                headers: sessionHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ mode, query })
            });
            
            if (!res.ok) {
                const errText = await res.text();
                throw new Error("HTTP " + res.status + " " + errText);
            }
            
            const data = await res.json();

            cancelSimulation(simIds);
            queryLog.updateLast(querySteps[querySteps.length - 1], 'muted');
            queryLog.add('Response generated successfully', 'success');
            
            loadingSpinner.classList.add('hidden');
            resultContent.classList.remove('hidden');
            
            if (data.response) {
                resultContent.innerHTML = marked.parse(data.response);
            } else {
                resultContent.innerHTML = '<div class="empty-state">No response generated.</div>';
            }
            
        } catch (err) {
            cancelSimulation(simIds);
            queryLog.add('Error generating response: ' + String(err).substring(0, 120), 'error');
            loadingSpinner.classList.add('hidden');
            resultContent.classList.remove('hidden');
            resultContent.innerHTML = '<div class="empty-state">Error generating insights: ' + String(err).substring(0, 500) + '</div>';
        }
    });

    // -----------------------------------------------------------------------
    // Semantic Clustering Map — ClusterMapController
    // -----------------------------------------------------------------------

    const CLUSTER_COLORS = [
        '#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b',
        '#ef4444', '#ec4899', '#14b8a6', '#a855f7', '#f97316',
        '#84cc16', '#0ea5e9', '#6366f1', '#22d3ee', '#fb923c',
        '#e879f9', '#34d399', '#fbbf24', '#60a5fa', '#f43f5e',
    ];
    const OUTLIER_COLOR = '#475569';

    class ClusterMapController {
        constructor() {
            this._rendered = false;
            this._data = null;
            this._showOutliers = true;
            this._showClusterLabels = true;
            this._showPaperLabels = false;
            this._filterCluster = 'all';
            this._filterYear = 'all';
            this._filterSearch = '';
            this._selectedClusterId = null;
            this._highlightActive = false;

            this._chart = document.getElementById('cluster-chart');
            this._empty = document.getElementById('cluster-empty');
            this._loading = document.getElementById('cluster-loading');
            this._log = new ActivityLog('cluster-log');
            this._statsEl = document.getElementById('cluster-stats');
            this._filtersEl = document.getElementById('cluster-filters');
            this._togglesEl = document.getElementById('cluster-toggles');
            this._methodBadge = document.getElementById('cluster-method-badge');
            this._detailPanel = document.getElementById('cluster-detail');

            this._filterClusterEl = document.getElementById('filter-cluster');
            this._filterYearEl = document.getElementById('filter-year');
            this._filterSearchEl = document.getElementById('filter-search');
            this._toggleOutliersEl = document.getElementById('toggle-outliers');
            this._toggleClusterLabelsEl = document.getElementById('toggle-cluster-labels');
            this._togglePaperLabelsEl = document.getElementById('toggle-paper-labels');

            this._detailTitle = document.getElementById('detail-title');
            this._detailAuthors = document.getElementById('detail-authors');
            this._detailYear = document.getElementById('detail-year');
            this._detailCluster = document.getElementById('detail-cluster');
            this._detailSimilarity = document.getElementById('detail-similarity');
            this._detailHighlightBtn = document.getElementById('detail-highlight-cluster');
            this._detailClearBtn = document.getElementById('detail-clear-highlight');
            this._detailClose = document.getElementById('detail-close');
            this._refreshBtn = document.getElementById('cluster-refresh-btn');

            this._setupEventListeners();
        }

        // ── Public ───────────────────────────────────────────────────────────

        reset() {
            this._rendered = false;
            this._data = null;
            this._filterCluster = 'all';
            this._filterYear = 'all';
            this._filterSearch = '';
            this._selectedClusterId = null;
            this._highlightActive = false;
            if (this._filterClusterEl) this._filterClusterEl.value = 'all';
            if (this._filterYearEl)    this._filterYearEl.value    = 'all';
            if (this._filterSearchEl)  this._filterSearchEl.value  = '';
            if (this._chart && typeof Plotly !== 'undefined') Plotly.purge(this._chart);
            this._showEmpty(true);
            this._statsEl.classList.add('hidden');
            this._filtersEl.classList.add('hidden');
            this._togglesEl.classList.add('hidden');
            this._methodBadge.classList.add('hidden');
            this._detailPanel.classList.add('hidden');
            this._refreshBtn.classList.add('hidden');
        }

        async render() {
            if (this._rendered && this._data) return;
            await this._fetchAndRender();
        }

        // ── Setup ────────────────────────────────────────────────────────────

        _setupEventListeners() {
            this._filterClusterEl.addEventListener('change', () => {
                this._filterCluster = this._filterClusterEl.value;
                this._refreshChart();
            });
            this._filterYearEl.addEventListener('change', () => {
                this._filterYear = this._filterYearEl.value;
                this._refreshChart();
            });

            let searchTimer;
            this._filterSearchEl.addEventListener('input', () => {
                clearTimeout(searchTimer);
                searchTimer = setTimeout(() => {
                    this._filterSearch = this._filterSearchEl.value.toLowerCase();
                    this._refreshChart();
                }, 200);
            });

            this._toggleOutliersEl.addEventListener('change', () => {
                this._showOutliers = this._toggleOutliersEl.checked;
                this._refreshChart();
            });
            this._toggleClusterLabelsEl.addEventListener('change', () => {
                this._showClusterLabels = this._toggleClusterLabelsEl.checked;
                this._refreshChart();
            });
            this._togglePaperLabelsEl.addEventListener('change', () => {
                this._showPaperLabels = this._togglePaperLabelsEl.checked;
                this._refreshChart();
            });

            this._detailClose.addEventListener('click', () => {
                this._detailPanel.classList.add('hidden');
                this._clearHighlight();
            });
            this._detailHighlightBtn.addEventListener('click', () => {
                if (this._selectedClusterId !== null) this._applyHighlight(this._selectedClusterId);
            });
            this._detailClearBtn.addEventListener('click', () => this._clearHighlight());
            this._refreshBtn.addEventListener('click', () => {
                this.reset();
                this.render();
            });
        }

        // ── Fetch + render ────────────────────────────────────────────────────

        async _fetchAndRender() {
            this._showEmpty(false);
            this._loading.classList.remove('hidden');
            this._log.clear();

            const simIds = simulateProgress(this._log, [
                'Fetching paper embeddings from the knowledge base…',
                'Normalising and projecting to 2-D (UMAP / PCA)…',
                'Running cluster detection (HDBSCAN / KMeans)…',
                'Building the interactive scatter map…',
            ], 1200);

            try {
                const res = await fetch('/api/clustering', { headers: sessionHeaders() });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();

                cancelSimulation(simIds);
                this._loading.classList.add('hidden');

                if (!data.points || data.points.length < 2) {
                    this._log.add('Upload at least 2 papers to generate the map.', 'warning');
                    this._showEmpty(true);
                    return;
                }

                this._data = data;
                this._rendered = true;

                this._updateStats(data.stats);
                this._populateClusterFilter(data.clusters);
                this._populateYearFilter(data.points);
                this._updateMethodBadge(data.method);
                this._renderChart();

                const { n_papers, n_clusters } = data.stats;
                this._log.add(
                    `Map ready — ${n_papers} paper${n_papers !== 1 ? 's' : ''}, ` +
                    `${n_clusters} cluster${n_clusters !== 1 ? 's' : ''} ` +
                    `(​${data.method.reduction.toUpperCase()} + ${data.method.clustering.toUpperCase()})`,
                    'success',
                );

                this._statsEl.classList.remove('hidden');
                this._filtersEl.classList.remove('hidden');
                this._togglesEl.classList.remove('hidden');
                this._methodBadge.classList.remove('hidden');
                this._refreshBtn.classList.remove('hidden');

            } catch (err) {
                cancelSimulation(simIds);
                this._loading.classList.add('hidden');
                this._log.add('Failed to load cluster map — ' + String(err).substring(0, 100), 'error');
                this._showEmpty(true);
                console.error('[ClusterMap]', err);
            }
        }

        // ── Chart ─────────────────────────────────────────────────────────────

        _getFilteredPoints() {
            if (!this._data) return [];
            return this._data.points.filter(p => {
                if (p.is_outlier && !this._showOutliers) return false;
                if (this._filterCluster !== 'all' && String(p.cluster_id) !== this._filterCluster) return false;
                if (this._filterYear !== 'all') {
                    if (p.year == null || String(p.year) !== this._filterYear) return false;
                }
                if (this._filterSearch && !p.title.toLowerCase().includes(this._filterSearch)) return false;
                return true;
            });
        }

        _buildTraces(filteredPoints) {
            const textMode = this._showPaperLabels ? 'markers+text' : 'markers';
            const grouped = new Map();

            for (const p of filteredPoints) {
                const key = p.is_outlier ? '__outlier__' : String(p.cluster_id);
                if (!grouped.has(key)) grouped.set(key, []);
                grouped.get(key).push(p);
            }

            const traces = [];
            for (const [key, pts] of grouped) {
                const isOutlier = key === '__outlier__';
                const color = isOutlier ? OUTLIER_COLOR
                    : (pts[0].color || CLUSTER_COLORS[pts[0].cluster_id % CLUSTER_COLORS.length]);
                const label = isOutlier ? 'Outliers' : pts[0].cluster_label;

                traces.push({
                    type: 'scatter',
                    mode: textMode,
                    name: label,
                    x: pts.map(p => p.x),
                    y: pts.map(p => p.y),
                    text: pts.map(p => p.title.length > 28 ? p.title.slice(0, 26) + '…' : p.title),
                    textposition: 'top center',
                    textfont: { size: 10, color: '#cbd5e1' },
                    customdata: pts,
                    marker: {
                        size: isOutlier ? 9 : 12,
                        color,
                        symbol: isOutlier ? 'x' : 'circle',
                        opacity: isOutlier ? 0.55 : 0.88,
                        line: { color: 'rgba(255,255,255,0.2)', width: 1 },
                    },
                    hovertemplate:
                        '<b>%{customdata.title}</b><br>' +
                        'Authors: %{customdata.authors}<br>' +
                        'Year: %{customdata.year}<br>' +
                        'Cluster: %{customdata.cluster_label}<br>' +
                        'Similarity: %{customdata.similarity_score}' +
                        '<extra></extra>',
                    hoverlabel: {
                        bgcolor: '#1e293b',
                        bordercolor: color,
                        font: { color: '#f8fafc', size: 13 },
                    },
                });
            }

            const annotations = this._showClusterLabels
                ? this._buildCentroidAnnotations(filteredPoints) : [];

            return { traces, annotations };
        }

        _buildCentroidAnnotations(filteredPoints) {
            const groups = new Map();
            for (const p of filteredPoints) {
                if (p.is_outlier) continue;
                if (!groups.has(p.cluster_id))
                    groups.set(p.cluster_id, { xs: [], ys: [], label: p.cluster_label, color: p.color });
                const g = groups.get(p.cluster_id);
                g.xs.push(p.x); g.ys.push(p.y);
            }
            const annotations = [];
            for (const [, g] of groups) {
                const cx = g.xs.reduce((a, b) => a + b, 0) / g.xs.length;
                const cy = g.ys.reduce((a, b) => a + b, 0) / g.ys.length;
                annotations.push({
                    x: cx, y: cy,
                    text: `<b>${escapeHtml(g.label)}</b>`,
                    showarrow: false,
                    font: { size: 12, color: g.color || '#94a3b8' },
                    bgcolor: 'rgba(15,23,42,0.75)',
                    bordercolor: g.color || '#334155',
                    borderwidth: 1,
                    borderpad: 4,
                });
            }
            return annotations;
        }

        _plotlyLayout(annotations) {
            return {
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor:  'rgba(15,23,42,0.5)',
                font: { color: '#94a3b8', family: 'Inter, sans-serif' },
                xaxis: {
                    showgrid: true, gridcolor: 'rgba(255,255,255,0.05)',
                    zeroline: false, showticklabels: false, title: '',
                },
                yaxis: {
                    showgrid: true, gridcolor: 'rgba(255,255,255,0.05)',
                    zeroline: false, showticklabels: false, title: '',
                    scaleanchor: 'x', scaleratio: 1,
                },
                legend: {
                    bgcolor: 'rgba(15,23,42,0.8)',
                    bordercolor: 'rgba(255,255,255,0.1)',
                    borderwidth: 1,
                    font: { color: '#e2e8f0', size: 12 },
                    itemsizing: 'constant',
                },
                margin: { l: 20, r: 20, t: 20, b: 20 },
                hovermode: 'closest',
                dragmode: 'pan',
                annotations,
                uirevision: 'cluster-map',
            };
        }

        _plotlyConfig() {
            return {
                responsive: true,
                displayModeBar: true,
                modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
                displaylogo: false,
                scrollZoom: true,
            };
        }

        _renderChart() {
            const filtered = this._getFilteredPoints();
            if (!filtered.length) {
                if (this._chart && typeof Plotly !== 'undefined') Plotly.purge(this._chart);
                return;
            }
            const { traces, annotations } = this._buildTraces(filtered);
            Plotly.react(this._chart, traces, this._plotlyLayout(annotations), this._plotlyConfig());
            this._attachPlotlyEvents();
        }

        _refreshChart() {
            if (!this._data) return;
            this._renderChart();
            if (this._highlightActive && this._selectedClusterId !== null)
                this._applyHighlight(this._selectedClusterId);
        }

        // ── Plotly events ─────────────────────────────────────────────────────

        _attachPlotlyEvents() {
            if (!this._chart || !this._chart.on) return;
            this._chart.removeAllListeners && this._chart.removeAllListeners('plotly_click');
            this._chart.on('plotly_click', eventData => {
                if (!eventData || !eventData.points.length) return;
                const paper = eventData.points[0].customdata;
                if (paper) this._showDetail(paper);
            });
        }

        // ── Highlight ─────────────────────────────────────────────────────────

        _applyHighlight(clusterId) {
            if (!this._chart || !this._data) return;
            this._highlightActive = true;
            this._selectedClusterId = clusterId;

            const filtered = this._getFilteredPoints();
            const { traces, annotations } = this._buildTraces(filtered);
            const updated = traces.map(t => {
                const inCluster = (t.customdata || []).some(p => p && p.cluster_id === clusterId);
                return { ...t, marker: { ...t.marker, opacity: inCluster ? 0.95 : 0.12 } };
            });
            Plotly.react(this._chart, updated, this._plotlyLayout(annotations), this._plotlyConfig());

            this._detailHighlightBtn.classList.add('hidden');
            this._detailClearBtn.classList.remove('hidden');
        }

        _clearHighlight() {
            this._highlightActive = false;
            this._detailHighlightBtn.classList.remove('hidden');
            this._detailClearBtn.classList.add('hidden');
            this._refreshChart();
        }

        // ── Detail panel ──────────────────────────────────────────────────────

        _showDetail(paper) {
            this._selectedClusterId = paper.cluster_id;
            this._detailTitle.textContent     = paper.title  || '—';
            this._detailAuthors.textContent   = paper.authors || 'Unknown';
            this._detailYear.textContent      = paper.year != null ? paper.year : '—';
            this._detailCluster.textContent   = paper.cluster_label || '—';
            this._detailSimilarity.textContent =
                paper.similarity_score != null
                    ? `${(paper.similarity_score * 100).toFixed(1)}%` : '—';
            this._detailPanel.classList.remove('hidden');
            this._detailHighlightBtn.classList.remove('hidden');
            this._detailClearBtn.classList.add('hidden');
        }

        // ── Stats / filters / badges ──────────────────────────────────────────

        _updateStats(stats) {
            document.getElementById('stat-papers').textContent   = stats.n_papers;
            document.getElementById('stat-clusters').textContent = stats.n_clusters;
            document.getElementById('stat-largest').textContent  = stats.largest_cluster_size;
            document.getElementById('stat-outliers').textContent = stats.outlier_count;
        }

        _populateClusterFilter(clusters) {
            this._filterClusterEl.innerHTML = '<option value="all">All clusters</option>';
            clusters.forEach(c => {
                const opt = document.createElement('option');
                opt.value = String(c.id);
                opt.textContent = `${c.label} (${c.size})`;
                this._filterClusterEl.appendChild(opt);
            });
            if (this._data.stats.outlier_count > 0) {
                const opt = document.createElement('option');
                opt.value = '-1';
                opt.textContent = `Outliers (${this._data.stats.outlier_count})`;
                this._filterClusterEl.appendChild(opt);
            }
        }

        _populateYearFilter(points) {
            const years = [...new Set(points.map(p => p.year).filter(Boolean))].sort().reverse();
            this._filterYearEl.innerHTML = '<option value="all">All years</option>';
            years.forEach(y => {
                const opt = document.createElement('option');
                opt.value = String(y);
                opt.textContent = y;
                this._filterYearEl.appendChild(opt);
            });
        }

        _updateMethodBadge(method) {
            this._methodBadge.textContent =
                `${method.reduction.toUpperCase()} + ${method.clustering.toUpperCase()}`;
        }

        _showEmpty(show) {
            if (!this._empty) return;
            this._empty.style.display = show ? 'flex' : 'none';
            if (this._chart) this._chart.style.display = show ? 'none' : 'block';
        }
    }

    // instantiate after DOM is ready
    const clusterMap = new ClusterMapController();

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
            const res = await fetch('/api/papers', { headers: sessionHeaders() });
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

        const analysisLog = new ActivityLog('analysis-log');
        const simIds = simulateProgress(analysisLog, [
            'Loading the selected paper from your knowledge base…',
            'Scanning each paragraph and classifying its section type…',
            'Calculating confidence scores for each classification…',
            'Searching for limitation statements and caveats…',
            'Generating plain-English summaries for each section…',
        ], 1500);

        try {
            const res = await fetch(`/api/paper/${paperId}/ml-analysis`, { method: 'POST', headers: sessionHeaders() });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || 'ML analysis failed');
            }
            const data = await res.json();

            cancelSimulation(simIds);
            analysisLog.updateLast('Generating plain-English summaries for each section…', 'muted');

            const secCount = (data.classified_sections || []).length;
            const limCount = (data.limitations || []).length;
            analysisLog.add(`Analysis complete — ${secCount} sections classified, ${limCount} limitation${limCount !== 1 ? 's' : ''} detected`, 'success');

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
            cancelSimulation(simIds);
            const analysisLog2 = new ActivityLog('analysis-log');
            analysisLog2.add('Analysis failed: ' + String(err).substring(0, 120), 'error');
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
            const res = await fetch('/api/papers', { headers: sessionHeaders() });
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

    // Agent-step descriptions for the live log
    const AGENT_STEP_MSGS = {
        router:    'Router is reading your question and choosing the best analysis strategy…',
        retrieval: 'Retrieval is searching your papers for the most relevant passages…',
        synthesis: 'Synthesis is combining the evidence into a drafted answer…',
        critic:    'Critic is reviewing the draft for weak claims and missing evidence…',
        writer:    'Writer is polishing the final response for clarity and accuracy…',
    };

    const AGENT_DONE_MSGS = {
        router:    'Router done — strategy selected',
        retrieval: 'Retrieval done — evidence collected from your papers',
        synthesis: 'Synthesis done — draft answer created',
        critic:    'Critic done — quality review complete',
        writer:    'Writer done — final response ready',
    };

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

        const agentLog = new ActivityLog('agent-log');
        agentLog.clear();
        agentLog.add('Starting the 5-agent research pipeline…', 'info');

        // Simulate the pipeline steps advancing in real time while the API runs
        const agentOrder = ['router', 'retrieval', 'synthesis', 'critic', 'writer'];
        const simIds = [];
        agentOrder.forEach((agent, i) => {
            // Mark as "running" at staggered intervals
            simIds.push(setTimeout(() => {
                updatePipelineStep(agent, 'running');
                agentLog.add(AGENT_STEP_MSGS[agent], 'info');
            }, i * 2200));
        });

        try {
            const res = await fetch('/api/research/agent-run', {
                method: 'POST',
                headers: sessionHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ query, mode, paper_id: paperId }),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || `HTTP ${res.status}`);
            }

            const state = await res.json();

            cancelSimulation(simIds);
            agentLoading.classList.add('hidden');
            renderPipelineFromState(state.agent_states);

            // Log final step outcomes
            agentOrder.forEach(agent => {
                const info = (state.agent_states || {})[agent] || {};
                if (info.status === 'completed') agentLog.add(AGENT_DONE_MSGS[agent], 'success');
                else if (info.status === 'failed')   agentLog.add(`${capitalise(agent)} encountered an issue — pipeline continued`, 'warning');
            });

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
                agentLog.add('Pipeline complete — your research answer is ready below', 'success');
            }

        } catch (err) {
            cancelSimulation(simIds);
            agentLoading.classList.add('hidden');
            agentLog.add('Pipeline failed: ' + String(err).substring(0, 120), 'error');
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
    const btnExportJson = document.getElementById('btn-export-json');
    const btnDownloadProof = document.getElementById('btn-download-proof');
    const provenanceActions = document.getElementById('provenance-actions');
    const chainStatus = document.getElementById('chain-status');
    const chainIndicator = document.getElementById('chain-indicator');
    const chainValidLabel = document.getElementById('chain-valid-label');
    const chainMessage = document.getElementById('chain-message');
    const chainModeBadge = document.getElementById('chain-mode-badge');
    const chainIpfsBadge = document.getElementById('chain-ipfs-badge');
    const chainRecordCount = document.getElementById('chain-record-count');
    const provenanceLoading = document.getElementById('provenance-loading');
    const provenanceTimeline = document.getElementById('provenance-timeline');

    // Track the currently loaded paper id and capabilities for export/proof actions
    let _currentProvPaperId = null;
    let _currentExplorerUrl = '';
    let _currentIpfsEnabled = false;

    async function refreshProvenancePaperSelector() {
        try {
            const res = await fetch('/api/papers', { headers: sessionHeaders() });
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
        provenanceActions.classList.add('hidden');

        const provLog = new ActivityLog('provenance-log');
        const simIds = simulateProgress(provLog, [
            'Fetching provenance records from the ledger…',
            'Verifying the integrity of the hash chain…',
            'Checking each record\'s fingerprint against the stored values…',
        ], 1000);

        try {
            const res = await fetch(`/api/provenance/${paperId}`, { headers: sessionHeaders() });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            cancelSimulation(simIds);
            provenanceLoading.classList.add('hidden');

            // Stash state for export / proof buttons
            _currentProvPaperId = paperId;
            _currentExplorerUrl = data.blockchain_explorer_url || '';
            _currentIpfsEnabled = !!data.ipfs_enabled;

            // Chain status
            const cv = data.chain_verification || {};
            const isValid = cv.valid !== false;
            const recCount = cv.record_count || 0;

            if (isValid) {
                provLog.add(`Chain verified — ${recCount} record${recCount !== 1 ? 's' : ''} intact, no tampering detected`, 'success');
            } else {
                provLog.add(`Chain integrity issue detected: ${cv.message || 'chain may be compromised'}`, 'error');
            }

            chainIndicator.className = `chain-status-indicator ${isValid ? 'chain-valid' : 'chain-invalid'}`;
            chainValidLabel.textContent = isValid ? '✓ Chain Intact' : '✗ Chain Compromised';
            chainMessage.textContent = cv.message || '';
            chainModeBadge.textContent = `Blockchain: ${data.blockchain_mode || 'mock'}`;
            chainIpfsBadge.textContent = `IPFS: ${data.ipfs_enabled ? 'enabled' : 'mock'}`;
            chainRecordCount.textContent = `${recCount} record(s)`;
            chainStatus.classList.remove('hidden');

            // Show export/proof actions
            provenanceActions.classList.remove('hidden');

            // Timeline
            const records = data.records || [];
            if (!records.length) {
                provenanceTimeline.innerHTML = '<div class="empty-state">No provenance records found for this paper.</div>';
                return;
            }

            provenanceTimeline.innerHTML = '';
            records.forEach((rec) => {
                const card = document.createElement('div');
                card.className = `provenance-card provenance-${rec.record_type}`;

                const typeIcon = { upload: '📄', summary: '📝', agent_output: '🤖' }[rec.record_type] || '📌';
                const shortHash = rec.content_hash ? rec.content_hash.substring(0, 16) + '…' : '—';
                const shortRecord = rec.record_hash ? rec.record_hash.substring(0, 16) + '…' : '—';
                const txHash = rec.tx_hash || null;
                const ipfsCid = rec.ipfs_cid || null;
                const ts = rec.timestamp ? new Date(rec.timestamp).toLocaleString() : '—';
                const meta = rec.metadata || {};

                // tx_hash row — clickable link when blockchain is real
                let txRow = '';
                if (txHash) {
                    const txShort = txHash.substring(0, 16) + '…';
                    if (_currentExplorerUrl) {
                        txRow = `<div class="prov-hash-row">
                            <span class="prov-hash-label">Tx Hash</span>
                            <a class="prov-hash prov-tx prov-link" href="${_currentExplorerUrl}/tx/${encodeURIComponent(txHash)}" target="_blank" rel="noopener" title="${escapeHtml(txHash)}">${escapeHtml(txShort)} ↗</a>
                            <button class="prov-copy-btn" data-copy="${escapeHtml(txHash)}" title="Copy full hash">⧉</button>
                        </div>`;
                    } else {
                        txRow = `<div class="prov-hash-row">
                            <span class="prov-hash-label">Tx Hash <span class="prov-mock-badge">(mock)</span></span>
                            <code class="prov-hash prov-tx" title="${escapeHtml(txHash)}">${escapeHtml(txShort)}</code>
                            <button class="prov-copy-btn" data-copy="${escapeHtml(txHash)}" title="Copy full hash">⧉</button>
                        </div>`;
                    }
                }

                // IPFS CID row — clickable link when IPFS is real
                let ipfsRow = '';
                if (ipfsCid) {
                    const cidShort = ipfsCid.substring(0, 20) + '…';
                    if (_currentIpfsEnabled) {
                        ipfsRow = `<div class="prov-hash-row">
                            <span class="prov-hash-label">IPFS CID</span>
                            <a class="prov-hash prov-ipfs prov-link" href="https://ipfs.io/ipfs/${encodeURIComponent(ipfsCid)}" target="_blank" rel="noopener" title="${escapeHtml(ipfsCid)}">${escapeHtml(cidShort)} ↗</a>
                            <button class="prov-copy-btn" data-copy="${escapeHtml(ipfsCid)}" title="Copy full CID">⧉</button>
                        </div>`;
                    } else {
                        ipfsRow = `<div class="prov-hash-row">
                            <span class="prov-hash-label">IPFS CID <span class="prov-mock-badge">(mock)</span></span>
                            <code class="prov-hash prov-ipfs" title="${escapeHtml(ipfsCid)}">${escapeHtml(cidShort)}</code>
                            <button class="prov-copy-btn" data-copy="${escapeHtml(ipfsCid)}" title="Copy full CID">⧉</button>
                        </div>`;
                    }
                }

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
                            <code class="prov-hash" title="${escapeHtml(rec.content_hash)}">${escapeHtml(shortHash)}</code>
                            <button class="prov-copy-btn" data-copy="${escapeHtml(rec.content_hash)}" title="Copy full hash">⧉</button>
                        </div>
                        <div class="prov-hash-row">
                            <span class="prov-hash-label">Record Hash</span>
                            <code class="prov-hash" title="${escapeHtml(rec.record_hash)}">${escapeHtml(shortRecord)}</code>
                            <button class="prov-copy-btn" data-copy="${escapeHtml(rec.record_hash)}" title="Copy full hash">⧉</button>
                        </div>
                        ${txRow}
                        ${ipfsRow}
                        ${metaHtml ? `<div class="prov-meta">${metaHtml}</div>` : ''}
                    </div>
                `;

                card.querySelectorAll('.prov-copy-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const text = btn.dataset.copy;
                        navigator.clipboard.writeText(text).then(() => {
                            btn.textContent = '✓';
                            btn.classList.add('prov-copy-btn--copied');
                            setTimeout(() => {
                                btn.textContent = '⧉';
                                btn.classList.remove('prov-copy-btn--copied');
                            }, 1500);
                        }).catch(() => {
                            const ta = document.createElement('textarea');
                            ta.value = text;
                            ta.style.position = 'fixed';
                            ta.style.opacity = '0';
                            document.body.appendChild(ta);
                            ta.select();
                            document.execCommand('copy');
                            document.body.removeChild(ta);
                            btn.textContent = '✓';
                            btn.classList.add('prov-copy-btn--copied');
                            setTimeout(() => {
                                btn.textContent = '⧉';
                                btn.classList.remove('prov-copy-btn--copied');
                            }, 1500);
                        });
                    });
                });
                provenanceTimeline.appendChild(card);
            });

        } catch (err) {
            cancelSimulation([]);
            const provLog2 = new ActivityLog('provenance-log');
            provLog2.add('Failed to load provenance records: ' + String(err).substring(0, 100), 'error');
            provenanceLoading.classList.add('hidden');
            provenanceTimeline.innerHTML = `<div class="empty-state" style="color:#f87171;">Error: ${escapeHtml(String(err))}</div>`;
        }
    });

    // Export full chain JSON
    btnExportJson.addEventListener('click', () => {
        if (!_currentProvPaperId) return;
        window.location.href = `/api/provenance/${encodeURIComponent(_currentProvPaperId)}/export?session_id=${encodeURIComponent(sessionId)}`;
    });

    // Download structured proof document
    btnDownloadProof.addEventListener('click', () => {
        if (!_currentProvPaperId) return;
        window.location.href = `/api/provenance/${encodeURIComponent(_currentProvPaperId)}/proof?session_id=${encodeURIComponent(sessionId)}`;
    });

    // Verify hash tool
    const btnVerifyHash = document.getElementById('btn-verify-hash');
    const verifyHashInput = document.getElementById('verify-hash-input');
    const verifyHashResult = document.getElementById('verify-hash-result');

    btnVerifyHash.addEventListener('click', async () => {
        const hash = verifyHashInput.value.trim().toLowerCase();
        if (!hash) { verifyHashInput.focus(); return; }

        verifyHashResult.className = 'verify-result';
        verifyHashResult.textContent = 'Searching…';
        verifyHashResult.classList.remove('hidden');

        try {
            const res = await fetch('/api/provenance/verify-hash', {
                method: 'POST',
                headers: sessionHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ content_hash: hash }),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || `HTTP ${res.status}`);
            }
            const data = await res.json();

            if (data.found) {
                const matchLines = data.matches.map(m => {
                    const ts = m.timestamp ? new Date(m.timestamp).toLocaleString() : '—';
                    const txNote = m.tx_hash ? ` · tx: ${m.tx_hash.substring(0,12)}…` : '';
                    const ipfsNote = m.ipfs_cid ? ` · IPFS: ${m.ipfs_cid.substring(0,14)}…` : '';
                    return `<div class="verify-match">
                        <span class="verify-match-icon">✓</span>
                        <div>
                            <strong>${escapeHtml(m.paper_title)}</strong>
                            <span class="verify-match-meta">${escapeHtml(m.record_type.replace('_',' '))} · ${ts}${txNote}${ipfsNote}</span>
                        </div>
                    </div>`;
                }).join('');
                verifyHashResult.innerHTML = `<div class="verify-found">
                    <p class="verify-found-title">✓ Hash verified — found in ${data.match_count} record${data.match_count !== 1 ? 's' : ''}</p>
                    ${matchLines}
                </div>`;
                verifyHashResult.className = 'verify-result verify-result--found';
            } else {
                verifyHashResult.innerHTML = `<p>✗ Hash not found in any provenance record. This content has not been registered, or was registered in a different session.</p>`;
                verifyHashResult.className = 'verify-result verify-result--notfound';
            }
        } catch (err) {
            verifyHashResult.textContent = 'Error: ' + String(err).substring(0, 120);
            verifyHashResult.className = 'verify-result verify-result--error';
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
