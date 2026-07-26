const state = {
  examples: [],
  recordings: [],
  selectedId: null,
  current: null,
  replayTimer: null,
  replayBusy: false,
  physical: null,
  modelRevision: 0,
  modelStream: null,
  modelRefreshBusy: false,
  modelRefreshPending: false,
  viewConnected: false,
  editorDefinitions: new Map(),
  draft: null,
  draftRequestSerial: 0,
};

const elements = Object.fromEntries([
  "textSizePreference", "fontPreference", "carrierStatus", "authorityStatus", "exampleCount", "exampleSearch", "exampleList",
  "frameInput", "frameMode", "inputByteCount", "inspectButton", "errorPanel",
  "errorCode", "errorMessage", "emptyState", "resultPanel", "starterExample",
  "resultFamily", "resultTitle", "resultSummary", "messageValue", "representation",
  "routeSource", "routeSourceValue", "routeDestination", "routeDestinationValue",
  "logicalSize", "fieldCount", "resultByteCount", "deliveryLabel", "deliveryRaw",
  "revisionLabel", "producerList", "consumerList", "fieldTable", "byteStrip",
  "wireGeneration", "bodyLength", "headerMessageType", "headerRoute", "journalCard", "journalList",
  "recordingSelect", "recordingDescription", "replayBody", "replayStateLabel", "replayPosition",
  "replayReset", "replayStep", "replayPlay", "replayPause", "replaySpeed", "replayProgress",
  "replayFrameCount", "replaySchedule",
  "captureContext", "captureDirection", "captureIdentity", "captureNote",
  "modeEyebrow", "modeHeading", "modeDescription", "truthCard", "truthTitle", "truthDetail",
  "radioCard", "radioProfile", "radioDevices", "radioFrequency", "radioChannel", "radioAddress",
  "radioCrc", "radioActivity", "radioPins", "transmitConfirm", "transmitButton",
  "draftBar", "draftStatus", "draftProvenance", "draftUndo", "draftRedo", "draftRevert",
  "draftDiscard", "draftRouteControls", "draftSource", "draftDestination",
].map((id) => [id, document.getElementById(id)]));

function applyTextSize(preference) {
  const choices = new Set(["comfortable", "large", "extra-large"]);
  const selected = choices.has(preference) ? preference : "large";
  document.documentElement.dataset.textSize = selected;
  elements.textSizePreference.value = selected;
  try {
    window.localStorage.setItem("packet-predator-text-size", selected);
  } catch (_) {
    // The preference remains active for this page when browser storage is unavailable.
  }
}

function storedTextSize() {
  try {
    return window.localStorage.getItem("packet-predator-text-size") || "large";
  } catch (_) {
    return "large";
  }
}

function applyTypeface(preference) {
  const selected = preference === "mono" ? "mono" : "sans";
  document.documentElement.dataset.font = selected;
  elements.fontPreference.value = selected;
  try {
    window.localStorage.setItem("packet-predator-typeface", selected);
  } catch (_) {
    // The preference remains active for this page when browser storage is unavailable.
  }
}

function storedTypeface() {
  try {
    return window.localStorage.getItem("packet-predator-typeface") || "sans";
  } catch (_) {
    return "sans";
  }
}

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

function toEnumFormat(value) {
  if (!value) return "";
  return String(value)
    .trim()
    .replace(/^v1-/i, "")
    .replace(/[\s-]+/g, "_")
    .toUpperCase();
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
  elements.errorPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
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
        <span class="example-copy"><strong>${escaped(toEnumFormat(item.display_name))}</strong><small>${escaped(item.source_label)} → ${escaped(item.destination_label)}</small></span>
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

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function inspectionKey(item) {
  if (item.id) return `inspection:${item.id}`;
  if (item.capture) {
    return `capture:${item.capture.transport}:${item.capture.sequence}:${item.received_frame_hex}`;
  }
  return `frame:${item.received_frame_hex}`;
}

function exactFieldText(row) {
  if (row.type === "bytes") return String(row.value);
  const octets = String(row.value_hex).match(/[0-9A-Fa-f]{2}/g) || [];
  let value = 0n;
  octets.forEach((octet, index) => {
    value += BigInt(parseInt(octet, 16)) << (8n * BigInt(index));
  });
  return value.toString(10);
}

function draftIdentifier() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return `pp-draft-${window.crypto.randomUUID()}`;
  }
  return `pp-draft-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function draftProvenance(item) {
  if (item.capture) {
    return `${item.capture.direction} ${item.capture.transport} observation ${item.capture.sequence + 1}`;
  }
  if (item.origin) return item.origin;
  if (state.selectedId) return `Protocol Contract fixture ${state.selectedId}`;
  return "pasted inspected frame";
}

function mayReplaceDraft(item) {
  if (!state.draft || state.draft.baseKey === inspectionKey(item) || !state.draft.dirty) return true;
  return window.confirm("Discard the unsaved packet draft and inspect another frame?");
}

async function beginDraft(item) {
  if (!state.editorDefinitions.has(item.meaning.name)) return;
  const token = ++state.draftRequestSerial;
  const values = Object.fromEntries(item.field_rows.map((row) => [row.name, exactFieldText(row)]));
  const draft = {
    id: draftIdentifier(),
    baseKey: inspectionKey(item),
    baseInspection: clone(item),
    provenance: draftProvenance(item),
    baseFixedHex: "",
    history: [],
    historyIndex: -1,
    dirty: false,
    transmitRequestId: null,
  };
  state.draft = draft;
  elements.draftBar.hidden = false;
  elements.draftRouteControls.hidden = false;
  elements.draftStatus.textContent = "Validating base frame…";
  elements.draftProvenance.textContent = `Derived from ${draft.provenance} · ${draft.id}`;
  try {
    const result = await composeDraft(
      item.meaning.name,
      item.route.source,
      item.route.destination,
      values,
    );
    if (token !== state.draftRequestSerial || state.draft !== draft) return;
    const inspection = clone(result.inspection);
    inspection.capture = item.capture || null;
    inspection.id = item.id;
    inspection.origin = item.origin;
    draft.baseFixedHex = result.fixed_frame_hex;
    pushDraftSnapshot({
      valid: true,
      error: null,
      definition: result.message_name,
      source: item.route.source,
      destination: item.route.destination,
      values: result.editor_values,
      logicalHex: result.logical_frame_hex,
      fixedHex: result.fixed_frame_hex,
      inspection,
    });
  } catch (detail) {
    if (token !== state.draftRequestSerial || state.draft !== draft) return;
    state.draft = null;
    elements.draftBar.hidden = true;
    elements.draftRouteControls.hidden = true;
    showError(detail);
  }
}

async function composeDraft(definition, source, destination, values) {
  return api("/api/v1/editor/compose", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      definition,
      source,
      destination,
      values,
      representation: "fixed",
    }),
  });
}

function currentDraftSnapshot() {
  if (!state.draft || state.draft.historyIndex < 0) return null;
  return state.draft.history[state.draft.historyIndex];
}

function pushDraftSnapshot(snapshot) {
  const draft = state.draft;
  if (!draft) return;
  draft.history = draft.history.slice(0, draft.historyIndex + 1);
  draft.history.push(clone(snapshot));
  draft.historyIndex = draft.history.length - 1;
  draft.dirty = draft.historyIndex > 0;
  renderDraftSnapshot();
}

function renderDraftSnapshot() {
  const draft = state.draft;
  const snapshot = currentDraftSnapshot();
  if (!draft || !snapshot) return;
  if (snapshot.valid) {
    renderResult(snapshot.inspection, false, true);
  } else {
    renderInvalidResult({
      received_frame_hex: snapshot.fixedHex,
      received_bytes: snapshot.fixedHex.length / 2,
      summary: "Draft bytes are preserved, but Protocol Contract rejected the frame.",
      inspection_error: snapshot.error,
      capture: draft.baseInspection.capture || null,
    }, false);
  }
  elements.frameInput.value = snapshot.fixedHex;
  elements.frameInput.dataset.origin = `editable draft: ${draft.id}`;
  elements.frameMode.value = "fixed";
  updateByteCount();
  renderDraftControls();
}

function renderDraftControls() {
  const draft = state.draft;
  const snapshot = currentDraftSnapshot();
  if (!draft || !snapshot) return;
  elements.draftBar.hidden = false;
  elements.draftRouteControls.hidden = !snapshot.valid;
  elements.draftStatus.textContent = snapshot.valid
    ? `${draft.dirty ? "Valid · modified" : "Valid · unchanged"} · ${changedByteCount(snapshot.fixedHex)} changed bytes`
    : `Invalid · ${snapshot.error.code}`;
  elements.draftProvenance.textContent = `Derived from ${draft.provenance} · ${draft.id}`;
  elements.draftUndo.disabled = draft.historyIndex <= 0;
  elements.draftRedo.disabled = draft.historyIndex >= draft.history.length - 1;
  elements.draftRevert.disabled = !draft.dirty;
  if (snapshot.valid) {
    elements.draftSource.value = snapshot.source;
    elements.draftDestination.value = snapshot.destination;
    renderEditableFields(snapshot);
  }
  renderEditableBytes(snapshot.fixedHex, snapshot.valid ? snapshot.inspection : null);
  updateTransmitAvailability();
}

function changedByteCount(fixedHex) {
  const base = (state.draft && state.draft.baseFixedHex.match(/.{2}/g)) || [];
  const current = fixedHex.match(/.{2}/g) || [];
  return current.filter((value, index) => value !== base[index]).length;
}

function draftTransmitProvenance() {
  const draft = state.draft;
  const snapshot = currentDraftSnapshot();
  if (!draft || !snapshot) return null;
  const base = draft.history[0];
  const changedFields = Object.keys(snapshot.values || {}).filter(
    (name) => String(snapshot.values[name]) !== String(base.values[name])
  );
  if (snapshot.source !== base.source) changedFields.unshift("source");
  if (snapshot.destination !== base.destination) changedFields.unshift("destination");
  const baseBytes = draft.baseFixedHex.match(/.{2}/g) || [];
  const currentBytes = snapshot.fixedHex.match(/.{2}/g) || [];
  const changedBytes = currentBytes
    .map((value, index) => value !== baseBytes[index] ? index : null)
    .filter((value) => value !== null);
  return {
    draft_id: draft.id,
    base_identity: draft.baseKey,
    changed_fields: changedFields,
    changed_bytes: changedBytes,
    console_run_id: null,
  };
}

function renderEditableFields(snapshot) {
  const definition = state.editorDefinitions.get(snapshot.definition);
  if (!definition) return;
  const rows = new Map(snapshot.inspection.field_rows.map((row) => [row.name, row]));
  elements.fieldTable.innerHTML = definition.payload.fields.map((field) => {
    const row = rows.get(field.name);
    const value = snapshot.values[field.name];
    let control;
    if (field.enum_values) {
      control = `<select class="draft-field-input" data-draft-field="${escaped(field.name)}">
        ${Object.entries(field.enum_values).map(([name, number]) =>
          `<option value="${number}" ${String(number) === String(value) ? "selected" : ""}>${escaped(prettyRole(name))} · ${number}</option>`
        ).join("")}
      </select>`;
    } else {
      const bytes = field.type === "bytes";
      control = `<input class="draft-field-input ${bytes ? "hex-value" : ""}" data-draft-field="${escaped(field.name)}"
        type="text" inputmode="${bytes ? "text" : "numeric"}" value="${escaped(value)}"
        aria-label="${escaped(field.name)}">`;
    }
    return `
      <tr data-field-start="${row.offset}" data-field-size="${row.size}">
        <td><div class="field-cell"><small>[${escaped(row.type)}]</small><strong>${escaped(row.name)}</strong></div></td>
        <td>${annotationText(row.annotation)}</td>
        <td class="draft-value">${control}</td>
        <td class="wire-value">${escaped(row.value_hex)}</td>
        <td class="numeric">${row.offset}–${row.offset + row.size - 1}</td>
      </tr>`;
  }).join("");
  elements.fieldTable.querySelectorAll("[data-draft-field]").forEach((input) => {
    input.addEventListener("change", applySemanticDraftEdit);
    input.addEventListener("focus", () => highlightField(input.closest("tr"), true));
    input.addEventListener("blur", () => highlightField(input.closest("tr"), false));
  });
}

function renderEditableBytes(fixedHex, inspection) {
  const values = fixedHex.match(/.{2}/g) || [];
  const rows = inspection ? inspection.byte_rows : [];
  elements.byteStrip.innerHTML = values.map((value, offset) => {
    const row = rows[offset] || { section: "body", role: "Uninterpreted draft byte" };
    const changed = state.draft && state.draft.baseFixedHex.slice(offset * 2, offset * 2 + 2).toLowerCase() !== value.toLowerCase();
    return `
      <label class="byte-cell editable ${escaped(row.section)} ${changed ? "changed" : ""}"
        data-byte-offset="${offset}" title="${escaped(row.role)} · decimal ${parseInt(value, 16)}">
        <input value="${escaped(value.toUpperCase())}" maxlength="2" inputmode="text" aria-label="Byte ${offset}">
        <small>${String(offset).padStart(2, "0")}</small>
      </label>`;
  }).join("");
  elements.byteStrip.querySelectorAll("[data-byte-offset] input").forEach((input) => {
    input.addEventListener("change", applyByteDraftEdit);
    input.addEventListener("focus", () => highlightByte(Number(input.parentElement.dataset.byteOffset), true));
    input.addEventListener("blur", () => highlightByte(Number(input.parentElement.dataset.byteOffset), false));
  });
}

function highlightField(row, active) {
  if (!row) return;
  row.classList.toggle("linked", active);
  const start = Number(row.dataset.fieldStart);
  const size = Number(row.dataset.fieldSize);
  for (let offset = start; offset < start + size; offset += 1) {
    elements.byteStrip.querySelector(`[data-byte-offset="${offset}"]`)?.classList.toggle("linked", active);
  }
}

function highlightByte(offset, active) {
  elements.byteStrip.querySelector(`[data-byte-offset="${offset}"]`)?.classList.toggle("linked", active);
  elements.fieldTable.querySelectorAll("[data-field-start]").forEach((row) => {
    const start = Number(row.dataset.fieldStart);
    const size = Number(row.dataset.fieldSize);
    if (offset >= start && offset < start + size) row.classList.toggle("linked", active);
  });
}

async function applySemanticDraftEdit() {
  const snapshot = currentDraftSnapshot();
  if (!snapshot) return;
  const values = {};
  elements.fieldTable.querySelectorAll("[data-draft-field]").forEach((input) => {
    values[input.dataset.draftField] = input.value.trim();
  });
  const source = Number(elements.draftSource.value);
  const destination = Number(elements.draftDestination.value);
  const token = ++state.draftRequestSerial;
  try {
    const result = await composeDraft(snapshot.definition, source, destination, values);
    if (token !== state.draftRequestSerial) return;
    const inspection = clone(result.inspection);
    inspection.capture = state.draft.baseInspection.capture || null;
    pushDraftSnapshot({
      valid: true,
      error: null,
      definition: result.message_name,
      source,
      destination,
      values: result.editor_values,
      logicalHex: result.logical_frame_hex,
      fixedHex: result.fixed_frame_hex,
      inspection,
    });
    clearError();
  } catch (detail) {
    if (token !== state.draftRequestSerial) return;
    pushDraftSnapshot({
      ...clone(snapshot),
      valid: false,
      error: detail,
      source,
      destination,
      values,
    });
    showError(detail);
  }
}

async function applyByteDraftEdit() {
  const snapshot = currentDraftSnapshot();
  if (!snapshot) return;
  const inputs = [...elements.byteStrip.querySelectorAll("[data-byte-offset] input")];
  const values = inputs.map((input) => input.value.trim());
  const malformed = values.find((value) => !/^[0-9a-fA-F]{2}$/.test(value));
  const fixedHex = values.join("").toLowerCase();
  if (malformed) {
    const detail = { code: "EDITOR_BYTE_HEX", message: "Each byte must contain exactly two hexadecimal digits." };
    pushDraftSnapshot({ ...clone(snapshot), valid: false, error: detail, fixedHex });
    showError(detail);
    return;
  }
  const token = ++state.draftRequestSerial;
  try {
    const inspection = await api("/api/v1/editor/inspect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frame_hex: fixedHex, mode: "fixed", origin: "draft" }),
    });
    if (token !== state.draftRequestSerial) return;
    const definition = inspection.meaning.name;
    const result = await composeDraft(
      definition,
      inspection.route.source,
      inspection.route.destination,
      inspection.editor_values,
    );
    if (token !== state.draftRequestSerial) return;
    const canonical = clone(result.inspection);
    canonical.capture = state.draft.baseInspection.capture || null;
    pushDraftSnapshot({
      valid: true,
      error: null,
      definition,
      source: inspection.route.source,
      destination: inspection.route.destination,
      values: result.editor_values,
      logicalHex: result.logical_frame_hex,
      fixedHex: result.fixed_frame_hex,
      inspection: canonical,
    });
    clearError();
  } catch (detail) {
    if (token !== state.draftRequestSerial) return;
    pushDraftSnapshot({ ...clone(snapshot), valid: false, error: detail, fixedHex });
    showError(detail);
  }
}

function moveDraftHistory(delta) {
  if (!state.draft) return;
  const next = state.draft.historyIndex + delta;
  if (next < 0 || next >= state.draft.history.length) return;
  state.draft.historyIndex = next;
  state.draft.dirty = next > 0;
  renderDraftSnapshot();
}

function revertDraft() {
  if (!state.draft || !state.draft.history.length) return;
  state.draft.historyIndex = 0;
  state.draft.dirty = false;
  renderDraftSnapshot();
}

function discardDraft() {
  state.draftRequestSerial += 1;
  state.draft = null;
  elements.draftBar.hidden = true;
  elements.draftRouteControls.hidden = true;
  updateTransmitAvailability();
}

function renderResult(item, shouldScroll = true, preserveDraft = false) {
  if (item.inspection_error) {
    renderInvalidResult(item, shouldScroll);
    return;
  }
  if (!preserveDraft && !mayReplaceDraft(item)) return;
  clearError();
  state.current = item;
  elements.emptyState.hidden = true;
  elements.resultPanel.hidden = false;
  elements.resultFamily.textContent = item.family.label;
  elements.resultTitle.textContent = item.meaning.name;
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
  elements.captureContext.hidden = !item.capture;
  if (item.capture) {
    const physical = item.capture.transport === "nrf905";
    elements.captureDirection.textContent = physical
      ? (item.capture.direction === "received" ? "Received over nRF905" : "Transmitted over nRF905")
      : (item.capture.direction === "received" ? "Into workbench" : "Recorded outbound");
    elements.captureIdentity.textContent = physical
      ? `${item.capture.profile_id} · radio frame ${item.capture.sequence + 1} · ${item.capture.observed_at_ms} ms after adapter start`
      : `${item.capture.recording_id} · frame ${item.capture.sequence + 1} · T+${item.capture.scheduled_at_ms} ms`;
    elements.captureNote.textContent = item.capture.note;
  }

  elements.fieldTable.innerHTML = item.field_rows.map((row) => `
    <tr>
      <td><div class="field-cell"><small>[${escaped(row.type)}]</small><strong>${escaped(row.name)}</strong></div></td>
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
  if (!preserveDraft) beginDraft(item);
  if (shouldScroll) elements.resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderInvalidResult(item, shouldScroll = true) {
  state.current = item;
  elements.emptyState.hidden = true;
  elements.resultPanel.hidden = false;
  elements.resultFamily.textContent = "Invalid frame";
  elements.resultTitle.textContent = "UNDECODABLE PHYSICAL FRAME";
  elements.resultSummary.textContent = item.summary;
  elements.messageValue.textContent = item.inspection_error.code;
  elements.representation.textContent = `${item.received_bytes} received bytes`;
  elements.routeSource.textContent = "Unknown";
  elements.routeSourceValue.textContent = "Envelope could not be decoded";
  elements.routeDestination.textContent = "Unknown";
  elements.routeDestinationValue.textContent = "Envelope could not be decoded";
  elements.logicalSize.textContent = "Not available";
  elements.fieldCount.textContent = "0";
  elements.resultByteCount.textContent = item.received_bytes;
  elements.deliveryLabel.textContent = "Rejected";
  elements.deliveryRaw.textContent = item.inspection_error.code;
  elements.revisionLabel.textContent = "No decoded revision";
  elements.producerList.textContent = "Unknown";
  elements.consumerList.textContent = "Unknown";
  elements.wireGeneration.textContent = "Unknown";
  elements.bodyLength.textContent = "Unknown";
  elements.headerMessageType.textContent = "Unknown";
  elements.headerRoute.textContent = "Unknown";
  elements.captureContext.hidden = !item.capture;
  if (item.capture) {
    elements.captureDirection.textContent = "Received over nRF905";
    elements.captureIdentity.textContent = `${item.capture.profile_id} · radio frame ${item.capture.sequence + 1} · ${item.capture.observed_at_ms} ms after adapter start`;
    elements.captureNote.textContent = item.capture.note;
  }
  elements.fieldTable.innerHTML = `
    <tr>
      <td><div class="field-cell"><small>[error]</small><strong>${escaped(item.inspection_error.code)}</strong></div></td>
      <td><span class="meaning-chip">Not decoded</span></td>
      <td colspan="3">${escaped(item.inspection_error.message)}</td>
    </tr>`;
  const bytes = item.received_frame_hex.match(/.{2}/g) || [];
  elements.byteStrip.innerHTML = bytes.map((value, offset) => `
    <div class="byte-cell payload" tabindex="0" title="Uninterpreted received byte · decimal ${parseInt(value, 16)}">
      <strong>${escaped(value.toUpperCase())}</strong><small>${String(offset).padStart(2, "0")}</small>
    </div>
  `).join("");
  showError(item.inspection_error);
  if (shouldScroll) elements.resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
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
    scheduleModelRefresh();
  } catch (detail) {
    showError(detail);
  } finally {
    elements.inspectButton.disabled = false;
    elements.inspectButton.firstChild.textContent = "Inspect frame ";
  }
}

function renderJournal(result) {
  elements.journalCard.hidden = result.count === 0;
  elements.journalList.innerHTML = result.entries.slice(0, 10).map((entry) => {
      let badgeHtml = '';
      if (entry.capture && entry.capture.direction) {
        if (entry.capture.direction === "received") {
          badgeHtml = `<span class="journal-badge incoming" title="Incoming frame received"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M19 12l-7 7-7-7"/></svg> INCOMING</span>`;
        } else if (entry.capture.direction === "sent") {
          badgeHtml = `<span class="journal-badge outgoing" title="Outgoing frame transmitted"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 19V5M5 12l7-7 7 7"/></svg> OUTGOING</span>`;
        } else {
          badgeHtml = `<span class="journal-badge neutral">${escaped(entry.capture.direction)}</span>`;
        }
      } else if (entry.origin && entry.origin.includes("example")) {
        badgeHtml = `<span class="journal-badge example" title="Conformance library example"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg> EXAMPLE</span>`;
      } else {
        badgeHtml = `<span class="journal-badge pasted" title="Pasted hexadecimal frame"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M15 2H9a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V3a1 1 0 0 0-1-1z"/></svg> PASTED</span>`;
      }

      const transportDetail = entry.capture
        ? (entry.capture.transport === "nrf905"
            ? `${entry.capture.observed_at_ms} ms · RF`
            : `T+${entry.capture.scheduled_at_ms} ms`)
        : escaped(entry.origin);

      return `
        <button class="journal-entry" type="button" data-inspection="${escaped(entry.id)}">
          <div class="journal-entry-body">
            <div class="journal-entry-top">
              ${badgeHtml}
              <strong class="journal-entry-title">${escaped(entry.title)}</strong>
            </div>
            <small class="journal-entry-meta">${transportDetail} · ${escaped(entry.summary)}</small>
          </div>
          <time datetime="${escaped(entry.observed_at)}">${new Date(entry.observed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
        </button>
      `;
  }).join("");
  elements.journalList.querySelectorAll("[data-inspection]").forEach((button) => {
    button.addEventListener("click", () => openInspection(button.dataset.inspection));
  });
}

async function openInspection(id) {
  try {
    const item = await api(`/api/inspections/${encodeURIComponent(id)}`);
    renderResult(item);
  } catch (detail) {
    showError(detail);
  }
}

function populateRecordings(result) {
  state.recordings = result.recordings;
  elements.recordingSelect.innerHTML = '<option value="">Choose a recording…</option>' + result.recordings.map((item) =>
    `<option value="${escaped(item.id)}">${escaped(item.title)} · ${item.frame_count} frames</option>`
  ).join("");
  if (result.active) {
    elements.recordingSelect.value = result.active.id;
    renderReplayState({ recording: result.active, carrier: result.carrier, delivered: [] });
  }
}

function formatSeconds(milliseconds) {
  return (milliseconds / 1000).toFixed(2);
}

function renderReplayState(result) {
  const carrier = result.carrier;
  const recording = result.recording || state.recordings.find((item) => item.id === carrier.recording_id);
  if (!recording) return;
  elements.replayBody.hidden = false;
  elements.recordingDescription.textContent = recording.description;
  elements.replayStateLabel.textContent = prettyRole(carrier.state);
  elements.replayPosition.textContent = `${formatSeconds(carrier.position_ms)} / ${formatSeconds(carrier.duration_ms)} seconds · ${carrier.cursor} of ${carrier.frame_count} frames`;
  elements.replayFrameCount.textContent = `${recording.frame_count} frame${recording.frame_count === 1 ? "" : "s"}`;
  elements.replayProgress.style.width = `${carrier.duration_ms ? Math.min(100, (carrier.position_ms / carrier.duration_ms) * 100) : 0}%`;
  elements.replaySpeed.value = String(carrier.speed);
  elements.replayPlay.hidden = carrier.state === "playing";
  elements.replayPause.hidden = carrier.state !== "playing";
  elements.replayPlay.disabled = carrier.state === "complete";
  elements.replayStep.disabled = carrier.state === "playing" || carrier.state === "complete";
  elements.replayReset.disabled = carrier.state === "ready" && carrier.cursor === 0;
  elements.replaySpeed.disabled = carrier.state === "complete";
  elements.carrierStatus.innerHTML = `<i></i> ${escaped(carrier.label)} · ${escaped(carrier.state)} · ${state.physical ? "RF bench also listening" : "no radio"}`;

  elements.replaySchedule.innerHTML = recording.schedule.map((item) => {
    const statusClass = item.sequence < carrier.cursor ? "delivered" : item.sequence === carrier.cursor ? "next" : "pending";
    const arrow = item.direction === "received" ? "↓" : "↑";
    const directionLabel = item.direction === "received" ? "Into workbench" : "Recorded outbound";
    return `
      <li class="schedule-item ${escaped(item.direction)} ${statusClass}" data-sequence="${item.sequence}">
        <time>T+${item.at_ms} ms</time>
        <span class="schedule-direction" title="${directionLabel}">${arrow}</span>
        <span class="schedule-kind"><strong>${escaped(toEnumFormat(item.display_name))}</strong><small>${escaped(item.source_label)} → ${escaped(item.destination_label)}</small></span>
        <span class="schedule-note"><strong>${escaped(item.note)}</strong><small>${escaped(directionLabel)} · ${escaped(item.fixture_id)}</small></span>
      </li>`;
  }).join("");

  if (result.delivered && result.delivered.length) {
    renderResult(result.delivered[result.delivered.length - 1], false);
    scheduleModelRefresh();
    const current = elements.replaySchedule.querySelector(`[data-sequence="${result.delivered[result.delivered.length - 1].capture.sequence}"]`);
    if (current) current.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  if (carrier.state === "playing") startReplayPolling();
  else stopReplayPolling();
}

async function selectRecording() {
  const identifier = elements.recordingSelect.value;
  if (!identifier) return;
  clearError();
  stopReplayPolling();
  try {
    const result = await api("/api/replays/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recording_id: identifier }),
    });
    renderReplayState(result);
  } catch (detail) {
    showError(detail);
  }
}

async function replayAction(action, includeSpeed = false) {
  if (state.replayBusy) return;
  state.replayBusy = true;
  clearError();
  try {
    const body = { action };
    if (includeSpeed) body.speed = Number(elements.replaySpeed.value);
    const result = await api("/api/replays/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    renderReplayState(result);
  } catch (detail) {
    showError(detail);
  } finally {
    state.replayBusy = false;
  }
}

async function pollReplay() {
  if (state.replayBusy) return;
  state.replayBusy = true;
  try {
    renderReplayState(await api("/api/replays/state"));
  } catch (detail) {
    stopReplayPolling();
    showError(detail);
  } finally {
    state.replayBusy = false;
  }
}

function startReplayPolling() {
  if (!state.replayTimer) state.replayTimer = window.setInterval(pollReplay, 100);
}

function stopReplayPolling() {
  if (state.replayTimer) window.clearInterval(state.replayTimer);
  state.replayTimer = null;
}

function renderPhysicalStatus(carrier) {
  state.physical = carrier;
  const profile = carrier.profile;
  elements.radioCard.hidden = false;
  elements.radioProfile.textContent = profile.id;
  elements.radioDevices.textContent = `${profile.spi_device} · ${profile.gpio_chip}`;
  elements.radioFrequency.textContent = `${profile.frequency_mhz.toFixed(1)} MHz`;
  elements.radioChannel.textContent = `band ${profile.band} · channel ${profile.channel} · ${profile.transmit_power_dbm} dBm`;
  elements.radioAddress.textContent = profile.physical_address_hex;
  elements.radioCrc.textContent = `${profile.crc_bits}-bit hardware CRC`;
  const pins = carrier.pins || {};
  elements.radioPins.textContent = `CD ${Number(Boolean(pins.carrier_detect))} · AM ${Number(Boolean(pins.address_match))} · DR ${Number(Boolean(pins.data_ready))}`;
  elements.transmitConfirm.disabled = !carrier.can_transmit;
  elements.carrierStatus.innerHTML = `<i></i> ${escaped(carrier.label)} · listening`;
  updateTransmitAvailability();
}

function updateTransmitAvailability() {
  const draft = currentDraftSnapshot();
  const validDraft = !state.draft || (draft && draft.valid);
  elements.transmitButton.disabled = !state.physical?.can_transmit || !validDraft;
  elements.transmitButton.textContent = state.draft
    ? "Transmit valid draft"
    : "Transmit current frame";
}

function renderModelSnapshot(snapshot) {
  state.modelRevision = snapshot.revision;
  renderJournal(snapshot.journal);
  if (snapshot.physical_adapter) {
    renderPhysicalStatus(snapshot.physical_adapter);
    const receiver = snapshot.receiver;
    const stateLabel = prettyRole(receiver.state);
    elements.carrierStatus.innerHTML = `<i></i> ${escaped(snapshot.physical_adapter.label)} · ${escaped(stateLabel)}`;
    if (receiver.last_error) {
      elements.radioActivity.textContent = `Receiver fault · ${receiver.last_error.code}`;
      showError(receiver.last_error);
    } else if (snapshot.physical_adapter.status_error) {
      elements.radioActivity.textContent = `Radio status unavailable · ${snapshot.physical_adapter.status_error.code}`;
      showError(snapshot.physical_adapter.status_error);
    } else if (state.viewConnected) {
      elements.radioActivity.textContent = `Live view connected · ${receiver.received_count} received`;
    } else {
      elements.radioActivity.textContent = `View reconnecting · radio ${receiver.state}`;
    }
  }
  if (!state.draft && snapshot.latest && snapshot.latest.id !== (state.current && state.current.id)) {
    renderResult(snapshot.latest, false);
  }
}

async function refreshModel() {
  if (state.modelRefreshBusy) {
    state.modelRefreshPending = true;
    return;
  }
  state.modelRefreshBusy = true;
  try {
    renderModelSnapshot(await api("/api/workbench/state"));
  } catch (detail) {
    showError(detail);
  } finally {
    state.modelRefreshBusy = false;
    if (state.modelRefreshPending) {
      state.modelRefreshPending = false;
      refreshModel();
    }
  }
}

function scheduleModelRefresh() {
  if (state.modelRefreshPending) return;
  state.modelRefreshPending = true;
  window.requestAnimationFrame(() => {
    state.modelRefreshPending = false;
    refreshModel();
  });
}

function connectModelStream() {
  if (!("EventSource" in window)) {
    showError({
      code: "LIVE_VIEW_UNSUPPORTED",
      message: "This browser cannot subscribe to live workbench updates. Use a current browser.",
    });
    return;
  }
  if (state.modelStream) state.modelStream.close();
  state.modelStream = new EventSource(`/api/workbench/events?after=${state.modelRevision}`);
  state.modelStream.onopen = () => {
    state.viewConnected = true;
    scheduleModelRefresh();
  };
  state.modelStream.addEventListener("model", scheduleModelRefresh);
  state.modelStream.addEventListener("resync", scheduleModelRefresh);
  state.modelStream.onerror = () => {
    state.viewConnected = false;
    if (state.physical) {
      elements.radioActivity.textContent = "Live view reconnecting · radio reception continues";
    }
  };
}

async function transmitFrame() {
  clearError();
  if (!elements.transmitConfirm.checked) {
    showError({ code: "TRANSMIT_CONFIRMATION_REQUIRED", message: "Tick the one-transmission confirmation first." });
    return;
  }
  const snapshot = currentDraftSnapshot();
  if (state.draft && (!snapshot || !snapshot.valid)) {
    showError({
      code: "EDITOR_DRAFT_INVALID",
      message: "Undo, revert, or correct the draft before transmitting.",
    });
    return;
  }
  const requestId = state.draft
    ? (state.draft.transmitRequestId ||= `browser-${state.draft.id}-${Date.now()}`)
    : null;
  elements.transmitButton.disabled = true;
  try {
    const result = await api("/api/carrier/transmit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        frame_hex: snapshot ? snapshot.fixedHex : elements.frameInput.value,
        mode: snapshot ? "fixed" : elements.frameMode.value,
        confirmed: true,
        request_id: requestId,
        provenance: draftTransmitProvenance(),
      }),
    });
    elements.transmitConfirm.checked = false;
    if (result.outcome === "unknown") {
      elements.radioActivity.textContent = "Transmission outcome unknown · do not resend";
      showError(result.error || {
        code: "TRANSMISSION_OUTCOME_UNKNOWN",
        message: "The adapter outcome is unknown. Recover this same request identity; do not create another RF action.",
      });
      return;
    }
    renderPhysicalStatus(result.carrier);
    elements.radioActivity.textContent = result.replayed_result
      ? "Recovered prior transmit result · no second RF send"
      : "Frame transmitted";
    if (result.delivered.length) renderResult(result.delivered[0], false, true);
    if (state.draft) state.draft.transmitRequestId = null;
    scheduleModelRefresh();
  } catch (detail) {
    showError(detail);
  } finally {
    updateTransmitAvailability();
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

function bindInputTabs() {
  document.querySelectorAll(".input-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".input-tab").forEach((item) => {
        const selected = item === tab;
        item.classList.toggle("active", selected);
        item.setAttribute("aria-selected", selected ? "true" : "false");
      });
      document.querySelectorAll(".input-tab-panel").forEach((panel) => {
        const selected = panel.id === `input-panel-${tab.dataset.inputTab}`;
        panel.classList.toggle("active", selected);
        panel.hidden = !selected;
      });
    });
  });
}

async function initialise() {
  applyTextSize(storedTextSize());
  applyTypeface(storedTypeface());
  bindTabs();
  bindInputTabs();
  try {
    const [status, examples, replays, model, editor] = await Promise.all([
      api("/api/status"),
      api("/api/v1/examples"),
      api("/api/replays"),
      api("/api/workbench/state"),
      api("/api/v1/editor/messages"),
    ]);
    elements.carrierStatus.innerHTML = `<i></i> ${escaped(status.carrier.label)} · ${status.physical_adapter ? "listening" : "no radio"}`;
    elements.authorityStatus.textContent = `Contract ${status.authority.authority_version}`;
    elements.authorityStatus.classList.add("ready");
    state.examples = examples.examples;
    state.editorDefinitions = new Map(
      editor.messages.map((definition) => [definition.name, definition])
    );
    elements.exampleCount.textContent = `${examples.example_count} frames`;
    renderExamples();
    populateRecordings(replays);
    renderModelSnapshot(model);
    connectModelStream();
  } catch (detail) {
    elements.exampleList.innerHTML = '<div class="loading-block">The shared contract could not be loaded.</div>';
    elements.authorityStatus.textContent = "Contract unavailable";
    showError(detail);
  }
}

elements.exampleSearch.addEventListener("input", renderExamples);
elements.textSizePreference.addEventListener("change", () => applyTextSize(elements.textSizePreference.value));
elements.fontPreference.addEventListener("change", () => applyTypeface(elements.fontPreference.value));
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
elements.transmitButton.addEventListener("click", transmitFrame);
elements.draftSource.addEventListener("change", applySemanticDraftEdit);
elements.draftDestination.addEventListener("change", applySemanticDraftEdit);
elements.draftUndo.addEventListener("click", () => moveDraftHistory(-1));
elements.draftRedo.addEventListener("click", () => moveDraftHistory(1));
elements.draftRevert.addEventListener("click", revertDraft);
elements.draftDiscard.addEventListener("click", () => {
  if (!state.draft?.dirty || window.confirm("Discard all changes to this packet draft?")) {
    discardDraft();
  }
});
elements.recordingSelect.addEventListener("change", selectRecording);
elements.replayPlay.addEventListener("click", () => replayAction("play", true));
elements.replayPause.addEventListener("click", () => replayAction("pause"));
elements.replayStep.addEventListener("click", () => replayAction("step"));
elements.replayReset.addEventListener("click", () => replayAction("reset"));
elements.replaySpeed.addEventListener("change", () => replayAction("speed", true));
elements.frameInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") inspectFrame();
});
document.addEventListener("keydown", (event) => {
  if (!state.draft || !(event.ctrlKey || event.metaKey)) return;
  if (event.key.toLowerCase() === "z" && !event.shiftKey) {
    event.preventDefault();
    moveDraftHistory(-1);
  } else if (
    event.key.toLowerCase() === "y"
    || (event.key.toLowerCase() === "z" && event.shiftKey)
  ) {
    event.preventDefault();
    moveDraftHistory(1);
  }
});
elements.starterExample.addEventListener("click", () => {
  const starter = state.examples.find((item) => item.name === "NODE_HELLO") || state.examples[0];
  if (starter) chooseExample(starter.id);
});

function initColumnResizer() {
  const table = document.querySelector('.table-wrap table');
  if (!table) return;
  const ths = table.querySelectorAll('thead th');
  ths.forEach((th) => {
    if (th.querySelector('.col-resizer')) return;
    const resizer = document.createElement('div');
    resizer.className = 'col-resizer';
    th.style.position = 'relative';
    th.appendChild(resizer);
    
    let startX, startWidth;
    resizer.addEventListener('mousedown', (e) => {
      e.preventDefault();
      e.stopPropagation();
      startX = e.clientX;
      startWidth = th.getBoundingClientRect().width;
      resizer.classList.add('active');
      document.body.style.cursor = 'col-resize';
      
      const onMouseMove = (moveEvent) => {
        const diff = moveEvent.clientX - startX;
        const newWidth = Math.max(40, startWidth + diff);
        th.style.width = `${newWidth}px`;
        th.style.minWidth = `${newWidth}px`;
      };
      
      const onMouseUp = () => {
        resizer.classList.remove('active');
        document.body.style.cursor = '';
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
      };
      
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });
  });
}

initialise();
initColumnResizer();
