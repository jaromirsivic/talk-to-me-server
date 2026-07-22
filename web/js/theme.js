import {getLatestSetup, persistSetup, showToast} from "./settings.js?v=sprint-0005";
import {translate} from "./i18n.js";

export function initializeTheme() {
  const button = document.querySelector("#theme-toggle");
  applyTheme(getLatestSetup().general.theme, button);
  button.disabled = false;
  button.addEventListener("click", async () => {
    const previous = getLatestSetup().general.theme;
    const selected = previous === "dark" ? "light" : "dark";
    applyTheme(selected, button);
    button.disabled = true;
    const next = structuredClone(getLatestSetup());
    next.general.theme = selected;
    try {
      await persistSetup(next);
      showToast(translate("theme.applied"));
    } catch (error) {
      applyTheme(previous, button);
      showToast(error.message, {kind: "error"});
    } finally {
      button.disabled = false;
    }
  });
}

function applyTheme(theme, button) {
  document.documentElement.dataset.theme = theme;
  const dark = theme === "dark";
  button.textContent = dark ? "☀" : "☾";
  button.setAttribute("aria-label", translate(dark ? "theme.light" : "theme.dark"));
}
