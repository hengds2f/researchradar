document.addEventListener('DOMContentLoaded', () => {
    // Nav logic
    const navSynthesis = document.getElementById('nav-synthesis');
    const navCluster = document.getElementById('nav-cluster');
    const navAnalysis = document.getElementById('nav-analysis');
    const viewSynthesis = document.getElementById('synthesis-view');
    const viewCluster = document.getElementById('cluster-view');
    const viewAnalysis = document.getElementById('analysis-view');

    function activateView(activeNav, activeView) {
        [navSynthesis, navCluster, navAnalysis].forEach(b => b.classList.remove('active'));
        [viewSynthesis, viewCluster, viewAnalysis].forEach(v => v.classList.add('hidden'));
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
