import {postApi, postMultipart} from "./api.js";
import {openDialog} from "./modal.js";
import {createSetupDialogController} from "./setup-dialog.js";
import {
  getLatestSetup, loadSetup, persistSetup, showToast,
} from "./settings.js?v=sprint-0005";
import {translate} from "./i18n.js";

const STATUS_ICON_PATHS = {
  ready: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z",
  downloadRequired: "M5 20h14v-2H5v2zM19 9h-4V3H9v6H5l7 7 7-7z",
};

let voices = [];
let downloadCandidate = null;
let selectCandidate = null;
let deleteCandidate = null;
let activeOption = -1;
let filterMode = "all";
let controller = null;

export function initializeVoices() {
  controller = createSetupDialogController({
    dialog: document.querySelector("#voice-dialog"),
    form: document.querySelector("#voice-form"),
    readSource: getLatestSetup,
    createDraft: (setup) => structuredClone(setup.voice),
    renderDraft,
    collectDraft: (draft) => draft,
    mergeDraft: (setup, draft) => { setup.voice = draft; },
    persist: persistSetup,
    onSaved: () => showToast(translate("voice.saved")),
    onError: (error) => showToast(error.message, {kind: "error"}),
    focusSelector: "#voice-search",
  });

  document.querySelector("[data-voice-dialog]").addEventListener("click", openVoiceSetup);
  document.querySelector("#voice-search").addEventListener("input", renderVoices);
  document.querySelector("#voice-search").addEventListener("keydown", handleSearchKeys);
  document.querySelector("#confirm-download-voice").addEventListener("click", downloadVoice);
  document.querySelector("#confirm-select-voice").addEventListener("click", selectVoice);
  document.querySelector("#confirm-delete-voice").addEventListener("click", deleteVoice);
  document.querySelector("#import-local-voice").addEventListener("click", importLocalVoice);
  document.querySelector("#voice-volume").addEventListener("input", (event) => {
    controller.updateDraft((draft) => { draft.volume = Number(event.currentTarget.value); });
  });
  for (const button of document.querySelectorAll("[data-voice-filter]")) {
    button.addEventListener("click", () => {
      filterMode = button.dataset.voiceFilter;
      renderFilter();
      renderVoices();
    });
  }
}

async function openVoiceSetup() {
  await loadSetup();
  resetImport();
  filterMode = "all";
  document.querySelector("#voice-search").value = "";
  renderFilter();
  await refreshVoices();
  controller.open();
}

function resetImport() {
  document.querySelector("#import-panel").open = false;
  document.querySelector("#custom-voice-name").value = "";
  document.querySelector("#custom-voice-license").value = "CC0-1.0";
  document.querySelector("#custom-model-file").value = "";
  document.querySelector("#custom-config-file").value = "";
  document.querySelector("#custom-rights").checked = false;
}

async function refreshVoices() {
  const {body, status} = await postApi("getVoices", {});
  if (status >= 400) {
    showToast(body.reasonText || translate("voice.loadError"), {kind: "error"});
    return;
  }
  voices = body.voices;
  renderVoices();
}

function visibleVoices() {
  const query = document.querySelector("#voice-search").value.trim().toLowerCase();
  const matches = voices.filter((voice) => {
    const passesFilter = filterMode === "all" || voice.status === "ready";
    return passesFilter && searchable(voice).includes(query);
  });
  return matches.sort(
    (left, right) => Number(right.status === "ready") - Number(left.status === "ready"),
  );
}

function renderVoices() {
  const list = document.querySelector("#voice-options");
  const search = document.querySelector("#voice-search");
  const selectedId = controller?.getDraft()?.speaker;
  const focusedVoiceId = document.activeElement?.closest?.("[data-voice-id]")?.dataset.voiceId;
  list.replaceChildren();
  activeOption = -1;
  const visible = visibleVoices();
  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "voice-empty";
    empty.textContent = translate("voice.noResults");
    list.append(empty);
    return;
  }
  for (const voice of visible) {
    const row = document.createElement("div");
    const option = document.createElement("button");
    const status = statusText(voice);
    const installedSize = voice.status === "ready" && voice.sizeBytes
      ? formatSize(voice.sizeBytes)
      : null;
    row.className = "voice-option-row";
    row.role = "listitem";
    row.dataset.voiceRowId = voice.id;
    option.type = "button";
    option.id = `voice-option-${safeId(voice.id)}`;
    option.className = "voice-option";
    option.dataset.voiceId = voice.id;
    const actionable = voice.status === "ready" || voice.status === "downloadRequired";
    option.tabIndex = actionable ? 0 : -1;
    if (!actionable) {
      option.disabled = true;
      option.setAttribute("aria-disabled", "true");
    }
    option.setAttribute("aria-pressed", String(voice.id === selectedId));
    option.setAttribute(
      "aria-label",
      `${voice.name}, ${voice.language}, ${voice.quality}, ${status}${installedSize ? `, ${installedSize}` : ""}${voice.blockedReason ? `, ${voice.blockedReason}` : ""}`,
    );
    if (voice.status === "ready" && voice.modelPath) option.title = voice.modelPath;

    const icon = document.createElement("span");
    icon.className = "voice-status";
    if (voice.status === "downloadRequired" && voice.requiresLicenseConfirmation) {
      icon.classList.add("requires-confirmation");
    }
    const svg = statusIcon(voice);
    if (svg) icon.append(svg);

    const content = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent = voice.name;
    const meta = document.createElement("small");
    meta.textContent = `${voice.language} · ${voice.quality} · ${voice.license || translate("voice.unknown")}`;
    content.append(title, meta);
    if (voice.source === "custom") {
      const source = document.createElement("span");
      source.className = "source-badge";
      source.textContent = translate("voice.custom");
      content.append(source);
    }

    option.append(icon, content);
    if (voice.status !== "ready") {
      const statusLabel = document.createElement("span");
      statusLabel.className = "voice-status-label";
      statusLabel.textContent = status;
      const statusDetails = document.createElement("span");
      statusDetails.className = "voice-status-details";
      statusDetails.append(statusLabel);
      option.append(statusDetails);
    }
    row.append(option);
    if (voice.status === "ready") {
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "voice-delete-button";
      const deleteLabel = translate("voice.deleteAction");
      deleteButton.textContent = installedSize
        ? `${deleteLabel} (${installedSize})`
        : deleteLabel;
      deleteButton.addEventListener("click", () => {
        requestVoiceDeletion(voice);
      });
      row.append(deleteButton);
    }
    if (actionable) {
      option.addEventListener("click", () => chooseVoice(voice));
    }
    list.append(row);
  }
  if (focusedVoiceId) focusVoiceOption(focusedVoiceId);
}

function renderFilter() {
  for (const button of document.querySelectorAll("[data-voice-filter]")) {
    button.setAttribute("aria-pressed", String(button.dataset.voiceFilter === filterMode));
  }
}

function renderDraft(draft) {
  document.querySelector("#voice-volume").value = draft.volume;
  document.querySelector("#volume-output").textContent = draft.volume;
  const selected = voices.find((voice) => voice.id === draft.speaker);
  document.querySelector("#current-voice").textContent =
    translate("voice.current", {name: selected?.name || draft.speaker});
  document.querySelector("#current-voice-language").textContent =
    translate("voice.language", {
      language: selected?.language || translate("voice.unknown"),
    });
  renderVoices();
}

function searchable(voice) {
  return `${voice.name} ${voice.id} ${voice.language} ${voice.source} ${voice.quality}`.toLowerCase();
}

function statusText(voice) {
  if (voice.status === "ready") return translate("voice.installed");
  if (voice.status === "downloadRequired" && voice.requiresLicenseConfirmation) {
    return translate("voice.confirmationRequired");
  }
  if (voice.status === "downloadRequired") return translate("voice.downloadRequired");
  return translate("voice.unavailable");
}

function statusIcon(voice) {
  const iconPath = STATUS_ICON_PATHS[voice.status];
  if (!iconPath) return null;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("material-icon");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", iconPath);
  svg.append(path);
  return svg;
}

function chooseVoice(voice) {
  if (voice.status === "downloadRequired") {
    downloadCandidate = voice;
    setDownloadProgress(false);
    const title = document.querySelector("#download-voice-title");
    title.textContent = voice.requiresLicenseConfirmation
      ? translate("voice.confirmLicense")
      : translate("voice.download");
    let message = translate("voice.freeDownloadMessage", {
      name: voice.name,
      size: formatSize(voice.sizeBytes),
    });
    if (voice.requiresLicenseConfirmation) {
      message = translate("voice.restrictedDownloadMessage", {
        name: voice.name,
        license: voice.license || translate("voice.unknown"),
        notice: voice.licenseNotice || translate("voice.confirmationRequired"),
      });
    }
    document.querySelector("#download-voice-message").textContent = message;
    openDialog(document.querySelector("#download-voice-dialog"), "#confirm-download-voice");
    return;
  }
  if (voice.status === "ready") {
    selectCandidate = voice;
    document.querySelector("#select-voice-message").textContent =
      translate("voice.selectMessage", {name: voice.name});
    openDialog(document.querySelector("#select-voice-dialog"), "#confirm-select-voice");
  }
}

function selectVoice() {
  const candidate = selectCandidate;
  if (!candidate) return;
  document.querySelector("#select-voice-dialog").close();
  selectCandidate = null;
  stageVoice(candidate.id);
  queueMicrotask(() => focusVoiceOption(candidate.id));
}

function requestVoiceDeletion(voice) {
  deleteCandidate = voice;
  document.querySelector("#delete-voice-message").textContent =
    translate("voice.deleteMessage", {name: voice.name});
  openDialog(document.querySelector("#delete-voice-dialog"), "#confirm-delete-voice");
}

async function downloadVoice() {
  const button = document.querySelector("#confirm-download-voice");
  button.disabled = true;
  setDownloadProgress(true);
  const candidate = downloadCandidate;
  const initiatingSession = controller.captureSession();
  try {
    const {body, status} = await postApi("downloadVoice", {
      voiceId: candidate.id,
      licenseConfirmed: candidate.requiresLicenseConfirmation,
    });
    if (status >= 400) throw new Error(body.reasonText || translate("voice.downloadError"));
    await refreshVoices();
    if (!voices.some((voice) => voice.id === body.voice.id)) voices.push(body.voice);
    if (controller.isCurrentSession(initiatingSession)) {
      stageVoice(body.voice.id);
    }
    const confirmation = document.querySelector("#download-voice-dialog");
    if (confirmation.open) confirmation.close();
    if (controller.isCurrentSession(initiatingSession)) {
      queueMicrotask(() => focusVoiceOption(body.voice.id));
    }
    showToast(translate("voice.downloaded"));
  } catch (error) {
    showToast(error.message, {kind: "error"});
  } finally {
    setDownloadProgress(false);
    button.disabled = false;
  }
}

async function deleteVoice() {
  const button = document.querySelector("#confirm-delete-voice");
  const candidate = deleteCandidate;
  if (!candidate) return;
  button.disabled = true;
  try {
    const {body, status} = await postApi("deleteVoice", {voiceId: candidate.id});
    if (status >= 400) throw new Error(body.reasonText || translate("voice.deleteError"));
    await refreshVoices();
    const confirmation = document.querySelector("#delete-voice-dialog");
    if (confirmation.open) confirmation.close();
    deleteCandidate = null;
    queueMicrotask(() => focusVoiceOption(candidate.id));
    showToast(translate("voice.deleted"));
  } catch (error) {
    showToast(error.message, {kind: "error"});
  } finally {
    button.disabled = false;
  }
}

function setDownloadProgress(isDownloading) {
  document.querySelector("#download-voice-progress").hidden = !isDownloading;
  document.querySelector("#confirm-download-voice").textContent = translate(
    isDownloading ? "voice.downloading" : "voice.downloadAndUse",
  );
}

function stageVoice(voiceId) {
  controller.updateDraft((draft) => { draft.speaker = voiceId; });
}

async function importLocalVoice() {
  if (!validateImportIdentity()) return;
  const model = document.querySelector("#custom-model-file").files[0];
  const config = document.querySelector("#custom-config-file").files[0];
  if (!model || !config || !model.name.endsWith(".onnx") || !config.name.endsWith(".onnx.json")) {
    showToast(translate("voice.selectFilesError"), {kind: "error"});
    return;
  }
  const initiatingSession = controller.captureSession();
  const form = new FormData();
  form.append("model", model);
  form.append("config", config);
  appendImportIdentity(form);
  await finishImport(postMultipart("importVoice", form), initiatingSession);
}

async function finishImport(request, initiatingSession) {
  try {
    const {body, status} = await request;
    if (status >= 400) throw new Error(body.reasonText || translate("voice.importError"));
    await refreshVoices();
    if (!voices.some((voice) => voice.id === body.voice.id)) voices.push(body.voice);
    if (controller.isCurrentSession(initiatingSession)) stageVoice(body.voice.id);
    showToast(translate("voice.imported"));
  } catch (error) {
    showToast(error.message, {kind: "error"});
  }
}

function validateImportIdentity() {
  if (!importName() || !importLicense()) {
    showToast(translate("voice.identityRequired"), {kind: "error"});
    return false;
  }
  if (!document.querySelector("#custom-rights").checked) {
    showToast(translate("voice.rightsRequired"), {kind: "error"});
    return false;
  }
  return true;
}

function appendImportIdentity(form) {
  form.append("displayName", importName());
  form.append("license", importLicense());
  form.append("rightsConfirmed", "true");
}

function importName() { return document.querySelector("#custom-voice-name").value.trim(); }
function importLicense() { return document.querySelector("#custom-voice-license").value.trim(); }
function formatSize(bytes) {
  if (!bytes) return translate("voice.files");
  const megabytes = bytes / 1_000_000;
  const formatted = new Intl.NumberFormat(document.documentElement.lang, {
    maximumFractionDigits: 1,
  }).format(megabytes);
  return `${formatted} MB`;
}
function safeId(value) { return value.replace(/[^A-Za-z0-9_-]/g, "-"); }

function focusVoiceOption(voiceId) {
  document.getElementById(`voice-option-${safeId(voiceId)}`)?.focus();
}

function handleSearchKeys(event) {
  const options = [...document.querySelectorAll("#voice-options .voice-option")];
  if (!options.length) return;
  if (event.key === "ArrowDown") activeOption = Math.min(activeOption + 1, options.length - 1);
  else if (event.key === "ArrowUp") activeOption = Math.max(activeOption - 1, 0);
  else if (event.key === "Enter" && activeOption >= 0) options[activeOption].click();
  else if (event.key === "Escape") {
    event.currentTarget.value = "";
    renderVoices();
    return;
  } else return;
  event.preventDefault();
  if (activeOption >= 0) {
    options[activeOption].scrollIntoView({block: "nearest"});
    options[activeOption].focus();
  }
}
