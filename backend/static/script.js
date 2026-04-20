// ═══════════════════════════════════════════════════════════
//  STATIC CREDENTIALS — Change these to update login details
// ═══════════════════════════════════════════════════════════
const AUTH_CONFIG = {
    username: 'freshbus',
    password: 'freshbus@2024'
};

// ═══════════════════════════════════════════════════════════
//  SESSION MANAGEMENT
// ═══════════════════════════════════════════════════════════
function getSession() {
    try { return JSON.parse(sessionStorage.getItem('fb_session') || 'null'); }
    catch { return null; }
}
function setSession(data) { sessionStorage.setItem('fb_session', JSON.stringify(data)); }
function clearSession() { sessionStorage.removeItem('fb_session'); }

// ═══════════════════════════════════════════════════════════
//  ROUTE CONTROLLER
// ═══════════════════════════════════════════════════════════
const pathname = window.location.pathname;

function navigateTo(path) {
    if (pathname !== path && pathname !== path + '.html' && !(path === '/' && pathname === '/index.html')) {
        window.location.href = path;
    }
}

// ═══════════════════════════════════════════════════════════
//  BOOT — Authentication guard and dynamic init
// ═══════════════════════════════════════════════════════════
(function boot() {
    const session = getSession();
    const isLoginPath = pathname === '/' || pathname === '/index.html' || pathname === '';

    if (session && session.loggedIn) {
        // If logged in but on login page, redirect to hub
        if (isLoginPath) {
            navigateTo('/campaign');
            return;
        }
        // Hydrate usernames globally
        const hubUser = document.getElementById('hubUserName');
        const dashUser = document.getElementById('dashUserName');
        if (hubUser) hubUser.textContent = session.username || 'Admin';
        if (dashUser) dashUser.textContent = session.username || 'Admin';
    } else {
        // Not logged in, kick out to login
        if (!isLoginPath) {
            navigateTo('/');
            return;
        }
    }

    // Initialize page-specific logic
    if (isLoginPath) initLogin();
    else if (pathname.includes('/campaign')) initCampaignHub();
    else if (pathname.includes('/inbound')) initDashboard();
})();

// ═══════════════════════════════════════════════════════════
//  LOGIN FORM
// ═══════════════════════════════════════════════════════════
function initLogin() {
    const form = document.getElementById('loginForm');
    const usernameInput = document.getElementById('loginUsername');
    const passwordInput = document.getElementById('loginPassword');
    const errorBox = document.getElementById('loginError');
    const loginBtn = document.getElementById('loginBtn');
    const togglePwdBtn = document.getElementById('togglePassword');
    const eyeIcon = document.getElementById('eyeIcon');

    togglePwdBtn?.addEventListener('click', () => {
        const isPwd = passwordInput.type === 'password';
        passwordInput.type = isPwd ? 'text' : 'password';
        eyeIcon?.setAttribute('data-lucide', isPwd ? 'eye-off' : 'eye');
        if (window.lucide) lucide.createIcons();
    });

    form?.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (errorBox) errorBox.style.display = 'none';
        loginBtn.disabled = true;
        loginBtn.innerHTML = '<i data-lucide="loader-2" style="animation:spin 1s linear infinite;width:16px"></i> Signing in...';
        if (window.lucide) lucide.createIcons();

        await new Promise(r => setTimeout(r, 700));

        const user = usernameInput?.value.trim();
        const pwd = passwordInput?.value;

        if (user === AUTH_CONFIG.username && pwd === AUTH_CONFIG.password) {
            setSession({ loggedIn: true, username: user });
            navigateTo('/campaign');
        } else {
            if (errorBox) {
                errorBox.style.display = 'flex';
                errorBox.style.animation = 'none';
                errorBox.offsetHeight; 
                errorBox.style.animation = '';
            }
            loginBtn.disabled = false;
            loginBtn.innerHTML = '<span>Sign In</span><i data-lucide="arrow-right"></i>';
            if (window.lucide) lucide.createIcons();
        }
    });
}

// ═══════════════════════════════════════════════════════════
//  CAMPAIGN HUB
// ═══════════════════════════════════════════════════════════
function initCampaignHub() {
    // Logout
    document.getElementById('logoutBtn')?.addEventListener('click', () => {
        clearSession();
        navigateTo('/');
    });

    const dynamicContainer = document.getElementById('dynamicCampaignCards');
    
    // Fetch and render campaigns
    const loadCampaigns = async () => {
        try {
            const res = await fetch('/api/sync/campaigns');
            if (res.ok) {
                const data = await res.json();
                dynamicContainer.innerHTML = '';
                
                data.groups.forEach(group => {
                    const card = document.createElement('div');
                    card.className = `campaign-card ${group.status === 'Live' ? 'active-campaign' : 'coming-soon'}`;
                    
                    const subCount = Array.isArray(group.sub_campaigns) ? group.sub_campaigns.length : 0;
                    
                    card.innerHTML = `
                        <div class="campaign-card-glow"></div>
                        <div class="campaign-icon-wrap" style="background: rgba(14, 165, 233, 0.1); border-color: rgba(14, 165, 233, 0.2); color: var(--accent-blue);">
                            <i data-lucide="${group.icon || 'folder'}"></i>
                        </div>
                        <div class="campaign-info">
                            <h3>${group.name}</h3>
                            <p>${group.description || 'No description provided.'}</p>
                        </div>
                        <div class="campaign-meta">
                            <span class="campaign-badge ${group.status === 'Live' ? 'live' : 'soon'}">
                                ${group.status === 'Live' ? '● Live' : group.status}
                            </span>
                            <span class="campaign-channels">${subCount} Linked</span>
                        </div>
                        <div class="campaign-arrow">
                            <i data-lucide="arrow-right"></i>
                        </div>
                    `;
                    
                    if (group.status === 'Live') {
                        card.addEventListener('click', () => {
                            navigateTo('/inbound?campaign=' + encodeURIComponent(group.name));
                        });
                    }
                    
                    dynamicContainer.appendChild(card);
                });
                
                if (window.lucide) lucide.createIcons();
            }
        } catch (err) {
            console.error('Failed to load campaigns:', err);
        }
    };
    
    // Initial Load
    if (dynamicContainer) loadCampaigns();

    // Campaign Configuration Modal
    const modalOverlay = document.getElementById('campaignModalOverlay');
    const openBtn = document.getElementById('openConfigBtn');
    const closeBtn = document.getElementById('closeConfigBtn');
    const configForm = document.getElementById('campaignConfigForm');
    const errorBox = document.getElementById('campaignConfigError');
    const successBox = document.getElementById('campaignConfigSuccess');
    const saveBtn = document.getElementById('saveCampaignBtn');
    
    const nameInput = document.getElementById('ozonetelNamesInput');
    const groupNameInput = document.getElementById('campaignGroupName');
    const groupDescInput = document.getElementById('campaignGroupDesc');

    openBtn?.addEventListener('click', () => {
        modalOverlay.style.display = 'flex';
        errorBox.style.display = 'none';
        successBox.style.display = 'none';
        nameInput.value = '';
        if(groupNameInput) groupNameInput.value = '';
        if(groupDescInput) groupDescInput.value = '';
    });

    closeBtn?.addEventListener('click', () => {
        modalOverlay.style.display = 'none';
    });
    
    // Close on click outside
    modalOverlay?.addEventListener('click', (e) => {
        if (e.target === modalOverlay) modalOverlay.style.display = 'none';
    });

    configForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        errorBox.style.display = 'none';
        successBox.style.display = 'none';
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i data-lucide="loader-2" style="animation:spin 1s linear infinite;width:16px;"></i> Saving...';
        if (window.lucide) lucide.createIcons();

        try {
            const payload = {
                name: groupNameInput.value,
                description: groupDescInput.value,
                campaigns: nameInput.value
            };
            
            const res = await fetch('/api/sync/campaigns', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();

            if (res.ok) {
                successBox.style.display = 'flex';
                // Reload list to show newly added campaign
                await loadCampaigns();
                setTimeout(() => { modalOverlay.style.display = 'none'; }, 1500);
            } else {
                throw new Error(data.detail || 'Failed to save campaigns.');
            }
        } catch (err) {
            errorBox.style.display = 'flex';
            document.getElementById('campaignConfigErrorText').textContent = err.message;
        } finally {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i data-lucide="save" style="width:16px;height:16px;"></i> Save Campaigns';
            if (window.lucide) lucide.createIcons();
        }
    });
}

// ═══════════════════════════════════════════════════════════
//  BACK TO HUB (from dashboard sidebar)
// ═══════════════════════════════════════════════════════════
document.getElementById('backToHubBtn')?.addEventListener('click', (e) => {
    e.preventDefault();
    navigateTo('/campaign');
});

// ═══════════════════════════════════════════════════════════
//  DASHBOARD
// ═══════════════════════════════════════════════════════════
function initDashboard() {
    // --- Global State ---
    let volumeChart = null;
    let distChart = null;
    let lastDashboardData = null;
    let currentDistType = 'dispositions';
    let currentViewType = 'daily';
    
    // Extract Active Campaign from URL
    const urlParams = new URLSearchParams(window.location.search);
    const activeParentCampaign = urlParams.get('campaign') || 'Inbound';
    
    // Update Branding UI
    const dashBranding = document.querySelector('.brand h2');
    if (dashBranding) {
        dashBranding.innerHTML = `FreshBus<br><span style="font-weight:400;font-size:0.8rem;opacity:0.6;">${activeParentCampaign} Ops</span>`;
    }
    const premiumHeadline = document.querySelector('.premium-headline');
    if (premiumHeadline) {
        premiumHeadline.textContent = `${activeParentCampaign} Intelligence`;
    }

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
    async function fetchMetrics() {
        try {
            const params = new URLSearchParams();
            params.append('view_type', currentViewType);
            params.append('agent_hc', document.getElementById('param_agent_hc')?.value || 10);
            params.append('gross_tickets', document.getElementById('param_gross_tickets')?.value || 0);

            // Add standard filters
            const filterForm = document.getElementById('filterForm');
            if(filterForm) {
                new FormData(filterForm).forEach((v, k) => {
                    if (v.trim() !== '') params.append(k, v.trim());
                });
                // Explicitly add start/end if they exist
                const start = document.getElementById('filter_start_date')?.value;
                const end = document.getElementById('filter_end_date')?.value;
                if(start && !params.has('start_date')) params.append('start_date', start);
                if(end && !params.has('end_date')) params.append('end_date', end);
            }
            
            // Critical: Add Tenant Partition Key
            params.append('parent_campaign', activeParentCampaign);

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
        if (!heatmapData || heatmapData.length === 0) return;
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
                const opacity = (val / maxVal) * 0.85 + 0.05;
                cell.style.background = `rgba(16, 185, 129, ${opacity})`;
                if (val === 0) {
                    cell.style.background = 'rgba(255,255,255,0.05)';
                    if (document.body.classList.contains('light-mode')) {
                        cell.style.background = 'rgba(0,0,0,0.05)';
                    }
                }
                
                rowEl.appendChild(cell);

                // --- CUSTOM TOOLTIP LOGIC ---
                cell.addEventListener('mouseenter', (e) => {
                    const tooltip = document.getElementById('heatmapTooltip');
                    if (tooltip) {
                        tooltip.style.display = 'block';
                        tooltip.innerHTML = `
                            <div style="font-weight:700; color:var(--accent-blue); margin-bottom:2px;">${days[dayIdx]} ${hour}:00</div>
                            <div><i data-lucide="phone" style="width:12px; vertical-align:middle; margin-right:4px;"></i> <b>${val}</b> Calls</div>
                        `;
                        lucide.createIcons({
                            attrs: { "stroke-width": 2, "width": 12, "height": 12 }
                        });
                    }
                });

                cell.addEventListener('mousemove', (e) => {
                    const tooltip = document.getElementById('heatmapTooltip');
                    if (tooltip) {
                        tooltip.style.left = (e.clientX + 15) + 'px';
                        tooltip.style.top = (e.clientY + 15) + 'px';
                    }
                });

                cell.addEventListener('mouseleave', () => {
                    const tooltip = document.getElementById('heatmapTooltip');
                    if (tooltip) tooltip.style.display = 'none';
                });
            }); // Correctly close row.forEach
            container.appendChild(rowEl);
        });
    };

    // --- Charting Engine ---
    const renderTrajectoryChart = (chartData) => {
        if (!chartData || chartData.length === 0) return;
        const ctx = document.getElementById('metricsChart')?.getContext('2d');
        if (!ctx) return;
        
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
            const res = await fetch('/api/metrics/filters?parent_campaign=' + encodeURIComponent(activeParentCampaign));
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

    // Move listeners to a safe initialization block
    function initDashboardListeners() {
        document.querySelectorAll('.view-btn[data-view]').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.view-btn[data-view]').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentViewType = btn.getAttribute('data-view');
                fetchMetrics();
            });
        });

        // Tabs for KPI Groups
        document.querySelectorAll('.kpi-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.kpi-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const group = tab.getAttribute('data-group');
                document.querySelectorAll('.metric-group').forEach(mg => mg.classList.remove('active'));
                document.getElementById('group-' + group)?.classList.add('active');
            });
        });

        // Other filters
        ['filter_agent', 'filter_campaign', 'filter_status', 'filter_disposition'].forEach(id => {
            document.getElementById(id)?.addEventListener('change', fetchMetrics);
        });
    }

    // Call it early in initDashboard


    // Ops Params Auto-Refresh
    ['param_agent_hc', 'param_gross_tickets'].forEach(id => {
        document.getElementById(id)?.addEventListener('change', fetchMetrics);
    });

    // OzoneTel Sync Logic
    const runSyncBtn = document.getElementById('runSyncBtn');
    const syncStatusLabel = document.getElementById('sync_status');
    const ozConfigDetails = document.getElementById('oz_config_details');

    const updateSyncStatus = async () => {
        try {
            const res = await fetch('/api/sync/status?campaign=' + encodeURIComponent(activeParentCampaign));
            if (res.ok) {
                const data = await res.json();
                if (ozConfigDetails) {
                    ozConfigDetails.innerHTML = `
                        User: ${data.config.userName}<br>
                        Tenant: ${activeParentCampaign}
                    `;
                }
                if (syncStatusLabel) {
                    const lastSyncStr = data.last_sync ? new Date(data.last_sync).toLocaleTimeString() : 'Never';
                    syncStatusLabel.innerHTML = `
                        <i data-lucide="check-circle" style="width: 10px;"></i> 
                        Last Sync: ${lastSyncStr}
                    `;
                    lucide.createIcons();
                }
            }
        } catch (e) { console.error('Status fetch failed:', e); }
    };

    if (runSyncBtn) {
        runSyncBtn.addEventListener('click', async () => {
            runSyncBtn.disabled = true;
            runSyncBtn.innerHTML = '<i data-lucide="refresh-cw" class="spin" style="width:12px"></i> Syncing...';
            lucide.createIcons();

            try {
                const res = await fetch(`/api/sync/run?campaign=${encodeURIComponent(activeParentCampaign)}`, { method: 'POST' });
                const data = await res.json();
                if (res.ok) {
                    alert(`Sync Complete! Integrated ${data.total_integrated} records for ${activeParentCampaign}.`);
                    fetchMetrics();
                    updateSyncStatus();
                } else {
                    alert(`Sync Failed: ${data.detail}`);
                }
            } catch (e) {
                console.error('Manual sync error:', e);
                alert('Connection error during sync.');
            } finally {
                runSyncBtn.disabled = false;
                runSyncBtn.innerHTML = '<i data-lucide="refresh-cw" style="width: 12px;"></i> Run Sync (Yesterday)';
                lucide.createIcons();
            }
        });
    }

    // Database Wipe Logic
    document.getElementById('wipeDataBtn')?.addEventListener('click', async () => {
        if (!confirm(`Are you ABSOLUTELY sure? This will delete all ingested call records for ${activeParentCampaign}!`)) return;
        try {
            const res = await fetch('/api/sync/wipe?campaign=' + encodeURIComponent(activeParentCampaign), { method: 'POST' });
            if (res.ok) {
                alert('Database wiped successfully.');
                fetchMetrics();
                updateSyncStatus();
            }
        } catch (e) { console.error('Wipe failed:', e); }
    });

    // --- Flatpickr Integration ---
    if (window.flatpickr) {
        const fpConfig = {
            dateFormat: "Y-m-d",
            disableMobile: "true",
            theme: "dark",
            onChange: () => {
                fetchMetrics();
            }
        };
        flatpickr("#filter_start_date", fpConfig);
        flatpickr("#filter_end_date", fpConfig);
    }

    // --- Mobile Sidebar Toggle ---
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const sidebar = document.querySelector('.sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');

    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', () => {
            sidebar.classList.toggle('active');
            sidebarOverlay.classList.toggle('active');
        });
        sidebarOverlay?.addEventListener('click', () => {
            sidebar.classList.remove('active');
            sidebarOverlay.classList.remove('active');
        });
        // Auto-close on nav click on small screens
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                if (window.innerWidth <= 1024) {
                    sidebar.classList.remove('active');
                    sidebarOverlay.classList.remove('active');
                }
            });
        });
    }

    initTheme();
    initTabs();
    initFilterOptions();
    initDashboardListeners();
    fetchMetrics();
    updateSyncStatus();
    // Poll status every 30 seconds
    setInterval(updateSyncStatus, 30000);
}
