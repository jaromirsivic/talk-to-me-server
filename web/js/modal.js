export function openDialog(dialog, focusSelector = "input, select, button") {
  dialog.showModal();
  queueMicrotask(() => dialog.querySelector(focusSelector)?.focus());
}

export function initializeBaseDialogs() {
  for (const trigger of document.querySelectorAll("[data-dialog]")) {
    trigger.addEventListener("click", () => {
      openDialog(document.querySelector(`#${trigger.dataset.dialog}`));
    });
  }
  for (const close of document.querySelectorAll(".dialog-close:not([data-setup-cancel])")) {
    close.addEventListener("click", () => close.closest("dialog").close());
  }
}
