const state = {
  examples: [],
  recordings: [],
  selectedId: null,
  current: null,
  replayTimer: null,
  replayBusy: false,
  radioTimer: null,
  radioBusy: false,
  physical: null,
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

  // Switch tab focus to Custom Hex Input
  const hexTab = document.querySelector('.input-tab[data-input-tab="hex"]');
  if (hexTab) hexTab.click();

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

function renderResult(item, shouldScroll = true) {
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
    elements.journalList.innerHTML = result.entries.slice(0, 10).map((entry) => {
      let badgeHtml = '';
      if (entry.capture && entry.capture.direction) {
        if (entry.capture.direction === "received") {
          badgeHtml = `<span class="journal-badge incoming" title="Incoming frame received"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M19 12l-7 7-7-7"/></svg> INCOMING</span>`;
        } else if (entry.capture.direction === "transmitted") {
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
  } catch (_) {
    elements.journalCard.hidden = true;
  }
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
  elements.modeEyebrow.textContent = "Physical adapter validation";
  elements.modeHeading.textContent = "See the exact bytes that cross your radio bench.";
  elements.modeDescription.textContent = "Packet Predator still validates every frame through the shared contract, while the configured nRF905 moves only complete 32-byte frames.";
  elements.truthTitle.textContent = "Live nRF905";
  elements.truthDetail.textContent = carrier.can_transmit ? "Receive and confirmed transmit are enabled." : "Listening only; transmit is disabled in the profile.";
  elements.radioProfile.textContent = profile.id;
  elements.radioDevices.textContent = `${profile.spi_device} · ${profile.gpio_chip}`;
  elements.radioFrequency.textContent = `${profile.frequency_mhz.toFixed(1)} MHz`;
  elements.radioChannel.textContent = `band ${profile.band} · channel ${profile.channel} · ${profile.transmit_power_dbm} dBm`;
  elements.radioAddress.textContent = profile.physical_address_hex;
  elements.radioCrc.textContent = `${profile.crc_bits}-bit hardware CRC`;
  const pins = carrier.pins || {};
  elements.radioPins.textContent = `CD ${Number(Boolean(pins.carrier_detect))} · AM ${Number(Boolean(pins.address_match))} · DR ${Number(Boolean(pins.data_ready))}`;
  elements.transmitButton.disabled = !carrier.can_transmit;
  elements.transmitConfirm.disabled = !carrier.can_transmit;
  elements.carrierStatus.innerHTML = `<i></i> ${escaped(carrier.label)} · listening`;
}

async function pollRadio() {
  if (state.radioBusy || !state.physical) return;
  state.radioBusy = true;
  try {
    const result = await api("/api/carrier/poll", { method: "POST" });
    renderPhysicalStatus(result.carrier);
    if (result.delivered.length) {
      elements.radioActivity.textContent = "Frame received";
      renderResult(result.delivered[result.delivered.length - 1], false);
    }
  } catch (detail) {
    stopRadioPolling();
    showError(detail);
  } finally {
    state.radioBusy = false;
  }
}

function startRadioPolling() {
  if (!state.radioTimer) state.radioTimer = window.setInterval(pollRadio, 50);
}

function stopRadioPolling() {
  if (state.radioTimer) window.clearInterval(state.radioTimer);
  state.radioTimer = null;
}

async function transmitFrame() {
  clearError();
  if (!elements.transmitConfirm.checked) {
    showError({ code: "TRANSMIT_CONFIRMATION_REQUIRED", message: "Tick the one-transmission confirmation first." });
    return;
  }
  elements.transmitButton.disabled = true;
  try {
    const result = await api("/api/carrier/transmit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        frame_hex: elements.frameInput.value,
        mode: elements.frameMode.value,
        confirmed: true,
      }),
    });
    elements.transmitConfirm.checked = false;
    renderPhysicalStatus(result.carrier);
    elements.radioActivity.textContent = "Frame transmitted";
    renderResult(result.delivered[0], false);
  } catch (detail) {
    showError(detail);
  } finally {
    if (state.physical) elements.transmitButton.disabled = !state.physical.can_transmit;
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
    const [status, examples, replays] = await Promise.all([api("/api/status"), api("/api/v1/examples"), api("/api/replays")]);
    elements.carrierStatus.innerHTML = `<i></i> ${escaped(status.carrier.label)} · ${status.physical_adapter ? "listening" : "no radio"}`;
    elements.authorityStatus.textContent = `Contract ${status.authority.authority_version}`;
    elements.authorityStatus.classList.add("ready");
    state.examples = examples.examples;
    elements.exampleCount.textContent = `${examples.example_count} frames`;
    renderExamples();
    populateRecordings(replays);
    if (status.physical_adapter) {
      renderPhysicalStatus(status.physical_adapter);
      startRadioPolling();
    }
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
elements.recordingSelect.addEventListener("change", selectRecording);
elements.replayPlay.addEventListener("click", () => replayAction("play", true));
elements.replayPause.addEventListener("click", () => replayAction("pause"));
elements.replayStep.addEventListener("click", () => replayAction("step"));
elements.replayReset.addEventListener("click", () => replayAction("reset"));
elements.replaySpeed.addEventListener("change", () => replayAction("speed", true));
elements.frameInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") inspectFrame();
});
elements.starterExample.addEventListener("click", () => {
  const starter = state.examples.find((item) => item.name === "NODE_HELLO") || state.examples[0];
  if (starter) chooseExample(starter.id);
});

initialise();
