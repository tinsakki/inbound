document.addEventListener('DOMContentLoaded', () => {
    // --- Global State ---
    let volumeChart = null;
    let distChart = null;
    let lastDashboardData = null;
    let currentViewType = 'daily';
    let currentDistType = 'dispositions';

    // Theme Elements
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = document.getElementById('themeIcon');

    // --- Tab Controller (Executive KPI Layers) ---
    const initTabs = () => {
        const tabs = document.querySelectorAll('.kpi-tab[data-group]');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const group = tab.getAttribute('data-group');
                // Update buttons
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                // Update visibility
                document.querySelectorAll('.metric-group').forEach(g => g.classList.remove('active'));
                document.getElementById(`group-${group}`).classList.add('active');
            });
        });

        // Outcome switcher
        const distBtns = document.querySelectorAll('.kpi-tab[data-dist]');
        distBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                distBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentDistType = btn.getAttribute('data-dist');
                if (lastDashboardData) renderDistChart(lastDashboardData.distributions[currentDistType]);
            });
        });
    };

    // --- Theme Logic ---
    const initTheme = () => {
        const savedTheme = localStorage.getItem('theme') || 'dark';
        if (savedTheme === 'light') {
            document.body.classList.add('light-mode');
            if(themeIcon) themeIcon.setAttribute('data-lucide', 'sun');
        } else {
            document.body.classList.remove('light-mode');
            if(themeIcon) themeIcon.setAttribute('data-lucide', 'moon');
        }
        lucide.createIcons();
    };

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const isLight = document.body.classList.toggle('light-mode');
            localStorage.setItem('theme', isLight ? 'light' : 'dark');
            if(themeIcon) themeIcon.setAttribute('data-lucide', isLight ? 'sun' : 'moon');
            lucide.createIcons();
            if (lastDashboardData) {
                renderTrajectoryChart(lastDashboardData.chart_data);
                renderDistChart(lastDashboardData.distributions[currentDistType]);
            }
        });
    }

    // --- Fetch & Data Processing ---
    const fetchMetrics = async () => {
        try {
            const params = new URLSearchParams();
            params.append('view_type', currentViewType);
            params.append('agent_hc', document.getElementById('param_agent_hc').value || 10);
            params.append('gross_tickets', document.getElementById('param_gross_tickets').value || 0);

            // Add standard filters
            const filterForm = document.getElementById('filterForm');
            if(filterForm) {
                new FormData(filterForm).forEach((v, k) => {
                    if (v.trim() !== '') params.append(k, v.trim());
                });
                // Explicitly add start/end if they exist
                const start = document.getElementById('filter_start_date').value;
                const end = document.getElementById('filter_end_date').value;
                if(start && !params.has('start_date')) params.append('start_date', start);
                if(end && !params.has('end_date')) params.append('end_date', end);
            }

            const res = await fetch('/api/metrics/aggregate?' + params.toString());
            if (res.ok) {
                const data = await res.json();
                lastDashboardData = data;
                processDashboard(data);
            }
        } catch (e) {
            console.error('Fetch failed:', e);
        }
    };

    const processDashboard = (data) => {
        const s = data.summary;
        // Update all metrics IDs
        const mappings = {
            'metric-total_offered': s.volume.total_offered,
            'metric-answered': s.volume.answered,
            'metric-inbound_wh_offered': s.volume.inbound_wh_offered,
            'metric-al_pct': s.service.al_pct,
            'metric-wh_answered': s.volume.wh_answered,
            'metric-wh_offered': s.volume.wh_offered,
            'metric-travel_update_offered': s.volume.travel_update_offered,
            'metric-sl_pct': s.service.sl_pct,
            'metric-sl_calls': s.service.sl_calls,
            'metric-avg_wait': s.service.avg_wait,
            'metric-on_hold': s.service.on_hold,
            'metric-avg_hold': s.service.avg_hold,
            'metric-aht': s.efficiency.aht,
            'metric-call_per_agent': s.efficiency.call_per_agent,
            'val_agent_hc': document.getElementById('param_agent_hc').value,
            'metric-same_day_repeat': s.efficiency.same_day_repeat,
            'metric-repeat_pct': s.efficiency.repeat_pct,
            'metric-long_calls': s.efficiency.long_calls,
            'metric-long_call_pct': s.efficiency.long_call_pct,
            'metric-gross_abn_pct': s.failure.gross_abn_pct,
            'metric-net_abn': s.failure.net_abn,
            'metric-net_abn_pct': s.failure.net_abn_pct,
            'metric-short_abn': s.failure.short_abn,
            'metric-short_pct': s.failure.short_pct,
            'metric-queue_level': s.failure.queue_level,
            'metric-intr_journey_pct': s.journey.intr_journey_pct,
            'metric-travel_util_pct': s.journey.travel_util_pct,
            'metric-same_day_disp_repeat': s.journey.same_day_disp_repeat,
            'metric-disp_repeat_pct': s.journey.disp_repeat_pct,
            'total_raw_rows': `${data.raw_count.toLocaleString()} records`
        };

        for (const [id, val] of Object.entries(mappings)) {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        }

        // Ledger Table Placeholder
        const tableBody = document.getElementById('tableBody');
        if(tableBody) {
            tableBody.innerHTML = `
                <tr>
                    <td>${new Date().toLocaleDateString()}</td>
                    <td><span class="badge" style="color:var(--accent-purple)">Aggregated IQ</span></td>
                    <td style="font-family:monospace">${data.raw_count.toLocaleString()} rows</td>
                    <td>Central Pipeline</td>
                    <td><span class="badge-success">Operational</span></td>
                </tr>
            `;
        }

        renderTrajectoryChart(data.chart_data);
        renderDistChart(data.distributions[currentDistType]);
        renderHeatmap(data.heatmap);
    };

    // --- Heatmap (Pulse Map) ---
    const renderHeatmap = (heatmapData) => {
        const container = document.getElementById('heatmap');
        if (!container) return;
        container.innerHTML = '';
        
        const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        
        // Find max value for scaling colors
        const maxVal = Math.max(...heatmapData.flat()) || 1;

        heatmapData.forEach((row, dayIdx) => {
            const rowEl = document.createElement('div');
            rowEl.className = 'heatmap-row';
            
            const label = document.createElement('div');
            label.className = 'day-label';
            label.textContent = days[dayIdx];
            rowEl.appendChild(label);

            row.forEach((val, hour) => {
                const cell = document.createElement('div');
                cell.className = 'heatmap-cell';
                cell.title = `${days[dayIdx]} ${hour}:00 - ${val} Calls`;
                
                // Color intensity (emerald/green for heavy call volume in dark mode)
                const opacity = (val / maxVal) * 0.9 + 0.1;
                cell.style.background = `rgba(16, 185, 129, ${opacity})`;
                if (val === 0) cell.style.background = 'rgba(255,255,255,0.02)';
                
                rowEl.appendChild(cell);
            });
            container.appendChild(rowEl);
        });
    };

    // --- Charting Engine ---
    const renderTrajectoryChart = (chartData) => {
        const ctx = document.getElementById('metricsChart').getContext('2d');
        if (volumeChart) volumeChart.destroy();

        const labels = chartData.map(d => d.label);
        const dataTotal = chartData.map(d => d.total);
        const dataAnswered = chartData.map(d => d.answered);
        const dataAbn = chartData.map(d => d.abn);

        const isLight = document.body.classList.contains('light-mode');
        const gridColor = isLight ? 'rgba(0, 0, 0, 0.05)' : 'rgba(255, 255, 255, 0.05)';

        volumeChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Offered',
                        data: dataTotal,
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        fill: true,
                        tension: 0.4,
                        borderWidth: 3,
                        pointRadius: 4
                    },
                    {
                        label: 'Answered',
                        data: dataAnswered,
                        borderColor: '#10b981',
                        borderDash: [5, 5],
                        tension: 0.4,
                        borderWidth: 2
                    },
                    {
                        label: 'Abandoned',
                        data: dataAbn,
                        borderColor: '#f43f5e',
                        tension: 0.4,
                        borderWidth: 2
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'top', labels: { usePointStyle: true, boxWidth: 6 } } },
                scales: {
                    x: { grid: { color: 'transparent' } },
                    y: { beginAtZero: true, grid: { color: gridColor } }
                }
            }
        });
    };

    const renderDistChart = (distData) => {
        const ctx = document.getElementById('distChart').getContext('2d');
        if (distChart) distChart.destroy();

        const labels = Object.keys(distData);
        const values = Object.values(distData);

        distChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: [
                        '#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', 
                        '#f43f5e', '#6366f1', '#ec4899', '#94a3b8'
                    ],
                    borderWidth: 0,
                    hoverOffset: 15
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '70%',
                plugins: {
                    legend: { display: false }
                }
            }
        });
    };

    // --- Bootstrapping ---
    const initFilterOptions = async () => {
        try {
            const res = await fetch('/api/metrics/filters');
            if (res.ok) {
                const data = await res.json();
                const populate = (id, options) => {
                    const sel = document.getElementById(id);
                    if(!sel) return;
                    sel.innerHTML = '<option value="">All</option>';
                    options.forEach(o => {
                        const el = document.createElement('option');
                        el.value = o; el.textContent = o;
                        sel.appendChild(el);
                    });
                };
                populate('filter_agent', data.agents);
                populate('filter_campaign', data.campaigns);
                populate('filter_status', data.statuses);
                populate('filter_disposition', data.dispositions);
            }
        } catch (e) { console.error(e); }
    };

    // Event Listeners
    document.getElementById('filterForm')?.addEventListener('submit', (e) => {
        e.preventDefault();
        fetchMetrics();
    });

    document.getElementById('clearFiltersBtn')?.addEventListener('click', () => {
        document.getElementById('filterForm').reset();
        fetchMetrics();
    });

    document.querySelectorAll('.view-btn[data-view]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.view-btn[data-view]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentViewType = btn.getAttribute('data-view');
            fetchMetrics();
        });
    });

    // Ops Params Auto-Refresh
    ['param_agent_hc', 'param_gross_tickets'].forEach(id => {
        document.getElementById(id)?.addEventListener('change', fetchMetrics);
    });

    // Manual Upload Logic
    const fileInput = document.getElementById('manual_upload');
    const uploadStatus = document.getElementById('upload_status');

    if (fileInput) {
        fileInput.addEventListener('change', async () => {
            const file = fileInput.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);

            uploadStatus.innerHTML = '<i data-lucide="refresh-cw" class="spin" style="width:12px"></i> Ingesting...';
            lucide.createIcons();

            try {
                const res = await fetch('/api/sync/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await res.json();
                if (res.ok) {
                    uploadStatus.innerHTML = `<span style="color:var(--accent-emerald)">✅ Integrated ${data.new_records_integrated} records</span>`;
                    fetchMetrics();
                } else {
                    uploadStatus.innerHTML = `<span style="color:var(--accent-rose)">❌ ${data.detail || 'Upload failed'}</span>`;
                }
            } catch (e) {
                console.error('Upload error:', e);
                uploadStatus.innerHTML = '<span style="color:var(--accent-rose)">❌ Connection error</span>';
            }

            // Reset input so same file can be uploaded again if needed
            fileInput.value = '';
        });
    }

    initTheme();
    initTabs();
    initFilterOptions();
    fetchMetrics();
});

