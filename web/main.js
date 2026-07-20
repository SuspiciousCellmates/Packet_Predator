// Global State variables
let registeredNodes = [];
let eventSource = null;
let packetsLog = [];
let packetCounter = 0;
let mapInterval = null;
let gameState = "LOBBY"; // Tracks match running state ("LOBBY" or "RUNNING")

// DOM Elements
const radioModeBadge = document.getElementById('radio-mode-badge');
const streamStatusBadge = document.getElementById('stream-status-badge');
const btnToggleSniff = document.getElementById('btn-toggle-sniff');
const btnClearSniff = document.getElementById('btn-clear-sniff');
const sniffTbody = document.getElementById('sniff-tbody');
const btnGameControl = document.getElementById('btn-game-control');

const spoofForm = document.getElementById('spoof-form');
const spoofMode = document.getElementById('spoof-mode');
const spoofSrcType = document.getElementById('spoof-src-type');
const spoofSrcId = document.getElementById('spoof-src-id');
const spoofDestType = document.getElementById('spoof-dest-type');
const spoofDestNodeSelect = document.getElementById('spoof-dest-node');
const spoofPayloadType = document.getElementById('spoof-payload-type');
const payloadFieldsContainer = document.getElementById('payload-fields-container');

const configForm = document.getElementById('config-form');
const detailModal = document.getElementById('detail-modal');

// Filter Elements
const filterHideDiagnostics = document.getElementById('filter-hide-diagnostics');
const filterSearch = document.getElementById('filter-search');

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    fetchNodes();
    fetchRadioConfig();
    
    // Bind Event Listeners
    btnToggleSniff.addEventListener('click', toggleSniffing);
    btnClearSniff.addEventListener('click', clearSniffLogs);
    if (btnGameControl) {
        btnGameControl.addEventListener('click', toggleGameState);
    }
    if (filterHideDiagnostics) {
        filterHideDiagnostics.addEventListener('change', applyFilters);
    }
    if (filterSearch) {
        filterSearch.addEventListener('input', applyFilters);
    }
    
    // Sim debug elements
    const btnSimReset = document.getElementById('btn-sim-reset');
    if (btnSimReset) {
        btnSimReset.addEventListener('click', handleSimReset);
    }
    const selectSimDifficulty = document.getElementById('sim-difficulty');
    if (selectSimDifficulty) {
        selectSimDifficulty.addEventListener('change', handleDifficultyChange);
    }
    const btnTriggerMeeting = document.getElementById('btn-trigger-meeting');
    if (btnTriggerMeeting) {
        btnTriggerMeeting.addEventListener('click', () => triggerSimAction('meeting'));
    }
    const btnTriggerSabotage = document.getElementById('btn-trigger-sabotage');
    if (btnTriggerSabotage) {
        btnTriggerSabotage.addEventListener('click', () => triggerSimAction('sabotage'));
    }
    
    spoofMode.addEventListener('change', updateSpoofLayout);
    spoofDestType.addEventListener('change', populateDestinationNodes);
    spoofPayloadType.addEventListener('change', populatePayloadFields);
    spoofForm.addEventListener('submit', handleSpoofSubmit);
    configForm.addEventListener('submit', handleConfigSubmit);
    
    // Initialize spoof form layout
    updateSpoofLayout();
    
    // Modal controls
    document.getElementById('btn-close-modal').addEventListener('click', closeModal);
    document.getElementById('btn-close-modal-footer').addEventListener('click', closeModal);
    detailModal.addEventListener('click', (e) => {
        if (e.target === detailModal) closeModal();
    });
});

// --- API Interactions ---

// Fetch node registry from backend
async function fetchNodes() {
    try {
        const response = await fetch('/api/nodes');
        registeredNodes = await response.json();
        populateDestinationNodes();
    } catch (err) {
        console.error('Failed to fetch nodes:', err);
    }
}

// Fetch active radio registers
async function fetchRadioConfig() {
    try {
        const response = await fetch('/api/config');
        const cfg = await response.json();
        
        // Fill form fields
        document.getElementById('cfg-channel').value = (cfg.CH_NO_MSB << 8) | cfg.CH_NO;
        document.getElementById('cfg-auto-retran').checked = cfg.AUTO_RETRAN === 1;
        document.getElementById('cfg-rx-pwr').value = cfg.RX_RED_PWR.toString();
        document.getElementById('cfg-pa-pwr').value = cfg.PA_PWR.toString();
        document.getElementById('cfg-address').value = cfg.RX_ADDRESS;
        document.getElementById('cfg-crc-en').checked = cfg.CRC_EN === 1;
        document.getElementById('cfg-crc-mode').value = cfg.CRC_MODE.toString();
        document.getElementById('cfg-xof').value = cfg.XOF.toString();
        
        // Update badge
        updateRadioBadge(true);
    } catch (err) {
        console.error('Failed to fetch radio config:', err);
        updateRadioBadge(false, err.message);
    }
}

function updateRadioBadge(active, errorMsg = '') {
    if (active) {
        radioModeBadge.textContent = "Radio Mode: Simulation";
        radioModeBadge.className = "badge badge-success";
        // Show simulated 2D map panel and controls
        document.getElementById('sim-map-panel').style.display = 'block';
        document.getElementById('sim-control-panel').style.display = 'block';
        startMapTracking();
    } else {
        radioModeBadge.textContent = "Radio: Offline";
        radioModeBadge.className = "badge badge-error";
        document.getElementById('sim-map-panel').style.display = 'none';
        document.getElementById('sim-control-panel').style.display = 'none';
        stopMapTracking();
    }
}

// Handle Configuration Form Submission
async function handleConfigSubmit(e) {
    e.preventDefault();
    const payload = {
        CH_NO: parseInt(document.getElementById('cfg-channel').value),
        AUTO_RETRAN: document.getElementById('cfg-auto-retran').checked ? 1 : 0,
        RX_RED_PWR: parseInt(document.getElementById('cfg-rx-pwr').value),
        PA_PWR: parseInt(document.getElementById('cfg-pa-pwr').value),
        HFREQ_PLL: 0, // 433 MHz band
        TX_AFW: 4,
        RX_AFW: 4,
        TX_PW: 32,
        RX_PW: 32,
        RX_ADDRESS: document.getElementById('cfg-address').value.trim(),
        CRC_MODE: parseInt(document.getElementById('cfg-crc-mode').value),
        CRC_EN: document.getElementById('cfg-crc-en').checked ? 1 : 0,
        XOF: parseInt(document.getElementById('cfg-xof').value),
        UP_CLK_EN: 0,
        UP_CLK_FREQ: 0
    };

    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            alert('Radio register configuration written successfully.');
            fetchRadioConfig();
        } else {
            const err = await response.json();
            alert(`Error: ${err.detail}`);
        }
    } catch (err) {
        alert(`Failed to save config: ${err}`);
    }
}

// --- Dynamic Form Population & Layout ---

// Restructure spoof panel layout depending on active Transaction Mode
function updateSpoofLayout() {
    const mode = spoofMode.value;
    const srcRow = document.getElementById('spoof-src-row');
    const destRow = document.getElementById('spoof-dest-row');
    
    if (mode === 'COMMAND') {
        // Source is locked to Controller. Destination is variable spoke.
        srcRow.style.display = 'none';
        destRow.style.display = 'grid';
        
        spoofSrcType.value = 'GAME_CONTROLLER';
        spoofSrcId.value = '1';
        
        spoofDestType.innerHTML = `
            <option value="TASK" selected>TASK</option>
            <option value="PLAYER">PLAYER</option>
            <option value="BROADCAST">BROADCAST</option>
        `;
        populateDestinationNodes();
    } else if (mode === 'TELEMETRY') {
        // Source is variable spoke. Destination is locked to Controller.
        srcRow.style.display = 'grid';
        destRow.style.display = 'none';
        
        spoofSrcType.innerHTML = `
            <option value="TASK" selected>TASK</option>
            <option value="PLAYER">PLAYER</option>
        `;
        
        spoofDestType.value = 'GAME_CONTROLLER';
        spoofDestNodeSelect.innerHTML = '<option value="1" selected>GAME_CONTROLLER #1</option>';
    } else {
        // Raw Override: All fields exposed and customizable
        srcRow.style.display = 'grid';
        destRow.style.display = 'grid';
        
        spoofSrcType.innerHTML = `
            <option value="GAME_CONTROLLER">GAME_CONTROLLER</option>
            <option value="PLAYER">PLAYER</option>
            <option value="TASK">TASK</option>
            <option value="GOD">GOD</option>
        `;
        spoofDestType.innerHTML = `
            <option value="TASK" selected>TASK</option>
            <option value="PLAYER">PLAYER</option>
            <option value="GAME_CONTROLLER">GAME_CONTROLLER</option>
            <option value="BROADCAST">BROADCAST</option>
            <option value="GOD">GOD</option>
        `;
        populateDestinationNodes();
    }
    populatePayloadFields();
}

// Populate destination dropdowns based on selected node type
function populateDestinationNodes() {
    const selectedType = spoofDestType.value;
    if (selectedType === 'BROADCAST') {
        spoofDestNodeSelect.innerHTML = '<option value="65535" selected>All Nodes (0xFFFF)</option>';
        return;
    }
    spoofDestNodeSelect.innerHTML = '<option value="" disabled selected>Select Node</option>';
    
    const filtered = registeredNodes.filter(node => node.node_type === selectedType);
    filtered.forEach(node => {
        const opt = document.createElement('option');
        opt.value = node.address; // Use ID/address as value
        opt.textContent = `${node.friendly_name} (ID: ${node.address})`;
        spoofDestNodeSelect.appendChild(opt);
    });
}

// Populate payload form fields dynamically based on packet type selection
function populatePayloadFields() {
    const type = spoofPayloadType.value;
    payloadFieldsContainer.innerHTML = '';
    
    if (type === 'CONFIG') {
        const mode = spoofMode.value;
        let targetType = 'TASK';
        let targetId = 1;
        
        if (mode === 'COMMAND') {
            targetType = spoofDestType.value;
            targetId = parseInt(spoofDestNodeSelect.value);
        } else if (mode === 'TELEMETRY') {
            targetType = spoofSrcType.value;
            targetId = parseInt(spoofSrcId.value);
        } else {
            targetType = spoofDestType.value;
            targetId = parseInt(spoofDestNodeSelect.value);
        }
        
        // Find matching node definition to get config setting keys
        const node = registeredNodes.find(n => n.node_type === targetType && n.address === targetId);
        if (node && node.config_settings) {
            node.config_settings.forEach(setting => {
                const group = document.createElement('div');
                group.className = 'form-group';
                group.style.marginTop = '10px';
                
                const label = document.createElement('label');
                label.textContent = setting.replace(/_/g, ' ');
                
                const input = document.createElement('input');
                input.type = 'number';
                input.name = `payload-${setting}`;
                input.placeholder = "Enter value";
                input.required = true;
                
                group.appendChild(label);
                group.appendChild(input);
                payloadFieldsContainer.appendChild(group);
            });
        } else {
            payloadFieldsContainer.innerHTML = '<p class="subtitle" style="color: var(--color-warning); font-size: 0.75rem;">Please select a Spoke Node first to view config settings.</p>';
        }
    } else if (type === 'EVENT') {
        const group = document.createElement('div');
        group.className = 'form-group';
        group.style.marginTop = '10px';
        
        const label = document.createElement('label');
        label.textContent = "Trigger Event";
        
        const select = document.createElement('select');
        select.name = "payload-event";
        select.required = true;
        
        const events = ['MEETING_START', 'MEETING_END', 'MATCH_END', 'SABOTAGE', 'COMPLETED', 'CHECK_IN', 'PLAYER_DEATH', 'TASK_FAIL'];
        events.forEach(ev => {
            const opt = document.createElement('option');
            opt.value = ev;
            opt.textContent = ev;
            select.appendChild(opt);
        });
        
        group.appendChild(label);
        group.appendChild(select);
        payloadFieldsContainer.appendChild(group);
    }
}

// Handle Spoof Submission
async function handleSpoofSubmit(e) {
    e.preventDefault();
    
    const mode = spoofMode.value;
    const payloadTypeVal = spoofPayloadType.value;
    const payloadData = {};
    
    if (payloadTypeVal === 'CONFIG') {
        const inputs = payloadFieldsContainer.querySelectorAll('input');
        inputs.forEach(input => {
            const settingKey = input.name.replace('payload-', '');
            payloadData[settingKey] = parseInt(input.value);
        });
    } else if (payloadTypeVal === 'EVENT') {
        const select = payloadFieldsContainer.querySelector('select');
        payloadData['event'] = select.value;
    }

    // Adapt source & destination addresses based on the transaction mode
    let srcType = spoofSrcType.value;
    let srcId = parseInt(spoofSrcId.value);
    let destType = spoofDestType.value;
    let destId = parseInt(spoofDestNodeSelect.value);

    if (mode === 'COMMAND') {
        srcType = 'GAME_CONTROLLER';
        srcId = 1;
    } else if (mode === 'TELEMETRY') {
        destType = 'GAME_CONTROLLER';
        destId = 1;
    }
    
    const payload = {
        dest_node_type: destType,
        dest_node_id: destId,
        src_node_type: srcType,
        src_node_id: srcId,
        payload_type: payloadTypeVal,
        payload_data: payloadData
    };
    
    try {
        const response = await fetch('/api/spoof', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            const res = await response.json();
            alert(`Packet successfully launched!\n\nPayload Hex: ${res.hex}`);
        } else {
            const err = await response.json();
            const detailStr = (err.detail && typeof err.detail === 'object') ? JSON.stringify(err.detail) : err.detail;
            alert(`Failed to launch packet: ${detailStr}`);
        }
    } catch (err) {
        alert(`Error: ${err}`);
    }
}

// --- Sniffer Logic ---

function toggleSniffing() {
    if (eventSource === null) {
        // Start Sniffing
        btnToggleSniff.textContent = "Stop Sniffing";
        btnToggleSniff.className = "btn btn-secondary";
        streamStatusBadge.textContent = "Stream Live";
        streamStatusBadge.className = "badge badge-success";
        
        // Remove empty placeholder row if present
        const emptyRow = sniffTbody.querySelector('.empty-row');
        if (emptyRow) emptyRow.remove();
        
        // Open SSE connection
        eventSource = new EventSource('/api/stream');
        
        eventSource.onmessage = (event) => {
            const packet = JSON.parse(event.data);
            addPacketToTable(packet);
        };
        
        eventSource.onerror = (err) => {
            console.error('SSE Stream error:', err);
            stopSniffing();
        };
    } else {
        stopSniffing();
    }
}

function stopSniffing() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    btnToggleSniff.textContent = "Start Sniffing";
    btnToggleSniff.className = "btn btn-primary";
    streamStatusBadge.textContent = "Stream Off";
    streamStatusBadge.className = "badge badge-error";
}

function addPacketToTable(packet) {
    const id = ++packetCounter;
    packetsLog.push(packet);
    
    const row = document.createElement('tr');
    row.dataset.id = id;
    
    row.innerHTML = `
        <td>${id}</td>
        <td>${packet.source_address}</td>
        <td>${packet.destination_address}</td>
        <td><span class="badge ${getDirectionBadgeClass(packet.context_address)}">${packet.context_address}</span></td>
        <td><span class="badge ${getPacketTypeBadgeClass(packet.payload_type)}">${packet.payload_type}</span></td>
        <td style="font-family: var(--font-mono)">${packet.timestamp}</td>
        <td style="font-family: var(--font-mono)">${packet.total_len} bytes</td>
    `;
    
    // Bind click to open detailed modal
    row.addEventListener('click', () => showPacketDetails(packet));
    
    // Check initial filter visibility
    row.style.display = isPacketVisible(packet) ? 'table-row' : 'none';
    
    // Prepend row (so newest is always on top)
    sniffTbody.insertBefore(row, sniffTbody.firstChild);
    
    // Limit UI lines to 100 to prevent page bloat
    if (sniffTbody.children.length > 100) {
        sniffTbody.lastChild.remove();
    }
}

function getDirectionBadgeClass(dir) {
    switch (dir) {
        case 'BROADCAST': return 'badge-success'; // Green
        case 'DOWNLINK': return 'badge-warning'; // Amber / Outbound
        case 'UPLINK': return 'badge-primary'; // Blue / Inbound
        case 'DIRECT': return 'badge-error'; // Red / Mismatch
        default: return 'badge-secondary';
    }
}

function getPacketTypeBadgeClass(type) {
    switch (type) {
        case 'SYNC': return 'badge-success';
        case 'CONFIG': return 'badge-warning';
        case 'EVENT': return 'badge-primary';
        case 'START': return 'badge-success';
        case 'STOP': return 'badge-error';
        default: return 'badge-secondary';
    }
}

function clearSniffLogs() {
    sniffTbody.innerHTML = `
        <tr class="empty-row">
            <td colspan="7">No packets captured yet. Start sniffing to monitor network.</td>
        </tr>
    `;
    packetsLog = [];
    packetCounter = 0;
}

// --- Detail Modal ---

// Display details of clicked packet
function showPacketDetails(packet) {
    document.getElementById('modal-src').textContent = packet.source_address;
    document.getElementById('modal-dest').textContent = packet.destination_address;
    document.getElementById('modal-type').textContent = packet.payload_type;
    document.getElementById('modal-time').textContent = packet.timestamp;
    document.getElementById('modal-len').textContent = `${packet.total_len} bytes`;
    
    const payloadContainer = document.getElementById('modal-payload');
    payloadContainer.textContent = JSON.stringify(packet.payload, null, 4);
    
    detailModal.classList.add('active');
}

function closeModal() {
    detailModal.classList.remove('active');
}

// --- 2D Proximity Map Rendering (Simulation) ---

function startMapTracking() {
    if (mapInterval === null) {
        mapInterval = setInterval(fetchAndDrawMap, 250); // query positions every 250ms
    }
}

function stopMapTracking() {
    if (mapInterval !== null) {
        clearInterval(mapInterval);
        mapInterval = null;
    }
}

async function fetchAndDrawMap() {
    const canvas = document.getElementById('sim-map-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    try {
        const response = await fetch('/api/sim/map');
        const nodes = await response.json();
        
        // 1. Reset background grid
        ctx.fillStyle = '#070a13';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // Draw grid coordinate overlay lines
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.02)';
        ctx.lineWidth = 1;
        const gridLines = 10;
        for (let i = 0; i <= gridLines; i++) {
            const x = (i / gridLines) * canvas.width;
            const y = (i / gridLines) * canvas.height;
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, canvas.height);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(canvas.width, y);
            ctx.stroke();
        }
        
        // Draw room zone boundaries
        const rooms = [
            { name: "Cafeteria", x: 50, y: 50, radius: 25 },
            { name: "Electrical", x: 10, y: 20, radius: 15 },
            { name: "Shields", x: 90, y: 80, radius: 15 },
            { name: "O2", x: 70, y: 30, radius: 15 },
            { name: "Reactor", x: 25, y: 80, radius: 20 }
        ];
        
        rooms.forEach(room => {
            const rx = (room.x / 100) * canvas.width;
            const ry = (room.y / 100) * canvas.height;
            const rr = (room.radius / 100) * canvas.width;
            
            // Draw room circle boundary
            ctx.strokeStyle = 'rgba(59, 130, 246, 0.15)';
            ctx.lineWidth = 1.5;
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            ctx.arc(rx, ry, rr, 0, 2 * Math.PI);
            ctx.stroke();
            ctx.setLineDash([]);
            
            // Room label
            ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
            ctx.font = '700 8px var(--font-sans)';
            ctx.textAlign = 'center';
            ctx.fillText(room.name.toUpperCase(), rx, ry - 3);
        });

        // 2. Draw Task Node points
        nodes.filter(n => n.node_type === "TASK").forEach(node => {
            const tx = (node.x / 100) * canvas.width;
            const ty = (node.y / 100) * canvas.height;
            
            ctx.fillStyle = '#3b82f6'; // Blue square
            ctx.shadowBlur = 8;
            ctx.shadowColor = '#3b82f6';
            ctx.fillRect(tx - 4, ty - 4, 8, 8);
            ctx.shadowBlur = 0; // reset shadow
            
            // Draw status text
            ctx.fillStyle = '#9ca3af';
            ctx.font = '400 7px var(--font-sans)';
            ctx.textAlign = 'center';
            let stateStr = "Idle";
            if (node.status === 1) {
                stateStr = "Active";
                ctx.fillStyle = '#f59e0b';
            } else if (node.status === 2) {
                stateStr = "Complete";
                ctx.fillStyle = '#10b981';
            } else if (node.status === 3) {
                stateStr = "Locked";
                ctx.fillStyle = '#ef4444';
            } else if (node.status === 4) {
                stateStr = "Sabotaged";
                ctx.fillStyle = '#f97316';
                // Draw pulsing warning ring for active sabotage targets
                const pulse = 10 + Math.sin(Date.now() / 150) * 4;
                ctx.strokeStyle = '#f97316';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.arc(tx, ty, pulse, 0, 2 * Math.PI);
                ctx.stroke();
            }
            ctx.fillText(`${node.name} (${stateStr})`, tx, ty + 12);
        });

        // 3. Draw Player Node dots
        nodes.filter(n => n.node_type === "PLAYER").forEach(node => {
            const px = (node.x / 100) * canvas.width;
            const py = (node.y / 100) * canvas.height;
            
            let color = '#10b981'; // Green (Crewmate)
            let statusLabel = "";
            
            if (node.state === "DEAD" || node.state === "GHOST") {
                color = '#6b7280'; // Gray (Ghost)
                statusLabel = " (Dead)";
            } else if (node.is_impostor) {
                color = '#ef4444'; // Red (Impostor)
                statusLabel = " (Impostor)";
            }
            
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(px, py, 5, 0, 2 * Math.PI);
            ctx.fill();
            
            // Outer glow ring
            ctx.strokeStyle = color;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(px, py, 8, 0, 2 * Math.PI);
            ctx.stroke();
            
            // Draw name tag
            ctx.fillStyle = '#f3f4f6';
            ctx.font = '600 8px var(--font-sans)';
            ctx.textAlign = 'center';
            ctx.fillText(node.name + statusLabel, px, py - 11);
            
            // Draw position coordinates
            ctx.fillStyle = '#6b7280';
            ctx.font = '400 7px var(--font-mono)';
            ctx.fillText(`(${node.x}, ${node.y})`, px, py - 3);
        });
        
        // Update Interactive Player Badge List Table
        const simPlayersTbody = document.getElementById('sim-players-tbody');
        if (simPlayersTbody) {
            const players = nodes.filter(n => n.node_type === "PLAYER");
            if (players.length === 0) {
                simPlayersTbody.innerHTML = `<tr><td colspan="3" style="padding: 10px; text-align: center; color: var(--text-muted);">No player nodes registered.</td></tr>`;
            } else {
                let html = '';
                players.forEach(p => {
                    const stateClass = p.state === 'DEAD' ? 'color: #ef4444; font-weight: bold;' : p.state === 'MEETING' ? 'color: #eab308; font-weight: bold;' : 'color: #10b981;';
                    
                    let actionButtons = '';
                    if (p.state !== 'DEAD' && p.state !== 'GHOST' && p.state !== 'LOBBY') {
                        // Kill action
                        actionButtons += `<button onclick="window.triggerSimAction('kill', ${p.node_id})" style="padding: 2px 6px; font-size: 0.65rem; background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #ef4444; border-radius: 3px; cursor: pointer; border-style: solid;">Kill</button>`;
                        
                        // Crewmate solve task action
                        if (!p.is_impostor) {
                            actionButtons += `<button onclick="window.triggerSimAction('complete_task', ${p.node_id})" style="padding: 2px 6px; font-size: 0.65rem; background: rgba(59, 130, 246, 0.15); border: 1px solid #3b82f6; color: #3b82f6; border-radius: 3px; cursor: pointer; margin-left: 4px; border-style: solid;">Solve</button>`;
                        }
                    } else {
                        actionButtons = `<span style="color: var(--text-muted); font-style: italic;">Inactive / Lobby</span>`;
                    }
                    
                    html += `
                        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); background: rgba(0,0,0,0.1);">
                            <td style="padding: 6px; font-weight: 500;">${p.name}</td>
                            <td style="padding: 6px; ${stateClass}">${p.state}</td>
                            <td style="padding: 6px; text-align: right;">${actionButtons}</td>
                        </tr>
                    `;
                });
                simPlayersTbody.innerHTML = html;
            }
        }
        
    } catch (err) {
        console.error('Failed to draw simulation map:', err);
    }
}

async function toggleGameState() {
    if (gameState === "LOBBY") {
        try {
            const response = await fetch('/api/game/start', { method: 'POST' });
            if (response.ok) {
                gameState = "RUNNING";
                btnGameControl.textContent = "Stop Match";
                btnGameControl.className = "btn btn-secondary";
            } else {
                alert("Failed to start match broadcast.");
            }
        } catch (err) {
            console.error("Game start network error:", err);
        }
    } else {
        try {
            const response = await fetch('/api/game/stop', { method: 'POST' });
            if (response.ok) {
                gameState = "LOBBY";
                btnGameControl.textContent = "Start Match";
                btnGameControl.className = "btn btn-primary";
            } else {
                alert("Failed to stop match broadcast.");
            }
        } catch (err) {
            console.error("Game stop network error:", err);
        }
    }
}

function applyFilters() {
    const hideDiag = filterHideDiagnostics ? filterHideDiagnostics.checked : true;
    const query = filterSearch ? filterSearch.value.toLowerCase().trim() : '';
    
    const rows = sniffTbody.querySelectorAll('tr:not(.empty-row)');
    rows.forEach(row => {
        const id = parseInt(row.dataset.id);
        const packet = packetsLog[id - 1];
        if (!packet) return;
        
        let show = true;
        if (hideDiag && packet.payload_type === 'DIAGNOSTIC') {
            show = false;
        }
        if (show && query) {
            const searchStr = `${packet.source_address} ${packet.destination_address} ${packet.payload_type} ${packet.context_address}`.toLowerCase();
            if (!searchStr.includes(query)) {
                show = false;
            }
        }
        
        row.style.display = show ? 'table-row' : 'none';
    });
}

function isPacketVisible(packet) {
    const hideDiag = filterHideDiagnostics ? filterHideDiagnostics.checked : true;
    const query = filterSearch ? filterSearch.value.toLowerCase().trim() : '';
    
    if (hideDiag && packet.payload_type === 'DIAGNOSTIC') {
        return false;
    }
    if (query) {
        const searchStr = `${packet.source_address} ${packet.destination_address} ${packet.payload_type} ${packet.context_address}`.toLowerCase();
        if (!searchStr.includes(query)) {
            return false;
        }
    }
    return true;
}

async function handleSimReset() {
    const crewCount = parseInt(document.getElementById('sim-crew-count').value);
    const impCount = parseInt(document.getElementById('sim-impostor-count').value);
    
    try {
        const response = await fetch('/api/sim/reset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ crew_count: crewCount, impostor_count: impCount })
        });
        if (response.ok) {
            alert("Simulation nodes reset successfully.");
            // Reset button text in header just in case
            gameState = "LOBBY";
            if (btnGameControl) {
                btnGameControl.textContent = "Start Match";
                btnGameControl.className = "btn btn-primary";
            }
        } else {
            const err = await response.json();
            alert("Reset failed: " + JSON.stringify(err.detail));
        }
    } catch (err) {
        console.error(err);
    }
}

async function triggerSimAction(action, targetId = null) {
    try {
        const response = await fetch('/api/sim/trigger', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: action, target_id: targetId })
        });
        if (response.ok) {
            console.log(`Action ${action} triggered successfully.`);
        } else {
            const err = await response.json();
            alert("Action failed: " + JSON.stringify(err.detail));
        }
    } catch (err) {
        console.error(err);
    }
}

async function handleDifficultyChange(e) {
    const difficulty = e.target.value;
    try {
        const response = await fetch('/api/sim/difficulty', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ difficulty })
        });
        if (!response.ok) {
            const err = await response.json();
            alert("Failed to set difficulty: " + JSON.stringify(err.detail));
        } else {
            console.log("Simulation difficulty successfully set to:", difficulty);
        }
    } catch (err) {
        console.error("Error setting difficulty:", err);
    }
}

window.triggerSimAction = triggerSimAction;
