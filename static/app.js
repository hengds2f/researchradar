document.addEventListener('DOMContentLoaded', () => {
    // Nav logic
    const navSynthesis = document.getElementById('nav-synthesis');
    const navCluster = document.getElementById('nav-cluster');
    const viewSynthesis = document.getElementById('synthesis-view');
    const viewCluster = document.getElementById('cluster-view');

    navSynthesis.addEventListener('click', () => {
        navSynthesis.classList.add('active');
        navCluster.classList.remove('active');
        viewSynthesis.classList.remove('hidden');
        viewCluster.classList.add('hidden');
    });

    navCluster.addEventListener('click', () => {
        navCluster.classList.add('active');
        navSynthesis.classList.remove('active');
        viewCluster.classList.remove('hidden');
        viewSynthesis.classList.add('hidden');
        renderD3Clustering();
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
        .then(res => res.json())
        .then(data => {
            if (data.papers) {
                updatePaperList(data.papers);
                dropZone.querySelector('p').textContent = 'Drag & drop more PDFs here, or click to browse';
            }
        })
        .catch(err => {
            console.error('Upload failed', err);
            dropZone.querySelector('p').textContent = 'Upload failed. Try again.';
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
            li.textContent = p.title;
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
            resultContent.innerHTML = '<div class="empty-state">Error generating insights.</div>';
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
});
