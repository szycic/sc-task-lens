/**
 * AI Settings Controller for SC Task Lens.
 */

const PROVIDER_MODELS = {
  mock: [
    { value: "", label: "Offline Mock (No Model Required)" }
  ],
  groq: [
    { value: "llama-3.2-11b-vision-preview", label: "Llama 3.2 11B Vision (Recommended - Fast & Free/Cheap)" },
    { value: "llama-3.2-90b-vision-preview", label: "Llama 3.2 90B Vision (Highly Accurate)" }
  ],
  openai: [
    { value: "gpt-4o-mini", label: "GPT-4o mini (Recommended - Balanced)" },
    { value: "gpt-4o", label: "GPT-4o (High Quality)" }
  ],
  gemini: [
    { value: "gemini-1.5-flash", label: "Gemini 1.5 Flash (Fast)" },
    { value: "gemini-1.5-pro", label: "Gemini 1.5 Pro (Powerful)" }
  ]
};

function toggleAIProviderFields(provider) {
  const apiKeyGroup = document.getElementById("ai-api-key-group");
  const modelNameGroup = document.getElementById("ai-model-name-group");
  const statusEl = document.getElementById("ai-connection-status");
  const modelSelect = document.getElementById("ai-model-name");

  if (provider === "mock") {
    if (apiKeyGroup) apiKeyGroup.style.display = "none";
    if (modelNameGroup) modelNameGroup.style.display = "none";
    if (statusEl) {
      statusEl.textContent = "Bypassed (Offline)";
      statusEl.className = "connection-badge status-connected";
    }
  } else {
    if (apiKeyGroup) apiKeyGroup.style.display = "flex";
    if (modelNameGroup) modelNameGroup.style.display = "flex";
    if (statusEl) {
      statusEl.textContent = "Untested";
      statusEl.className = "connection-badge status-disconnected";
    }

    // Populate model options
    if (modelSelect) {
      const models = PROVIDER_MODELS[provider] || [];
      modelSelect.innerHTML = models.map(m => `<option value="${m.value}">${m.label}</option>`).join("");
    }
  }
}

async function loadAISettings() {
  try {
    const res = await fetch("/api/ai/settings");
    if (!res.ok) return;

    const data = await res.json();
    const providerSelect = document.getElementById("ai-provider");
    const keyInput = document.getElementById("ai-api-key");
    const promptInput = document.getElementById("ai-custom-prompt");
    const statusEl = document.getElementById("ai-connection-status");

    if (providerSelect) {
      providerSelect.value = data.provider;
      toggleAIProviderFields(data.provider);
    }

    if (keyInput && data.api_key_configured) {
      keyInput.placeholder = "••••••••••••••••••••••••••••••••";
    }

    // Select the saved model
    const modelSelect = document.getElementById("ai-model-name");
    if (modelSelect && data.model_name) {
      modelSelect.value = data.model_name;
    }

    if (promptInput && data.custom_prompt) {
      promptInput.value = data.custom_prompt;
    }

    if (statusEl && data.provider !== "mock") {
      if (data.api_key_configured) {
        statusEl.textContent = "Configured (Untested)";
        statusEl.className = "connection-badge status-connected";
      } else {
        statusEl.textContent = "Key Missing";
        statusEl.className = "connection-badge status-disconnected";
      }
    }
  } catch (err) {
    console.error("AI Settings load error", err);
  }
}

async function saveAISettings(event) {
  if (event) event.preventDefault();

  const provider = document.getElementById("ai-provider").value;
  const apiKey = document.getElementById("ai-api-key").value;
  const modelName = document.getElementById("ai-model-name").value;
  const customPrompt = document.getElementById("ai-custom-prompt").value;

  showToast("Saving AI settings...", "info");

  try {
    const res = await fetch("/api/ai/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider,
        api_key: apiKey ? apiKey : null,
        model_name: modelName,
        custom_prompt: customPrompt
      })
    });

    if (res.ok) {
      showToast("AI preferences saved successfully!", "success");
      loadAISettings();
    } else {
      const err = await res.json();
      showToast(err.detail || "Failed to save AI preferences", "error");
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

async function testAIConnection() {
  const provider = document.getElementById("ai-provider").value;
  const apiKey = document.getElementById("ai-api-key").value;
  const modelName = document.getElementById("ai-model-name").value;
  const statusEl = document.getElementById("ai-connection-status");

  showToast("Testing AI vision API connectivity...", "loading");

  try {
    const res = await fetch("/api/ai/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider,
        api_key: apiKey ? apiKey : null,
        model_name: modelName
      })
    });

    const data = await res.json();
    if (res.ok) {
      showToast("AI vision connection verified successfully!", "success");
      if (statusEl) {
        statusEl.textContent = "Verified Connected";
        statusEl.className = "connection-badge status-connected";
      }
    } else {
      showToast(data.detail || "AI API test failed", "error");
      if (statusEl) {
        statusEl.textContent = "Verification Failed";
        statusEl.className = "connection-badge status-disconnected";
      }
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}
