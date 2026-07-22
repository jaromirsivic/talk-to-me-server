import {postApi} from "./api.js";
import {appendChatCard, appendFirstMessageNotice} from "./chat.js";
import {initializeCodeControls} from "./code-controls.js";
import {parseJson, prettyJson} from "./json.js";
import {initializeBaseDialogs, openDialog} from "./modal.js";
import {initializeI18n, translate} from "./i18n.js";
import {initializeSettings} from "./settings.js";
import {initializeTheme} from "./theme.js";
import {initializeVoices} from "./voices.js";

const editor = document.querySelector("#request-json");
const editorView = document.querySelector(".composer-editor");
const sendButton = document.querySelector("#send-request");
const stopButton = document.querySelector("#stop-playback");
const resetButton = document.querySelector("#reset-request");
const resetDialog = document.querySelector("#reset-confirm-dialog");
const confirmResetButton = document.querySelector("#confirm-reset");
const composer = document.querySelector("#composer");
const composerToggle = document.querySelector("#composer-size-toggle");
const composerResizeHandle = document.querySelector(".composer-resize-handle");
const header = document.querySelector(".app-header");
const history = document.querySelector("#chat-history");
const status = document.querySelector("#composer-status");
const errorDialog = document.querySelector("#json-error-dialog");
const errorMessage = document.querySelector("#json-error-message");
let initialRequest = null;
let editorControls = null;
let queuePollTimer = null;
let stopRequestInFlight = false;
const QUEUE_POLL_INTERVAL_MS = 1_000;

const fallbackRequest = {
  value: "If you here this voice then talk to me server works. You can play positive gong {{play('positive_gong.wav')}} or neutral gong {{play('neutral_gong.wav')}} or negative gong {{play('negative_gong.wav')}}. And make a pause {{pause(2000)}} in the middle of a text. {{pause(500)}} You can control the priority of text to speech conversion using the importance parameter. If importance is set to high, the text is added to the end of the queue and played when its turn comes. If importance is set to low, the text is played immediately if the queue is empty. If there is at least one text item waiting in the queue, it is not played at all. {{pause(500)}} You can adjust the text volume using the volume multiplier parameter. {{pause(500)}} Setting the calculate stats parameter to true runs the model’s performance tests. {{pause(500)}} And if you want to wait until the entire text has been played, set wait until playback finished to true. If wait until playback finished parameter is set to false, the server returns a response immediately.",
  importance: "high",
  volumeMultiplier: 0.95,
  calculateStats: false,
  waitUntilPlaybackFinished: false,
};

async function loadInitialRequest() {
  const response = await fetch("/master-data/request.json", {cache: "no-store"});
  if (!response.ok) throw new Error("Unable to load the master request");
  initialRequest = await response.json();
  editor.value = prettyJson(initialRequest);
  editorControls?.refresh();
}

function showJsonError(error) {
  errorMessage.textContent = translate("dialog.invalidJsonMessage", error);
  errorDialog.showModal();
}

async function sendRequest() {
  setComposerMaximized(false);
  const parsed = parseJson(editor.value);
  if (parsed.error) {
    showJsonError(parsed.error);
    return;
  }
  sendButton.disabled = true;
  status.textContent = translate("composer.sending");
  if (!history.querySelector('[data-kind="request"]')) {
    appendFirstMessageNotice(history);
  }
  appendChatCard(history, "request", parsed.value, new Date());
  try {
    const result = await postApi("textToSpeech", parsed.value);
    appendChatCard(history, "response", result.body, new Date());
    status.textContent = result.status < 400 ? translate("composer.received") : `Server returned ${result.status}`;
  } catch (error) {
    appendChatCard(history, "response", {version: 1, reasonCode: 0, reasonText: error.message}, new Date());
    status.textContent = translate("composer.transportError");
  } finally {
    sendButton.disabled = false;
  }
}

function scheduleQueuePoll() {
  clearTimeout(queuePollTimer);
  queuePollTimer = setTimeout(pollQueueInfo, QUEUE_POLL_INTERVAL_MS);
}

async function pollQueueInfo() {
  queuePollTimer = null;
  if (stopRequestInFlight) {
    scheduleQueuePoll();
    return;
  }
  try {
    const result = await postApi("queueInfo", {mode: "min"});
    if (stopRequestInFlight) return;
    const valid = result.status < 400
      && typeof result.body.hasActiveJobs === "boolean"
      && Number.isInteger(result.body.activeJobCount)
      && result.body.activeJobCount >= 0
      && result.body.hasActiveJobs === (result.body.activeJobCount > 0);
    stopButton.disabled = !valid || !result.body.hasActiveJobs;
  } catch (_error) {
    stopButton.disabled = true;
  } finally {
    scheduleQueuePoll();
  }
}

async function stopPlayback() {
  if (stopButton.disabled || stopRequestInFlight) return;
  stopRequestInFlight = true;
  stopButton.disabled = true;
  clearTimeout(queuePollTimer);
  queuePollTimer = null;
  try {
    await postApi("stop", {});
  } catch (_error) {
    stopButton.disabled = true;
  } finally {
    stopRequestInFlight = false;
    scheduleQueuePoll();
  }
}

function initializeComposerControls() {
  let resizeStart = null;

  function updateComposerClearance() {
    if (composer.classList.contains("is-maximized")) return;
    const bounds = composer.getBoundingClientRect();
    const clearance = Math.ceil(window.innerHeight - bounds.top + 24);
    document.documentElement.style.setProperty("--composer-clearance", `${clearance}px`);
    composerResizeHandle.setAttribute("aria-valuenow", String(Math.round(bounds.height)));
  }

  function composerHeightLimits() {
    const bounds = composer.getBoundingClientRect();
    const bottomGap = Math.max(0, window.innerHeight - bounds.bottom);
    return {
      minimum: 200,
      maximum: Math.max(200, window.innerHeight - header.getBoundingClientRect().bottom - bottomGap - 12),
    };
  }

  function setComposerHeight(height) {
    const limits = composerHeightLimits();
    const nextHeight = Math.min(limits.maximum, Math.max(limits.minimum, height));
    composer.style.height = `${Math.round(nextHeight)}px`;
    updateComposerClearance();
  }

  composerResizeHandle.addEventListener("pointerdown", (event) => {
    if (composer.classList.contains("is-maximized")) return;
    resizeStart = {
      pointerY: event.clientY,
      height: composer.getBoundingClientRect().height,
    };
    composer.classList.add("is-resizing");
    composerResizeHandle.setPointerCapture(event.pointerId);
  });
  composerResizeHandle.addEventListener("pointermove", (event) => {
    if (!resizeStart) return;
    setComposerHeight(resizeStart.height + resizeStart.pointerY - event.clientY);
  });
  const finishResize = () => {
    resizeStart = null;
    composer.classList.remove("is-resizing");
  };
  composerResizeHandle.addEventListener("pointerup", finishResize);
  composerResizeHandle.addEventListener("pointercancel", finishResize);
  composerResizeHandle.addEventListener("keydown", (event) => {
    if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const direction = event.key === "ArrowUp" ? 1 : -1;
    setComposerHeight(composer.getBoundingClientRect().height + direction * 20);
  });

  composerToggle.addEventListener("click", () => {
    setComposerMaximized(!composer.classList.contains("is-maximized"));
  });
  document.addEventListener("talktome:localechange", updateComposerToggle);
  window.addEventListener("resize", () => {
    if (composer.classList.contains("is-maximized")) updateComposerTop();
    else setComposerHeight(composer.getBoundingClientRect().height);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && composer.classList.contains("is-maximized")) {
      setComposerMaximized(false);
    }
  });
  new ResizeObserver(updateComposerClearance).observe(composer);
  updateComposerToggle();
  updateComposerClearance();
}

function updateComposerTop() {
  composer.style.setProperty("--composer-top", `${header.getBoundingClientRect().bottom}px`);
}

function updateComposerToggle() {
  const maximized = composer.classList.contains("is-maximized");
  const key = maximized ? "composer.restore" : "composer.maximize";
  composerToggle.dataset.i18nAriaLabel = key;
  composerToggle.dataset.i18nTooltip = key;
  composerToggle.setAttribute("aria-label", translate(key));
  composerToggle.dataset.tooltip = translate(key);
  composerToggle.setAttribute("aria-pressed", String(maximized));
}

function setComposerMaximized(maximized) {
  if (maximized) updateComposerTop();
  composer.classList.toggle("is-maximized", maximized);
  updateComposerToggle();
}

sendButton.addEventListener("click", sendRequest);
stopButton.addEventListener("click", stopPlayback);
editor.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") sendRequest();
});
resetButton.addEventListener("click", () => {
  openDialog(resetDialog, "#cancel-reset");
});
confirmResetButton.addEventListener("click", () => {
  if (initialRequest) editor.value = prettyJson(initialRequest);
  editorControls?.refresh();
  editor.focus();
});

loadInitialRequest().catch((error) => {
  status.textContent = error.message;
  initialRequest = structuredClone(fallbackRequest);
  editor.value = prettyJson(initialRequest);
  editorControls?.refresh();
});
await initializeI18n();
editorControls = initializeCodeControls({scope: composer, view: editorView, textElement: editor});
initializeComposerControls();
initializeBaseDialogs();
initializeVoices();
scheduleQueuePoll();
const settingsReady = initializeSettings();
settingsReady.then(initializeTheme).catch((error) => {
  status.textContent = error.message;
});
