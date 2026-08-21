/**
 * Admin Panel Controller for SC Task Lens.
 */

async function loadAdminSettings() {
  try {
    const res = await fetch("/api/admin/settings");
    if (!res.ok) return;

    const data = await res.json();
    
    document.getElementById("admin-ui-refresh").checked = data.ui_auto_refresh_enabled;
    document.getElementById("admin-ui-interval").value = data.ui_auto_refresh_interval_seconds;
    
    document.getElementById("admin-purge-synced").checked = data.auto_purge_synced_enabled;
    document.getElementById("admin-purge-synced-days").value = data.purge_synced_days;
    
    document.getElementById("admin-purge-ignored").checked = data.auto_purge_ignored_enabled;
    document.getElementById("admin-purge-ignored-days").value = data.purge_ignored_days;
  } catch (err) {
    console.error("Failed to load admin settings", err);
  }
}

async function saveAdminSettings(event) {
  if (event) event.preventDefault();

  const payload = {
    ui_auto_refresh_enabled: document.getElementById("admin-ui-refresh").checked,
    ui_auto_refresh_interval_seconds: parseInt(document.getElementById("admin-ui-interval").value, 10),
    auto_purge_synced_enabled: document.getElementById("admin-purge-synced").checked,
    purge_synced_days: parseInt(document.getElementById("admin-purge-synced-days").value, 10),
    auto_purge_ignored_enabled: document.getElementById("admin-purge-ignored").checked,
    purge_ignored_days: parseInt(document.getElementById("admin-purge-ignored-days").value, 10)
  };

  showToast("Saving system preferences...", "info");

  try {
    const res = await fetch("/api/admin/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      showToast("System configurations saved successfully!", "success");
      loadAdminSettings();
    } else {
      const err = await res.json();
      showToast(err.detail || "Failed to save administrative settings", "error");
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

async function runDiagnostics() {
  const badge = document.getElementById("diagnostics-summary-badge");
  const logBox = document.getElementById("diagnostics-log");

  if (badge) {
    badge.textContent = "Running...";
    badge.className = "connection-badge status-disconnected";
  }

  showToast("Executing health check diagnostics...", "loading");

  try {
    const res = await fetch("/api/admin/diagnostics/run", { method: "POST" });
    const data = await res.json();

    if (badge) {
      if (data.overall_status === "ok") {
        badge.textContent = "Healthy";
        badge.className = "connection-badge status-connected";
      } else if (data.overall_status === "warning") {
        badge.textContent = "Warning";
        badge.className = "connection-badge status-disconnected";
        badge.style.backgroundColor = "rgba(245, 158, 11, 0.15)";
        badge.style.color = "#fde047";
        badge.style.borderColor = "rgba(245, 158, 11, 0.3)";
      } else {
        badge.textContent = "Error";
        badge.className = "connection-badge status-disconnected";
      }
    }

    if (logBox) {
      logBox.style.display = "block";
      logBox.innerHTML = Object.entries(data.results).map(([key, check]) => {
        return `
          <div class="diagnostics-row">
            [${check.latency_ms}ms] <span class="font-semibold">${escapeHtml(check.name)}</span>: 
            <span class="diagnostics-status ${check.status}">${check.status.toUpperCase()}</span>
            <div style="color:var(--text-dim); margin-left:15px; font-size:11px;">${escapeHtml(check.details)}</div>
          </div>
        `;
      }).join("");
    }

    showToast("Diagnostics complete!", "success");
  } catch (err) {
    showToast(`Diagnostics run failed: ${err.message}`, "error");
    if (badge) {
      badge.textContent = "Diagnostics Failed";
      badge.className = "connection-badge status-disconnected";
    }
  }
}

/* Backups Import Modal */
function openConfigImportModal() {
  const modal = document.getElementById("config-import-modal");
  if (modal) modal.classList.add("active");
}

function closeConfigImportModal(event, force = false) {
  const modal = document.getElementById("config-import-modal");
  if (!modal) return;
  if (force || event.target === modal) {
    modal.classList.remove("active");
  }
}

function handleConfigImport(event) {
  event.preventDefault();
  
  const fileInput = document.getElementById("config-file-input");
  if (!fileInput || fileInput.files.length === 0) return;

  const file = fileInput.files[0];
  const reader = new FileReader();

  reader.onload = async function(e) {
    try {
      const configData = JSON.parse(e.target.result);
      showToast("Uploading configuration backup...", "loading");

      const res = await fetch("/api/admin/config/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(configData)
      });

      if (res.ok) {
        showToast("System configurations imported successfully!", "success");
        closeConfigImportModal(null, true);
        loadAdminSettings();
        loadNotionConfig();
      } else {
        const err = await res.json();
        showToast(err.detail || "Import failed", "error");
      }
    } catch (err) {
      showToast("Invalid JSON config backup file format.", "error");
    }
  };

  reader.readAsText(file);
}

/* Danger Zone actions */
async function purgeIgnoredDanger() {
  if (!confirm("Are you sure you want to permanently delete all ignored candidates and screenshots? This cannot be undone.")) return;

  try {
    const res = await fetch("/api/admin/danger/purge-ignored", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, "success");
      loadCandidates();
    }
  } catch (err) {
    showToast("Failed to purge ignored candidates", "error");
  }
}

async function resetSettingsDanger() {
  if (!confirm("Are you sure you want to reset system preferences back to factory defaults?")) return;

  try {
    const res = await fetch("/api/admin/danger/reset-settings", { method: "POST" });
    if (res.ok) {
      showToast("Administrative preferences reset to defaults.", "success");
      loadAdminSettings();
    }
  } catch (err) {
    showToast("Failed to reset preferences", "error");
  }
}

async function clearAllInboxDanger() {
  if (!confirm("⚠️ WARNING: This will permanently delete ALL task candidates and screenshots. This action is completely irreversible. Are you sure?")) return;

  try {
    const res = await fetch("/api/inbox/clear-all", { method: "DELETE" });
    if (res.ok) {
      showToast("Inbox data purged completely.", "success");
      loadCandidates();
    }
  } catch (err) {
    showToast("Failed to purge inbox", "error");
  }
}
