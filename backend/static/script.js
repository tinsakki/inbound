document.addEventListener('DOMContentLoaded', () => {
    // --- UI Elements ---
    const dropArea = document.getElementById('dropArea');
    const fileInput = document.getElementById('file');
    const fileState = document.getElementById('fileState');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const removeFileBtn = document.getElementById('removeFileBtn');
    const uploadForm = document.getElementById('uploadForm');
    const statusMessage = document.getElementById('statusMessage');
    const submitBtn = document.getElementById('submitBtn');
    
    // Filters
    const filterForm = document.getElementById('filterForm');
    const clearFiltersBtn = document.getElementById('clearFiltersBtn');
    
    // --- Global State ---
    let volumeChart = null;
    let loadingTimeout;

    // --- Drag and Drop Logic ---
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        if(dropArea) dropArea.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }

    ['dragenter', 'dragover'].forEach(eventName => {
        if(dropArea) dropArea.addEventListener(eventName, () => dropArea.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        if(dropArea) dropArea.addEventListener(eventName, () => dropArea.classList.remove('dragover'), false);
    });

    if(dropArea) dropArea.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleFile(files[0]);
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(files[0]);
            fileInput.files = dataTransfer.files;
        }
    });

    if(dropArea) dropArea.addEventListener('click', () => fileInput.click());

    if(fileInput) fileInput.addEventListener('change', function() {
        if (this.files.length > 0) {
            handleFile(this.files[0]);
        }
    });

    function handleFile(file) {
        dropArea.style.display = 'none';
        fileState.style.display = 'block';
        fileName.textContent = file.name;
        fileSize.textContent = (file.size / 1024 / 1024).toFixed(2) + ' MB';
    }

    if(removeFileBtn) removeFileBtn.addEventListener('click', () => {
        fileInput.value = '';
        fileState.style.display = 'none';
        dropArea.style.display = 'block';
    });


    // --- Advanced Filters Logic ---
    const initFilterOptions = async () => {
        try {
            const res = await fetch('/api/metrics/filters');
            if(res.ok) {
                const data = await res.json();
                populateSelect('filter_agent', data.agents);
                populateSelect('filter_campaign', data.campaigns);
                populateSelect('filter_status', data.statuses);
                populateSelect('filter_disposition', data.dispositions);
            }
        } catch(e) { console.error(e); }
    };

    const populateSelect = (id, options) => {
        const sel = document.getElementById(id);
        if(!sel) return;
        options.forEach(opt => {
            const el = document.createElement('option');
            el.value = opt; el.textContent = opt;
            sel.appendChild(el);
        });
    };

    const fetchMetrics = async () => {
        try {
            // Build Query Params
            const params = new URLSearchParams();
            if(filterForm) {
                new FormData(filterForm).forEach((value, key) => {
                    if (value.trim() !== '') params.append(key, value.trim());
                });
            }

            const response = await fetch('/api/metrics/aggregate?' + params.toString());
            if (response.ok) {
                const data = await response.json();
                processDashboardData(data);
            }
        } catch (error) {
            console.error('Failed to load dynamic metrics:', error);
        }
    };

    const processDashboardData = (data) => {
        if (!data || !data.summary) return;
        const summary = data.summary;

        // Update KPIs with counting animation
        animateValue("kpiTotalCalls", parseInt(document.getElementById("kpiTotalCalls").textContent.replace(/,/g, '')) || 0, summary['Total Calls Offered'], 800);
        animateValue("kpiAgentCalls", parseInt(document.getElementById("kpiAgentCalls").textContent.replace(/,/g, '')) || 0, summary['Agent Calls Offered'], 800);
        animateValue("kpiCallsAnswered", parseInt(document.getElementById("kpiCallsAnswered").textContent.replace(/,/g, '')) || 0, summary['Calls Answered'], 800);
        
        animateValue("kpiSlCalls", parseInt(document.getElementById("kpiSlCalls").textContent.replace(/,/g, '')) || 0, summary['SL Calls'], 800);
        animateValue("kpiWhCalls", parseInt(document.getElementById("kpiWhCalls").textContent.replace(/,/g, '')) || 0, summary['WH Total Calls Offered'], 800);
        
        animateValue("kpiOverallAbn", parseInt(document.getElementById("kpiOverallAbn")?.textContent.replace(/,/g, '')) || 0, summary['Overall Abn'], 800);
        animateValue("kpiNetAbn", parseInt(document.getElementById("kpiNetAbn")?.textContent.replace(/,/g, '')) || 0, summary['Net Abandoned'], 800);
        animateValue("kpiShortAbn", parseInt(document.getElementById("kpiShortAbn")?.textContent.replace(/,/g, '')) || 0, summary['Short Call Abn'], 800);
        
        animateValue("kpiGrossPct", parseFloat(document.getElementById("kpiGrossPct")?.textContent) || 0, summary['Gross Abn %'], 800, true);

        const answerRate = summary['Total Calls Offered'] > 0 ? ((summary['Calls Answered'] / summary['Total Calls Offered']) * 100).toFixed(1) : 0;
        document.getElementById("kpiAnswerRate").textContent = `${answerRate}%`;
        document.getElementById("kpiWhAnswered").textContent = `${summary['WH Calls Answered']} WH Total Calls Answered`;
        document.getElementById("kpiShortPct").textContent = `${summary['Short Call %']}% Short Call % - Abn`;

        // Populate Raw Status in Table
        const tableBody = document.getElementById('tableBody');
        tableBody.innerHTML = `
            <tr>
                <td><span style="color:var(--text-main); font-weight:500;">Live Query</span></td>
                <td><span class="badge" style="color:var(--accent-purple)">DWH Engine</span></td>
                <td style="font-family:monospace; font-size:1.1rem">${data.raw_count.toLocaleString()} rows</td>
                <td>Active Dataset</td>
                <td><span class="badge-success">Succeed</span></td>
            </tr>
        `;

        // Update Chart
        renderChart(data.chart_data);
    };

    function animateValue(id, start, end, duration, floatVals=false) {
        if (start === end) return;
        let obj = document.getElementById(id);
        if(!obj) return;
        let range = end - start;
        let current = start;
        let increment = end > start ? (floatVals ? 0.1 : 1) : (floatVals ? -0.1 : -1);
        let stepTime = Math.abs(Math.floor(duration / (range/Math.abs(increment))));
        if (stepTime < 10) stepTime = 10;
        
        let timer = setInterval(function() {
            current += increment;
            if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
                current = end;
                clearInterval(timer);
            }
            obj.innerHTML = floatVals ? current.toFixed(2) : Math.floor(current).toLocaleString();
        }, stepTime);
    }

    // --- Chart.js Rendering ---
    const renderChart = (chartData) => {
        const ctx = document.getElementById('metricsChart').getContext('2d');
        
        const labels = chartData.map(d => d.call_date);
        const dataTotal = chartData.map(d => d.total_calls);
        const dataAnswered = chartData.map(d => d.answered_calls);

        if (volumeChart) volumeChart.destroy();

        Chart.defaults.color = '#94a3b8';
        Chart.defaults.font.family = "'Plus Jakarta Sans', sans-serif";

        volumeChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Total Calls',
                        data: dataTotal,
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        borderWidth: 3,
                        pointBackgroundColor: '#05050a',
                        pointBorderColor: '#3b82f6',
                        fill: true,
                        tension: 0.4
                    },
                    {
                        label: 'Calls Answered',
                        data: dataAnswered,
                        borderColor: '#10b981',
                        borderWidth: 2,
                        pointBackgroundColor: '#05050a',
                        pointBorderColor: '#10b981',
                        borderDash: [5, 5],
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top', labels: { usePointStyle: true, boxWidth: 8 } }
                },
                scales: {
                    x: { grid: { color: 'rgba(255, 255, 255, 0.05)' } },
                    y: { beginAtZero: true, grid: { color: 'rgba(255, 255, 255, 0.05)' } }
                }
            }
        });
    };

    // --- Upload Action ---
    if(uploadForm) {
        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            statusMessage.className = 'status-alert';
            statusMessage.textContent = 'Migrating dataset into Warehouse...';
            statusMessage.style.display = 'block';
            submitBtn.disabled = true;

            const formData = new FormData(uploadForm);

            try {
                const response = await fetch('/api/upload/', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();

                if (response.ok) {
                    statusMessage.className = 'status-alert success';
                    statusMessage.textContent = `Migration complete. Loaded ${result.metrics_saved} dynamic records.`;
                    
                    setTimeout(() => {
                        removeFileBtn.click();
                        statusMessage.style.display = 'none';
                    }, 3000);

                    initFilterOptions(); // Refresh dropdowns
                    fetchMetrics(); // Force Refresh metrics
                } else {
                    statusMessage.className = 'status-alert error';
                    statusMessage.textContent = result.detail || 'An error occurred';
                }
            } catch (error) {
                statusMessage.className = 'status-alert error';
                statusMessage.textContent = 'Connection compromised. Re-establishing link...';
            } finally {
                submitBtn.disabled = false;
            }
        });
    }

    // Manual Trigger for Filters via Apply Button
    if(filterForm) {
        filterForm.addEventListener('submit', (e) => {
            e.preventDefault();
            fetchMetrics();
        });
    }

    if(clearFiltersBtn) {
        clearFiltersBtn.addEventListener('click', (e) => {
            e.preventDefault();
            filterForm.reset();
            fetchMetrics();
        });
    }

    const wipeDataBtn = document.getElementById('wipeDataBtn');
    if (wipeDataBtn) {
        wipeDataBtn.addEventListener('click', async () => {
            if (confirm("WARNING: Are you sure you want to permanently delete ALL uploaded spreadsheet data natively stored in the Data Warehouse? This cannot be undone.")) {
                try {
                    const res = await fetch('/api/upload/clear', { method: 'DELETE' });
                    if (res.ok) {
                        fetchMetrics();
                        initFilterOptions();
                    } else {
                        alert("Failed to wipe database.");
                    }
                } catch (e) {
                    console.error("Error wiping database", e);
                }
            }
        });
    }

    // Initial Bootstrap
    initFilterOptions();
    fetchMetrics();
});
