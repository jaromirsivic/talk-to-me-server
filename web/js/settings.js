import {postApi} from "./api.js";
import {createSetupDialogController} from "./setup-dialog.js";
import {translate} from "./i18n.js";

let latestSetup = null;
let loadingSetup = null;

export function getLatestSetup() {
  return latestSetup;
}

export async function loadSetup() {
  if (!loadingSetup) {
    loadingSetup = postApi("getSetup", {}).then(({body}) => {
      if (!body.setup) throw new Error(body.reasonText || "Unable to load setup");
      latestSetup = body.setup;
      return latestSetup;
    });
  }
  return loadingSetup;
}

export async function persistSetup(nextSetup) {
  const {body, status} = await postApi("setSetup", {setup: nextSetup});
  if (status >= 400 || !body.setup) throw new Error(body.reasonText || "Unable to save setup");
  latestSetup = body.setup;
  return body;
}

export function initializeSettings() {
  const setupPromise = loadSetup();
  const controllers = {
    network: createNetworkController(),
    general: createGeneralController(),
  };
  for (const trigger of document.querySelectorAll("[data-settings-dialog]")) {
    trigger.addEventListener("click", async () => {
      await setupPromise;
      controllers[trigger.dataset.settingsDialog].open();
    });
  }
  return setupPromise;
}

function createNetworkController() {
  const controller = createSetupDialogController({
    dialog: document.querySelector("#network-dialog"),
    form: document.querySelector("#network-form"),
    readSource: getLatestSetup,
    createDraft: createNetworkDraft,
    renderDraft: renderNetwork,
    collectDraft: collectNetwork,
    mergeDraft: mergeNetwork,
    persist: persistSetup,
    onSaved: showSetupSaved,
    onError: (error) => showToast(error.message, true),
  });
  document.querySelector("#remote-management").addEventListener("change", updateRemoteWarning);
  return controller;
}

function createGeneralController() {
  return createSetupDialogController({
    dialog: document.querySelector("#general-dialog"),
    form: document.querySelector("#general-form"),
    readSource: getLatestSetup,
    createDraft: createGeneralDraft,
    renderDraft: renderGeneral,
    collectDraft: collectGeneral,
    mergeDraft: mergeGeneral,
    persist: persistSetup,
    onSaved: showSetupSaved,
    onError: (error) => showToast(error.message, true),
  });
}

function createNetworkDraft(setup) {
  return structuredClone(setup.network);
}

function renderNetwork(network) {
  setChecked("#ipv4-enabled", network.ipv4Enabled);
  setValue("#ipv4-address", network.ipv4Address);
  setChecked("#ipv6-enabled", network.ipv6Enabled);
  setValue("#ipv6-address", network.ipv6Address);
  setValue("#network-port", network.port);
  setChecked("#remote-management", network.remoteManagementEnabled);
  updateRemoteWarning();
}

function collectNetwork() {
  return {
    ipv4Address: value("#ipv4-address"),
    ipv4Enabled: checked("#ipv4-enabled"),
    ipv6Address: value("#ipv6-address"),
    ipv6Enabled: checked("#ipv6-enabled"),
    port: numberValue("#network-port"),
    remoteManagementEnabled: checked("#remote-management"),
  };
}

function mergeNetwork(next, draft) {
  Object.assign(next.network, draft);
}

function createGeneralDraft(setup) {
  return structuredClone(setup.general);
}

function renderGeneral(general) {
  setValue("#compute-device", general.device);
  setValue("#synthesis-workers", general.workers);
  setValue("#temp-directory", general.directories.tempDirectory);
  setValue("#speech-directory", general.directories.speechDirectory);
  setValue("#text-directory", general.directories.textDirectory);
  setValue("#gc-timeout", general.directories.garbageCollectorTimeout);
}

function collectGeneral() {
  return {
    device: value("#compute-device"),
    workers: numberValue("#synthesis-workers"),
    directories: {
      tempDirectory: value("#temp-directory"),
      speechDirectory: value("#speech-directory"),
      textDirectory: value("#text-directory"),
      garbageCollectorTimeout: numberValue("#gc-timeout"),
    },
  };
}

function mergeGeneral(next, draft) {
  const directories = next.general.directories;
  Object.assign(next.general, draft);
  next.general.directories = {...directories, ...draft.directories};
}

function showSetupSaved(body) {
  const message = body.restartRequired
    ? `Restart required: ${body.restartFields.join(", ")}`
    : translate("settings.applied");
  showToast(message);
}

export function showToast(message, isError = false) {
  const toast = document.querySelector("#portal-toast");
  const supportsPopover = typeof toast.showPopover === "function";
  if (supportsPopover && toast.matches(":popover-open")) toast.hidePopover();
  const modalDialogs = document.querySelectorAll("dialog:modal");
  const toastHost = modalDialogs[modalDialogs.length - 1] || document.body;
  toastHost.append(toast);
  toast.querySelector("[data-toast-message]").textContent = message;
  toast.dataset.kind = isError ? "error" : "success";
  toast.setAttribute("role", isError ? "alert" : "status");
  toast.setAttribute("aria-live", isError ? "assertive" : "polite");
  toast.hidden = false;
  toast.querySelector("[data-toast-close]").onclick = () => hideToast(toast);
  if (supportsPopover) toast.showPopover();
}

function hideToast(toast) {
  if (typeof toast.hidePopover === "function" && toast.matches(":popover-open")) {
    toast.hidePopover();
    return;
  }
  toast.hidden = true;
}

function setValue(selector, valueToSet) {
  document.querySelector(selector).value = valueToSet;
}
function setChecked(selector, valueToSet) {
  document.querySelector(selector).checked = valueToSet;
}
function value(selector) {
  return document.querySelector(selector).value;
}
function numberValue(selector) {
  return Number(value(selector));
}
function checked(selector) {
  return document.querySelector(selector).checked;
}

function updateRemoteWarning() {
  document.querySelector("#remote-management-warning").hidden =
    !document.querySelector("#remote-management").checked;
}
