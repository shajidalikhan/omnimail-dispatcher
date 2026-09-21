// Global State
let appConfig = null;
let currentStep = 1;
let currentPreviewIndex = 0;
let totalRecipients = 0;
let isDispatching = false;
let dispatchPollInterval = null;
let debounceTimer = null;

// Zero-Retention Multi-Tenant Session ID
function getSessionId() {
  let sid = sessionStorage.getItem("omnimail_session_id");
  if (!sid) {
    sid = "sess_" + Math.random().toString(36).substring(2, 11) + "_" + Date.now().toString(36);
    sessionStorage.setItem("omnimail_session_id", sid);
  }
  return sid;
}

// Intercept all API calls to automatically attach isolated session ID
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
  options.headers = options.headers || {};
  if (options.headers instanceof Headers) {
    options.headers.set("X-Session-ID", getSessionId());
  } else if (Array.isArray(options.headers)) {
    options.headers.push(["X-Session-ID", getSessionId()]);
  } else {
    options.headers["X-Session-ID"] = getSessionId();
  }
  return originalFetch(url, options);
};

// Initialize on page load
document.addEventListener("DOMContentLoaded", async () => {
  setupDragAndDrop();
  await loadInitialConfig();
  updateExportLinks();
});

function updateExportLinks() {
  const sid = getSessionId();
  document.querySelectorAll('a[href*="/api/export-results"]').forEach(el => {
    const base = el.getAttribute("href").split("&session_id=")[0];
    el.setAttribute("href", `${base}&session_id=${sid}`);
  });
}

// Fetch configuration & presets
async function loadInitialConfig() {
  try {
    const res = await fetch("/api/config");
    appConfig = await res.json();

    const saved = appConfig.saved || {};

    // Pre-fill dispatcher
    if (saved.dispatcher_type) {
      document.getElementById("dispatcher-type").value = saved.dispatcher_type;
    }

    // LOCAL MODE: pre-fill all fields from server-saved .env credentials
    if (saved.sender_email) {
      document.getElementById("sender-email").value = saved.sender_email;
    }
    if (saved.sender_name) {
      document.getElementById("sender-name").value = saved.sender_name;
    }
    // Pre-fill key from .env (local mode — single user machine only)
    const keyFromEnv = saved.sender_key || sessionStorage.getItem("omnimail_key") || "";
    if (keyFromEnv) {
      document.getElementById("sender-key").value = keyFromEnv;
      sessionStorage.setItem("omnimail_key", keyFromEnv);
    }

    applyLocalModeUi(appConfig.local_mode !== false);
    if (saved.custom_smtp_server) {
      document.getElementById("custom-host").value = saved.custom_smtp_server;
    }
    if (saved.custom_smtp_port) {
      document.getElementById("custom-port").value = saved.custom_smtp_port;
    }

    // Populate templates
    document.getElementById("template-subject").value = appConfig.default_subject || "";
    document.getElementById("template-body").value = appConfig.default_body_html || "";

    // Populate guidelines
    renderGuidelines(appConfig.guidelines || []);

    onDispatcherChange();
    onTemplateContentChanged();
    updateSummaryView();
  } catch (err) {
    console.error("Failed to load initial configuration:", err);

  }
}


// Step Navigation
function switchStep(stepNum) {
  currentStep = stepNum;
  for (let i = 1; i <= 4; i++) {
    const panel = document.getElementById(`panel-step-${i}`);
    const nav = document.getElementById(`step-nav-${i}`);
    if (panel) panel.classList.toggle("active", i === stepNum);
    if (nav) nav.classList.toggle("active", i === stepNum);
  }
  if (stepNum === 3) {
    renderPreview();
    analyzeTemplate();
    fetchAttachments();
  }
  if (stepNum === 4) {
    updateSummaryView();
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// Attachment Management
function formatBytes(bytes, decimals = 1) {
  if (!+bytes) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

async function handleAttachmentUpload(event) {
  const files = event.target.files;
  if (!files || files.length === 0) return;

  for (let i = 0; i < files.length; i++) {
    const formData = new FormData();
    formData.append("file", files[i]);
    try {
      const res = await fetch("/api/upload-attachment", {
        method: "POST",
        body: formData
      });
      if (!res.ok) {
        const err = await res.json();
        alert(`Error uploading '${files[i].name}': ${err.detail || 'Upload failed'}`);
      }
    } catch (err) {
      alert(`Network error uploading file: ${err.message}`);
    }
  }

  event.target.value = "";
  await fetchAttachments();
}

async function fetchAttachments() {
  try {
    const res = await fetch("/api/attachments");
    const data = await res.json();
    renderAttachments(data.attachments || [], data.total_size || 0);
  } catch (err) {
    console.error("Failed to fetch attachments:", err);
  }
}

function renderAttachments(attachments, totalSize) {
  const listContainer = document.getElementById("attachment-list");
  const sizeBadge = document.getElementById("attachment-size-badge");
  const previewRow = document.getElementById("preview-attachments-row");
  const previewText = document.getElementById("preview-attachments-text");

  if (sizeBadge) {
    sizeBadge.textContent = `${attachments.length} file(s) (${formatBytes(totalSize)} / 25 MB max)`;
    sizeBadge.classList.toggle("warning", totalSize > 20 * 1024 * 1024);
  }

  if (listContainer) {
    if (attachments.length === 0) {
      listContainer.innerHTML = '<span class="text-dim" style="font-size: 0.78rem;" id="no-attachments-msg">No files attached yet. Click "+ Attach File(s)" to include documents.</span>';
    } else {
      listContainer.innerHTML = attachments.map(a => `
        <div class="attachment-chip">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
          <span><strong>${escapeHtml(a.filename)}</strong> (${formatBytes(a.size)})</span>
          <button type="button" class="attachment-remove-btn" onclick="removeAttachment('${escapeHtml(a.filename)}')" title="Remove file">&times;</button>
        </div>
      `).join("");
    }
  }

  if (previewRow && previewText) {
    if (attachments.length > 0) {
      previewRow.style.display = "block";
      previewText.textContent = attachments.map(a => `${a.filename} (${formatBytes(a.size)})`).join(", ");
    } else {
      previewRow.style.display = "none";
    }
  }
}

async function removeAttachment(filename) {
  try {
    const res = await fetch(`/api/delete-attachment/${encodeURIComponent(filename)}`, {
      method: "DELETE"
    });
    const data = await res.json();
    renderAttachments(data.attachments || [], data.total_size || 0);
  } catch (err) {
    alert("Failed to remove attachment: " + err.message);
  }
}


// Dispatcher change
function onDispatcherChange() {
  const dType = document.getElementById("dispatcher-type").value;
  const customPanel = document.getElementById("custom-smtp-fields");
  const keyHint = document.getElementById("key-hint");
  const badgeText = document.getElementById("header-dispatcher-name");

  if (dType === "custom") {
    customPanel.classList.remove("hidden-panel");
    keyHint.textContent = "Enter password or SMTP access token for your institutional server.";
    badgeText.textContent = "Custom SMTP";
  } else {
    customPanel.classList.add("hidden-panel");
    if (dType === "gmail") {
      keyHint.textContent = "Use your 16-character Google App Password (not standard Gmail password).";
      badgeText.textContent = "Gmail SMTP";
    } else if (dType === "outlook") {
      keyHint.textContent = "Use your Microsoft 365 or Outlook App Password / Key.";
      badgeText.textContent = "Outlook SMTP";
    } else if (dType === "dry_run") {
      keyHint.textContent = "Safe Sandbox Mode active. No real emails will be dispatched.";
      badgeText.textContent = "Dry Run (Safe)";
    } else {
      keyHint.textContent = "Enter your mail account password or app password.";
      badgeText.textContent = dType.toUpperCase();
    }
  }
  updateSummaryView();
}

// Password toggle
function toggleKeyVisibility() {
  const input = document.getElementById("sender-key");
  input.type = input.type === "password" ? "text" : "password";
}

function applyLocalModeUi(isLocal) {
  document.querySelectorAll(".local-mode-only").forEach((el) => {
    el.classList.toggle("hidden-panel", !isLocal);
  });
}

// LOCAL MODE: Save credentials to server .env file for persistence across restarts
async function saveCredentials() {
  const dType = document.getElementById("dispatcher-type").value;
  const sEmail = document.getElementById("sender-email").value.trim();
  const sName = document.getElementById("sender-name").value.trim();
  const sKey = document.getElementById("sender-key").value.trim();
  const cHost = document.getElementById("custom-host")?.value.trim() || "";
  const cPort = parseInt(document.getElementById("custom-port")?.value || "587");
  const cTls = document.getElementById("custom-tls")?.checked ?? true;

  if (!sEmail || !sKey) {
    alert("Please fill in your Sender Email and Mail Key before saving.");
    return;
  }

  try {
    const res = await fetch("/api/save-credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dispatcher_type: dType,
        sender_email: sEmail,
        sender_name: sName,
        sender_key: sKey,
        custom_smtp_server: cHost,
        custom_smtp_port: cPort,
        custom_use_tls: cTls
      })
    });
    const data = await res.json();
    if (data.success) {
      // Also cache in sessionStorage for instant use
      sessionStorage.setItem("omnimail_key", sKey);
      alert("✅ Saved to .env!\n\n" + data.message);
    } else {
      alert("Failed to save: " + (data.message || "Unknown error"));
    }
  } catch (err) {
    alert("Error saving credentials: " + err.message);
  }
  updateSummaryView();
}

function clearSessionCredentials() {
  sessionStorage.removeItem("omnimail_key");
  sessionStorage.removeItem("omnimail_email");
  sessionStorage.removeItem("omnimail_name");
  document.getElementById("sender-key").value = "";
  alert("Key cleared from browser memory.\n\nNote: The .env file on your machine still has the saved key. Delete it manually to fully remove it.");
}


// Drag and drop setup
function setupDragAndDrop() {
  const dropZone = document.getElementById("drop-zone");
  if (!dropZone) return;

  ["dragenter", "dragover"].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    }, false);
  });

  ["dragleave", "drop"].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
    }, false);
  });

  dropZone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length) {
      uploadFile(files[0]);
    }
  });
}

function handleFileSelect(event) {
  const file = event.target.files[0];
  if (file) uploadFile(file);
}

// File upload
async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/upload", {
      method: "POST",
      body: formData
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Upload failed");
    }
    const data = await res.json();
    applyParsedData(data);
  } catch (err) {
    alert("Upload Error: " + err.message);
  }
}

// Built-in sample loader
async function loadSampleData() {
  try {
    // Read local sample csv via fetch
    const rawCsv = `Name,Email,University,Research_Area
Dr. Sarah Jenkins,sarah.jenkins@stanford.edu,Stanford University,Artificial Intelligence
Prof. Michael Chang,m.chang@oxford.ac.uk,University of Oxford,Distributed Systems & Cloud
Dr. Priya Sharma,priya.sharma@iitd.ac.in,IIT Delhi,Machine Learning in Healthcare
Prof. David Miller,d.miller@mit.edu,MIT,Quantum Computing & Cryptography
Elena Rostova,elena.rostova@tum.de,Technical University of Munich,Cyber-Physical Systems
Invalid Contact,,Unknown University,Data Mining
Dr. Duplicate Test,sarah.jenkins@stanford.edu,Stanford University,Artificial Intelligence`;

    const res = await fetch("/api/paste", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_text: rawCsv })
    });
    const data = await res.json();
    applyParsedData(data);
  } catch (err) {
    alert("Failed to load sample dataset: " + err.message);
  }
}

// Raw paste submit
async function submitPastedData() {
  const rawText = document.getElementById("paste-input").value.trim();
  if (!rawText) return alert("Please paste data first.");

  try {
    const res = await fetch("/api/paste", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_text: rawText })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to parse pasted text");
    }
    const data = await res.json();
    applyParsedData(data);
  } catch (err) {
    alert("Paste Error: " + err.message);
  }
}

// Apply parsed data to UI
function applyParsedData(data) {
  document.getElementById("data-summary-section").classList.remove("hidden-panel");

  const summary = data.validation_summary || {};
  document.getElementById("stat-total").textContent = summary.total || data.total_rows || 0;
  document.getElementById("stat-valid").textContent = summary.valid_count || 0;
  document.getElementById("stat-invalid").textContent = summary.invalid_count || 0;
  document.getElementById("stat-duplicate").textContent = summary.duplicate_count || 0;

  totalRecipients = summary.valid_count || 0;

  // Email column select
  const select = document.getElementById("email-column-select");
  select.innerHTML = "";
  (data.columns || []).forEach(col => {
    const opt = document.createElement("option");
    opt.value = col;
    opt.textContent = col;
    if (col === data.selected_email_col) opt.selected = true;
    select.appendChild(opt);
  });

  // Table preview
  renderPreviewTable(data.columns || [], data.sample_rows || []);

  // Populate dynamic variable chips for Step 3
  renderVariableChips(data.columns || []);

  updateSummaryView();
}

async function changeEmailColumn() {
  const col = document.getElementById("email-column-select").value;
  try {
    const res = await fetch("/api/set-email-column", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email_column: col })
    });
    const data = await res.json();
    const summary = data.validation_summary || {};
    document.getElementById("stat-total").textContent = summary.total || 0;
    document.getElementById("stat-valid").textContent = summary.valid_count || 0;
    document.getElementById("stat-invalid").textContent = summary.invalid_count || 0;
    document.getElementById("stat-duplicate").textContent = summary.duplicate_count || 0;
    totalRecipients = summary.valid_count || 0;
    updateSummaryView();
  } catch (err) {
    console.error(err);
  }
}

function renderPreviewTable(columns, rows) {
  const thead = document.getElementById("preview-table-head");
  const tbody = document.getElementById("preview-table-body");

  thead.innerHTML = `<tr>${columns.map(c => `<th>${escapeHtml(c)}</th>`).join("")}</tr>`;
  tbody.innerHTML = rows.map(r => {
    return `<tr>${columns.map(c => `<td>${escapeHtml(String(r[c] || ""))}</td>`).join("")}</tr>`;
  }).join("");
}

function renderVariableChips(columns) {
  const container = document.getElementById("variable-chips");
  container.innerHTML = "";
  columns.forEach(col => {
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.textContent = `+ {{${col}}}`;
    btn.onclick = () => insertVariable(`{{${col}}}`);
    container.appendChild(btn);
  });
}

function switchDataTab(tab) {
  document.getElementById("tab-upload-btn").classList.toggle("active", tab === "upload");
  document.getElementById("tab-paste-btn").classList.toggle("active", tab === "paste");
  document.getElementById("data-tab-upload").classList.toggle("active", tab === "upload");
  document.getElementById("data-tab-paste").classList.toggle("active", tab === "paste");
}

// Template & Studio Logic
function insertVariable(token) {
  const bodyTextarea = document.getElementById("template-body");
  const start = bodyTextarea.selectionStart;
  const end = bodyTextarea.selectionEnd;
  const val = bodyTextarea.value;
  bodyTextarea.value = val.substring(0, start) + token + val.substring(end);
  bodyTextarea.focus();
  bodyTextarea.selectionStart = bodyTextarea.selectionEnd = start + token.length;
  onTemplateContentChanged();
}

function insertFallbackSyntax() {
  insertVariable("{{Field_Name | default('Valued Colleague')}}");
}

function resetDefaultTemplate() {
  if (confirm("Reset subject and body to default academic outreach template?")) {
    document.getElementById("template-subject").value = appConfig?.default_subject || "";
    document.getElementById("template-body").value = appConfig?.default_body_html || "";
    onTemplateContentChanged();
  }
}

function onTemplateContentChanged() {
  const subject = document.getElementById("template-subject").value;
  document.getElementById("subject-char-count").textContent = `${subject.length} chars`;

  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    renderPreview();
    analyzeTemplate();
  }, 300);
}

// Render Preview
async function renderPreview() {
  const subject = document.getElementById("template-subject").value;
  const body = document.getElementById("template-body").value;
  const senderName = document.getElementById("sender-name")?.value || "";
  const senderEmail = document.getElementById("sender-email")?.value || "";

  try {
    const res = await fetch("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        subject_template: subject,
        body_template: body,
        recipient_index: currentPreviewIndex,
        sender_name: senderName,
        sender_email: senderEmail
      })
    });
    const data = await res.json();
    document.getElementById("preview-rendered-subject").textContent = data.rendered_subject;
    document.getElementById("preview-rendered-body").innerHTML = data.rendered_body;
    document.getElementById("preview-to-email").textContent = data.recipient_context?.Email || data.recipient_context?.email || "recipient@example.com";
    document.getElementById("preview-index-counter").textContent = `Recipient ${data.current_index + 1} of ${data.total_records}`;
  } catch (err) {
    console.error("Preview render error:", err);
  }
}

function prevPreviewRecipient() {
  if (currentPreviewIndex > 0) {
    currentPreviewIndex--;
    renderPreview();
  }
}

function nextPreviewRecipient() {
  currentPreviewIndex++;
  renderPreview();
}

// Analyze Template Hygiene & Spam
async function analyzeTemplate() {
  const subject = document.getElementById("template-subject").value;
  const body = document.getElementById("template-body").value;

  try {
    const res = await fetch("/api/analyze-template", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject, body })
    });
    const data = await res.json();

    const scoreBadge = document.getElementById("hygiene-score");
    scoreBadge.textContent = `${data.score} / 100`;
    scoreBadge.className = "score-badge " + (data.score >= 80 ? "score-good" : (data.score >= 50 ? "score-medium" : "score-bad"));

    const warnBox = document.getElementById("hygiene-warnings");
    if (data.warnings && data.warnings.length > 0) {
      warnBox.classList.remove("hidden-panel");
      warnBox.innerHTML = `<strong>Deliverability Suggestions:</strong><ul style="margin-top: 0.3rem; padding-left: 1.2rem;">${data.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join("")}</ul>`;
    } else {
      warnBox.classList.add("hidden-panel");
    }
  } catch (err) {
    console.error("Analysis error:", err);
  }
}

// Render Guidelines
function renderGuidelines(guidelines) {
  const container = document.getElementById("guidelines-container");
  container.innerHTML = guidelines.map(g => `
    <div class="guide-item">
      <div class="guide-item-title">${escapeHtml(g.title)}</div>
      <div class="guide-item-desc">${escapeHtml(g.description)}</div>
      ${g.example ? `<div class="guide-item-example">${escapeHtml(g.example)}</div>` : ""}
    </div>
  `).join("");
}

// Single Test Email Modal
function openTestEmailModal() {
  document.getElementById("test-email-modal").classList.add("active");
  const myEmail = document.getElementById("sender-email").value.trim();
  if (myEmail && !document.getElementById("modal-test-recipient").value) {
    document.getElementById("modal-test-recipient").value = myEmail;
  }
  document.getElementById("modal-test-result").classList.add("hidden-panel");
}

function closeTestEmailModal() {
  document.getElementById("test-email-modal").classList.remove("active");
}

async function dispatchTestEmail() {
  const recipient = document.getElementById("modal-test-recipient").value.trim();
  if (!recipient) return alert("Please enter a recipient email address.");

  const btn = document.getElementById("modal-send-btn");
  btn.disabled = true;
  btn.textContent = "Sending Test...";

  const payload = {
    dispatcher_type: document.getElementById("dispatcher-type").value,
    sender_email: document.getElementById("sender-email").value.trim(),
    sender_name: document.getElementById("sender-name").value.trim(),
    sender_key: document.getElementById("sender-key").value.trim(),
    test_recipient_email: recipient,
    subject: document.getElementById("template-subject").value,
    body_html: document.getElementById("template-body").value,
    custom_smtp_server: document.getElementById("custom-host")?.value.trim() || "",
    custom_smtp_port: parseInt(document.getElementById("custom-port")?.value || "587"),
    custom_use_tls: document.getElementById("custom-tls")?.checked ?? true
  };

  try {
    const res = await fetch("/api/test-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    const resultBox = document.getElementById("modal-test-result");
    resultBox.classList.remove("hidden-panel");
    resultBox.className = "alert-box " + (data.success ? "success" : "error");
    resultBox.textContent = data.message || (data.success ? "Email successfully dispatched!" : "Delivery failed.");
  } catch (err) {
    alert("Test dispatch error: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Send Test Email";
  }
}

// Step 4: Dispatch Controls
function updateDelayDisplay(val) {
  document.getElementById("delay-badge").textContent = `${parseFloat(val).toFixed(1)} seconds`;
}

function updateSummaryView() {
  const dType = document.getElementById("dispatcher-type")?.value || "gmail";
  const sEmail = document.getElementById("sender-email")?.value.trim();
  
  const sumDisp = document.getElementById("summary-dispatcher");
  const sumSend = document.getElementById("summary-sender");
  const sumCount = document.getElementById("summary-count");

  if (sumDisp) sumDisp.textContent = dType.toUpperCase();
  if (sumSend) sumSend.textContent = sEmail || "Not configured yet";
  if (sumCount) sumCount.textContent = `${totalRecipients} valid recipients`;
}

async function startBatchDispatch() {
  if (totalRecipients === 0) {
    return alert("No valid recipients loaded! Please import data in Step 2.");
  }

  const dType = document.getElementById("dispatcher-type").value;
  const sEmail = document.getElementById("sender-email").value.trim();
  const sKey =
    document.getElementById("sender-key").value.trim() ||
    sessionStorage.getItem("omnimail_key") ||
    "";

  if (dType !== "dry_run" && (!sEmail || !sKey)) {
    return alert("Please configure your Sender Email and Mail Key / App Password in Step 1 (or Save to .env).");
  }

  const confirmed = confirm(`Are you sure you want to launch dispatch to ${totalRecipients} recipients using [${dType.toUpperCase()}]?`);
  if (!confirmed) return;

  const payload = {
    dispatcher_type: dType,
    sender_email: sEmail,
    sender_name: document.getElementById("sender-name").value.trim(),
    sender_key: sKey,
    subject_template: document.getElementById("template-subject").value,
    body_template: document.getElementById("template-body").value,
    delay_seconds: parseFloat(document.getElementById("throttle-delay").value),
    custom_smtp_server: document.getElementById("custom-host")?.value.trim() || "",
    custom_smtp_port: parseInt(document.getElementById("custom-port")?.value || "587"),
    custom_use_tls: document.getElementById("custom-tls")?.checked ?? true,
    save_settings: true
  };

  try {
    const res = await fetch("/api/start-dispatch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Dispatch launch failed");
    }

    isDispatching = true;
    document.getElementById("start-dispatch-btn").disabled = true;
    document.getElementById("pause-btn").disabled = false;
    document.getElementById("stop-btn").disabled = false;
    document.getElementById("retry-failed-btn").style.display = "none";
    document.getElementById("progress-pulse").classList.add("running");

    startPollingStatus();
  } catch (err) {
    alert("Failed to start dispatch: " + err.message);
  }
}

function startPollingStatus() {
  if (dispatchPollInterval) clearInterval(dispatchPollInterval);
  dispatchPollInterval = setInterval(async () => {
    try {
      const res = await fetch("/api/dispatch-status");
      const status = await res.json();

      document.getElementById("progress-bar").style.width = `${status.progress_percent}%`;
      document.getElementById("dispatch-status-text").textContent = status.is_running ? (status.is_paused ? "Paused" : "Dispatching...") : "Completed";
      document.getElementById("progress-count-text").textContent = `${status.current_index} / ${status.total_count} processed (${status.progress_percent}%)`;
      document.getElementById("stat-current-recipient").textContent = status.current_recipient || "-";
      document.getElementById("stat-sent-count").textContent = status.sent_count;
      document.getElementById("stat-failed-count").textContent = status.failed_count;

      // Render logs
      renderLogs(status.recent_logs || []);

      if (!status.is_running && isDispatching) {
        // Finished
        clearInterval(dispatchPollInterval);
        isDispatching = false;
        document.getElementById("start-dispatch-btn").disabled = false;
        document.getElementById("pause-btn").disabled = true;
        document.getElementById("stop-btn").disabled = true;
        document.getElementById("progress-pulse").classList.remove("running");
        
        if (status.failed_count > 0) {
          document.getElementById("retry-failed-btn").style.display = "inline-flex";
        }
      }
    } catch (err) {
      console.error("Polling error:", err);
    }
  }, 1000);
}

function renderLogs(logs) {
  const logWindow = document.getElementById("activity-log-window");
  logWindow.innerHTML = logs.map(l => {
    const levelClass = l.level === "SUCCESS" ? "log-success" : (l.level === "ERROR" ? "log-error" : (l.level === "WARNING" ? "log-warning" : "log-info"));
    return `<div class="log-entry ${levelClass}">[${escapeHtml(l.timestamp)}] ${escapeHtml(l.message)}</div>`;
  }).join("");
}

async function togglePauseJob() {
  try {
    const res = await fetch("/api/dispatch-control/toggle-pause", { method: "POST" });
    const data = await res.json();
    document.getElementById("pause-btn").textContent = data.is_paused ? "Resume" : "Pause";
  } catch (err) {
    alert("Pause toggle error: " + err.message);
  }
}

async function stopJob() {
  if (confirm("Stop the ongoing email dispatch? Current in-flight email will finish.")) {
    try {
      await fetch("/api/dispatch-control/stop", { method: "POST" });
    } catch (err) {
      console.error(err);
    }
  }
}

async function retryFailedRecipients() {
  const confirmed = confirm("Retry sending only to failed recipients?");
  if (!confirmed) return;

  const payload = {
    dispatcher_type: document.getElementById("dispatcher-type").value,
    sender_email: document.getElementById("sender-email").value.trim(),
    sender_name: document.getElementById("sender-name").value.trim(),
    sender_key: document.getElementById("sender-key").value.trim(),
    subject_template: document.getElementById("template-subject").value,
    body_template: document.getElementById("template-body").value,
    delay_seconds: parseFloat(document.getElementById("throttle-delay").value),
    custom_smtp_server: document.getElementById("custom-host")?.value.trim() || "",
    custom_smtp_port: parseInt(document.getElementById("custom-port")?.value || "587"),
    custom_use_tls: document.getElementById("custom-tls")?.checked ?? true
  };

  try {
    const res = await fetch("/api/retry-failed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    alert(data.message);
    isDispatching = true;
    document.getElementById("start-dispatch-btn").disabled = true;
    document.getElementById("pause-btn").disabled = false;
    document.getElementById("stop-btn").disabled = false;
    document.getElementById("retry-failed-btn").style.display = "none";
    document.getElementById("progress-pulse").classList.add("running");
    startPollingStatus();
  } catch (err) {
    alert("Retry error: " + err.message);
  }
}

function escapeHtml(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
