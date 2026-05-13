/* ─────────────────────────────────────────────────────────────
   RAG Assistant – Frontend JavaScript
   All API calls go through the BASE_URL constant.
   In Docker the nginx proxy rewrites /api/* → backend:8000/*
   When running locally without Docker, set BASE_URL = "http://localhost:8000"
───────────────────────────────────────────────────────────── */

const BASE_URL = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
  ? "http://localhost:8000"   // local dev
  : "/api";                   // Docker (nginx proxies /api -> backend)

/* ──────────────────────────────────────
   TAB SWITCHING
────────────────────────────────────── */
document.querySelectorAll(".nav-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.tab;

    document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));

    tab.classList.add("active");
    document.getElementById(`panel-${target}`).classList.add("active");
  });
});

/* ──────────────────────────────────────
   HEALTH CHECK – update status badge
────────────────────────────────────── */
async function checkHealth() {
  const badge = document.getElementById("statusBadge");
  const label = badge.querySelector(".status-label");
  try {
    const res = await fetch(`${BASE_URL}/docs`, { method: "HEAD", signal: AbortSignal.timeout(4000) });
    if (res.ok || res.status === 200 || res.status === 405) {
      badge.className = "status-badge online";
      label.textContent = "API Online";
    } else {
      throw new Error("non-ok");
    }
  } catch {
    badge.className = "status-badge offline";
    label.textContent = "API Offline";
  }
}
checkHealth();
setInterval(checkHealth, 15000);

/* ──────────────────────────────────────
   UTILITY – BUTTON LOADING STATE
────────────────────────────────────── */
function setLoading(btnId, loading, originalHTML) {
  const btn = document.getElementById(btnId);
  if (loading) {
    btn.dataset.original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<div class="btn-spinner"></div><span>Working…</span>`;
  } else {
    btn.disabled = false;
    btn.innerHTML = originalHTML || btn.dataset.original;
  }
}

/* ──────────────────────────────────────
   UTILITY – SHOW RESULT
────────────────────────────────────── */
function showResult(elId, { type, title, detail }) {
  const el = document.getElementById(elId);
  el.style.display = "block";
  el.className = `result-box ${type}`;
  el.innerHTML = `<strong>${title}</strong>${detail ? `<pre>${detail}</pre>` : ""}`;
}

/* ──────────────────────────────────────
   CHAT HELPERS
────────────────────────────────────── */
function appendUserMessage(text) {
  const win = document.getElementById("chatWindow");
  const empty = document.getElementById("chatEmpty");
  if (empty) empty.remove();

  const wrap = document.createElement("div");
  wrap.className = "chat-message user-msg";
  wrap.innerHTML = `<div class="chat-bubble">${escapeHtml(text)}</div>`;
  win.appendChild(wrap);
  win.scrollTop = win.scrollHeight;
}

function showTyping() {
  const win = document.getElementById("chatWindow");
  const indicator = document.createElement("div");
  indicator.className = "chat-message ai-msg";
  indicator.id = "typingIndicator";
  indicator.innerHTML = `
    <div class="typing-indicator">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    </div>`;
  win.appendChild(indicator);
  win.scrollTop = win.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById("typingIndicator");
  if (el) el.remove();
}

function appendAiMessage({ answer, context_used, model_used, filtered_by_user }) {
  const win = document.getElementById("chatWindow");
  const wrap = document.createElement("div");
  wrap.className = "chat-message ai-msg";

  const metaUser  = filtered_by_user ? `<span class="meta-tag">user: ${filtered_by_user}</span>` : "";
  const metaModel = model_used        ? `<span class="meta-tag">${model_used}</span>` : "";

  let contextHtml = "";
  if (context_used && context_used.length > 0) {
    const chunks = context_used.map(c =>
      `<div class="context-chunk">${escapeHtml(c)}</div>`
    ).join("");
    contextHtml = `
      <div class="context-accordion">
        <button class="context-toggle" onclick="toggleContext(this)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
          ${context_used.length} context chunk${context_used.length > 1 ? "s" : ""} used
        </button>
        <div class="context-body">${chunks}</div>
      </div>`;
  }

  wrap.innerHTML = `
    <div class="chat-bubble">${escapeHtml(answer)}</div>
    <div class="chat-meta">${metaUser}${metaModel}</div>
    ${contextHtml}`;

  win.appendChild(wrap);
  win.scrollTop = win.scrollHeight;
}

function appendErrorMessage(text) {
  const win = document.getElementById("chatWindow");
  const wrap = document.createElement("div");
  wrap.className = "chat-message ai-msg";
  wrap.innerHTML = `<div class="chat-bubble" style="background:var(--danger-dim);border:1px solid rgba(244,63,94,0.25);color:#fda4af;">${escapeHtml(text)}</div>`;
  win.appendChild(wrap);
  win.scrollTop = win.scrollHeight;
}

function toggleContext(btn) {
  const body = btn.nextElementSibling;
  body.classList.toggle("open");
  const icon = btn.querySelector("svg polyline");
  icon.setAttribute("points", body.classList.contains("open") ? "18 15 12 9 6 15" : "9 18 15 12 9 6");
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ──────────────────────────────────────
   KEYBOARD SHORTCUT – Ctrl/Cmd+Enter to send
────────────────────────────────────── */
document.getElementById("askQuestion").addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") handleAsk();
});

/* ──────────────────────────────────────
   HANDLE ASK
────────────────────────────────────── */
async function handleAsk() {
  const question = document.getElementById("askQuestion").value.trim();
  const user     = document.getElementById("askUser").value.trim();

  if (!question) {
    document.getElementById("askQuestion").focus();
    return;
  }

  appendUserMessage(question);
  document.getElementById("askQuestion").value = "";

  setLoading("askBtn", true);
  showTyping();

  try {
    const params = new URLSearchParams({ question });
    if (user) params.append("user", user);

    const res = await fetch(`${BASE_URL}/ask?${params}`);
    const data = await res.json();

    removeTyping();

    if (!res.ok) {
      appendErrorMessage(data.detail || JSON.stringify(data));
    } else {
      appendAiMessage(data);
    }
  } catch (err) {
    removeTyping();
    appendErrorMessage(`Network error: ${err.message}`);
  } finally {
    setLoading("askBtn", false);
  }
}

/* ──────────────────────────────────────
   FILE SELECT (PDF)
────────────────────────────────────── */
function handleFileSelect(event) {
  const file = event.target.files[0];
  if (!file) return;
  const nameEl = document.getElementById("fileSelectedName");
  const box    = document.getElementById("fileSelected");
  nameEl.textContent = file.name;
  box.style.display = "flex";
}

// Drag & Drop
const dropzone = document.getElementById("dropzone");
dropzone.addEventListener("dragover",  e => { e.preventDefault(); dropzone.classList.add("drag-over"); });
dropzone.addEventListener("dragleave", ()  => dropzone.classList.remove("drag-over"));
dropzone.addEventListener("drop", e => {
  e.preventDefault();
  dropzone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file && file.type === "application/pdf") {
    const dt = new DataTransfer();
    dt.items.add(file);
    document.getElementById("pdfFile").files = dt.files;
    handleFileSelect({ target: { files: [file] } });
  }
});

/* ──────────────────────────────────────
   HANDLE PDF UPLOAD
────────────────────────────────────── */
async function handlePdfUpload() {
  const username = document.getElementById("pdfUsername").value.trim();
  const fileInput = document.getElementById("pdfFile");

  if (!username) return showResult("pdfResult", { type: "error", title: "Username is required." });
  if (!fileInput.files[0]) return showResult("pdfResult", { type: "error", title: "Please select a PDF file." });

  setLoading("uploadPdfBtn", true);

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  try {
    const res  = await fetch(`${BASE_URL}/upload-pdf?username=${encodeURIComponent(username)}`, {
      method: "POST",
      body: formData
    });
    const data = await res.json();

    if (!res.ok) {
      showResult("pdfResult", { type: "error", title: "Upload failed.", detail: JSON.stringify(data, null, 2) });
    } else {
      showResult("pdfResult", {
        type: "success",
        title: `✓ ${data.message}`,
        detail: `Username: ${data.username}\nChunks added: ${data.chunks_added}`
      });
      fileInput.value = "";
      document.getElementById("fileSelected").style.display = "none";
    }
  } catch (err) {
    showResult("pdfResult", { type: "error", title: "Network error.", detail: err.message });
  } finally {
    setLoading("uploadPdfBtn", false);
  }
}

/* ──────────────────────────────────────
   HANDLE ADD DOCUMENT (TEXT)
────────────────────────────────────── */
async function handleAddDocument() {
  const username = document.getElementById("docUsername").value.trim();
  const content  = document.getElementById("docContent").value.trim();

  if (!username) return showResult("docResult", { type: "error", title: "Username is required." });
  if (!content)  return showResult("docResult", { type: "error", title: "Document content is required." });

  setLoading("addDocBtn", true);

  try {
    const res  = await fetch(`${BASE_URL}/user_documents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, content })
    });
    const data = await res.json();

    if (!res.ok) {
      showResult("docResult", { type: "error", title: "Failed to add document.", detail: JSON.stringify(data, null, 2) });
    } else {
      showResult("docResult", {
        type: "success",
        title: `✓ ${data.message}`,
        detail: `Username: ${data.username}\nChunks added: ${data.chunks_added}`
      });
      document.getElementById("docContent").value = "";
    }
  } catch (err) {
    showResult("docResult", { type: "error", title: "Network error.", detail: err.message });
  } finally {
    setLoading("addDocBtn", false);
  }
}

/* ──────────────────────────────────────
   HANDLE DELETE
────────────────────────────────────── */
async function handleDelete() {
  const username = document.getElementById("deleteUsername").value.trim();
  if (!username) return showResult("deleteResult", { type: "error", title: "Username is required." });

  const confirmed = confirm(`Delete ALL documents for user "${username}"?\nThis cannot be undone.`);
  if (!confirmed) return;

  setLoading("deleteBtn", true);

  try {
    const res  = await fetch(`${BASE_URL}/user_documents/${encodeURIComponent(username)}`, {
      method: "DELETE"
    });
    const data = await res.json();

    if (!res.ok) {
      showResult("deleteResult", { type: "error", title: "Delete failed.", detail: JSON.stringify(data, null, 2) });
    } else {
      showResult("deleteResult", {
        type: "success",
        title: `✓ ${data.message}`
      });
      document.getElementById("deleteUsername").value = "";
    }
  } catch (err) {
    showResult("deleteResult", { type: "error", title: "Network error.", detail: err.message });
  } finally {
    setLoading("deleteBtn", false);
  }
}
