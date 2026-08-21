/**
 * Notion Integration Settings & Field Mapping Controller for SC Task Lens.
 */

let fetchedNotionProperties = [];
let currentFieldMappings = [];

async function loadNotionConfig() {
  try {
    const res = await fetch("/api/notion/config");
    if (!res.ok) return;

    const data = await res.json();
    const tokenInput = document.getElementById("notion-api-token");
    const dbInput = document.getElementById("notion-database-id");
    const statusEl = document.getElementById("notion-connection-status");
    const mappingCard = document.getElementById("mapping-card");

    if (tokenInput && data.api_token_configured) {
      tokenInput.placeholder = "••••••••••••••••••••••••••••••••";
    }
    if (dbInput && data.database_id) {
      dbInput.value = data.database_id;
    }

    if (statusEl) {
      if (data.api_token_configured && data.database_id) {
        statusEl.textContent = `Connected to: ${data.database_title || 'Notion Database'}`;
        statusEl.className = "connection-badge status-connected";
        if (mappingCard) mappingCard.style.display = "block";
      } else {
        statusEl.textContent = "Not Configured";
        statusEl.className = "connection-badge status-disconnected";
        if (mappingCard) mappingCard.style.display = "none";
      }
    }

    if (data.last_schema_json) {
      try {
        fetchedNotionProperties = JSON.parse(data.last_schema_json) || [];
      } catch (e) {}
    }
    await loadNotionMapping();
  } catch (err) {
    console.error("Notion config error", err);
    loadNotionMapping();
  }
}

async function saveNotionConfig(event) {
  if (event) event.preventDefault();
  
  const apiToken = document.getElementById("notion-api-token").value;
  const dbId = document.getElementById("notion-database-id").value;

  if (!dbId) {
    showToast("Please enter a valid Notion Database ID", "error");
    return;
  }

  showToast("Saving Notion Config & fetching schema...", "info");

  try {
    const res = await fetch("/api/notion/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_token: apiToken, database_id: dbId })
    });

    const data = await res.json();
    if (res.ok) {
      showToast("Notion details saved!", "success");
      loadNotionConfig();
      fetchNotionSchema();
    } else {
      showToast(data.detail || "Error saving config", "error");
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

async function fetchNotionSchema() {
  showToast("Fetching Database Properties from Notion API...", "info");
  try {
    const res = await fetch("/api/notion/fetch-schema", { method: "POST" });
    const data = await res.json();

    if (res.ok && data.properties) {
      fetchedNotionProperties = data.properties;
      showToast(`Found ${data.properties.length} database properties!`, "success");
      loadNotionMapping();
    } else {
      showToast(data.detail || "Failed to fetch schema", "error");
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

async function loadNotionMapping() {
  const container = document.getElementById("mapping-table-body");
  if (!container) return;

  try {
    const res = await fetch("/api/notion/mapping");
    if (!res.ok) return;

    const mappings = await res.json();
    currentFieldMappings = mappings;
    renderMappingTable(mappings);
  } catch (err) {
    console.error("Load mapping error", err);
  }
}

function renderMappingTable(mappings) {
  const container = document.getElementById("mapping-table-body");
  if (!container) return;

  container.innerHTML = mappings.map(m => {
    const propOptionsList = [...fetchedNotionProperties];
    if (m.notion_property_name && !propOptionsList.some(p => p.name === m.notion_property_name)) {
      propOptionsList.push({ name: m.notion_property_name, type: m.notion_property_type || "property" });
    }

    const matchedProp = fetchedNotionProperties.find(p => p.name === m.notion_property_name);
    const availableOptions = matchedProp && matchedProp.options ? matchedProp.options : [];

    const selectOptions = [
      `<option value="">-- Ignore / Do Not Map --</option>`,
      ...propOptionsList.map(p => {
        const isSelected = p.name === m.notion_property_name;
        return `<option value="${escapeHtml(p.name)}" data-type="${p.type}" ${isSelected ? 'selected' : ''}>
          ${escapeHtml(p.name)} (${p.type})
        </option>`;
      })
    ].join("");

    let valMapObj = {};
    if (m.value_mappings_json) {
      try { valMapObj = JSON.parse(m.value_mappings_json) || {}; } catch (e) {}
    }

    const showValMapping = m.task_field === "priority" && availableOptions.length > 0;

    let valueMappingFormHtml = "";
    if (showValMapping) {
      valueMappingFormHtml = `
        <div style="margin-top:10px; background:rgba(0,0,0,0.15); padding:10px; border-radius:6px; border:1px solid var(--border-color);">
          <div style="font-size:12px; font-weight:600; color:var(--text-main); margin-bottom:8px;">Map Priority Select Options</div>
          <div style="display:flex; flex-direction:column; gap:6px;">
            ${["HIGH", "MEDIUM", "LOW"].map(prio => {
              const currentVal = valMapObj[prio] || "";
              return `
                <div style="display:flex; align-items:center; gap:8px;">
                  <span style="font-size:11px; width:70px; color:var(--text-muted);">${prio}:</span>
                  <select class="value-mapping-select select-input" data-source-val="${prio}" style="padding:4px 8px; font-size:12px;">
                    <option value="">-- Leave Unmapped / Use Option name --</option>
                    ${availableOptions.map(opt => `<option value="${escapeHtml(opt)}" ${opt === currentVal ? 'selected' : ''}>${escapeHtml(opt)}</option>`).join("")}
                  </select>
                </div>
              `;
            }).join("")}
          </div>
        </div>
      `;
    }

    return `
      <tr data-field="${m.task_field}">
        <td>
          <strong style="color:var(--text-main); font-size:14px;">${escapeHtml(m.label)}</strong>
          <div style="font-size:12px; color:var(--text-dim);">${escapeHtml(m.description)}</div>
        </td>
        <td>
          <select class="mapping-notion-prop-select select-input" onchange="handleMappingPropChange(this)" style="padding:6px 10px; font-size:13px;">
            ${selectOptions}
          </select>
        </td>
        <td>
          <span class="status-badge" style="font-size:11px; background:rgba(255,255,255,0.05); border:1px solid var(--border-color);" id="prop-type-${m.task_field}">
            ${escapeHtml(m.notion_property_type || "None")}
          </span>
        </td>
        <td>
          <div id="mapping-options-wrap-${m.task_field}">
            ${showValMapping ? valueMappingFormHtml : `<span style="font-size:12px; color:var(--text-dim);">${m.notion_property_type === 'files' ? 'Attachments upload automatically' : 'Direct mapping (No mapping options required)'}</span>`}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function handleMappingPropChange(selectEl) {
  const tr = selectEl.closest("tr");
  const field = tr.getAttribute("data-field");
  const selectedOpt = selectEl.options[selectEl.selectedIndex];
  const propType = selectedOpt.getAttribute("data-type") || "None";

  const typeEl = document.getElementById(`prop-type-${field}`);
  if (typeEl) typeEl.textContent = propType;

  // Refresh mapping table body row if we selected a select type for priority
  const matchedProp = fetchedNotionProperties.find(p => p.name === selectEl.value);
  const availableOptions = matchedProp && matchedProp.options ? matchedProp.options : [];
  const optionsWrap = document.getElementById(`mapping-options-wrap-${field}`);

  if (optionsWrap) {
    if (field === "priority" && availableOptions.length > 0) {
      optionsWrap.innerHTML = `
        <div style="margin-top:10px; background:rgba(0,0,0,0.15); padding:10px; border-radius:6px; border:1px solid var(--border-color);">
          <div style="font-size:12px; font-weight:600; color:var(--text-main); margin-bottom:8px;">Map Priority Select Options</div>
          <div style="display:flex; flex-direction:column; gap:6px;">
            ${["HIGH", "MEDIUM", "LOW"].map(prio => {
              return `
                <div style="display:flex; align-items:center; gap:8px;">
                  <span style="font-size:11px; width:70px; color:var(--text-muted);">${prio}:</span>
                  <select class="value-mapping-select select-input" data-source-val="${prio}" style="padding:4px 8px; font-size:12px;">
                    <option value="">-- Leave Unmapped --</option>
                    ${availableOptions.map(opt => `<option value="${escapeHtml(opt)}">${escapeHtml(opt)}</option>`).join("")}
                  </select>
                </div>
              `;
            }).join("")}
          </div>
        </div>
      `;
    } else {
      optionsWrap.innerHTML = `<span style="font-size:12px; color:var(--text-dim);">${propType === 'files' ? 'Attachments upload automatically' : 'Direct mapping (No mapping options required)'}</span>`;
    }
  }
}

async function saveFieldMappings() {
  const rows = document.querySelectorAll("#mapping-table-body tr");
  const mappings = [];

  rows.forEach(tr => {
    const taskField = tr.getAttribute("data-field");
    const selectProp = tr.querySelector(".mapping-notion-prop-select");
    const notionPropName = selectProp.value;
    const selectedOpt = selectProp.options[selectProp.selectedIndex];
    const notionPropType = selectedOpt.getAttribute("data-type") || "";

    // Serialize value mappings if priority
    let valueMappingsJson = null;
    if (taskField === "priority") {
      const valSelects = tr.querySelectorAll(".value-mapping-select");
      if (valSelects.length > 0) {
        const valMap = {};
        valSelects.forEach(sel => {
          const sourceVal = sel.getAttribute("data-source-val");
          const targetVal = sel.value;
          if (targetVal) {
            valMap[sourceVal] = targetVal;
          }
        });
        valueMappingsJson = JSON.stringify(valMap);
      }
    }

    mappings.push({
      task_field: taskField,
      notion_property_name: notionPropName,
      notion_property_type: notionPropType,
      value_mappings_json: valueMappingsJson
    });
  });

  try {
    const res = await fetch("/api/notion/mapping", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mappings })
    });
    if (res.ok) {
      showToast("Notion field mappings saved successfully!", "success");
      loadNotionConfig();
    } else {
      const err = await res.json();
      showToast(err.detail || "Failed to save mapping config", "error");
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}
