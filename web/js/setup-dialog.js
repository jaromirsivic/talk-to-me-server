import {translate} from "./i18n.js";
import {openDialog} from "./modal.js";

export function createSetupDialogController({
  dialog, form, readSource, createDraft, renderDraft, collectDraft, mergeDraft,
  persist, onSaved = () => {}, onError = () => {}, focusSelector = "input, select",
}) {
  let session = null;
  const submit = form.querySelector('[type="submit"]');
  const status = form.querySelector("[data-save-status]");

  function open() {
    session = {draft: createDraft(readSource()), saving: false};
    submit.disabled = false;
    status.textContent = "";
    renderDraft(session.draft);
    openDialog(dialog, focusSelector);
  }

  function discard() {
    session = null;
    submit.disabled = false;
    status.textContent = "";
    dialog.close();
  }

  function updateDraft(mutator) {
    if (!session) return;
    mutator(session.draft);
    renderDraft(session.draft);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitted = session;
    if (!submitted || submitted.saving) return;
    submitted.saving = true;
    submit.disabled = true;
    status.textContent = translate("settings.saving");
    try {
      submitted.draft = collectDraft(submitted.draft);
      const next = structuredClone(readSource());
      mergeDraft(next, submitted.draft);
      const result = await persist(next);
      if (session !== submitted) return;
      session = null;
      dialog.close();
      onSaved(result);
    } catch (error) {
      if (session !== submitted) return;
      status.textContent = error.message;
      onError(error);
    } finally {
      submitted.saving = false;
      if (session === submitted) submit.disabled = false;
    }
  });

  dialog.querySelectorAll("[data-setup-cancel]").forEach((button) => {
    button.addEventListener("click", discard);
  });
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    discard();
  });

  return {
    open,
    getDraft: () => session?.draft || null,
    updateDraft,
    captureSession: () => session,
    isCurrentSession: (candidate) => candidate !== null && candidate === session,
  };
}
