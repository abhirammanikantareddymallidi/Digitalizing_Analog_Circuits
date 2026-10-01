// Frontend logic for Hybrid Physics/ML Framework
// Supports all parameters and measurable objectives from Digitizing Analog Design Space

let circuitData = {};
let currentCircuit = null;
let technologyNodes = [];

const SUPERSCRIPT_DIGITS = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻"
};

function formatExponent(exponent) {
    return String(exponent).replace(/[0-9+-]/g, char => SUPERSCRIPT_DIGITS[char] || char);
}

function formatNumericValue(value, decimals = 3) {
    if (typeof value !== "number") return value;
    if (!Number.isFinite(value)) return String(value);
    if (Object.is(value, -0) || value === 0) return "0.00";

    const magnitude = Math.abs(value);
    if (magnitude < 1e-3 || magnitude > 1e4) {
        const [mantissa, exponent] = value.toExponential(decimals).split("e");
        return `${mantissa} × 10<sup>${formatExponent(Number(exponent))}</sup>`;
    }
    return value.toFixed(decimals);
}

function formatScientificText(text) {
    if (typeof text !== "string") return text;
    return text.replace(/(-?\d+(?:\.\d+)?)[eE]([+-]?\d+)/g, (_, mantissa, exponent) =>
        `${mantissa} × 10<sup>${formatExponent(Number(exponent))}</sup>`
    );
}

const TARGET_META = {
    "Av": { label: "Voltage Gain (Av)", unit: "V/V", placeholder: "e.g. -10.0" },
    "Av_magnitude": { label: "Voltage Gain Magnitude (|Av|)", unit: "V/V", placeholder: "e.g. 10.0" },
    "Av_dB": { label: "Voltage Gain (dB)", unit: "dB", placeholder: "e.g. 20.0" },
    "BW_MHz": { label: "Bandwidth (-3dB)", unit: "MHz", placeholder: "e.g. 100.0" },
    "GBW_MHz": { label: "Gain-Bandwidth Product", unit: "MHz", placeholder: "e.g. 500.0" },
    "phase_margin_deg": { label: "Phase Margin (PM)", unit: "°", placeholder: "e.g. 65.0" },
    "power_mW": { label: "DC Power Dissipation", unit: "mW", placeholder: "e.g. 0.5" },
    "P_total": { label: "Total Dynamic Power", unit: "W", placeholder: "e.g. 0.001" },
    "total_noise_nV": { label: "Input-Referred Noise", unit: "nV/√Hz", placeholder: "e.g. 80.0" },
    "output_swing_pp": { label: "Peak-to-Peak Output Swing", unit: "V", placeholder: "e.g. 1.2" },
    "output_swing_V": { label: "Peak Single-Ended Swing", unit: "V", placeholder: "e.g. 0.6" },
    "total_area_um2": { label: "Total Circuit Area", unit: "µm²", placeholder: "e.g. 15.0" },
    "transistor_area_um2": { label: "Transistor Active Area", unit: "µm²", placeholder: "e.g. 5.0" },
    "IIP3_V": { label: "Linearity (IIP3)", unit: "V", placeholder: "e.g. 0.35" },
    "PSRR_dB": { label: "Supply Rejection (PSRR)", unit: "dB", placeholder: "e.g. 25.0" },
    "CMRR_dB": { label: "Common Mode Rejection (CMRR)", unit: "dB", placeholder: "e.g. 40.0" },
    "ID_uA": { label: "Quiescent Bias Current (ID)", unit: "µA", placeholder: "e.g. 300.0" },
    "I_out_uA": { label: "Output Mirror Current", unit: "µA", placeholder: "e.g. 200.0" },
    "f_osc_MHz": { label: "Oscillation Frequency", unit: "MHz", placeholder: "e.g. 500.0" },
    "f_osc": { label: "Oscillation Frequency", unit: "Hz", placeholder: "e.g. 1e9" },
    "tpd": { label: "Propagation Delay", unit: "ps", placeholder: "e.g. 50.0" },
    "tpd_ps": { label: "Propagation Delay", unit: "ps", placeholder: "e.g. 50.0" },
    "gm": { label: "Transconductance (gm)", unit: "S", placeholder: "" },
    "gm_mS": { label: "Transconductance (gm)", unit: "mS", placeholder: "" },
    "ro": { label: "Output Resistance (ro)", unit: "Ω", placeholder: "" },
    "ro_kOhm": { label: "Output Resistance (ro)", unit: "kΩ", placeholder: "" }
};

const METRIC_GROUPS = [
    {
        name: "Gain & Frequency Response",
        icon: "ph-chart-line-up",
        keys: ["Av", "Av_magnitude", "Av_dB", "BW_MHz", "BW", "GBW_MHz", "GBW", "phase_margin_deg"]
    },
    {
        name: "DC Operating Point & Biasing",
        icon: "ph-lightning",
        keys: ["operating_region", "ID_uA", "ID", "IBIAS", "VBIAS", "VDS", "VOV", "VDS_sat", "gm_mS", "ro_kOhm", "Rout_kOhm", "Rin"]
    },
    {
        name: "Power & Physical Area",
        icon: "ph-bounding-box",
        keys: ["power_mW", "power_dissipation", "transistor_area_um2", "total_area_um2"]
    },
    {
        name: "Noise & Linearity (IIP3)",
        icon: "ph-waveform",
        keys: ["total_noise_nV", "thermal_noise_nV", "flicker_noise_nV", "integrated_noise_uV", "IIP3_V", "IIP3_dBm"]
    },
    {
        name: "Headroom, Swing & Rejection",
        icon: "ph-arrows-out-cardinal",
        keys: ["output_swing_V", "output_swing_pp", "PSRR_dB", "PSRR", "CMRR_dB", "CMRR", "Ad_dB", "Acm_dB"]
    }
];

document.addEventListener("DOMContentLoaded", () => {
    fetchCircuits();
    fetchTechnologies();
    setupEventListeners();
});

function setupEventListeners() {
    // Mode toggles
    document.getElementById("btn-forward").addEventListener("click", () => switchMode("forward"));
    document.getElementById("btn-inverse").addEventListener("click", () => switchMode("inverse"));

    // Tabs
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
            document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
            
            const target = e.currentTarget;
            target.classList.add("active");
            document.getElementById(target.dataset.target).classList.add("active");
        });
    });

    // Run actions
    document.getElementById("run-forward-btn").addEventListener("click", runForwardAnalysis);
    document.getElementById("run-inverse-btn").addEventListener("click", runInverseDesign);
    document.getElementById("sel-node").addEventListener("change", updateTechnologySelection);
    document.getElementById("sel-device").addEventListener("change", updateTechnologySelection);
}

async function fetchTechnologies() {
    try {
        const res = await fetch("/api/technologies");
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || "Technology API request failed");

        technologyNodes = data.nodes || [];
        updateTechnologyNodes();
    } catch (e) {
        document.getElementById("sel-node").innerHTML = '<option value="">Unavailable</option>';
        document.getElementById("tech-status-text").textContent = "Technology data unavailable";
        console.error("Failed to load technologies:", e);
    }
}

function updateTechnologyNodes() {
    const nodeSelect = document.getElementById("sel-node");
    const statusText = document.getElementById("tech-status-text");
    nodeSelect.innerHTML = '<option value="">Select Node</option>';

    const availableNodes = technologyNodes
        .filter(node => node.has_model_file && node.valid);
    availableNodes.forEach(node => {
            const option = document.createElement("option");
            option.value = node.node_name;
            option.textContent = node.node_name;
            nodeSelect.appendChild(option);
        });

    technologyNodes
        .filter(node => node.has_model_file && !node.valid)
        .forEach(node => {
            const option = document.createElement("option");
            option.textContent = `${node.node_name} (invalid model)`;
            option.disabled = true;
            option.title = (node.parse_errors || []).join("; ");
            nodeSelect.appendChild(option);
        });

    if (availableNodes.length === 0 && !technologyNodes.some(node => node.has_model_file && !node.valid)) {
        const option = document.createElement("option");
        option.textContent = "No PTM nodes available";
        option.disabled = true;
        nodeSelect.appendChild(option);
    }
    nodeSelect.value = "";
    updateTechnologySelection();
    if (availableNodes.length === 0) {
        statusText.textContent = "No valid technology models available";
    }
}

async function updateTechnologySelection() {
    const nodeName = document.getElementById("sel-node").value;
    const badge = document.getElementById("tech-status-badge");
    const statusText = document.getElementById("tech-status-text");
    const pill = document.getElementById("tech-context-pill");
    const pillText = document.getElementById("tech-context-text");
    const node = technologyNodes.find(item => item.node_name === nodeName);

    if (!node) {
        badge.className = "tech-status-badge no-file";
        statusText.textContent = "Select a technology node";
        pill.style.display = "none";
        return;
    }

    badge.className = `tech-status-badge ${node.has_model_file ? "has-file" : "no-file"}`;
    statusText.textContent = node.has_model_file ? `PTM model loaded (${node.node_nm} nm)` : "No PTM model file";
    pill.style.display = "flex";
    pillText.textContent = `${node.node_name} | ${document.getElementById("sel-device").value}`;

    if (node.has_model_file) {
        try {
            const deviceType = document.getElementById("sel-device").value;
            const response = await fetch(`/api/tech-defaults/${encodeURIComponent(node.node_name)}?device_type=${deviceType}`);
            const data = await response.json();
            Object.entries(data.defaults || {}).forEach(([name, value]) => {
                const input = document.getElementById(`in_${name}`);
                if (input && typeof value === "number") input.value = value;
            });
        } catch (error) {
            console.error("Failed to load technology defaults:", error);
        }
    }
}

function getTechnologySelection() {
    return {
        technology_node: document.getElementById("sel-node").value || null,
        device_type: document.getElementById("sel-device").value
    };
}

async function fetchCircuits() {
    try {
        const res = await fetch("/api/circuits");
        const data = await res.json();
        circuitData = data.details;
        
        const list = document.getElementById("circuit-list");
        list.innerHTML = "";
        
        data.circuits.forEach((c, idx) => {
            const config = circuitData[c];
            const btn = document.createElement("button");
            btn.className = "circuit-btn" + (idx === 0 ? " active" : "");
            btn.innerHTML = `${config.abbreviation} - ${config.name}`;
            btn.onclick = () => selectCircuit(c, btn);
            list.appendChild(btn);
            
            if (idx === 0) selectCircuit(c, btn);
        });
    } catch (e) {
        console.error("Failed to load circuits:", e);
    }
}

function selectCircuit(circuitId, btnElement) {
    document.querySelectorAll(".circuit-btn").forEach(b => b.classList.remove("active"));
    btnElement.classList.add("active");
    
    currentCircuit = circuitId;
    const config = circuitData[circuitId];
    
    document.getElementById("current-circuit-title").textContent = config.name;
    document.getElementById("current-circuit-desc").textContent = config.description;
    
    buildInputForms(config);
    if (document.getElementById("sel-node").value) updateTechnologySelection();
    clearResults();
}

function buildInputForms(config) {
    // 1. Forward Inputs
    const fwdContainer = document.getElementById("forward-inputs");
    fwdContainer.innerHTML = '<div class="input-grid"></div>';
    const grid = fwdContainer.querySelector(".input-grid");
    
    for (const [pname, info] of Object.entries(config.input_parameters)) {
        if ((config.technology_parameters || []).includes(pname)) continue;
        let step = "any";
        if (pname === "L" || pname === "Ln") step = "0.01";
        else if (pname === "W" || pname === "Wn") step = "0.1";
        else if (pname.startsWith("V")) step = "0.05";
        
        grid.innerHTML += `
            <div class="input-group">
                <label>${pname} <span class="unit-tag">${info.unit || ""}</span></label>
                <input type="number" id="in_${pname}" value="${info.default}" step="${step}" title="${info.description}">
            </div>
        `;
    }

    // 2. Inverse Targets
    const invContainer = document.getElementById("inverse-targets");
    invContainer.innerHTML = "";

    const fixedInputsHtml = "";

    // Add preset quick buttons for Common Source
    let presetsHtml = "";
    if (currentCircuit === "common_source") {
        presetsHtml = `
            <div class="preset-bar">
                <span class="preset-lbl"><i class="ph-bold ph-lightning"></i> Presets:</span>
                <button type="button" class="preset-pill" onclick="applyPreset({Av_dB: 20, BW_MHz: 100, phase_margin_deg: 65, power_mW: 0.5})">Standard (20dB, 100MHz)</button>
                <button type="button" class="preset-pill" onclick="applyPreset({Av_dB: 26, BW_MHz: 40, phase_margin_deg: 70, power_mW: 0.8})">High Gain (26dB)</button>
                <button type="button" class="preset-pill" onclick="applyPreset({Av_dB: 14, BW_MHz: 500, phase_margin_deg: 75, power_mW: 0.9})">Wideband (500MHz)</button>
                <button type="button" class="preset-pill" onclick="applyPreset({Av_dB: 18, BW_MHz: 50, power_mW: 0.25, phase_margin_deg: 75})">Low Power (0.25mW)</button>
            </div>
        `;
    } else if (currentCircuit === "differential_amplifier") {
        presetsHtml = `
            <div class="preset-bar">
                <span class="preset-lbl"><i class="ph-bold ph-lightning"></i> Presets:</span>
                <button type="button" class="preset-pill" onclick="applyPreset({Ad_dB: 24, BW_MHz: 80, CMRR_dB: 50, power_mW: 1.0})">Balanced DiffAmp</button>
                <button type="button" class="preset-pill" onclick="applyPreset({Ad_dB: 30, BW_MHz: 30, CMRR_dB: 60, power_mW: 1.5})">High CMRR DiffAmp</button>
            </div>
        `;
    } else if (currentCircuit === "single_stage_opamp") {
        presetsHtml = `
            <div class="preset-bar">
                <span class="preset-lbl"><i class="ph-bold ph-lightning"></i> Presets:</span>
                <button type="button" class="preset-pill" onclick="applyPreset({Av_dB: 33.98, GBW_MHz: 3183.1, power_mW: 0.09})">Standard / Balanced</button>
                <button type="button" class="preset-pill" onclick="applyPreset({Av_dB: 36})">High Gain</button>
                <button type="button" class="preset-pill" onclick="applyPreset({GBW_MHz: 5000})">High Bandwidth</button>
                <button type="button" class="preset-pill" onclick="applyPreset({power_mW: 0.05})">Low Power</button>
            </div>
        `;
    } else if (currentCircuit === "two_stage_opamp") {
        presetsHtml = `
            <div class="preset-bar">
                <span class="preset-lbl"><i class="ph-bold ph-lightning"></i> Presets:</span>
                <button type="button" class="preset-pill" onclick="applyPreset({Av_dB: 79.17, GBW_MHz: 43405.9, power_mW: 0.09})">Standard / Balanced</button>
                <button type="button" class="preset-pill" onclick="applyPreset({Av_dB: 80.5})">High Gain</button>
                <button type="button" class="preset-pill" onclick="applyPreset({GBW_MHz: 50000})">High Bandwidth</button>
                <button type="button" class="preset-pill" onclick="applyPreset({power_mW: 0.06})">Low Power</button>
            </div>
        `;
    } else if (currentCircuit === "ring_oscillator") {
        presetsHtml = `
            <div class="preset-bar">
                <span class="preset-lbl"><i class="ph-bold ph-lightning"></i> Presets:</span>
                <button type="button" class="preset-pill" onclick="applyPreset({f_osc: 172600000000, P_total: 0.0139806})">Standard Ring Oscillator</button>
                <button type="button" class="preset-pill" onclick="applyPreset({f_osc: 1000000000000})">High Frequency</button>
                <button type="button" class="preset-pill" onclick="applyPreset({P_total: 0.0007})">Low Power</button>
                <button type="button" class="preset-pill" onclick="applyPreset({f_osc: 150000000000, P_total: 0.012})">Balanced</button>
            </div>
        `;
    }

    let targetInputsHtml = '<div class="input-grid">';
    let renderedCount = 0;

    // Filter outputs to find all targetable metrics
    config.output_parameters.forEach(tname => {
        if (TARGET_META[tname] || tname.includes("dB") || tname.includes("MHz") || tname.includes("mW")) {
            const meta = TARGET_META[tname] || {
                label: tname.replace(/_/g, " "),
                unit: tname.includes("dB") ? "dB" : (tname.includes("MHz") ? "MHz" : (tname.includes("mW") ? "mW" : "")),
                placeholder: "0"
            };
            
            targetInputsHtml += `
                <div class="input-group">
                    <label>${meta.label} <span class="unit-tag">${meta.unit}</span></label>
                    <input type="number" id="tgt_${tname}" placeholder="${meta.placeholder}" step="any">
                </div>
            `;
            renderedCount++;
        }
    });

    targetInputsHtml += '</div>';

    if (renderedCount === 0) {
        invContainer.innerHTML = `<div class="empty-state inline"><i class="ph ph-info"></i><p>No targetable objectives defined for this circuit.</p></div>`;
    } else {
        invContainer.innerHTML = fixedInputsHtml + presetsHtml + targetInputsHtml;
    }
}

function applyPreset(presetObj) {
    // Clear existing
    document.querySelectorAll("#inverse-targets input").forEach(inp => inp.value = "");
    for (const [k, v] of Object.entries(presetObj)) {
        const inp = document.getElementById(`tgt_${k}`);
        if (inp) inp.value = v;
    }
}

function clearResults() {
    document.getElementById("physics-results").innerHTML = `<div class="empty-state"><i class="ph-fill ph-calculator"></i><p>Run analysis to view physics-derived results.</p></div>`;
    document.getElementById("equations-results").innerHTML = "";
    document.getElementById("constraint-results").innerHTML = `<div class="empty-state inline"><p>Physics constraints will be verified here.</p></div>`;
    document.getElementById("verification-badge").className = "status-badge hidden";
    document.getElementById("inverse-results").innerHTML = `<div class="empty-state"><i class="ph-fill ph-cube"></i><p>Run synthesis to generate physically verified design candidates.</p></div>`;
    document.getElementById("candidates-count").textContent = "0 found";
}

function switchMode(mode) {
    document.getElementById("btn-forward").classList.toggle("active", mode === "forward");
    document.getElementById("btn-inverse").classList.toggle("active", mode === "inverse");
    
    document.getElementById("forward-mode").classList.toggle("active", mode === "forward");
    document.getElementById("inverse-mode").classList.toggle("active", mode === "inverse");
}

async function runForwardAnalysis() {
    if (!currentCircuit) return;
    
    const config = circuitData[currentCircuit];
    const params = {};
    for (const pname of Object.keys(config.input_parameters)) {
        const inp = document.getElementById(`in_${pname}`);
        if (inp && inp.value !== "") {
            params[pname] = parseFloat(inp.value);
        }
    }
    
    const btn = document.getElementById("run-forward-btn");
    btn.innerHTML = '<i class="ph-bold ph-spinner ph-spin"></i> Computing...';
    
    try {
        const res = await fetch("/api/forward", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                circuit_type: currentCircuit,
                params: params,
                include_ml: false,
                ...getTechnologySelection()
            })
        });
        
        const result = await res.json();
        renderForwardResults(result);
    } catch (e) {
        alert("Error running analysis: " + e.message);
    } finally {
        btn.innerHTML = '<i class="ph-bold ph-play"></i> Run Analysis';
    }
}

function renderForwardResults(res) {
    if (res.error) {
        alert(res.error);
        return;
    }
    
    // Status Badge
    const badge = document.getElementById("verification-badge");
    const status = res.verification_summary ? res.verification_summary.overall_status : "FAIL";
    let icon = status === "PASS" ? "ph-check-circle" : (status === "WARNING" ? "ph-warning" : "ph-x-circle");
    badge.innerHTML = `<i class="ph-fill ${icon}"></i> ${status === "PASS" ? "PHYSICS VERIFIED" : "CHECKS NEED ATTENTION"}`;
    badge.className = `status-badge ${status}`;
    
    // Grouped Physics Results
    const container = document.getElementById("physics-results");
    container.innerHTML = "";
    
    const phys = res.physics_results || {};
    const usedKeys = new Set();
    let groupedHtml = "";

    METRIC_GROUPS.forEach(grp => {
        let groupItemsHtml = "";
        grp.keys.forEach(k => {
            if (k in phys) {
                usedKeys.add(k);
                const val = phys[k];
                const formatted = formatNumericValue(val);
                
                const meta = TARGET_META[k] || { label: k, unit: "" };
                groupItemsHtml += `
                    <div class="result-card">
                        <div class="result-label">${meta.label || k} ${meta.unit ? `<span class="unit-tag">${meta.unit}</span>` : ""}</div>
                        <div class="result-val">${formatted}</div>
                    </div>
                `;
            }
        });

        if (groupItemsHtml) {
            groupedHtml += `
                <div class="category-group">
                    <div class="category-header"><i class="ph-bold ${grp.icon}"></i> ${grp.name}</div>
                    <div class="category-grid">${groupItemsHtml}</div>
                </div>
            `;
        }
    });

    // Any remaining outputs not in groups
    let otherItemsHtml = "";
    const hiddenInternalOutputs = new Set([
        "nmos_ID", "pmos_ID", "nmos_ID_uA", "pmos_ID_uA",
        "ID_n_numeric", "ID_p_abs_numeric",
    ]);
    for (const [k, v] of Object.entries(phys)) {
        if (!usedKeys.has(k) && !hiddenInternalOutputs.has(k) && !k.includes("equations") && !k.includes("conditions")) {
            const formatted = formatNumericValue(v);
            otherItemsHtml += `
                <div class="result-card">
                    <div class="result-label">${k}</div>
                    <div class="result-val">${formatted}</div>
                </div>
            `;
        }
    }
    if (otherItemsHtml) {
        groupedHtml += `
            <div class="category-group">
                <div class="category-header"><i class="ph-bold ph-list-plus"></i> Additional Output Metrics</div>
                <div class="category-grid">${otherItemsHtml}</div>
            </div>
        `;
    }

    container.innerHTML = groupedHtml || `<div class="empty-state"><p>No outputs computed.</p></div>`;
    
    // Equations Audit Trail
    let eqHtml = "";
    if (res.equations_used) {
        res.equations_used.forEach(eq => {
            eqHtml += `<div class="eq-item">${formatScientificText(eq)}</div>`;
        });
    }
    if (res.small_signal_equations) {
        res.small_signal_equations.forEach(eq => {
            eqHtml += `<div class="eq-item">${formatScientificText(eq)}</div>`;
        });
    }
    document.getElementById("equations-results").innerHTML = eqHtml || '<div class="empty-state inline"><p>No equations logged.</p></div>';
    
    // Constraints Checks
    let cHtml = "";
    if (res.constraint_checks) {
        res.constraint_checks.forEach(c => {
            const cClass = c.satisfied ? "pass" : `fail ${(c.severity || "warning").toLowerCase()}`;
            const statusText = c.satisfied ? "PASS" : (c.severity || "FAIL");
            cHtml += `
                <div class="constraint-card ${cClass}">
                    <div class="c-head">
                        <span class="c-name">${c.name}</span>
                        <span class="c-status ${statusText}">${statusText}</span>
                    </div>
                    <div class="c-cond">${formatScientificText(c.condition)}</div>
                    <div class="c-rule"><i class="ph-bold ph-info"></i> ${formatScientificText(c.rule)}</div>
                </div>
            `;
        });
    }
    document.getElementById("constraint-results").innerHTML = cHtml || '<div class="empty-state inline"><p>Constraints verified.</p></div>';
    
}

async function runInverseDesign() {
    if (!currentCircuit) return;

    const selectedNode = document.getElementById("sel-node").value;
    const selectedTechnology = technologyNodes.find(node => node.node_name === selectedNode);
    if (selectedNode && (!selectedTechnology || !selectedTechnology.has_model_file)) {
        alert("Please select a technology node with a PTM parameter file.");
        return;
    }
    
    const targets = {};
    document.querySelectorAll("#inverse-targets input[id^='tgt_']").forEach(inp => {
        const tname = inp.id.replace("tgt_", "");
        if (inp.value && parseFloat(inp.value) !== 0 && !isNaN(parseFloat(inp.value))) {
            targets[tname] = parseFloat(inp.value);
        }
    });
    
    if (Object.keys(targets).length === 0) {
        alert("Please specify at least one target specification value (or click a Preset).");
        return;
    }

    // Fixed supply voltage
    const vddInput = document.getElementById("in_VDD");
    const fixed = { "VDD": parseFloat(vddInput ? vddInput.value : 1.8) };
    
    const btn = document.getElementById("run-inverse-btn");
    btn.innerHTML = '<i class="ph-bold ph-spinner ph-spin"></i> Synthesizing...';
    
    try {
        const res = await fetch("/api/inverse", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                circuit_type: currentCircuit,
                targets: targets,
                fixed_params: fixed,
                ...getTechnologySelection()
            })
        });
        
        const result = await res.json();
        renderInverseResults(result);
    } catch (e) {
        alert("Error running synthesis: " + e.message);
    } finally {
        btn.innerHTML = '<i class="ph-bold ph-magic-wand"></i> Synthesize Design';
    }
}

function renderInverseResults(res) {
    if (res.error) {
        alert(res.error);
        return;
    }
    
    document.getElementById("candidates-count").textContent = `${res.n_candidates} found`;
    const container = document.getElementById("inverse-results");
    
    if (res.n_candidates === 0) {
        container.innerHTML = `<div class="empty-state"><i class="ph-fill ph-x-circle"></i><p>No feasible design found satisfying the constraints.</p></div>`;
        return;
    }
    
    let html = '<div style="display:flex; flex-direction:column; gap:20px;">';
    
    res.candidates.forEach((cand, idx) => {
        const calculatedParameters = cand.calculatedParameters || cand.design_parameters || {};
        const isValid = cand.physically_valid ? 
            `<span class="badge" style="background:rgba(16, 185, 129, 0.2); color:var(--status-success); border:1px solid rgba(16, 185, 129, 0.4)"><i class="ph-bold ph-check" style="margin-right:4px;"></i> Physically Valid</span>` : 
            `<span class="badge" style="background:rgba(239, 68, 68, 0.2); color:var(--status-danger); border:1px solid rgba(239, 68, 68, 0.4)"><i class="ph-bold ph-warning" style="margin-right:4px;"></i> ${cand.critical_failures} Constraint Violation(s)</span>`;
            
        let paramsHtml = "";
        for (const [k, v] of Object.entries(calculatedParameters)) {
            const unit = (circuitData[currentCircuit] && circuitData[currentCircuit].input_parameters[k]) ?
                circuitData[currentCircuit].input_parameters[k].unit : "";
            const formattedValue = formatNumericValue(v);
            const parameterKind = ["VGS", "VDS"].includes(k) ? "calculated" :
                (res.variable_params.includes(k) ? "optimized" : "fixed");
            paramsHtml += `<div class="cand-row"><span class="cand-lbl">${k} <small>(${parameterKind})</small></span> <span style="color:var(--accent-cyan); font-weight:600;">${formattedValue} ${unit}</span></div>`;
        }

        const outputMeta = [
            ["ID_uA", "Calculated ID", "µA"],
            ["VOV", "VOV", "V"],
            ["gm_mS", "gm", "mS"],
            ["ro_kOhm", "ro", "kΩ"],
            ["Av", "Av", "V/V"],
            ["Av_magnitude", "|Av|", "V/V"],
            ["Av_dB", "Gain", "dB"],
            ["operating_region", "Operating Region", ""]
        ];
        let operatingHtml = "";
        const outputs = cand.computed_outputs || {};
        outputMeta.forEach(([key, label, unit]) => {
            if (outputs[key] === undefined) return;
            const value = formatNumericValue(outputs[key]);
            operatingHtml += `<div class="cand-row"><span class="cand-lbl">${label}</span> <span style="color:var(--accent-cyan); font-weight:600;">${value} ${unit}</span></div>`;
        });
        
        let targetHtml = "";
        for (const [k, v] of Object.entries(cand.target_status)) {
            const color = v.met ? 'var(--status-success)' : 'var(--status-warning)';
            const meta = TARGET_META[k] || { label: k, unit: "" };
            targetHtml += `
                <div class="cand-row">
                    <span class="cand-lbl">${meta.label || k}</span>
                    <div>
                        <span style="color:${color}; font-weight:600;">${formatNumericValue(v.achieved, 2)} ${meta.unit}</span>
                        <span class="cand-val-tgt">(tgt: ${v.target} ${meta.unit})</span>
                    </div>
                </div>
            `;
        }

        // Serialized params for button
        const paramsJson = encodeURIComponent(JSON.stringify(calculatedParameters));
        
        html += `
            <div class="cand-card">
                <div class="cand-card-header">
                    <div class="cand-title"><i class="ph-fill ph-cpu"></i> Candidate ${idx+1} <span style="color:var(--text-tertiary); font-size:0.85rem; font-weight:400;">(${cand.method})</span></div>
                    ${isValid}
                </div>
                
                <div class="cand-grid">
                    <div>
                        <div class="cand-section-title"><i class="ph-bold ph-sliders"></i> Synthesized Parameters</div>
                        ${paramsHtml}
                    </div>
                    <div>
                        <div class="cand-section-title"><i class="ph-bold ph-target"></i> Target Verification</div>
                        ${targetHtml}
                    </div>
                    <div>
                        <div class="cand-section-title"><i class="ph-bold ph-chart-line-up"></i> Calculated Operating Point</div>
                        ${operatingHtml}
                    </div>
                </div>

                <div class="cand-footer">
                    <button type="button" class="apply-cand-btn" onclick="applyCandidateToForward('${paramsJson}')">
                        <i class="ph-bold ph-arrow-counter-clockwise"></i> Load into Forward Analysis
                    </button>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
}

function applyCandidateToForward(encodedParams) {
    try {
        const params = JSON.parse(decodeURIComponent(encodedParams));
        for (const [k, v] of Object.entries(params)) {
            const inp = document.getElementById(`in_${k}`);
            if (inp) {
                inp.value = parseFloat(v.toFixed(4));
            }
        }
        switchMode("forward");
        runForwardAnalysis();
    } catch (e) {
        console.error("Failed to apply candidate:", e);
    }
}
