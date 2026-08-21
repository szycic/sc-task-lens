/**
 * SC Task Lens Application Bootstrap and Global Keyboard Shortcuts.
 */

document.addEventListener("DOMContentLoaded", async () => {
  initTabs();
  initInboxStateFromUrl();
  loadCandidates();
  initUploadDropzone();
  await loadNotionConfig();
  loadAISettings();
  await loadAdminSettings();
  connectWebSocket();

  // Register Service Worker for PWA / Notifications
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker
      .register("/sw.js")
      .then((reg) => console.log("Service Worker registered successfully!"))
      .catch((err) => console.error("Service Worker registration failed:", err));
  }

  // Initialize keyboard shortcut event listeners
  document.addEventListener("keydown", handleGlobalKeydown);
});

// Shortcuts Help Modal helper
function toggleShortcutsHelpModal(forceState) {
  const modal = document.getElementById("shortcuts-help-modal");
  if (!modal) return;
  const isOpen = modal.classList.contains("active");
  const shouldOpen = forceState !== undefined ? forceState : !isOpen;

  if (shouldOpen) {
    modal.classList.add("active");
  } else {
    modal.classList.remove("active");
  }
}

function closeShortcutsHelpModal(event, force = false) {
  const modal = document.getElementById("shortcuts-help-modal");
  if (!modal) return;
  if (force || event.target === modal) {
    modal.classList.remove("active");
  }
}

function handleGlobalKeydown(e) {
  // Ignore shortcuts if the user is typing in a form input, select, or textarea
  const tag = e.target.tagName.toLowerCase();
  if (tag === "input" || tag === "select" || tag === "textarea" || e.target.isContentEditable) {
    return;
  }

  const focusedCard = document.querySelector(".candidate-card:focus") || document.querySelector(".candidate-card.focused");
  const visibleCards = document.querySelectorAll(".candidate-card");

  // ESC: Close all open modals
  if (e.key === "Escape") {
    closeTaskReviewModal(null, true);
    closeShortcutsHelpModal(null, true);
    closeConfigImportModal(null, true);
    return;
  }

  // '?': Toggle shortcuts help modal
  if (e.key === "?") {
    e.preventDefault();
    toggleShortcutsHelpModal();
    return;
  }

  // Handle card navigation (only if inbox tab is active and there are cards)
  const isInboxActive = document.getElementById("tab-inbox").classList.contains("active");
  if (!isInboxActive || visibleCards.length === 0) return;

  if (e.key === "j" || e.key === "ArrowDown") {
    e.preventDefault();
    focusedCandidateIndex = (focusedCandidateIndex + 1) % visibleCards.length;
    visibleCards[focusedCandidateIndex].focus();
    visibleCards[focusedCandidateIndex].scrollIntoView({ block: "nearest", behavior: "smooth" });
  } 
  else if (e.key === "k" || e.key === "ArrowUp") {
    e.preventDefault();
    focusedCandidateIndex = (focusedCandidateIndex - 1 + visibleCards.length) % visibleCards.length;
    visibleCards[focusedCandidateIndex].focus();
    visibleCards[focusedCandidateIndex].scrollIntoView({ block: "nearest", behavior: "smooth" });
  } 
  else if (e.key === "Space") {
    // Space: Toggle selection checkbox on focused card
    if (focusedCard) {
      e.preventDefault();
      const cb = focusedCard.querySelector(".candidate-select-cb");
      if (cb) {
        cb.checked = !cb.checked;
        const cid = parseInt(cb.getAttribute("data-id"), 10);
        toggleCandidateSelection(cid, cb.checked);
      }
    }
  } 
  else if (e.key === "Enter" || e.key === "o") {
    // Enter or 'o': Open review modal on focused card
    if (focusedCard) {
      e.preventDefault();
      const cb = focusedCard.querySelector(".candidate-select-cb");
      if (cb) {
        const cid = parseInt(cb.getAttribute("data-id"), 10);
        openTaskReviewModal(cid);
      }
    }
  }
  else if (e.key === "a") {
    // 'a': Toggle select all
    e.preventDefault();
    const selectAllCb = document.getElementById("select-all-cb");
    if (selectAllCb) {
      selectAllCb.checked = !selectAllCb.checked;
      toggleSelectAllCandidates(selectAllCb.checked);
    }
  }
  else if (e.key === "i") {
    // 'i': Ignore focused candidate
    if (focusedCard) {
      e.preventDefault();
      const cb = focusedCard.querySelector(".candidate-select-cb");
      if (cb) {
        const cid = parseInt(cb.getAttribute("data-id"), 10);
        activeReviewCandidateId = cid;
        ignoreCandidateReview();
      }
    }
  }
  else if (e.key === "r") {
    // 'r': Re-run AI Vision on focused card
    if (focusedCard) {
      e.preventDefault();
      const cb = focusedCard.querySelector(".candidate-select-cb");
      if (cb) {
        const cid = parseInt(cb.getAttribute("data-id"), 10);
        activeReviewCandidateId = cid;
        reanalyzeCandidateReview();
      }
    }
  }
  else if (e.key === "p") {
    // 'p': Push focused card to Notion directly
    if (focusedCard) {
      e.preventDefault();
      const cb = focusedCard.querySelector(".candidate-select-cb");
      if (cb) {
        const cid = parseInt(cb.getAttribute("data-id"), 10);
        activeReviewCandidateId = cid;
        syncCandidateReview();
      }
    }
  }
}
