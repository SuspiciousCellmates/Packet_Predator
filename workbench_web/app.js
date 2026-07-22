const state = {
  examples: [],
  selectedId: null,
  current: null,
};

const elements = Object.fromEntries([
  "carrierStatus", "authorityStatus", "exampleCount", "exampleSearch", "exampleList",
  "frameInput", "frameMode", "inputByteCount", "inspectButton", "errorPanel",
  "errorCode", "errorMessage", "emptyState", "resultPanel", "starterExample",
  "resultFamily", "resultTitle", "resultSummary", "messageValue", "representation",
  "routeSource", "routeSourceValue", "routeDestination", "routeDestinationValue",
  "logicalSize", "fieldCount", "resultByteCount", "deliveryLabel", "deliveryRaw",
  "revisionLabel", "producerList", "consumerList", "fieldTable", "byteStrip",
  "wireGeneration", "bodyLength", "headerMessageType", "headerRoute", "journalCard", "journalList",
].map((id) => [id, document.getElementById(id)]));

function escaped(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function prettyRole(value) {
  return String(value).replaceAll("_", " ").toLowerCase().replace(/(^|\s)\S/g, (letter) => letter.toUpperCase());
}

function compactHex(value) {
  return value.trim().replace(/^0x/i, "").replace(/[\s:_-]+/g, "");
}

function updateByteCount() {
  const compact = compactHex(elements.frameInput.value);
  const count = compact.length ? Math.floor(compact.length / 2) : 0;
  const suffix = compact.length % 2 ? " + half byte" : "";
  elements.inputByteCount.textContent = `${count} byte${count === 1 ? "" : "s"}${suffix}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.error) {
    const detail = body.error || { code: `HTTP_${response.status}`, message: "The workbench returned an unexpected response." };
    throw detail;
  }
  return body;
}

function showError(detail) {
  elements.errorCode.textContent = prettyRole(detail.code || "Inspection error");
  elements.errorMessage.textContent = detail.message || "The frame could not be inspected.";
  elements.errorPanel.hidden = false;
}

function clearError() {
  elements.errorPanel.hidden = true;
}

function renderExamples() {
  const needle = elements.exampleSearch.value.trim().toLowerCase();
  const filtered = state.examples.filter((item) =>
    !needle || item.name.toLowerCase().includes(needle) || item.family.label.toLowerCase().includes(needle)
  );
  const groups = new Map();
  filtered.forEach((item) => {
    if (!groups.has(item.family.label)) groups.set(item.family.label, []);
    groups.get(item.family.label).push(item);
  });
  if (!filtered.length) {
    elements.exampleList.innerHTML = '<div class="loading-block">No examples match that search.</div>';
    return;
  }
  elements.exampleList.innerHTML = [...groups.entries()].map(([family, items]) => `
    <div class="family-label">${escaped(family)}</div>
    ${items.map((item) => `
      <button class="example-button ${item.id === state.selectedId ? "active" : ""}" type="button" data-example="${escaped(item.id)}">
        <span class="example-code">0x${String(item.frame_hex.slice(2, 4)).toUpperCase()}</span>
        <span class="example-copy"><strong>${escaped(item.display_name)}</strong><small>${escaped(item.source_label)} → ${escaped(item.destination_label)}</small></span>
      </button>`).join("")}
  `).join("");
  elements.exampleList.querySelectorAll("[data-example]").forEach((button) => {
    button.addEventListener("click", () => chooseExample(button.dataset.example));
  });
}

function chooseExample(id) {
  const item = state.examples.find((candidate) => candidate.id === id);
  if (!item) return;
  state.selectedId = id;
  const fixed = elements.frameMode.value === "fixed";
  elements.frameInput.value = fixed ? item.padded_frame_hex : item.frame_hex;
  elements.frameInput.dataset.origin = `contract example: ${item.id}`;
  renderExamples();
  updateByteCount();
  inspectFrame();
}

function valueText(row) {
  if (typeof row.value === "string") return row.value.toUpperCase();
  return String(row.value);
}

function annotationText(annotation) {
  if (!annotation) return '<span class="meaning-chip">Raw value</span>';
  if (annotation.kind === "enum") return `<span class="meaning-chip">${escaped(prettyRole(annotation.name))}</span>`;
  if (annotation.kind === "flags") {
    const names = (annotation.names || []).map(prettyRole).join(", ") || "No flags set";
    return `<span class="meaning-chip">${escaped(names)}</span>`;
  }
  return '<span class="meaning-chip">Annotated</span>';
}

function renderResult(item) {
  state.current = item;
  elements.emptyState.hidden = true;
  elements.resultPanel.hidden = false;
  elements.resultFamily.textContent = item.family.label;
  elements.resultTitle.textContent = item.title;
  elements.resultSummary.textContent = item.summary;
  elements.messageValue.textContent = `${item.envelope.message_type_hex} · ${item.meaning.name}`;
  elements.representation.textContent = item.representation;
  elements.routeSource.textContent = item.route.source_label;
  elements.routeSourceValue.textContent = `address ${item.route.source}`;
  elements.routeDestination.textContent = item.route.destination_label;
  elements.routeDestinationValue.textContent = `address ${item.route.destination}`;
  elements.logicalSize.textContent = `${item.logical_bytes} logical bytes`;
  elements.fieldCount.textContent = item.field_rows.length;
  elements.resultByteCount.textContent = item.received_bytes;
  elements.deliveryLabel.textContent = item.meaning.delivery_label;
  elements.deliveryRaw.textContent = item.meaning.delivery;
  elements.revisionLabel.textContent = item.meaning.revision_label;
  elements.producerList.textContent = item.route.producers.map(prettyRole).join(" · ");
  elements.consumerList.textContent = item.route.consumers.map(prettyRole).join(" · ");
  elements.wireGeneration.textContent = item.envelope.wire_generation;
  elements.bodyLength.textContent = `${item.envelope.payload_length} bytes`;
  elements.headerMessageType.textContent = `${item.envelope.message_type_hex} / ${item.envelope.message_type}`;
  elements.headerRoute.textContent = `${item.envelope.source} → ${item.envelope.destination}`;

  elements.fieldTable.innerHTML = item.field_rows.map((row) => `
    <tr>
      <td><strong>${escaped(row.label)}</strong><small>${escaped(row.name)} · ${escaped(row.type)}</small></td>
      <td>${annotationText(row.annotation)}</td>
      <td class="numeric">${escaped(valueText(row))}</td>
      <td class="wire-value">${escaped(row.value_hex)}</td>
      <td class="numeric">${row.offset}–${row.offset + row.size - 1}</td>
    </tr>
  `).join("");
  elements.byteStrip.innerHTML = item.byte_rows.map((byte) => `
    <div class="byte-cell ${escaped(byte.section)}" tabindex="0" title="${escaped(byte.role)} · decimal ${byte.decimal}">
      <strong>${escaped(byte.hex)}</strong><small>${String(byte.offset).padStart(2, "0")}</small>
    </div>
  `).join("");
  renderJournal();
  elements.resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function inspectFrame() {
  clearError();
  elements.inspectButton.disabled = true;
  elements.inspectButton.firstChild.textContent = "Inspecting ";
  try {
    const item = await api("/api/v1/inspect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        frame_hex: elements.frameInput.value,
        mode: elements.frameMode.value,
        origin: elements.frameInput.dataset.origin || "pasted frame",
      }),
    });
    renderResult(item);
  } catch (detail) {
    showError(detail);
  } finally {
    elements.inspectButton.disabled = false;
    elements.inspectButton.firstChild.textContent = "Inspect frame ";
  }
}

async function renderJournal() {
  try {
    const result = await api("/api/inspections");
    elements.journalCard.hidden = result.count === 0;
    elements.journalList.innerHTML = result.entries.slice(0, 5).map((entry) => `
      <div class="journal-entry">
        <div><strong>${escaped(entry.title)}</strong><small>${escaped(entry.origin)} · ${escaped(entry.summary)}</small></div>
        <time datetime="${escaped(entry.observed_at)}">${new Date(entry.observed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
      </div>
    `).join("");
  } catch (_) {
    elements.journalCard.hidden = true;
  }
}

function bindTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => {
        const selected = item === tab;
        item.classList.toggle("active", selected);
        item.setAttribute("aria-selected", selected ? "true" : "false");
      });
      document.querySelectorAll(".tab-panel").forEach((panel) => {
        const selected = panel.id === `tab-${tab.dataset.tab}`;
        panel.classList.toggle("active", selected);
        panel.hidden = !selected;
      });
    });
  });
}

async function initialise() {
  bindTabs();
  try {
    const [status, examples] = await Promise.all([api("/api/status"), api("/api/v1/examples")]);
    elements.carrierStatus.innerHTML = `<i></i> ${escaped(status.carrier.label)} · no radio`;
    elements.authorityStatus.textContent = `Contract ${status.authority.authority_version}`;
    elements.authorityStatus.classList.add("ready");
    state.examples = examples.examples;
    elements.exampleCount.textContent = `${examples.example_count} frames`;
    renderExamples();
  } catch (detail) {
    elements.exampleList.innerHTML = '<div class="loading-block">The shared contract could not be loaded.</div>';
    elements.authorityStatus.textContent = "Contract unavailable";
    showError(detail);
  }
}

elements.exampleSearch.addEventListener("input", renderExamples);
elements.frameInput.addEventListener("input", () => {
  elements.frameInput.dataset.origin = "pasted frame";
  updateByteCount();
});
elements.frameMode.addEventListener("change", () => {
  if (state.selectedId) {
    const item = state.examples.find((candidate) => candidate.id === state.selectedId);
    if (item) {
      elements.frameInput.value = elements.frameMode.value === "fixed" ? item.padded_frame_hex : item.frame_hex;
      updateByteCount();
    }
  }
});
elements.inspectButton.addEventListener("click", inspectFrame);
elements.frameInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") inspectFrame();
});
elements.starterExample.addEventListener("click", () => {
  const starter = state.examples.find((item) => item.name === "NODE_HELLO") || state.examples[0];
  if (starter) chooseExample(starter.id);
});

initialise();
