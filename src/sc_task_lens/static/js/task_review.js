/**
 * Task Candidate Review Modal Controller for SC Task Lens.
 */

let activeReviewCandidateId = null;

function openTaskReviewModal(candidateId) {
  activeReviewCandidateId = candidateId;

  const modal = document.getElementById("task-review-modal");
  if (!modal) return;

  // Clear fields initially
  document.getElementById("review-candidate-id").value = "";
  document.getElementById("review-title").value = "Loading...";
  document.getElementById("review-summary").value = "";
  document.getElementById("review-priority").value = "MEDIUM";
  document.getElementById("review-start-date").value = "";
  document.getElementById("review-deadline").value = "";
  document.getElementById("review-source-url").value = "";
  document.getElementById("review-screenshot-img").src = "";
  document.getElementById("review-screenshot-link").href = "";

  fetch(`/api/inbox/candidates/${candidateId}`)
    .then(res => {
      if (!res.ok) throw new Error("Failed to load candidate");
      return res.json();
    })
    .then(data => {
      document.getElementById("review-candidate-id").value = data.id;
      document.getElementById("review-title").value = data.title || "";
      document.getElementById("review-summary").value = data.summary || "";
      updatePriorityDropdownInModal(data);
      
      // Format dates for picker (YYYY-MM-DD)
      document.getElementById("review-start-date").value = formatDateForPicker(data.start_date);
      document.getElementById("review-deadline").value = formatDateForPicker(data.deadline);
      document.getElementById("review-source-url").value = data.source_url || "";

      // Load Screenshot Image
      if (data.screenshot_url) {
        document.getElementById("review-screenshot-img").src = data.screenshot_url;
        document.getElementById("review-screenshot-link").href = data.screenshot_url;
      }

      // Configure Action Buttons depending on status
      const btnSync = document.getElementById("review-btn-sync");
      const btnIgnore = document.getElementById("review-btn-ignore");

      if (btnSync) {
        if (data.status === "CREATED") {
          btnSync.innerHTML = "🔄 Update in Notion";
          btnSync.disabled = false;
          btnSync.className = "btn btn-success btn-sm";
        } else {
          btnSync.innerHTML = "🚀 Push to Notion";
          btnSync.disabled = false;
          btnSync.className = "btn btn-success btn-sm";
        }
      }

      if (btnIgnore) {
        if (data.status === "CREATED") {
          btnIgnore.style.display = "none";
        } else {
          btnIgnore.style.display = "";
          if (data.status === "IGNORED") {
            btnIgnore.innerHTML = "🔄 Unignore";
            btnIgnore.onclick = unignoreCandidateReview;
          } else {
            btnIgnore.innerHTML = "🚫 Ignore";
            btnIgnore.onclick = ignoreCandidateReview;
          }
        }
      }

      const btnReanalyze = document.getElementById("review-btn-reanalyze");
      if (btnReanalyze) {
        if (data.status === "PENDING") {
          btnReanalyze.innerHTML = "🤖 Process";
        } else {
          btnReanalyze.innerHTML = "🤖 Reprocess";
        }
      }

      switchReviewTab("form");
      modal.classList.add("active");
    })
    .catch(err => {
      showToast("Could not retrieve candidate details.", "error");
      console.error(err);
    });
}

function switchReviewTab(tabName) {
  const layout = document.getElementById("review-split-layout");
  const btnForm = document.getElementById("review-tab-btn-form");
  const btnImage = document.getElementById("review-tab-btn-image");

  if (layout) {
    layout.setAttribute("data-active-tab", tabName);
  }

  if (tabName === "image") {
    btnForm?.classList.remove("active");
    btnForm?.setAttribute("aria-selected", "false");
    btnImage?.classList.add("active");
    btnImage?.setAttribute("aria-selected", "true");
  } else {
    btnImage?.classList.remove("active");
    btnImage?.setAttribute("aria-selected", "false");
    btnForm?.classList.add("active");
    btnForm?.setAttribute("aria-selected", "true");
  }
}
window.switchReviewTab = switchReviewTab;

function closeTaskReviewModal(event, force = false) {
  const modal = document.getElementById("task-review-modal");
  if (!modal) return;

  // Close only if clicking background or close button
  if (force || event.target === modal) {
    modal.classList.remove("active");
    activeReviewCandidateId = null;
  }
}

function saveTaskReviewForm(event) {
  if (event) event.preventDefault();
  if (!activeReviewCandidateId) return Promise.resolve();

  const payload = {
    title: document.getElementById("review-title").value.trim(),
    summary: document.getElementById("review-summary").value.trim(),
    priority: document.getElementById("review-priority").value,
    start_date: document.getElementById("review-start-date").value || null,
    deadline: document.getElementById("review-deadline").value || null,
    source_url: document.getElementById("review-source-url").value.trim() || null
  };

  return fetch(`/api/inbox/candidates/${activeReviewCandidateId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })
    .then(res => {
      if (!res.ok) throw new Error("Save failed");
      return res.json();
    })
    .then(data => {
      showToast("Changes saved successfully.", "success");
      loadCandidates();
      return data;
    })
    .catch(err => {
      showToast("Failed to save changes.", "error");
      console.error(err);
      throw err;
    });
}

function reanalyzeCandidateReview() {
  if (!activeReviewCandidateId) return;
  const toast = showToast("Running AI Vision extraction...", "loading", true);

  fetch(`/api/inbox/candidates/${activeReviewCandidateId}/prepare-task?force=true`, {
    method: "POST"
  })
    .then(res => {
      if (!res.ok) throw new Error("Analysis failed");
      return res.json();
    })
    .then(data => {
      toast.update("Analysis completed successfully!", "success");
      setTimeout(() => toast.dismiss(), 2000);
      
      // Update form fields
      document.getElementById("review-title").value = data.title || "";
      document.getElementById("review-summary").value = data.summary || "";
      updatePriorityDropdownInModal(data);
      document.getElementById("review-start-date").value = formatDateForPicker(data.start_date);
      document.getElementById("review-deadline").value = formatDateForPicker(data.deadline);
      document.getElementById("review-source-url").value = data.source_url || "";
      
      loadCandidates();
    })
    .catch(err => {
      toast.update("AI Vision analysis failed.", "error");
      setTimeout(() => toast.dismiss(), 3000);
      console.error(err);
    });
}

function ignoreCandidateReview() {
  if (!activeReviewCandidateId) return;

  fetch(`/api/inbox/candidates/${activeReviewCandidateId}/ignore`, {
    method: "POST"
  })
    .then(res => {
      if (!res.ok) throw new Error("Ignore failed");
      return res.json();
    })
    .then(() => {
      showToast("Candidate marked as Ignored.", "success");
      const modal = document.getElementById("task-review-modal");
      if (modal) modal.classList.remove("active");
      loadCandidates();
    })
    .catch(err => console.error(err));
}

function unignoreCandidateReview() {
  if (!activeReviewCandidateId) return;

  fetch(`/api/inbox/candidates/${activeReviewCandidateId}/unignore`, {
    method: "POST"
  })
    .then(res => {
      if (!res.ok) throw new Error("Unignore failed");
      return res.json();
    })
    .then(() => {
      showToast("Candidate restored successfully.", "success");
      const modal = document.getElementById("task-review-modal");
      if (modal) modal.classList.remove("active");
      loadCandidates();
    })
    .catch(err => console.error(err));
}

function deleteCandidateReview() {
  if (!activeReviewCandidateId) return;
  if (!confirm("Are you sure you want to permanently delete this screenshot and task candidate?")) return;

  fetch(`/api/inbox/candidates/${activeReviewCandidateId}`, {
    method: "DELETE"
  })
    .then(res => {
      if (!res.ok) throw new Error("Delete failed");
      return res.json();
    })
    .then(() => {
      showToast("Candidate deleted successfully.", "success");
      const modal = document.getElementById("task-review-modal");
      if (modal) modal.classList.remove("active");
      loadCandidates();
    })
    .catch(err => console.error(err));
}

function syncCandidateReview() {
  if (!activeReviewCandidateId) return;
  
  // Save form edits first
  saveTaskReviewForm()
    .then(() => {
      const toast = showToast("Uploading attachment & pushing task to Notion...", "loading", true);

      fetch(`/api/inbox/candidates/${activeReviewCandidateId}/create-task`, {
        method: "POST"
      })
        .then(async res => {
          if (!res.ok) {
            let errMsg = "Sync failed";
            try {
              const errData = await res.json();
              if (errData && errData.detail) errMsg = errData.detail;
            } catch(e) {}
            throw new Error(errMsg);
          }
          return res.json();
        })
        .then(data => {
          const msg = data.updated ? "Successfully updated Notion task page!" : "Successfully created Notion task page!";
          toast.update(msg, "success");
          setTimeout(() => toast.dismiss(), 2000);
          
          const modal = document.getElementById("task-review-modal");
          if (modal) modal.classList.remove("active");
          
          loadCandidates();
        })
        .catch(err => {
          toast.update(`Failed to sync to Notion: ${err.message}`, "error");
          setTimeout(() => toast.dismiss(), 6000);
          console.error(err);
        });
    })
    .catch(err => {
      console.error("Sync aborted because save failed:", err);
    });
}

function updatePriorityDropdownInModal(candidate) {
  const prioritySelect = document.getElementById("review-priority");
  if (!prioritySelect) return;

  const priorityMapping = currentFieldMappings.find(m => m.task_field === "priority");
  let options = [];

  if (priorityMapping && priorityMapping.notion_property_name) {
    const matchedProp = fetchedNotionProperties.find(p => p.name === priorityMapping.notion_property_name);
    if (matchedProp && matchedProp.options && matchedProp.options.length > 0) {
      options = [...matchedProp.options];
    }

    if (priorityMapping.value_mappings_json) {
      try {
        const valMapObj = JSON.parse(priorityMapping.value_mappings_json);
        if (typeof valMapObj === "object") {
          Object.values(valMapObj).forEach(val => {
            if (val && !options.includes(val)) {
              options.push(val);
            }
          });
        }
      } catch (e) { }
    }
  }

  if (options.length === 0) {
    options = ["HIGH", "MEDIUM", "LOW"];
  }

  prioritySelect.innerHTML = options.map(opt => `<option value="${escapeHtml(opt)}">${escapeHtml(opt)}</option>`).join("");

  let targetVal = candidate.priority || "MEDIUM";
  if (priorityMapping && priorityMapping.value_mappings_json) {
    try {
      const valMapObj = JSON.parse(priorityMapping.value_mappings_json);
      if (valMapObj[targetVal]) {
        targetVal = valMapObj[targetVal];
      }
    } catch (e) { }
  }

  // Case-insensitive match against allowed Notion schema options
  let matchedOption = options.find(opt => opt.toLowerCase() === targetVal.toLowerCase());

  if (matchedOption) {
    prioritySelect.value = matchedOption;
  } else {
    // Fallback to Medium or Normal before resorting to first option
    let defaultMatch = options.find(opt => opt.toLowerCase() === "medium" || opt.toLowerCase() === "normal") || options[0];
    if (defaultMatch) {
      prioritySelect.value = defaultMatch;
    }
  }
}
