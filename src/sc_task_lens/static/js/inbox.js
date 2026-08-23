/**
 * Inbox Candidate List, File Uploads, and WebSocket Controller for SC Task Lens.
 */

let currentCandidates = [];
let currentStatusFilter = "PENDING";
let currentPage = 1;
let pageSize = 12;
let totalCandidates = 0;
let totalPages = 1;

let lastSyncedIso = null;
let searchDebounceTimer = null;
let selectedCandidateIds = new Set();
let focusedCandidateIndex = -1;

function initInboxStateFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const statusParam = params.get("status");
  const pageParam = params.get("page");
  const searchParam = params.get("search");

  if (statusParam) {
    const validStatuses = ["PENDING", "AI_PROCESSED", "CREATED", "IGNORED", "ALL"];
    if (validStatuses.includes(statusParam.toUpperCase())) {
      currentStatusFilter = statusParam.toUpperCase();
      document.querySelectorAll(".inbox-filter-btn").forEach(b => b.classList.remove("active"));
      const btn = document.getElementById(`filter-btn-${currentStatusFilter}`);
      if (btn) btn.classList.add("active");
    }
  }

  if (pageParam) {
    const p = parseInt(pageParam, 10);
    if (!isNaN(p) && p >= 1) currentPage = p;
  }

  if (searchParam) {
    const searchInput = document.getElementById("filter-search");
    if (searchInput) searchInput.value = searchParam;
  }
}

function updateUrlParams() {
  const url = new URL(window.location);

  if (currentStatusFilter && currentStatusFilter !== "PENDING") {
    url.searchParams.set("status", currentStatusFilter);
  } else {
    url.searchParams.delete("status");
  }

  if (currentPage && currentPage > 1) {
    url.searchParams.set("page", currentPage);
  } else {
    url.searchParams.delete("page");
  }

  const searchVal = document.getElementById("filter-search")?.value?.trim();
  if (searchVal) {
    url.searchParams.set("search", searchVal);
  } else {
    url.searchParams.delete("search");
  }

  const newUrl = url.pathname + url.search + url.hash;
  if (window.location.pathname + window.location.search + window.location.hash !== newUrl) {
    history.replaceState(null, "", newUrl);
  }
}

function toggleCandidateSelection(candidateId, isChecked) {
  if (isChecked) {
    selectedCandidateIds.add(candidateId);
  } else {
    selectedCandidateIds.delete(candidateId);
  }
  updateBulkActionUI();
}

function toggleSelectAllCandidates(isChecked) {
  const visibleCbs = document.querySelectorAll(".candidate-select-cb");
  visibleCbs.forEach(cb => {
    cb.checked = isChecked;
    const id = parseInt(cb.getAttribute("data-id"), 10);
    if (id) {
      if (isChecked) selectedCandidateIds.add(id);
      else selectedCandidateIds.delete(id);
    }
  });
  updateBulkActionUI();
}

function updateBulkActionUI() {
  const bulkBar = document.getElementById("bulk-action-bar");
  if (currentStatusFilter === "ALL") {
    if (bulkBar) bulkBar.style.display = "none";
    return;
  }
  if (bulkBar) bulkBar.style.display = "flex";

  const count = selectedCandidateIds.size;
  const countEl = document.getElementById("bulk-selected-count");
  if (countEl) countEl.textContent = `(${count} selected)`;

  const btnProcess = document.getElementById("btn-bulk-process");
  const btnReprocess = document.getElementById("btn-bulk-reprocess");
  const btnNotion = document.getElementById("btn-bulk-notion");
  const btnIgnore = document.getElementById("btn-bulk-ignore");
  const btnUnignore = document.getElementById("btn-bulk-unignore");

  if (btnProcess) {
    btnProcess.style.display = currentStatusFilter === "PENDING" ? "inline-flex" : "none";
    btnProcess.disabled = count === 0;
  }

  if (btnReprocess) {
    btnReprocess.style.display = currentStatusFilter === "AI_PROCESSED" ? "inline-flex" : "none";
    btnReprocess.disabled = count === 0;
  }

  if (btnNotion) {
    btnNotion.style.display = currentStatusFilter === "CREATED" ? "inline-flex" : "none";
    btnNotion.disabled = count === 0;
  }

  if (btnIgnore) {
    const showIgnore = currentStatusFilter !== "IGNORED" && currentStatusFilter !== "CREATED";
    btnIgnore.style.display = showIgnore ? "inline-flex" : "none";
    btnIgnore.disabled = count === 0;
  }

  if (btnUnignore) {
    btnUnignore.style.display = currentStatusFilter === "IGNORED" ? "inline-flex" : "none";
    btnUnignore.disabled = count === 0;
  }
}

function filterInbox(status) {
  currentStatusFilter = status;
  currentPage = 1;
  selectedCandidateIds.clear();
  const selectAllCb = document.getElementById("select-all-cb");
  if (selectAllCb) selectAllCb.checked = false;

  document.querySelectorAll(".inbox-filter-btn").forEach(b => {
    b.classList.remove("active");
  });
  const activeBtn = document.getElementById(`filter-btn-${status}`);
  if (activeBtn) activeBtn.classList.add("active");

  updateUrlParams();
  loadCandidates();
  updateBulkActionUI();
}

function handleSearchInput() {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    currentPage = 1;
    updateUrlParams();
    loadCandidates();
  }, 300);
}

function loadCandidates() {
  const searchVal = document.getElementById("filter-search")?.value?.trim() || "";
  const sortVal = document.getElementById("sort-candidates")?.value || "NEWEST";

  let url = `/api/inbox/candidates?status=${currentStatusFilter}&page=${currentPage}&page_size=${pageSize}&sort_by=${sortVal}`;
  if (searchVal) {
    url += `&search=${encodeURIComponent(searchVal)}`;
  }

  fetch(url)
    .then(res => res.json())
    .then(data => {
      currentCandidates = data.items || [];
      totalCandidates = data.total || 0;
      totalPages = data.total_pages || 1;
      currentPage = data.page || 1;

      renderCandidates();
      renderPagination();
      updateFilterBadges();
      updateBulkActionUI();
    })
    .catch(err => {
      showToast("Failed to load task candidates.", "error");
      console.error(err);
    });
}

function updateFilterBadges() {
  fetch("/api/inbox/stats")
    .then(res => res.json())
    .then(data => {
      const counts = data.counts || {};
      for (const [status, count] of Object.entries(counts)) {
        const badge = document.getElementById(`badge-${status}`);
        if (badge) badge.textContent = count;
      }

      const lastSyncedIndicator = document.getElementById("last-synced-indicator");
      if (lastSyncedIndicator && data.last_synced_at) {
        lastSyncedIso = data.last_synced_at;
        lastSyncedIndicator.textContent = `Last updated: ${formatTimeAgo(data.last_synced_at)}`;
      }
    })
    .catch(err => console.error(err));
}

function renderCandidates() {
  const container = document.getElementById("candidates-list");
  if (!container) return;

  if (currentCandidates.length === 0) {
    container.className = "empty-state-container";
    container.innerHTML = `
      <div class="empty-state" style="padding: 60px 20px; text-align: center; color: var(--text-muted);">
        <div class="empty-icon" style="font-size: 48px; margin-bottom: 12px; opacity: 0.35;">📷</div>
        <h3>No task candidates found</h3>
        <p style="font-size: 13px;">Upload screenshots to extract tasks and sync them to Notion.</p>
      </div>
    `;
    return;
  }

  container.className = "candidates-grid";
  container.innerHTML = currentCandidates.map((c, idx) => {
    const isSelected = selectedCandidateIds.has(c.id);
    const timeAgoStr = formatTimeAgo(c.created_at);
    const borderClass = c.priority ? `${c.priority.toLowerCase()}-importance` : '';

    let thumbnailHtml = `<div class="candidate-thumbnail-placeholder">📄</div>`;
    if (c.screenshot_url) {
      thumbnailHtml = `<img src="${c.screenshot_url}" class="candidate-thumbnail-img" loading="lazy">`;
    }

    return `
      <div class="candidate-card ${borderClass} ${focusedCandidateIndex === idx ? 'focused' : ''}" 
           tabindex="0" 
           onclick="handleCardClick(event, ${c.id})"
           onfocus="focusedCandidateIndex = ${idx}">
        
        <div class="candidate-thumbnail-box">
          ${thumbnailHtml}
        </div>

        <div class="candidate-card-body">
          <div class="candidate-card-header">
            <input type="checkbox" 
                   class="candidate-select-cb" 
                   data-id="${c.id}" 
                   ${isSelected ? 'checked' : ''} 
                   onclick="handleCheckboxClick(event, ${c.id})">
            
            ${c.priority ? `<span class="importance-badge ${c.priority}">${c.priority}</span>` : ''}
          </div>

          <h3 class="candidate-card-title">${escapeHtml(c.title)}</h3>
          <p class="candidate-card-desc">${escapeHtml(c.summary || "No description generated.")}</p>
          
          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">
            <div class="candidate-card-meta" style="margin-top:0; padding-top:0;">
              <span>📅 ${timeAgoStr}</span>
            </div>
            ${c.status === "PENDING" ? `
              <button class="btn btn-primary btn-xs card-process-btn" 
                      onclick="processSingleCandidate(event, ${c.id})"
                      style="font-size:11px; padding:2px 8px; border-radius:4px; margin-left:8px; line-height:1.2;">
                🤖 Process
              </button>
            ` : ''}
            ${c.notion_url ? `
              <a href="${c.notion_url}" target="_blank" class="btn btn-success btn-xs"
                 onclick="event.stopPropagation();"
                 style="font-size:11px; padding:2px 8px; border-radius:4px; margin-left:8px; line-height:1.2; text-decoration:none; display:inline-flex; align-items:center;">
                🔗 Open in Notion
              </a>
            ` : ''}
          </div>
        </div>
      </div>
    `;
  }).join("");
}

function handleCardClick(event, candidateId) {
  // Prevent opening modal if checkbox was clicked
  if (event.target.classList.contains("candidate-select-cb")) {
    return;
  }
  openTaskReviewModal(candidateId);
}

function handleCheckboxClick(event, candidateId) {
  event.stopPropagation();
  toggleCandidateSelection(candidateId, event.target.checked);
}

function renderPagination() {
  const container = document.getElementById("inbox-pagination");
  if (!container) return;

  if (totalPages <= 1) {
    container.innerHTML = "";
    return;
  }

  let html = `
    <button class="btn btn-outline btn-sm" onclick="changePage(1)" ${currentPage === 1 ? 'disabled' : ''}>&laquo;</button>
    <button class="btn btn-outline btn-sm" onclick="changePage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>&lsaquo;</button>
  `;

  const maxVisiblePages = 5;
  let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
  let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

  if (endPage - startPage + 1 < maxVisiblePages) {
    startPage = Math.max(1, endPage - maxVisiblePages + 1);
  }

  for (let i = startPage; i <= endPage; i++) {
    html += `
      <button class="btn ${i === currentPage ? 'btn-primary' : 'btn-outline'} btn-sm" onclick="changePage(${i})">${i}</button>
    `;
  }

  html += `
    <button class="btn btn-outline btn-sm" onclick="changePage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''}>&rsaquo;</button>
    <button class="btn btn-outline btn-sm" onclick="changePage(${totalPages})" ${currentPage === totalPages ? 'disabled' : ''}>&raquo;</button>
  `;

  container.innerHTML = html;
}

function changePage(page) {
  if (page < 1 || page > totalPages) return;
  currentPage = page;
  updateUrlParams();
  loadCandidates();
}

/* Drag and Drop Upload logic */
function initUploadDropzone() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");

  if (!dropzone || !fileInput) return;

  dropzone.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      uploadFiles(e.target.files);
    }
  });

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragover");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
      uploadFiles(e.dataTransfer.files);
    }
  });

  // Handle global paste event for screenshots in clipboard
  document.addEventListener("paste", (e) => {
    // Ignore paste if target is an input/textarea/editable
    const tag = e.target.tagName.toLowerCase();
    if (tag === "input" || tag === "select" || tag === "textarea" || e.target.isContentEditable) {
      return;
    }

    const items = (e.clipboardData || window.clipboardData).items;
    const filesToUpload = [];
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf("image") !== -1) {
        const file = items[i].getAsFile();
        if (file) {
          const renamedFile = new File([file], `clipboard_${Date.now()}.png`, { type: file.type });
          filesToUpload.push(renamedFile);
        }
      }
    }
    if (filesToUpload.length > 0) {
      uploadFiles(filesToUpload);
    }
  });
}

function uploadFiles(files) {
  Array.from(files).forEach(file => {
    if (!file.type.startsWith("image/")) {
      showToast(`${file.name} is not an image file.`, "error");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    const toast = showToast(`Uploading ${file.name}...`, "loading", true);

    fetch("/api/inbox/upload", {
      method: "POST",
      body: formData
    })
      .then(res => {
        if (!res.ok) throw new Error("Upload failed");
        return res.json();
      })
      .then(data => {
        toast.update(`Successfully uploaded ${file.name}.`, "success");
        setTimeout(() => toast.dismiss(), 2000);
        loadCandidates();
      })

      .catch(err => {
        toast.update(`Failed to upload ${file.name}.`, "error");
        setTimeout(() => toast.dismiss(), 4000);
      });
  });
}

/* Batch Operations */
function bulkProcessCandidates() {
  if (selectedCandidateIds.size === 0) return;
  const ids = Array.from(selectedCandidateIds);
  const toast = showToast(`Processing ${ids.length} candidates in background...`, "loading", true);

  fetch("/api/inbox/candidates/batch-process", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_ids: ids })
  })
    .then(res => res.json())
    .then(data => {
      toast.update(`Processing started in background!`, "success");
      setTimeout(() => toast.dismiss(), 3000);
      selectedCandidateIds.clear();
      const selectAllCb = document.getElementById("select-all-cb");
      if (selectAllCb) selectAllCb.checked = false;
      loadCandidates();
    })
    .catch(err => {
      toast.update("Batch processing failed.", "error");
      setTimeout(() => toast.dismiss(), 3000);
    });
}

function bulkReprocessCandidates() {
  if (selectedCandidateIds.size === 0) return;
  const ids = Array.from(selectedCandidateIds);
  const toast = showToast(`Reprocessing ${ids.length} candidates in background...`, "loading", true);

  fetch("/api/inbox/candidates/batch-process", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_ids: ids })
  })
    .then(res => res.json())
    .then(data => {
      toast.update(`Reprocessing started in background!`, "success");
      setTimeout(() => toast.dismiss(), 3000);
      selectedCandidateIds.clear();
      const selectAllCb = document.getElementById("select-all-cb");
      if (selectAllCb) selectAllCb.checked = false;
      loadCandidates();
    })
    .catch(err => {
      toast.update("Batch reprocessing failed.", "error");
      setTimeout(() => toast.dismiss(), 3000);
    });
}

function bulkIgnoreCandidates() {
  if (selectedCandidateIds.size === 0) return;
  const ids = Array.from(selectedCandidateIds);

  fetch("/api/inbox/candidates/batch-ignore", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_ids: ids })
  })
    .then(res => res.json())
    .then(() => {
      showToast(`Successfully ignored ${ids.length} candidates.`, "success");
      selectedCandidateIds.clear();
      loadCandidates();
    })
    .catch(() => showToast("Batch ignore failed.", "error"));
}

function bulkUnignoreCandidates() {
  if (selectedCandidateIds.size === 0) return;
  const ids = Array.from(selectedCandidateIds);

  fetch("/api/inbox/candidates/batch-unignore", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_ids: ids })
  })
    .then(res => res.json())
    .then(() => {
      showToast(`Successfully restored ${ids.length} candidates.`, "success");
      selectedCandidateIds.clear();
      loadCandidates();
    })
    .catch(() => showToast("Batch restore failed.", "error"));
}

/* WebSocket Listener */
let wsConn = null;
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/api/inbox/ws/sync-updates`;

  if (wsConn) {
    try { wsConn.close(); } catch (e) { }
  }

  wsConn = new WebSocket(wsUrl);

  wsConn.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.event === "sync_completed") {
        updateFilterBadges();
        // Only refresh list if on page 1 or if candidate list has changed
        if (currentPage === 1) {
          loadCandidates();
        }
      }
    } catch (e) {
      console.error("WebSocket message parsing error:", e);
    }
  };

  wsConn.onclose = () => {
    // Reconnect after 5 seconds
    setTimeout(connectWebSocket, 5000);
  };

  wsConn.onerror = () => {
    wsConn.close();
  };
}

// Add animation style for spinner
const style = document.createElement('style');
style.innerHTML = `
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  .toast-spin {
    display: inline-block;
    animation: spin 1.5s linear infinite;
  }
`;
document.head.appendChild(style);

function processSingleCandidate(event, candidateId) {
  event.stopPropagation();
  const toast = showToast("Running AI Vision extraction...", "loading", true);
  fetch(`/api/inbox/candidates/${candidateId}/prepare-task?force=true`, {
    method: "POST"
  })
    .then(res => {
      if (!res.ok) throw new Error("Analysis failed");
      return res.json();
    })
    .then(data => {
      toast.update("Analysis completed successfully!", "success");
      setTimeout(() => toast.dismiss(), 2000);
      loadCandidates();
    })
    .catch(err => {
      toast.update("AI Vision analysis failed.", "error");
      setTimeout(() => toast.dismiss(), 3000);
      console.error(err);
    });
}

function bulkOpenNotionTasks() {
  if (selectedCandidateIds.size === 0) return;
  let openedCount = 0;

  currentCandidates.forEach(c => {
    if (selectedCandidateIds.has(c.id) && c.notion_url) {
      window.open(c.notion_url, "_blank");
      openedCount++;
    }
  });

  if (openedCount > 0) {
    showToast(`Opened ${openedCount} Notion task(s)`, "info");
  } else {
    showToast("No Notion links available for selected candidates", "warning");
  }
}
