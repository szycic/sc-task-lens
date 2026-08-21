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
  document.getElementById("review-project").value = "";
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
      document.getElementById("review-priority").value = data.priority || "MEDIUM";
      document.getElementById("review-project").value = data.project || "";
      
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
          btnSync.innerHTML = "✅ Synced to Notion";
          btnSync.disabled = true;
          btnSync.className = "btn btn-outline btn-sm";
        } else {
          btnSync.innerHTML = "🚀 Push to Notion";
          btnSync.disabled = false;
          btnSync.className = "btn btn-success btn-sm";
        }
      }

      if (btnIgnore) {
        if (data.status === "IGNORED") {
          btnIgnore.innerHTML = "🔄 Unignore";
          btnIgnore.onclick = unignoreCandidateReview;
        } else {
          btnIgnore.innerHTML = "🚫 Ignore";
          btnIgnore.onclick = ignoreCandidateReview;
        }
      }

      modal.classList.add("active");
    })
    .catch(err => {
      showToast("Could not retrieve candidate details.", "error");
      console.error(err);
    });
}

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
  if (!activeReviewCandidateId) return;

  const payload = {
    title: document.getElementById("review-title").value.trim(),
    summary: document.getElementById("review-summary").value.trim(),
    priority: document.getElementById("review-priority").value,
    project: document.getElementById("review-project").value.trim(),
    start_date: document.getElementById("review-start-date").value || null,
    deadline: document.getElementById("review-deadline").value || null,
    source_url: document.getElementById("review-source-url").value.trim() || null
  };

  fetch(`/api/inbox/candidates/${activeReviewCandidateId}`, {
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
    })
    .catch(err => {
      showToast("Failed to save changes.", "error");
      console.error(err);
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
      document.getElementById("review-priority").value = data.priority || "MEDIUM";
      document.getElementById("review-project").value = data.project || "";
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
  saveTaskReviewForm();

  const toast = showToast("Uploading attachment & pushing task to Notion...", "loading", true);

  fetch(`/api/inbox/candidates/${activeReviewCandidateId}/create-task`, {
    method: "POST"
  })
    .then(res => {
      if (!res.ok) throw new Error("Sync failed");
      return res.json();
    })
    .then(data => {
      toast.update("Successfully created Notion task page!", "success");
      setTimeout(() => toast.dismiss(), 2000);
      
      const modal = document.getElementById("task-review-modal");
      if (modal) modal.classList.remove("active");
      
      loadCandidates();
    })
    .catch(err => {
      toast.update("Failed to sync to Notion. Ensure your database mappings are correct.", "error");
      setTimeout(() => toast.dismiss(), 4000);
      console.error(err);
    });
}
