// ── Config ────────────────────────────────────────────────────────────────
const API = "";  // mismo origen
let SESSION_TOKEN = localStorage.getItem("cert_token") || "";
let SESSION_USER  = JSON.parse(localStorage.getItem("cert_user") || "null");

// Estado actual del detalle abierto
let currentCertId  = null;
let currentCertData = null;
let pendingStageNum = null;
let certTypesList   = [];

// ── Helpers de fetch ──────────────────────────────────────────────────────
async function api(method, path, body = null) {
  const opts = {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Session-Token": SESSION_TOKEN,
    },
  };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(API + path, opts);
  if (r.status === 401) { doLogout(); return null; }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Error ${r.status}`);
  return data;
}

async function apiForm(path, formData) {
  const r = await fetch(API + path, {
    method: "POST",
    headers: { "X-Session-Token": SESSION_TOKEN },
    body: formData,
  });
  if (r.status === 401) { doLogout(); return null; }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Error ${r.status}`);
  return data;
}

// ── Toast ─────────────────────────────────────────────────────────────────
function toast(msg, type = "info") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById("toast-container").appendChild(el);
  requestAnimationFrame(() => { el.classList.add("show"); });
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, 3500);
}

// ── Vistas ────────────────────────────────────────────────────────────────
function showView(id) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById(id).classList.add("active");
}

// ── Auth ──────────────────────────────────────────────────────────────────
async function doLogin() {
  const btn = document.getElementById("login-btn");
  const err = document.getElementById("login-error");
  const user = document.getElementById("login-user").value.trim();
  const pass = document.getElementById("login-pass").value;
  err.textContent = "";
  if (!user || !pass) { err.textContent = "Completa los campos."; return; }
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';
  try {
    const data = await fetch(API + "/cert/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: user, password: pass }),
    });
    const json = await data.json();
    if (!data.ok) { err.textContent = json.detail || "Error de autenticación."; return; }
    SESSION_TOKEN = json.token;
    SESSION_USER  = json;
    localStorage.setItem("cert_token", SESSION_TOKEN);
    localStorage.setItem("cert_user", JSON.stringify(json));
    initApp();
  } catch (e) {
    err.textContent = "No se pudo conectar al servidor.";
  } finally {
    btn.disabled = false;
    btn.textContent = "Iniciar sesión";
  }
}

function doLogout() {
  fetch(API + "/cert/auth/logout", {
    method: "POST",
    headers: { "X-Session-Token": SESSION_TOKEN },
  }).catch(() => {});
  SESSION_TOKEN = "";
  SESSION_USER = null;
  localStorage.removeItem("cert_token");
  localStorage.removeItem("cert_user");
  showView("view-login");
}

// ── Inicialización ────────────────────────────────────────────────────────
function initApp() {
  if (!SESSION_TOKEN) { showView("view-login"); return; }
  document.getElementById("topbar-username").textContent =
    SESSION_USER?.full_name || SESSION_USER?.username || "Usuario";
  showView("view-app");
  loadStats();
  loadCertificates();
  loadAlerts();
}

// ── Stats ─────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const d = await api("GET", "/cert/stats");
    if (!d) return;
    document.getElementById("stat-active").textContent    = d.total_active;
    document.getElementById("stat-overdue").textContent   = d.overdue;
    document.getElementById("stat-completed").textContent = d.completed_month;
    document.getElementById("stat-total").textContent     = d.total_all;
  } catch (e) { /* silencioso */ }
}

// ── Alertas ───────────────────────────────────────────────────────────────
async function loadAlerts() {
  try {
    const d = await api("GET", "/cert/alerts");
    if (!d || d.count === 0) {
      document.getElementById("alert-banner").style.display = "none";
      return;
    }
    const banner = document.getElementById("alert-banner");
    const title  = document.getElementById("alert-banner-title");
    const items  = document.getElementById("alert-banner-items");

    banner.style.display = "block";
    const hasOverdue = d.alerts.some(a => a.alert.level === "overdue");
    banner.classList.toggle("has-warnings", !hasOverdue);
    title.className = "alert-banner-title" + (hasOverdue ? "" : " warning");
    title.textContent = hasOverdue
      ? `🔴 ${d.count} certificado(s) VENCIDO(S)`
      : `⚠️ ${d.count} certificado(s) requieren atención`;

    items.innerHTML = d.alerts.map(a => `
      <div class="alert-item" onclick="openDetail('${a.cert_id}')">
        <strong>${a.tracking_code}</strong>
        <span>${a.student_name.split(" ").slice(0,2).join(" ")}</span>
        <span>${a.alert.message}</span>
      </div>
    `).join("");
  } catch (e) { /* silencioso */ }
}

// ── Tabla de certificados ─────────────────────────────────────────────────
async function loadCertificates() {
  const filter = document.getElementById("filter-status").value;
  const tbody  = document.getElementById("cert-table-body");
  tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text2);">Cargando…</td></tr>`;

  try {
    const url = filter ? `/cert/certificates?status=${filter}` : "/cert/certificates";
    const d   = await api("GET", url);
    if (!d) return;

    if (d.certificates.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7">
        <div class="empty-state">
          <div class="icon">📋</div>
          <h3>Sin certificados</h3>
          <p>Crea una nueva solicitud con el botón "Nueva solicitud"</p>
        </div>
      </td></tr>`;
      return;
    }

    tbody.innerHTML = d.certificates.map(c => {
      const alert   = c.alert || {};
      const stage   = STAGE_NAMES[c.current_stage] || "—";
      const types   = (c.certificate_types || []).slice(0,2).join(", ");
      const created = formatDate(c.created_at);
      const prog    = Math.round(((c.current_stage - 1) / 8) * 100);
      const badgeClass = alertBadgeClass(alert.level, c.status);
      const badgeText  = alertBadgeText(alert.level, c.status, alert.message);

      return `<tr onclick="openDetail('${c.id}')">
        <td><code style="font-family:var(--font-mono,monospace);font-size:0.8rem;">${c.tracking_code}</code></td>
        <td class="td-name">${escHtml(c.student_name)}</td>
        <td style="max-width:150px;overflow:hidden;text-overflow:ellipsis;">${escHtml(types)}</td>
        <td>
          <div style="font-size:0.8rem;margin-bottom:0.3rem;">${c.status==='completed'?'✅ Completado':escHtml(stage)}</div>
          <div class="progress-bar"><div class="progress-fill ${progColor(alert.level)}" style="width:${c.status==='completed'?100:prog}%"></div></div>
        </td>
        <td>${alert.days_remaining != null ? `<span style="color:${daysColor(alert.days_remaining)};">${alert.days_remaining} día(s) hábil(es)</span>` : '—'}</td>
        <td><span class="badge ${badgeClass}">${badgeText}</span></td>
        <td style="color:var(--text2);">${created}</td>
      </tr>`;
    }).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" style="color:var(--red);text-align:center;">${e.message}</td></tr>`;
  }
}

const STAGE_NAMES = {
  1: "Solicitud recibida",
  2: "Polígrafo enviado",
  3: "Comprobante de pago recibido",
  4: "Certificado elaborado → Sec. División",
  5: "Firmado en Sec. División",
  6: "Firmado en Sec. General",
  7: "Recibido de Sec. División",
  8: "Enviado al estudiante",
};

function alertBadgeClass(level, status) {
  if (status === "completed") return "badge-completed";
  if (status === "cancelled" || status === "cancelled_no_payment") return "badge-info";
  return { ok: "badge-ok", warning: "badge-warning", critical: "badge-critical", overdue: "badge-overdue", info: "badge-info" }[level] || "badge-info";
}
function alertBadgeText(level, status, msg) {
  if (status === "completed") return "✅ Completado";
  if (status === "cancelled_no_payment") return "Sin pago";
  if (status === "cancelled") return "Cancelado";
  if (level === "ok") return "🟢 En tiempo";
  if (level === "warning") return "🟡 Por vencer";
  if (level === "critical") return "🟠 Urgente";
  if (level === "overdue") return "🔴 Vencido";
  return msg || "—";
}
function progColor(level) {
  return { warning: "yellow", critical: "yellow", overdue: "red" }[level] || "";
}
function daysColor(days) {
  if (days <= 0) return "var(--red)";
  if (days <= 1) return "var(--orange)";
  if (days <= 2) return "var(--yellow)";
  return "var(--green)";
}

// ── Detalle de certificado ─────────────────────────────────────────────────
async function openDetail(certId) {
  currentCertId = certId;
  document.getElementById("detail-panel").classList.add("open");
  document.getElementById("dp-stages-list").innerHTML =
    '<div style="text-align:center;padding:2rem;color:var(--text2);"><span class="spinner"></span></div>';
  await refreshDetail();
}

function closeDetail() {
  document.getElementById("detail-panel").classList.remove("open");
  currentCertId  = null;
  currentCertData = null;
}

async function refreshDetail() {
  if (!currentCertId) return;
  try {
    const c = await api("GET", `/cert/certificates/${currentCertId}`);
    if (!c) return;
    currentCertData = c;
    renderDetail(c);
  } catch (e) {
    toast("Error cargando detalle: " + e.message, "error");
  }
}

function renderDetail(c) {
  // Header
  document.getElementById("dp-code").textContent  = c.tracking_code;
  document.getElementById("dp-name").textContent  = c.student_name;
  document.getElementById("dp-student-id").textContent = "Doc: " + c.student_id;
  document.getElementById("dp-email").textContent = c.student_email;
  const phoneEl = document.getElementById("dp-phone");
  if (c.student_phone) {
    phoneEl.textContent = c.student_phone;
    phoneEl.style.display = "";
  } else {
    phoneEl.style.display = "none";
  }

  // Tipos de certificado
  const types = c.certificate_types || [];
  document.getElementById("dp-cert-types").innerHTML =
    `<div class="cert-types">${types.map(t => `<span class="cert-type-chip">${escHtml(t)}</span>`).join("")}</div>`;

  // Badge de estado
  const alert = c.alert || {};
  document.getElementById("dp-status-badge").innerHTML =
    `<span class="badge ${alertBadgeClass(alert.level, c.status)}">${alertBadgeText(alert.level, c.status, alert.message)}</span>`;

  // Deadline box
  renderDeadlineBox(c);

  // Acciones bar (ocultar si completado/cancelado)
  const isDone = c.status !== "active";
  document.getElementById("dp-actions-bar").style.display = isDone ? "none" : "flex";
  document.getElementById("btn-cancel-cert").style.display =
    c.status === "active" ? "" : "none";

  // Tabs counters
  document.getElementById("tab-attach-count").textContent = (c.attachments || []).length;
  document.getElementById("tab-email-count").textContent  = (c.emails || []).length;

  // Etapas
  renderStages(c);

  // Archivos
  renderAttachments(c.attachments || []);

  // Correos
  renderEmails(c.emails || []);
}

function renderDeadlineBox(c) {
  const box = document.getElementById("dp-deadline-box");
  if (c.delivery_deadline && c.status === "active") {
    const dl   = new Date(c.delivery_deadline);
    const today = new Date();
    today.setHours(0,0,0,0);
    dl.setHours(0,0,0,0);
    const diff = Math.round((dl - today) / 86400000);
    let colorClass = "green";
    let icon = "📅";
    if (diff <= 0) { colorClass = "red"; icon = "🔴"; }
    else if (diff <= 1) { colorClass = "red"; icon = "🟠"; }
    else if (diff <= 2) { colorClass = "yellow"; icon = "🟡"; }

    box.style.display = "flex";
    box.className = `deadline-box ${colorClass}`;
    box.innerHTML = `
      <div class="deadline-icon">${icon}</div>
      <div class="deadline-text">
        <div class="deadline-label">Fecha límite de entrega (5 días hábiles desde pago)</div>
        <div class="deadline-value">${formatDateLong(c.delivery_deadline)} ${diff <= 0 ? '— VENCIDO' : diff === 1 ? '— Hoy es el último día' : `— ${diff} días calendario restantes`}</div>
      </div>`;
  } else if (c.poligrafo_deadline && !c.payment_received_at && c.status === "active") {
    const dl   = new Date(c.poligrafo_deadline);
    const today = new Date();
    today.setHours(0,0,0,0);
    dl.setHours(0,0,0,0);
    const diff = Math.round((dl - today) / 86400000);
    let colorClass = diff <= 0 ? "red" : diff <= 1 ? "yellow" : "green";
    box.style.display = "flex";
    box.className = `deadline-box ${colorClass}`;
    box.innerHTML = `
      <div class="deadline-icon">💳</div>
      <div class="deadline-text">
        <div class="deadline-label">Vencimiento del polígrafo (5 días hábiles para pagar)</div>
        <div class="deadline-value">${formatDateLong(c.poligrafo_deadline)} ${diff <= 0 ? '— VENCIDO (solicitar nueva solicitud)' : `— ${diff} días calendario restantes`}</div>
      </div>`;
  } else {
    box.style.display = "none";
  }
}

function renderStages(c) {
  const stages = c.stages || [];
  const currentStage = c.current_stage;
  const alert = c.alert || {};
  const isActive = c.status === "active";
  const container = document.getElementById("dp-stages-list");

  container.innerHTML = stages.map(s => {
    const done    = s.completed === 1 || s.completed === true;
    const isCurrent = s.stage_number === currentStage && !done && isActive;
    const isOverdue = isCurrent && (alert.level === "overdue" || alert.level === "critical");
    let dotClass = done ? "done" : isCurrent ? (isOverdue ? "overdue current" : "current") : "";

    const actionBtn = isActive && isCurrent
      ? `<button class="btn btn-success btn-sm" onclick="event.stopPropagation();openCompleteStage(${s.stage_number})">✅ Marcar completada</button>`
      : done && isActive
      ? `<button class="btn btn-ghost btn-sm" onclick="event.stopPropagation();undoStage(${s.stage_number})" title="Deshacer">↩ Deshacer</button>`
      : "";

    const specialInfo = stageSpecialInfo(s, c);

    return `
    <div class="stage-item">
      <div class="stage-dot ${dotClass}">${done ? "✓" : s.stage_number}</div>
      <div class="stage-content">
        <div class="stage-title">
          ${escHtml(s.stage_name)}
          ${done ? '<span class="badge badge-ok" style="font-size:0.7rem;">✓ Completada</span>' : isCurrent ? '<span class="badge badge-blue" style="font-size:0.7rem;">← Etapa actual</span>' : ''}
        </div>
        <div class="stage-meta">
          ${done ? `<span>📅 ${formatDate(s.completed_at)}</span><span>👤 ${s.completed_by || "—"}</span>` : ""}
          ${specialInfo}
        </div>
        ${s.notes ? `<div class="stage-notes">💬 ${escHtml(s.notes)}</div>` : ""}
        <div class="stage-actions">${actionBtn}</div>
      </div>
    </div>`;
  }).join("");
}

function stageSpecialInfo(s, c) {
  if (s.stage_number === 2 && c.poligrafo_deadline) {
    return `<span style="color:var(--yellow);">⚠️ Plazo pago: ${formatDateLong(c.poligrafo_deadline)}</span>`;
  }
  if (s.stage_number === 3 && c.delivery_deadline) {
    return `<span style="color:var(--accent);">📅 Plazo entrega: ${formatDateLong(c.delivery_deadline)}</span>`;
  }
  return "";
}

function renderAttachments(attachments) {
  const el = document.getElementById("dp-attachments-list");
  if (!attachments.length) {
    el.innerHTML = `<div class="empty-state"><div class="icon">📎</div><h3>Sin archivos adjuntos</h3></div>`;
    return;
  }
  const icons = { "application/pdf": "📄", "image/png": "🖼️", "image/jpeg": "🖼️" };
  el.innerHTML = attachments.map(a => `
    <div class="attachment-item">
      <div class="attachment-icon">${a.is_certificate ? "📜" : (icons[a.content_type] || "📎")}</div>
      <div class="attachment-info">
        <div class="attachment-name">${escHtml(a.original_name)}</div>
        <div class="attachment-meta">
          ${a.description ? escHtml(a.description) + " · " : ""}
          Etapa ${a.stage_number || "—"} · ${formatDate(a.uploaded_at)} · ${a.uploaded_by}
          ${a.is_certificate ? ' · <strong style="color:var(--green);">Certificado oficial</strong>' : ""}
        </div>
      </div>
      <div class="attachment-actions">
        <a class="btn btn-ghost btn-sm" href="/cert/attachments/${a.id}/download"
           target="_blank" title="Descargar">⬇</a>
        <button class="btn btn-danger btn-sm" title="Eliminar"
                onclick="deleteAttachment('${a.id}')">🗑</button>
      </div>
    </div>
  `).join("");
}

function renderEmails(emails) {
  const el = document.getElementById("dp-emails-list");
  if (!emails.length) {
    el.innerHTML = `<div class="empty-state"><div class="icon">📧</div><h3>Sin correos registrados</h3></div>`;
    return;
  }
  el.innerHTML = emails.map(e => `
    <div class="email-item">
      <div class="email-header">
        <span class="email-subject">${escHtml(e.subject || "(sin asunto)")}</span>
        <span class="email-badge ${e.direction}">${e.direction === "inbound" ? "📥 Recibido" : "📤 Enviado"}</span>
        ${e.stage_number ? `<span class="badge badge-blue" style="font-size:0.7rem;">Etapa ${e.stage_number}</span>` : ""}
      </div>
      <div class="email-meta">
        De: ${escHtml(e.from_addr)} → Para: ${escHtml(e.to_addr)} · ${formatDate(e.logged_at)}
      </div>
      ${e.body ? `<div class="email-body">${escHtml(e.body)}</div>` : ""}
      <div style="margin-top:0.5rem;">
        <button class="btn btn-danger btn-sm" onclick="deleteEmail('${e.id}')">🗑 Eliminar</button>
      </div>
    </div>
  `).join("");
}

// ── Tabs ──────────────────────────────────────────────────────────────────
function switchTab(tabId) {
  document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(tabId).classList.add("active");
  event.target.classList.add("active");
}

// ── Modal — Nueva solicitud ───────────────────────────────────────────────
function openNewCertModal() {
  certTypesList = [];
  document.getElementById("nc-name").value  = "";
  document.getElementById("nc-id").value    = "";
  document.getElementById("nc-email").value = "";
  document.getElementById("nc-phone").value = "";
  document.getElementById("nc-notes").value = "";
  document.getElementById("nc-type-input").value = "";
  renderCertTypesList();
  openModal("modal-new-cert");
}

function addCertType() {
  const val = document.getElementById("nc-type-input").value.trim();
  if (!val || certTypesList.includes(val)) return;
  certTypesList.push(val);
  document.getElementById("nc-type-input").value = "";
  renderCertTypesList();
}

function removeCertType(idx) {
  certTypesList.splice(idx, 1);
  renderCertTypesList();
}

function renderCertTypesList() {
  document.getElementById("cert-types-list").innerHTML = certTypesList.map((t, i) => `
    <div style="display:flex;align-items:center;gap:0.5rem;background:var(--bg3);
                border-radius:6px;padding:0.4rem 0.75rem;font-size:0.85rem;">
      <span style="flex:1;">${escHtml(t)}</span>
      <button onclick="removeCertType(${i})" style="background:none;border:none;
              color:var(--text2);cursor:pointer;font-size:1rem;">✕</button>
    </div>
  `).join("");
}

async function createCertificate() {
  const name  = document.getElementById("nc-name").value.trim();
  const id    = document.getElementById("nc-id").value.trim();
  const email = document.getElementById("nc-email").value.trim();
  const phone = document.getElementById("nc-phone").value.trim();
  const notes = document.getElementById("nc-notes").value.trim();

  if (!name || !id || !email) {
    toast("Completa los campos obligatorios (nombre, documento, correo).", "error");
    return;
  }
  if (certTypesList.length === 0) {
    toast("Agrega al menos un tipo de certificado.", "error");
    return;
  }

  const btn = document.getElementById("btn-create-cert");
  btn.disabled = true;
  try {
    const r = await api("POST", "/cert/certificates", {
      student_name: name,
      student_id: id,
      student_email: email,
      student_phone: phone,
      certificate_types: certTypesList,
      notes,
    });
    closeModal("modal-new-cert");
    toast(`✅ Solicitud creada: ${r.tracking_code}`, "success");
    loadCertificates();
    loadStats();
    openDetail(r.id);
  } catch (e) {
    toast("Error: " + e.message, "error");
  } finally {
    btn.disabled = false;
  }
}

// ── Modal — Completar etapa ───────────────────────────────────────────────
function openCompleteStage(stageNum) {
  pendingStageNum = stageNum;
  const names = {
    1: "Solicitud recibida",
    2: "Polígrafo enviado al estudiante",
    3: "Comprobante de pago recibido",
    4: "Certificado elaborado y enviado a Sec. División",
    5: "Firmado en Sec. División",
    6: "Firmado en Sec. General",
    7: "Recibido de Sec. División",
    8: "Certificado enviado al estudiante",
  };
  document.getElementById("complete-stage-title").textContent =
    `✅ Etapa ${stageNum}: ${names[stageNum]}`;

  // Fecha por defecto: hoy
  document.getElementById("stage-date").value = todayISO();
  document.getElementById("stage-notes").value = "";

  // Info extra según etapa
  const extra = document.getElementById("stage-extra-info");
  if (stageNum === 2) {
    extra.style.display = "block";
    extra.innerHTML = `<div class="deadline-box yellow" style="margin-bottom:0.75rem;">
      <div class="deadline-icon">⚠️</div>
      <div class="deadline-text">
        <div class="deadline-label">Al marcar esta etapa</div>
        <div class="deadline-value" style="font-size:0.9rem;">El sistema calculará automáticamente la fecha límite de pago (5 días hábiles). Si el estudiante no paga en ese tiempo, se debe cancelar el trámite.</div>
      </div>
    </div>`;
  } else if (stageNum === 3) {
    extra.style.display = "block";
    extra.innerHTML = `<div class="deadline-box green" style="margin-bottom:0.75rem;">
      <div class="deadline-icon">⏱️</div>
      <div class="deadline-text">
        <div class="deadline-label">Al marcar esta etapa</div>
        <div class="deadline-value" style="font-size:0.9rem;">Arranca el reloj oficial: <strong>5 días hábiles</strong> para entregar el certificado al estudiante.</div>
      </div>
    </div>`;
  } else {
    extra.style.display = "none";
    extra.innerHTML = "";
  }

  openModal("modal-complete-stage");
}

async function confirmCompleteStage() {
  if (!pendingStageNum || !currentCertId) return;
  const dateVal  = document.getElementById("stage-date").value;
  const notesVal = document.getElementById("stage-notes").value.trim();
  try {
    await api("POST", `/cert/certificates/${currentCertId}/stages/${pendingStageNum}/complete`, {
      completed_at: dateVal || todayISO(),
      notes: notesVal,
    });
    closeModal("modal-complete-stage");
    toast(`Etapa ${pendingStageNum} marcada como completada ✅`, "success");
    await refreshDetail();
    loadCertificates();
    loadAlerts();
    loadStats();
  } catch (e) {
    toast("Error: " + e.message, "error");
  }
}

async function undoStage(stageNum) {
  if (!confirm("¿Deshacer la marca de esta etapa?")) return;
  try {
    await api("POST", `/cert/certificates/${currentCertId}/stages/${stageNum}/undo`);
    toast("Etapa deshecha.", "info");
    await refreshDetail();
    loadCertificates();
    loadAlerts();
    loadStats();
  } catch (e) {
    toast("Error: " + e.message, "error");
  }
}

// ── Cancelar certificado ──────────────────────────────────────────────────
async function cancelCert() {
  const opts = [
    "cancelled_no_payment — El estudiante no pagó a tiempo",
    "cancelled — Otro motivo",
  ];
  const choice = prompt(
    "¿Motivo de cancelación?\n1: Sin pago\n2: Otro motivo\n\nEscribe 1 o 2:"
  );
  if (!choice) return;
  const reason = choice.trim() === "1" ? "cancelled_no_payment" : "cancelled";
  try {
    await api("DELETE", `/cert/certificates/${currentCertId}?reason=${reason}`);
    toast("Trámite cancelado.", "info");
    closeDetail();
    loadCertificates();
    loadStats();
    loadAlerts();
  } catch (e) {
    toast("Error: " + e.message, "error");
  }
}

// ── Modal — Correo ────────────────────────────────────────────────────────
function openEmailModal() {
  document.getElementById("email-subject").value = "";
  document.getElementById("email-from").value    = "";
  document.getElementById("email-to").value      = "";
  document.getElementById("email-body").value    = "";
  openModal("modal-email");
}

async function saveEmailLog() {
  const direction = document.getElementById("email-direction").value;
  const subject   = document.getElementById("email-subject").value.trim();
  const from      = document.getElementById("email-from").value.trim();
  const to        = document.getElementById("email-to").value.trim();
  const body      = document.getElementById("email-body").value.trim();
  const stage     = document.getElementById("email-stage").value;

  if (!subject) { toast("El asunto es obligatorio.", "error"); return; }
  try {
    await api("POST", `/cert/certificates/${currentCertId}/emails`, {
      direction, subject, from_addr: from, to_addr: to, body,
      stage_number: stage ? parseInt(stage) : null,
    });
    closeModal("modal-email");
    toast("Correo registrado en la trazabilidad ✅", "success");
    await refreshDetail();
  } catch (e) {
    toast("Error: " + e.message, "error");
  }
}

async function deleteEmail(emailId) {
  if (!confirm("¿Eliminar este registro de correo?")) return;
  try {
    await api("DELETE", `/cert/emails/${emailId}`);
    toast("Correo eliminado.", "info");
    await refreshDetail();
  } catch (e) {
    toast("Error: " + e.message, "error");
  }
}

// ── Modal — Upload ────────────────────────────────────────────────────────
function openUploadModal() {
  document.getElementById("upload-file-input").value = "";
  document.getElementById("upload-desc").value       = "";
  document.getElementById("upload-is-cert").checked  = false;
  document.getElementById("upload-area-text").textContent =
    "Haz clic para seleccionar o arrastra el archivo aquí";
  openModal("modal-upload");
}

function onFileSelected(input) {
  const file = input.files[0];
  if (file) {
    document.getElementById("upload-area-text").textContent = `📎 ${file.name}`;
  }
}

async function doUpload() {
  const fileInput = document.getElementById("upload-file-input");
  const file      = fileInput.files[0];
  if (!file) { toast("Selecciona un archivo.", "error"); return; }

  const desc     = document.getElementById("upload-desc").value.trim();
  const stageNum = document.getElementById("upload-stage").value;
  const isCert   = document.getElementById("upload-is-cert").checked;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("description", desc);
  formData.append("is_certificate", isCert ? "true" : "false");
  if (stageNum) formData.append("stage_number", stageNum);

  const btn = document.getElementById("btn-upload");
  btn.disabled = true;
  btn.textContent = "Subiendo…";
  try {
    await apiForm(`/cert/certificates/${currentCertId}/attachments`, formData);
    closeModal("modal-upload");
    toast("Archivo subido correctamente ✅", "success");
    await refreshDetail();
  } catch (e) {
    toast("Error: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Subir archivo";
  }
}

async function deleteAttachment(attachId) {
  if (!confirm("¿Eliminar este archivo?")) return;
  try {
    await api("DELETE", `/cert/attachments/${attachId}`);
    toast("Archivo eliminado.", "info");
    await refreshDetail();
  } catch (e) {
    toast("Error: " + e.message, "error");
  }
}

// ── Modals ────────────────────────────────────────────────────────────────
function openModal(id) {
  document.getElementById(id).classList.add("open");
}
function closeModal(id) {
  document.getElementById(id).classList.remove("open");
}
// Cerrar modal al hacer click fuera
document.querySelectorAll(".modal-overlay").forEach(overlay => {
  overlay.addEventListener("click", e => {
    if (e.target === overlay) overlay.classList.remove("open");
  });
});

// ── Formateo de fechas ────────────────────────────────────────────────────
function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("es-CO", {
      day: "2-digit", month: "short", year: "numeric"
    });
  } catch { return iso; }
}
function formatDateLong(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("es-CO", {
      weekday: "long", day: "numeric", month: "long", year: "numeric"
    });
  } catch { return iso; }
}
function todayISO() {
  return new Date().toISOString().split("T")[0];
}

// ── Utilidades ────────────────────────────────────────────────────────────
function escHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Bootstrap ─────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  if (SESSION_TOKEN && SESSION_USER) {
    initApp();
  } else {
    showView("view-login");
    setTimeout(() => document.getElementById("login-user").focus(), 100);
  }
});
