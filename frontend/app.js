/* ═══════════════════════════════════════════════════════
   CHVN Paper Reviewer — app.js v4
   Groq API · Railway · Token auth · Sequential mode
   ═══════════════════════════════════════════════════════ */

const API = window.location.origin;

let state = {
  sessionId:    localStorage.getItem("lastSessionId") || null,
  filename:     null,
  uploadData:   null,
  polling:      null,
  timerInterval: null,
  results:      null,
  suggestionDecisions: {},
};

// ─── AUTH TOKEN ───────────────────────────────────────────────────────────────
function getToken()       { return localStorage.getItem("chvn_token") || ""; }
function setToken(t)      { localStorage.setItem("chvn_token", t); }
function clearToken()     { localStorage.removeItem("chvn_token"); }

/** Wrapper for all API calls — injects auth token and handles 401 */
async function apiFetch(url, opts = {}) {
  const token = getToken();
  opts.headers = opts.headers || {};
  if (token) opts.headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, opts);
  if (res.status === 401) {
    showLoginOverlay("Token incorrecto o expirado. Ingresa de nuevo.");
    throw new Error("Unauthorized");
  }
  return res;
}

function showLoginOverlay(msg = "") {
  document.getElementById("loginOverlay").style.display = "flex";
  if (msg) document.getElementById("loginMsg").textContent = msg;
}
function hideLoginOverlay() {
  document.getElementById("loginOverlay").style.display = "none";
}

async function submitToken() {
  const input = document.getElementById("tokenInput").value.trim();
  if (!input) return;
  setToken(input);
  // Verify token with a health check
  try {
    const res = await apiFetch(`${API}/config`);
    if (res.ok) {
      hideLoginOverlay();
      initApp();
    } else {
      clearToken();
      document.getElementById("loginMsg").textContent = "Token inválido. Intenta de nuevo.";
    }
  } catch {
    // 401 already handled by apiFetch
  }
}

// ─── INIT ─────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  // Check if auth is needed
  const res = await fetch(`${API}/health`).catch(() => null);
  if (!res) {
    document.getElementById("healthDot").className = "health-dot err";
    document.getElementById("healthLabel").textContent = "API offline";
    return;
  }
  const data = await res.json().catch(() => ({}));

  // If token auth is enabled (health endpoint works but /config needs token)
  const cfgRes = await apiFetch(`${API}/config`).catch(() => null);
  if (cfgRes && cfgRes.status === 401) {
    const saved = getToken();
    if (saved) {
      // Try saved token
      const verify = await apiFetch(`${API}/config`, {
        headers: { "Authorization": `Bearer ${saved}` }
      }).catch(() => null);
      if (verify && verify.ok) {
        hideLoginOverlay();
        initApp();
      } else {
        clearToken();
        showLoginOverlay("Ingresa tu token de acceso.");
      }
    } else {
      showLoginOverlay("Ingresa tu token de acceso.");
    }
  } else {
    hideLoginOverlay();
    initApp();
  }
});

function initApp() {
  checkHealth();
  loadConfig();
  loadAvailableModels();
  loadHistory();
  setupModeCards();
  setInterval(checkHealth, 30000);
}

// ─── NAVIGATION ───────────────────────────────────────────────────────────────
function showPanel(name) {
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
  document.getElementById(`panel-${name}`).classList.add("active");
  document.querySelector(`[data-panel="${name}"]`).classList.add("active");
  if (name === "history") loadHistory();
}

// ─── HEALTH ───────────────────────────────────────────────────────────────────
async function checkHealth() {
  const dot   = document.getElementById("healthDot");
  const label = document.getElementById("healthLabel");
  try {
    const res  = await fetch(`${API}/health`);
    const data = await res.json();
    const groq = data.groq || data.ollama || {};
    if (groq.groq_api || groq.ollama_running) {
      dot.className     = "health-dot ok";
      label.textContent = `${data.config?.model || "llama-3.3-70b"} · Ready`;
    } else {
      dot.className     = "health-dot err";
      label.textContent = groq.error || "API not configured";
    }
  } catch {
    dot.className     = "health-dot err";
    label.textContent = "API offline";
  }
}

// ─── MODEL DROPDOWN ───────────────────────────────────────────────────────────
async function loadAvailableModels() {
  try {
    const res  = await apiFetch(`${API}/models`);
    const data = await res.json();
    const sel  = document.getElementById("cfgModelSelect");
    sel.innerHTML = "";

    if (!data.models?.length) {
      sel.innerHTML = '<option value="">No models available</option>';
      return;
    }
    data.models.forEach(m => {
      const opt      = document.createElement("option");
      opt.value      = m;
      opt.textContent = m;
      if (m === data.current || m.startsWith(data.current)) opt.selected = true;
      sel.appendChild(opt);
    });
    if (sel.value) document.getElementById("cfgModel").value = sel.value;
  } catch {
    document.getElementById("cfgModelSelect").innerHTML = '<option value="">Groq models</option>';
  }
}

function onModelSelect() {
  const v = document.getElementById("cfgModelSelect").value;
  if (v) document.getElementById("cfgModel").value = v;
}

// ─── FILE HANDLING ────────────────────────────────────────────────────────────
function handleDragOver(e) {
  e.preventDefault();
  document.getElementById("dropZone").classList.add("drag-over");
}
function handleDragLeave() {
  document.getElementById("dropZone").classList.remove("drag-over");
}
function handleDrop(e) {
  e.preventDefault();
  document.getElementById("dropZone").classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) processFile(file);
}
function handleFileSelect(e) {
  if (e.target.files[0]) processFile(e.target.files[0]);
}

async function processFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showToast("Only PDF files accepted.", "error"); return;
  }
  if (file.size > 20 * 1024 * 1024) {
    showToast("File exceeds 20 MB.", "error"); return;
  }

  document.getElementById("filePreview").style.display = "block";
  document.getElementById("dropZone").style.display    = "none";
  document.getElementById("previewName").textContent   = file.name;
  document.getElementById("previewMeta").textContent   = `${(file.size/1024/1024).toFixed(2)} MB — parsing...`;

  showToast("Uploading and parsing PDF...", "info");

  const fd = new FormData();
  fd.append("file", file);

  try {
    const res  = await apiFetch(`${API}/upload`, { method: "POST", body: fd });
    const data = await res.json();

    if (!res.ok) { showToast(data.detail || "Upload failed.", "error"); clearFile(); return; }

    state.sessionId  = data.session_id;
    state.filename   = data.filename;
    state.uploadData = data;
    // Guarda en localStorage para persistir entre recargas
    localStorage.setItem("lastSessionId", data.session_id);

    document.getElementById("previewMeta").textContent =
      `${data.size_mb} MB · ${data.word_count.toLocaleString()} words · ${data.format_detected}`;

    renderParseResults(data);

    document.getElementById("parseResults").style.display  = "block";
    document.getElementById("modeSelector").style.display  = "block";
    document.getElementById("actionBar").style.display     = "flex";
    updateSidebar(data);
    showToast(`Parsed — ${data.sections_found.length} sections · ${data.format_detected} format`, "success");

  } catch {
    showToast("Backend error — is the server running?", "error");
    clearFile();
  }
}

function renderParseResults(data) {
  document.getElementById("formatBadge").textContent = `📋 ${data.format_detected}`;

  const grid = document.getElementById("sectionsGrid");
  grid.innerHTML = "";
  ["title","abstract","keywords","introduction","literature","methodology",
   "experiments","results","discussion","conclusions","references"].forEach(s => {
    const c = document.createElement("span");
    c.className = "chip" + (data.sections_found.includes(s) ? " on" : "");
    c.textContent = s;
    grid.appendChild(c);
  });

  const fb = document.getElementById("featureBadges");
  fb.innerHTML = "";
  [
    { k:"has_statistics", label:"📊 Statistics",  count: null },
    { k:"has_equations",  label:"∑ Equations",    count:"equation_count" },
    { k:"has_figures",    label:"📈 Figures",      count:"figure_count" },
    { k:"has_tables",     label:"📋 Tables",       count:"table_count" },
  ].forEach(f => {
    const c = document.createElement("span");
    const n = f.count && data[f.count] ? ` ×${data[f.count]}` : "";
    c.className   = `chip ${data[f.k] ? "has" : "no"}`;
    c.textContent = data[f.k] ? `${f.label}${n}` : `${f.label} ✗`;
    fb.appendChild(c);
  });

  renderDetectedFields(data);

  const wb = document.getElementById("warningsBox");
  if (data.warnings?.length) {
    wb.style.display = "block";
    wb.innerHTML = data.warnings.map(w => `<div class="warning-item">⚠ ${w}</div>`).join("");
  } else {
    wb.style.display = "none";
  }
}

function renderDetectedFields(data) {
  const box = document.getElementById("detectedFields");
  const fields = [
    ["Title", data.detected_title],
    ["Abstract", data.detected_abstract],
    ["Keywords", data.detected_keywords],
  ];
  box.innerHTML = fields.map(([label, value]) => {
    const text = (value || "").trim();
    // Aumentado de 420 a 1500 para mostrar abstractos completos
    const short = text.length > 1500 ? `${text.slice(0, 1500)}...` : text;
    return `<div class="detected-field ${text ? "ok" : "missing"}">
      <div class="detected-label">${label}</div>
      <div class="detected-text">${short || "Not detected"}</div>
    </div>`;
  }).join("");
}

function clearFile() {
  document.getElementById("dropZone").style.display        = "block";
  document.getElementById("filePreview").style.display     = "none";
  document.getElementById("parseResults").style.display    = "none";
  document.getElementById("modeSelector").style.display    = "none";
  document.getElementById("actionBar").style.display       = "none";
  document.getElementById("progressSection").style.display = "none";
  document.getElementById("suggestionGate").style.display  = "none";
  document.getElementById("fileInput").value = "";
  state.uploadData = null;
}

// ─── MODE CARDS ───────────────────────────────────────────────────────────────
function setupModeCards() {
  document.querySelectorAll(".mode-card").forEach(card => {
    card.addEventListener("click", () => {
      document.querySelectorAll(".mode-card").forEach(c => c.classList.remove("active-mode"));
      card.classList.add("active-mode");
    });
  });
}
function getMode() {
  return document.querySelector('input[name="mode"]:checked')?.value || "fast";
}

// ─── TIMER ────────────────────────────────────────────────────────────────────
let timerStart = null;

function startTimer() {
  timerStart = Date.now();
  if (state.timerInterval) clearInterval(state.timerInterval);
  state.timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - timerStart) / 1000);
    const m = Math.floor(elapsed / 60).toString().padStart(2, "0");
    const s = (elapsed % 60).toString().padStart(2, "0");
    document.getElementById("timerDisplay").textContent = `${m}:${s}`;
  }, 1000);
}

function stopTimer() {
  if (state.timerInterval) { clearInterval(state.timerInterval); state.timerInterval = null; }
}

// ─── REVIEW ───────────────────────────────────────────────────────────────────
async function startReview() {
  if (!state.sessionId) { showToast("Upload a PDF first.", "error"); return; }
  const mode = getMode();
  const runBtn  = document.getElementById("runBtn");
  const stopBtn = document.getElementById("stopBtn");

  runBtn.disabled       = true;
  stopBtn.style.display = "inline-flex";
  document.getElementById("progressSection").style.display = "block";
  renderPipelineChips();
  renderLiveAgentCards();
  showPanel("agents");
  updateProgress(5, "Starting review...");
  startTimer();

  try {
    const res  = await apiFetch(`${API}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id:  state.sessionId,
        mode,
        publisher:   document.getElementById("publisherSelect").value  || null,
        paper_type:  document.getElementById("paperTypeSelect").value  || null,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Failed to start.", "error");
      runBtn.disabled = false;
      stopBtn.style.display = "none";
      stopTimer();
      updateProgress(0, data.detail || "Review not started");
      if (res.status === 404) {
        state.sessionId = null;
        showPanel("upload");
      }
      return;
    }
    const pub  = document.getElementById("publisherSelect").value;
    const ptype = document.getElementById("paperTypeSelect").value;
    const rubricTag = pub ? ` · ${pub.toUpperCase()}` : "";
    const typeTag   = ptype ? ` · ${ptype.replace(/_/g," ")}` : "";
    showToast(`Review started — ${mode} mode${rubricTag}${typeTag}`, "info");
    startPolling();
  } catch {
    showToast("Backend error.", "error");
    runBtn.disabled = false; stopBtn.style.display = "none"; stopTimer();
  }
}

async function stopReview() {
  if (!state.sessionId) return;
  try {
    await apiFetch(`${API}/stop/${state.sessionId}`, { method: "POST" });
    showToast("Stopping — completed agents saved.", "info");
    document.getElementById("stopBtn").style.display = "none";
  } catch { showToast("Could not stop.", "error"); }
}

// ─── POLLING ──────────────────────────────────────────────────────────────────
function startPolling() {
  if (state.polling) clearInterval(state.polling);
  state.polling = setInterval(pollStatus, 2500);
}

async function pollStatus() {
  if (!state.sessionId) return;
  try {
    const res  = await apiFetch(`${API}/status/${state.sessionId}`);
    if (!res.ok) {
      const data = await safeJson(res);
      clearInterval(state.polling);
      state.polling = null;
      stopTimer();
      document.getElementById("stopBtn").style.display = "none";
      document.getElementById("runBtn").disabled = false;
      updateProgress(0, data.detail || "Session not available");
      showToast(data.detail || "Session not available. Upload the PDF again.", "error");
      return;
    }
    const data = await res.json();

    updateProgress(data.progress, data.current_agent || "Processing...");
    updatePipelineChips(data.current_agent, data.agents_done);
    await fetchPartialResults(data.current_agent);

    // Update timer from server
    if (data.elapsed_sec > 0) {
      const m = Math.floor(data.elapsed_sec / 60).toString().padStart(2,"0");
      const s = (data.elapsed_sec % 60).toString().padStart(2,"0");
      document.getElementById("timerDisplay").textContent = `${m}:${s}`;
    }

    if (data.status === "completed" || data.status === "stopped") {
      clearInterval(state.polling);
      stopTimer();
      // Guarda sessionId en localStorage para Modo Autor
      if (state.sessionId) localStorage.setItem("lastSessionId", state.sessionId);
      updateProgress(100, data.status === "stopped" ? "Stopped — partial report saved" : "Review complete!");
      document.getElementById("stopBtn").style.display = "none";
      document.getElementById("runBtn").disabled = false;
      document.getElementById("newReviewBtn").style.display = "inline-flex";
      await fetchResults();
      loadHistory();
      enableAuthorTab();
      showPanel("report");
      showToast(data.status === "stopped" ? "Partial review saved." : "Review complete! ✓", "success");
    } else if (data.status === "error") {
      clearInterval(state.polling);
      state.polling = null;
      stopTimer();
      showToast(`Error: ${data.error}`, "error");
      updateProgress(data.progress || 1, data.error || "Error — check backend log");
      document.getElementById("stopBtn").style.display = "none";
      document.getElementById("runBtn").disabled = false;
    }
  } catch (e) {
    console.error("Poll:", e);
    showToast("Could not read review status. Backend may have restarted.", "error");
  }
}

async function fetchResults() {
  try {
    const res  = await apiFetch(`${API}/results/${state.sessionId}`);
    if (!res.ok) {
      const data = await safeJson(res);
      showToast(data.detail || "Results not ready.", "error");
      return;
    }
    const data = await res.json();
    state.results = data;
    renderAgentCards(data.agent_results);
    renderSuggestionGate(data.meta_review?.specific_recommendations || []);
    renderReport(data);
    if (data.report_ready) document.getElementById("downloadBtn").style.display = "inline-flex";
  } catch { showToast("Could not fetch results.", "error"); }
}

async function fetchPartialResults(currentAgent = "") {
  try {
    const res = await apiFetch(`${API}/partial-results/${state.sessionId}`);
    if (!res.ok) return;
    const data = await res.json();
    renderLiveAgentCards(data.agent_results || [], currentAgent || data.current_agent);
  } catch (e) { console.error("Partial results:", e); }
}

async function safeJson(res) {
  try { return await res.json(); }
  catch { return {}; }
}

// ─── PROGRESS ─────────────────────────────────────────────────────────────────
function updateProgress(pct, label) {
  document.getElementById("progressBar").style.width   = `${pct}%`;
  document.getElementById("progressPct").textContent   = `${pct}%`;
  document.getElementById("progressLabel").textContent = label;
}

const AGENTS = [
  { key: "TitleAbstractKeywordsReviewer", label: "Title/Abstract" },
  { key: "StructureReviewer",             label: "Structure"       },
  { key: "MethodologyReviewer",           label: "Methodology"     },
  { key: "StatisticsReviewer",            label: "Statistics"      },
  { key: "FiguresTablesEquationsReviewer",label: "Figs/Tables/Eq"  },
  { key: "ResultsReviewer",               label: "Results"         },
  { key: "DiscussionConclusionsReviewer", label: "Discussion"      },
  { key: "WritingReviewer",               label: "Writing"         },
  { key: "ReferencesReviewer",            label: "References"      },
  { key: "EthicsLimitationsReviewer",     label: "Ethics"          },
  { key: "MetaReviewer",                  label: "MetaReview"      },
];

function renderPipelineChips() {
  const c = document.getElementById("agentPipeline");
  c.innerHTML = "";
  AGENTS.forEach(a => {
    const chip = document.createElement("span");
    chip.className   = "p-chip";
    chip.id          = `chip-${a.key}`;
    chip.textContent = a.label;
    c.appendChild(chip);
  });
}

function updatePipelineChips(current, done) {
  AGENTS.forEach((a, i) => {
    const chip = document.getElementById(`chip-${a.key}`);
    if (!chip) return;
    chip.className = i < done ? "p-chip done"
                   : a.key === current ? "p-chip running"
                   : "p-chip";
  });
}

// ─── AGENT CARDS ──────────────────────────────────────────────────────────────
function renderAgentCards(agents) {
  const grid = document.getElementById("agentsGrid");
  if (!agents?.length) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-icon">🤖</div><p>No results yet</p></div>`;
    return;
  }
  agents.forEach(a => {
    if (a.agent_name === "MetaReviewer") return;
    _upsertCard(grid, a.agent_name, buildCard(a));
  });
}

function renderLiveAgentCards(doneAgents = [], currentAgent = "") {
  const doneByName = new Map((doneAgents || []).map(a => [a.agent_name, a]));
  const grid = document.getElementById("agentsGrid");
  // First pass: ensure all agent slots exist in order
  if (!grid.children.length || grid.querySelector(".empty-state")) {
    grid.innerHTML = "";
    AGENTS.filter(a => a.key !== "MetaReviewer").forEach(a => {
      grid.appendChild(buildPendingCard(a, false));
    });
  }
  // Second pass: update only changed cards (preserves expanded state)
  AGENTS.filter(a => a.key !== "MetaReviewer").forEach(a => {
    const result = doneByName.get(a.key);
    const existing = grid.querySelector(`[data-agent="${a.key}"]`);
    const running  = a.key === currentAgent;
    if (result) {
      if (!existing || existing.dataset.done !== "1") {
        _upsertCard(grid, a.key, buildCard(result));
      }
    } else {
      if (!existing || existing.dataset.done === "1") {
        _upsertCard(grid, a.key, buildPendingCard(a, running));
      } else if (running !== (existing.dataset.running === "1")) {
        _upsertCard(grid, a.key, buildPendingCard(a, running));
      }
    }
  });
}

function _upsertCard(grid, agentKey, newCard) {
  const existing = grid.querySelector(`[data-agent="${agentKey}"]`);
  if (existing) {
    existing.replaceWith(newCard);
  } else {
    grid.appendChild(newCard);
  }
}

function buildPendingCard(a, running) {
  const card = document.createElement("div");
  card.className = `agent-card ${running ? "agent-running" : "agent-pending"}`;
  card.dataset.agent   = a.key;
  card.dataset.done    = "0";
  card.dataset.running = running ? "1" : "0";
  card.innerHTML = `
    <div class="agent-card-header">
      <div>
        <div class="agent-title">${AGENT_LABELS[a.key] || a.label}</div>
        <div class="agent-scope">${running ? "Running now" : "Waiting"}</div>
      </div>
      <div class="score-badge ${running ? "gd" : "sk"}">${running ? "Running" : "Pending"}</div>
    </div>
    <div class="agent-card-body">
      <div class="agent-placeholder">${running ? "Analyzing this agent..." : "Result will appear here when finished."}</div>
    </div>`;
  return card;
}

const AGENT_LABELS = {
  "TitleAbstractKeywordsReviewer": "Title / Abstract / Keywords",
  "StructureReviewer":             "Structure",
  "MethodologyReviewer":           "Methodology",
  "StatisticsReviewer":            "Statistics",
  "FiguresTablesEquationsReviewer":"Figures · Tables · Equations",
  "ResultsReviewer":               "Results",
  "DiscussionConclusionsReviewer": "Discussion & Conclusions",
  "WritingReviewer":               "Scientific Writing",
  "ReferencesReviewer":            "References",
  "EthicsLimitationsReviewer":     "Ethics & Limitations",
};

function buildCard(a) {
  const card    = document.createElement("div");
  card.className = "agent-card";
  card.dataset.agent = a.agent_name;
  card.dataset.done  = "1";
  const score   = parseFloat(a.score || 0);
  const sk      = a.skipped || false;
  const cls     = sk ? "sk" : score>=4.5?"ex":score>=3.5?"gd":score>=2.5?"ok":"wk";
  const barW    = sk ? 0 : (score/5)*100;
  const barC    = score>=4?"#22c55e":score>=3?"#2563eb":score>=2?"#f59e0b":"#ef4444";

  card.innerHTML = `
    <div class="agent-card-header">
      <div>
        <div class="agent-title">${AGENT_LABELS[a.agent_name] || a.agent_name}</div>
        <div class="agent-scope">${a.scope || ""}</div>
      </div>
      <div class="score-badge ${cls}">${sk?"Skipped":`${score.toFixed(1)} / 5`}</div>
    </div>
    <div class="agent-card-body">
      ${sk
        ? `<div class="agent-skipped">⊘ ${a.skip_reason || "Skipped"}</div>`
        : `<div class="score-mini-bar">
             <div class="score-mini-track">
               <div class="score-mini-fill" style="width:${barW}%;background:${barC}"></div>
             </div>
           </div>
           ${buildSections(a)}`
      }
    </div>`;
  return card;
}

function buildSections(a) {
  let html = "";
  [
    ["✓ Strengths",       a.strengths || []],
    ["⚠ Weaknesses",      a.weaknesses || []],
    ["● Major Comments",  a.major_comments || []],
    ["→ Recommendations", a.specific_recommendations || []],
  ].forEach(([title, items]) => {
    if (!items.length) return;
    const secId = `sec-${Math.random().toString(36).slice(2)}`;
    html += `<div class="agent-sec-title">${title}</div>`;
    items.slice(0,3).forEach(item => { html += `<div class="agent-item">${escapeHtml(formatItem(item))}</div>`; });
    if (items.length > 3) {
      html += `<div id="${secId}" style="display:none">`;
      items.slice(3).forEach(item => { html += `<div class="agent-item">${escapeHtml(formatItem(item))}</div>`; });
      html += `</div>`;
      html += `<div class="agent-item agent-show-more" onclick="const el=document.getElementById('${secId}');const show=el.style.display==='none';el.style.display=show?'block':'none';this.textContent=show?'▲ Show less':'▼ ${items.length-3} more'" style="color:var(--blue-light);font-size:10px;cursor:pointer;user-select:none">▼ ${items.length-3} more</div>`;
    }
  });
  return html;
}

function formatItem(item) {
  if (item === null || item === undefined) return "";
  if (typeof item === "string") return item;
  if (typeof item === "number" || typeof item === "boolean") return String(item);
  if (Array.isArray(item)) return item.map(formatItem).filter(Boolean).join("; ");
  if (typeof item === "object") {
    const preferred = ["comment", "issue", "recommendation", "text", "description", "finding", "weakness", "strength"];
    for (const key of preferred) {
      if (item[key]) {
        const prefix = item.criterion || item.section || "";
        const body = formatItem(item[key]);
        return prefix ? `${prefix}: ${body}` : body;
      }
    }
    return Object.entries(item)
      .map(([key, value]) => `${key}: ${formatItem(value)}`)
      .filter(Boolean)
      .join("; ");
  }
  return String(item);
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// ─── REPORT ───────────────────────────────────────────────────────────────────
function renderReport(data) {
  const el      = document.getElementById("reportContent");
  const meta    = data.meta_review || {};
  const dec     = meta.editorial_decision || "N/A";
  const score   = parseFloat(meta.final_weighted_score || 0);
  const conf    = parseFloat(meta.overall_confidence || 0);
  const synth   = meta.llm_synthesis || {};
  const elapsed = data.elapsed_sec || 0;
  const decCls  = {Accept:"accept","Minor Revision":"minor","Major Revision":"major",Reject:"reject"}[dec]||"minor";

  const mm = Math.floor(elapsed/60).toString().padStart(2,"0");
  const ss = (elapsed%60).toString().padStart(2,"0");
  const timeStr = elapsed > 0 ? `${mm}:${ss}` : "—";

  el.innerHTML = `
    ${data.stopped_early ? `<div class="ai-notice">⚠ <strong>Partial Review:</strong> Stopped early — results from completed agents only.</div>` : ""}
    <div class="ai-notice">⚠ <strong>AI-Assisted Review Notice:</strong> Generated by ${data.model_used||"phi3:mini"} running locally. All findings must be validated by a qualified domain expert. Rubrics: Elsevier, IEEE, Emerald Q1 standards.</div>

    <div class="decision-card ${decCls}">
      <div>
        <span class="decision-verdict ${decCls}">${dec}</span>
        <div class="decision-score">Weighted Score: <strong>${score.toFixed(2)} / 5.0</strong></div>
        ${synth.decision_rationale?`<div style="font-size:11.5px;color:var(--text-muted);margin-top:8px;max-width:500px;line-height:1.6">${synth.decision_rationale}</div>`:""}
      </div>
      <div class="decision-meta">
        <div class="decision-conf-label">Confidence</div>
        <div class="decision-conf-val">${(conf*100).toFixed(0)}%</div>
        <div class="decision-info">${data.mode?.toUpperCase()} · ${data.model_used}</div>
        <div class="decision-elapsed">⏱ ${timeStr} total</div>
      </div>
    </div>

    ${synth.executive_summary?`<div class="comments-block"><div class="comments-heading">Executive Summary</div><div class="comment-row">${synth.executive_summary}</div></div>`:""}

    <div class="score-table-wrap">
      <table class="score-table">
        <thead><tr><th>Criterion (Q1 Rubric)</th><th>Score</th><th>Rating</th><th>Visual</th><th>Weight</th></tr></thead>
        <tbody>${buildScoreRows(meta.score_table||{})}</tbody>
      </table>
    </div>

    ${buildComments("Major Comments", meta.major_comments||[], "major", "Must be addressed before acceptance.")}
    ${buildComments("Minor Comments", meta.minor_comments||[], "minor", "Suggestions to improve quality.")}
    ${buildComments("Specific Recommendations", meta.specific_recommendations||[], "rec", "Actionable revision steps.")}
    ${buildComments("Manuscript Strengths", meta.all_strengths||[], "rec", "")}
  `;
}

const WEIGHTS = {
  "Originality & Novelty":"8%","Manuscript Structure":"8%",
  "Methodology & Equations":"20%","Statistical Analysis":"12%",
  "Results & Evidence":"15%","Discussion & Conclusions":"10%",
  "Figures & Tables":"8%","Scientific Writing":"8%",
  "References & Citations":"7%","Ethics & Transparency":"4%",
};

function buildScoreRows(table) {
  return Object.entries(table).map(([crit, score]) => {
    const s  = parseFloat(score);
    const sk = s === 0;
    const lb = sk?"Skipped":s>=4.5?"Excellent":s>=3.5?"Good":s>=2.5?"Acceptable":s>=1.5?"Weak":"Very Weak";
    const bar = sk?"—":"■".repeat(Math.round(s))+"□".repeat(5-Math.round(s));
    return `<tr>
      <td>${crit}</td>
      <td><span class="score-num">${sk?"—":s.toFixed(1)}</span></td>
      <td style="font-size:11.5px;color:var(--text-muted)">${lb}</td>
      <td><span class="score-bar-str">${bar}</span></td>
      <td style="font-size:10.5px;color:var(--text-muted);font-family:var(--font-mono)">${WEIGHTS[crit]||""}</td>
    </tr>`;
  }).join("");
}

function buildComments(title, items, type, sub) {
  if (!items?.length) return "";
  return `<div class="comments-block">
    <div class="comments-heading">${title}</div>
    ${sub?`<p style="font-size:12px;color:var(--text-muted);margin-bottom:12px">${sub}</p>`:""}
    ${items.map((item,i)=>`<div class="comment-row ${type}"><div class="comment-num">[${i+1}]</div>${escapeHtml(formatItem(item))}</div>`).join("")}
  </div>`;
}

function renderSuggestionGate(recommendations) {
  const gate = document.getElementById("suggestionGate");
  state.suggestionDecisions = {};
  if (!recommendations?.length) {
    gate.style.display = "none";
    return;
  }
  gate.style.display = "block";
  gate.innerHTML = `
    <div class="suggestion-header">
      <div class="comments-heading">Review Suggestions</div>
      <div class="suggestion-bulk">
        <button class="btn-sm active" onclick="setBulkDecision('accepted')">✓ Accept All</button>
        <button class="btn-sm" onclick="setBulkDecision('rejected')">✕ Reject All</button>
      </div>
    </div>
    <p class="suggestion-help">Accept or reject each suggestion before downloading the PDF report.</p>
    ${recommendations.map((item, i) => `
      <div class="suggestion-row" data-suggestion="${i}">
        <div class="suggestion-text">${escapeHtml(formatItem(item))}</div>
        <div class="suggestion-actions">
          <button class="btn-sm" onclick="setSuggestionDecision(${i}, 'accepted')">Accept</button>
          <button class="btn-sm" onclick="setSuggestionDecision(${i}, 'rejected')">Reject</button>
        </div>
      </div>
    `).join("")}`;
}

function setBulkDecision(decision) {
  document.querySelectorAll(".suggestion-row").forEach(row => {
    setSuggestionDecision(parseInt(row.dataset.suggestion), decision);
  });
  const expected = decision === "accepted" ? "accept all" : "reject all";
  document.querySelectorAll(".suggestion-bulk .btn-sm").forEach(btn => {
    btn.classList.toggle("active", btn.textContent.trim().toLowerCase().includes(expected.split(" ")[0]));
  });
}

function setSuggestionDecision(index, decision) {
  state.suggestionDecisions[index] = decision;
  const row = document.querySelector(`[data-suggestion="${index}"]`);
  if (!row) return;
  row.classList.remove("accepted", "rejected");
  row.classList.add(decision);
  row.querySelectorAll("button").forEach(btn => {
    const expected = decision === "accepted" ? "accept" : "reject";
    btn.classList.toggle("active", btn.textContent.trim().toLowerCase() === expected);
  });
}

function suggestionsResolved() {
  const rows = document.querySelectorAll(".suggestion-row");
  if (!rows.length) return true;
  return Array.from(rows).every(row => state.suggestionDecisions[row.dataset.suggestion]);
}

// ─── DOWNLOAD ─────────────────────────────────────────────────────────────────
async function downloadReport() {
  if (!state.sessionId) return;
  if (!suggestionsResolved()) {
    showToast("Accept or reject all suggestions before downloading.", "error");
    showPanel("report");
    return;
  }
  try {
    const res = await apiFetch(`${API}/download-report/${state.sessionId}`);
    if (!res.ok) { showToast("Report not ready.", "error"); return; }
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url;
    a.download = `CHVN_Review_${state.filename?.replace(".pdf","") || "paper"}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("Report downloaded. ✓", "success");
  } catch { showToast("Download failed.", "error"); }
}

// ─── HISTORY ─────────────────────────────────────────────────────────────────
async function loadHistory() {
  const box = document.getElementById("historyContent");
  if (!box) return;
  try {
    const res = await apiFetch(`${API}/history`);
    if (!res.ok) throw new Error("history failed");
    const data = await res.json();
    renderHistory(data.history || []);
  } catch {
    box.innerHTML = `<div class="empty-state"><div class="empty-icon">🕘</div><p>Could not load history</p></div>`;
  }
}

function renderHistory(items) {
  const box = document.getElementById("historyContent");
  if (!items.length) {
    box.innerHTML = `<div class="empty-state"><div class="empty-icon">🕘</div><p>No completed reviews yet</p></div>`;
    return;
  }
  const completed = items.filter(item => !item.stopped_early).length;
  const avgScore = items.reduce((sum, item) => sum + parseFloat(item.final_weighted_score || 0), 0) / items.length;
  const last = items[0];
  box.innerHTML = `
  <div class="history-summary">
    <div class="history-stat">
      <div class="history-stat-label">Reviews</div>
      <div class="history-stat-value">${items.length}</div>
    </div>
    <div class="history-stat">
      <div class="history-stat-label">Completed</div>
      <div class="history-stat-value">${completed}</div>
    </div>
    <div class="history-stat">
      <div class="history-stat-label">Average Score</div>
      <div class="history-stat-value">${avgScore ? avgScore.toFixed(2) : "—"}</div>
    </div>
    <div class="history-stat wide">
      <div class="history-stat-label">Latest</div>
      <div class="history-stat-title">${escapeHtml(last.title || last.filename || "Untitled paper")}</div>
    </div>
  </div>
  <div class="history-table-wrap">
    <div class="history-table-head">
      <span>Paper</span><span>Mode</span><span>Decision</span><span>Score</span><span>Time</span><span>Report</span><span></span>
    </div>
    ${items.map(item => {
      const score = parseFloat(item.final_weighted_score || 0);
      const date = item.created_at ? new Date(item.created_at).toLocaleString() : "—";
      const elapsed = formatElapsed(item.elapsed_sec || 0);
      const title = escapeHtml(item.title || item.filename || "Untitled paper");
      const file = escapeHtml(item.filename || "");
      const decision = escapeHtml(item.editorial_decision || "N/A");
      const mode = escapeHtml((item.mode || "fast").toUpperCase());
      const model = escapeHtml(item.model_used || "");
      const decisionClass = decision.toLowerCase().includes("minor") ? "minor"
        : decision.toLowerCase().includes("major") ? "major"
        : decision.toLowerCase().includes("reject") ? "reject"
        : decision.toLowerCase().includes("accept") ? "accept"
        : "minor";
      return `<div class="history-row">
        <div class="history-paper">
          <div class="history-title">${title}</div>
          <div class="history-file">${file}</div>
          <div class="history-meta"><span>${date}</span><span>${model}</span>${item.stopped_early ? "<span>Partial</span>" : ""}</div>
        </div>
        <div><span class="history-mode">${mode}</span></div>
        <div><span class="decision-pill ${decisionClass}">${decision}</span></div>
        <div class="history-score">
          <span>${score ? score.toFixed(2) : "—"}</span>
          <div class="history-score-track"><div class="history-score-fill" style="width:${Math.max(0, Math.min(100, (score/5)*100))}%"></div></div>
        </div>
        <div class="history-time">${elapsed}</div>
        <button class="btn-download" ${item.report_ready ? "" : "disabled"} onclick="downloadHistoryReport('${item.id}')">PDF</button>
        <button class="btn-download" style="background: #f59e0b; box-shadow: 0 3px 14px #f59e0b40;" title="Load and use Author Mode" onclick="loadHistoryForAuthorMode('${item.id}')">✍️ Author</button>
        <button class="btn-delete-history" title="Delete from history" onclick="deleteHistoryItem('${item.id}', this)">✕</button>
      </div>`;
    }).join("")}
  </div>`;
}

function formatElapsed(sec) {
  if (!sec) return "—";
  const m = Math.floor(sec / 60).toString().padStart(2, "0");
  const s = (sec % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

async function loadHistoryForAuthorMode(sessionId) {
  // Carga una revisión pasada y activa Modo Autor
  state.sessionId = sessionId;
  localStorage.setItem("lastSessionId", sessionId);
  showPanel("author");
  showToast("Revisión cargada. Haz click en 'Generar Sugerencias'", "info");
}

async function downloadHistoryReport(id) {
  try {
    const res = await apiFetch(`${API}/history/${id}/download`);
    if (!res.ok) { showToast("History report not found.", "error"); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `CHVN_Review_${id.slice(0,8)}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    showToast("Download failed.", "error");
  }
}

async function deleteHistoryItem(id, btn) {
  btn.disabled = true;
  try {
    const res = await apiFetch(`${API}/history/${id}`, { method: "DELETE" });
    if (!res.ok) { showToast("Could not delete record.", "error"); btn.disabled = false; return; }
    const row = btn.closest(".history-row");
    row.style.transition = "opacity 0.2s";
    row.style.opacity = "0";
    setTimeout(() => { row.remove(); }, 200);
    showToast("Record deleted.", "info");
  } catch {
    showToast("Delete failed.", "error");
    btn.disabled = false;
  }
}

// ─── CLEAR ────────────────────────────────────────────────────────────────────
async function clearSession() {
  if (state.sessionId) {
    try { await apiFetch(`${API}/session/${state.sessionId}`, { method: "DELETE" }); } catch {}
  }
  if (state.polling) clearInterval(state.polling);
  stopTimer();
  if (authorPolling) { clearInterval(authorPolling); authorPolling = null; }
  state = { sessionId:null, filename:null, uploadData:null, polling:null, timerInterval:null, results:null, suggestionDecisions:{} };
  clearFile();
  document.getElementById("agentsGrid").innerHTML    = `<div class="empty-state"><div class="empty-icon">🤖</div><p>Run a review to see agent results</p></div>`;
  document.getElementById("reportContent").innerHTML = `<div class="empty-state"><div class="empty-icon">📊</div><p>Complete a review to generate the report</p></div>`;
  document.getElementById("authorContent").innerHTML = `<div class="empty-state"><div class="empty-icon">✍️</div><p>Completa una revisión y haz clic en <strong>Generar Sugerencias</strong><br>para obtener instrucciones de mejora y código LaTeX por sección.</p></div>`;
  document.getElementById("authorProgress").style.display = "none";
  document.getElementById("authorRunBtn").disabled = false;
  document.getElementById("authorRunBtn").textContent = "▶ Generar Sugerencias";
  const navAuthor = document.getElementById("navAuthor");
  if (navAuthor) { navAuthor.disabled = true; navAuthor.title = "Completa una revisión primero"; }
  document.getElementById("suggestionGate").style.display = "none";
  document.getElementById("downloadBtn").style.display   = "none";
  document.getElementById("newReviewBtn").style.display  = "none";
  document.getElementById("sidebarSession").style.display = "none";
  document.getElementById("stopBtn").style.display       = "none";
  document.getElementById("runBtn").disabled = false;
  document.getElementById("timerDisplay").textContent = "00:00";
  showToast("Session cleared.", "info");
  showPanel("upload");
}

// ─── SIDEBAR ──────────────────────────────────────────────────────────────────
function updateSidebar(data) {
  document.getElementById("sidebarSession").style.display = "block";
  document.getElementById("sidebarFilename").textContent  = data.filename;
  document.getElementById("sidebarMeta").textContent =
    `${data.word_count?.toLocaleString()} words · ${data.size_mb} MB`;
  const bc = document.getElementById("sidebarBadges");
  bc.innerHTML = `<span class="badge-mini">${data.format_detected}</span>`;
  if (data.has_statistics) bc.innerHTML += `<span class="badge-mini">📊 Stats</span>`;
  if (data.has_equations)  bc.innerHTML += `<span class="badge-mini">∑ ×${data.equation_count}</span>`;
  if (data.has_figures)    bc.innerHTML += `<span class="badge-mini">📈 ×${data.figure_count}</span>`;
  if (data.has_tables)     bc.innerHTML += `<span class="badge-mini">📋 ×${data.table_count}</span>`;
}

// ─── CONFIG ───────────────────────────────────────────────────────────────────
async function loadConfig() {
  try {
    const res = await apiFetch(`${API}/config`);
    const cfg = await res.json();
    if (cfg.model)          document.getElementById("cfgModel").value   = cfg.model;
    if (cfg.ollama_url)     document.getElementById("cfgUrl").value     = cfg.ollama_url;
    const setSlider = (id, valId, val) => {
      if (val !== undefined) {
        document.getElementById(id).value             = val;
        document.getElementById(valId).textContent    = val;
      }
    };
    setSlider("cfgTemp",   "tempVal",   cfg.temperature);
    setSlider("cfgTopP",   "topPVal",   cfg.top_p);
    setSlider("cfgTokens", "tokensVal", cfg.max_tokens);
    setSlider("cfgCtx",    "ctxVal",    cfg.context_length);
  } catch {}
}

async function saveConfig() {
  const cfg = {
    model:          document.getElementById("cfgModel").value.trim(),
    ollama_url:     document.getElementById("cfgUrl").value.trim(),
    temperature:    parseFloat(document.getElementById("cfgTemp").value),
    top_p:          parseFloat(document.getElementById("cfgTopP").value),
    max_tokens:     parseInt(document.getElementById("cfgTokens").value),
    context_length: parseInt(document.getElementById("cfgCtx").value),
  };
  try {
    const res = await apiFetch(`${API}/config`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
    });
    if (res.ok) {
      document.getElementById("configStatus").textContent = "✓ Saved";
      setTimeout(() => document.getElementById("configStatus").textContent = "", 3000);
      showToast(`Config saved — ${cfg.model}`, "success");
      checkHealth(); loadAvailableModels();
    }
  } catch { showToast("Failed to save.", "error"); }
}

function resetConfig() {
  const set = (id, vid, val) => {
    document.getElementById(id).value           = val;
    if (vid) document.getElementById(vid).textContent = val;
  };
  set("cfgModel", null, "llama3.2");
  set("cfgUrl",   null, "http://localhost:11434");
  set("cfgTemp",   "tempVal",   0.2);
  set("cfgTopP",   "topPVal",   0.9);
  set("cfgTokens", "tokensVal", 4096);
  set("cfgCtx",    "ctxVal",    49152);
  saveConfig();
}

// ─── TOASTS ───────────────────────────────────────────────────────────────────
// ─── MODO AUTOR ───────────────────────────────────────────────────────────────

let authorPolling = null;

function enableAuthorTab() {
  const btn = document.getElementById("navAuthor");
  if (btn) { btn.disabled = false; btn.title = ""; }
}

async function startAuthorMode() {
  if (!state.sessionId) { showToast("No hay sesión activa.", "error"); return; }

  const runBtn = document.getElementById("authorRunBtn");
  runBtn.disabled = true;
  runBtn.textContent = "⏳ Generando...";

  document.getElementById("authorProgress").style.display = "block";
  document.getElementById("authorContent").innerHTML =
    `<div class="empty-state"><div class="empty-icon">✍️</div><p>Analizando secciones…</p></div>`;

  try {
    const res = await apiFetch(`${API}/author-mode/${state.sessionId}`, { method: "POST" });
    if (!res.ok) {
      const data = await safeJson(res);
      showToast(data.detail || "Error al iniciar Modo Autor.", "error");
      runBtn.disabled = false;
      runBtn.textContent = "▶ Generar Sugerencias";
      return;
    }
    showToast("Generando sugerencias LaTeX por sección…", "info");
    pollAuthorMode();
  } catch {
    showToast("Error de conexión.", "error");
    runBtn.disabled = false;
    runBtn.textContent = "▶ Generar Sugerencias";
  }
}

function pollAuthorMode() {
  if (authorPolling) clearInterval(authorPolling);
  authorPolling = setInterval(async () => {
    if (!state.sessionId) { clearInterval(authorPolling); return; }
    try {
      const res  = await apiFetch(`${API}/author-mode/${state.sessionId}`);
      if (!res.ok) return;
      const data = await res.json();

      const pct = data.progress || 0;
      document.getElementById("authorProgressBar").style.width = `${pct}%`;
      document.getElementById("authorProgressPct").textContent = `${pct}%`;
      document.getElementById("authorProgressLabel").textContent =
        data.current ? `Procesando: ${AGENT_LABELS[data.current] || data.current}` : "Procesando…";

      if (data.results?.length) renderAuthorPartial(data.results);

      if (data.status === "completed") {
        clearInterval(authorPolling);
        document.getElementById("authorProgress").style.display = "none";
        const runBtn = document.getElementById("authorRunBtn");
        runBtn.disabled = false;
        runBtn.textContent = "↻ Regenerar";
        renderAuthorResults(data.results, data.publisher, data.paper_type);
        showToast("¡Sugerencias LaTeX listas! ✓", "success");
      } else if (data.status === "error") {
        clearInterval(authorPolling);
        document.getElementById("authorProgress").style.display = "none";
        showToast(`Error: ${data.error}`, "error");
        document.getElementById("authorRunBtn").disabled = false;
        document.getElementById("authorRunBtn").textContent = "▶ Generar Sugerencias";
      }
    } catch (e) { console.error("AuthorMode poll:", e); }
  }, 2500);
}

function renderAuthorPartial(results) {
  const box = document.getElementById("authorContent");
  const done = results.length;
  box.innerHTML = `<div style="font-size:12px;color:var(--text-muted);margin-bottom:16px">
    ${done} sección${done !== 1 ? "es" : ""} procesada${done !== 1 ? "s" : ""}…
  </div>` + renderAuthorCards(results, false);
}

function renderAuthorResults(results, publisher, paperType) {
  const PUB_NAMES = {
    ieee:"IEEE", elsevier:"Elsevier / ScienceDirect", mdpi:"MDPI",
    emerald:"Emerald", sage:"SAGE", taylor:"Taylor & Francis"
  };
  const pubLabel = publisher ? PUB_NAMES[publisher] || publisher.toUpperCase() : "General";
  const typeLabel = paperType ? ` · ${paperType.replace(/_/g," ")}` : "";
  const badge = `<div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;padding:10px 16px;
    background:var(--blue-glow);border:1px solid var(--blue-light);border-radius:10px;">
    <span style="font-size:13px;color:var(--blue-light);font-weight:700">📋 Editorial:</span>
    <span style="font-size:13px;color:var(--text);font-weight:600">${pubLabel}${typeLabel}</span>
    <span style="font-size:11px;color:var(--text-muted);margin-left:auto">Sugerencias ajustadas al estilo y formato de esta editorial</span>
  </div>`;
  document.getElementById("authorContent").innerHTML = badge + renderAuthorCards(results, true);
  const firstBad = document.querySelector(".author-card:not(.no-issues)");
  if (firstBad) firstBad.classList.add("open");
}

function renderAuthorCards(results, final) {
  if (!results?.length) return `<div class="empty-state"><div class="empty-icon">✍️</div><p>Sin resultados aún.</p></div>`;

  return `<div class="author-grid">` +
    results.map((r, idx) => {
      const score = parseFloat(r.score || 0);
      const pillCls = r.skipped ? "sk" : score >= 4 ? "ok" : score >= 3 ? "med" : score >= 2 ? "low" : "bad";
      const pillTxt = r.skipped ? "Omitida" : `${score.toFixed(1)} / 5`;
      const noIssues = !r.issues?.length && !r.skipped;
      const hasLatex = !!r.latex_code;

      const issuesHtml = (r.issues || []).map(iss =>
        `<div class="author-issue-item">${escapeHtml(iss)}</div>`
      ).join("");

      const latexHtml = hasLatex ? `
        <div class="author-latex-block">
          <div class="author-latex-header">
            <span class="author-latex-label">📄 Sugerencia LaTeX</span>
            <button class="btn-copy-latex" onclick="copyLatex(this, 'latex-${idx}')">Copiar</button>
          </div>
          <pre class="author-latex-code" id="latex-${idx}">${escapeHtml(r.latex_code)}</pre>
        </div>` : "";

      const instructionHtml = r.instruction ? `
        <div class="author-instruction-block">
          <div class="author-instruction-label">💡 Qué hacer</div>
          <div class="author-instruction-text">${escapeHtml(r.instruction)}</div>
        </div>` : "";

      return `
        <div class="author-card${noIssues ? " no-issues" : ""}" id="author-card-${idx}">
          <div class="author-card-header" onclick="toggleAuthorCard(${idx})">
            <div>
              <div class="author-section-name">${escapeHtml(r.section_label)}</div>
              <div class="author-section-score">${(r.issues || []).length} problema${(r.issues || []).length !== 1 ? "s" : ""} encontrado${(r.issues || []).length !== 1 ? "s" : ""}</div>
            </div>
            <div style="display:flex;align-items:center;gap:10px">
              <span class="author-score-pill ${pillCls}">${pillTxt}</span>
              <span class="author-chevron">▼</span>
            </div>
          </div>
          <div class="author-card-body">
            ${r.skipped
              ? `<div class="author-empty-note">Esta sección fue omitida en la revisión.</div>`
              : noIssues
              ? `<div class="author-empty-note">✓ Sin problemas detectados en esta sección.</div>`
              : `
                <div class="author-issues-label">Problemas encontrados</div>
                ${issuesHtml}
                ${instructionHtml}
                ${latexHtml}
              `
            }
          </div>
        </div>`;
    }).join("") +
  `</div>`;
}

function toggleAuthorCard(idx) {
  const card = document.getElementById(`author-card-${idx}`);
  if (card) card.classList.toggle("open");
}

function copyLatex(btn, id) {
  const pre = document.getElementById(id);
  if (!pre) return;
  navigator.clipboard.writeText(pre.textContent).then(() => {
    btn.textContent = "✓ Copiado";
    btn.classList.add("copied");
    setTimeout(() => { btn.textContent = "Copiar"; btn.classList.remove("copied"); }, 2000);
  }).catch(() => showToast("No se pudo copiar.", "error"));
}

// ─── TOASTS ───────────────────────────────────────────────────────────────────
function showToast(msg, type = "info") {
  const c = document.getElementById("toastContainer");
  const t = document.createElement("div");
  t.className   = `toast ${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 4500);
}
