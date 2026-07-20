import {translate} from "./i18n.js";

function codeText(element) {
  return element instanceof HTMLTextAreaElement ? element.value : element.textContent;
}

function setToggle(button, enabled) {
  button.setAttribute("aria-pressed", String(enabled));
}

function setFeedback(button, key) {
  button.setAttribute("aria-label", translate(key));
  button.dataset.tooltip = translate(key);
}

export function initializeCodeControls({scope, view, textElement}) {
  const copyButton = scope.querySelector('[data-code-action="copy"]');
  const wrapButton = scope.querySelector('[data-code-action="wrap"]');
  const lineNumbersButton = scope.querySelector('[data-code-action="line-numbers"]');
  const gutter = view.querySelector(".line-number-gutter");
  const numberList = view.querySelector(".line-number-list");
  const measure = document.createElement("div");
  measure.className = "code-line-measure";
  measure.setAttribute("aria-hidden", "true");
  view.append(measure);

  let wrapped = wrapButton.getAttribute("aria-pressed") === "true";
  let numbered = lineNumbersButton.getAttribute("aria-pressed") === "true";
  let refreshFrame = null;
  let feedbackTimer = null;

  function syncGutterScroll() {
    numberList.style.transform = `translateY(${-textElement.scrollTop}px)`;
  }

  function lineMetrics() {
    const style = getComputedStyle(textElement);
    const lineHeight = Number.parseFloat(style.lineHeight)
      || Number.parseFloat(style.fontSize) * 1.55;
    const contentWidth = Math.max(
      1,
      textElement.clientWidth
        - Number.parseFloat(style.paddingLeft)
        - Number.parseFloat(style.paddingRight),
    );
    Object.assign(measure.style, {
      width: `${contentWidth}px`,
      font: style.font,
      fontFamily: style.fontFamily,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      letterSpacing: style.letterSpacing,
      lineHeight: `${lineHeight}px`,
      tabSize: style.tabSize,
    });
    Object.assign(gutter.style, {
      font: style.font,
      fontFamily: style.fontFamily,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      letterSpacing: style.letterSpacing,
      lineHeight: `${lineHeight}px`,
    });
    return {lineHeight, contentWidth};
  }

  function renderLineNumbers() {
    if (!numbered) return;
    const lines = codeText(textElement).split("\n");
    const {lineHeight} = lineMetrics();
    measure.replaceChildren();
    numberList.replaceChildren();
    for (const [index, line] of lines.entries()) {
      const measuredLine = document.createElement("div");
      measuredLine.className = "code-measure-line";
      measuredLine.textContent = line || "\u200b";
      measure.append(measuredLine);

      const number = document.createElement("span");
      number.className = "line-number";
      number.textContent = String(index + 1);
      const measuredHeight = wrapped
        ? Math.max(lineHeight, measuredLine.getBoundingClientRect().height)
        : lineHeight;
      number.style.height = `${measuredHeight}px`;
      numberList.append(number);
    }
    syncGutterScroll();
  }

  function queueLineNumbers() {
    if (refreshFrame !== null) cancelAnimationFrame(refreshFrame);
    refreshFrame = requestAnimationFrame(() => {
      refreshFrame = null;
      renderLineNumbers();
    });
  }

  copyButton.addEventListener("click", async () => {
    await navigator.clipboard.writeText(codeText(textElement));
    setFeedback(copyButton, "code.copied");
    window.clearTimeout(feedbackTimer);
    feedbackTimer = window.setTimeout(() => setFeedback(copyButton, "code.copy"), 1400);
  });
  wrapButton.addEventListener("click", () => {
    wrapped = !wrapped;
    textElement.classList.toggle("is-wrapped", wrapped);
    if (textElement instanceof HTMLTextAreaElement) {
      textElement.wrap = wrapped ? "soft" : "off";
    }
    setToggle(wrapButton, wrapped);
    queueLineNumbers();
  });
  lineNumbersButton.addEventListener("click", () => {
    numbered = !numbered;
    view.classList.toggle("has-line-numbers", numbered);
    gutter.hidden = !numbered;
    setToggle(lineNumbersButton, numbered);
    queueLineNumbers();
  });
  textElement.addEventListener("input", queueLineNumbers);
  textElement.addEventListener("scroll", syncGutterScroll);
  new ResizeObserver(queueLineNumbers).observe(textElement);
  textElement.classList.toggle("is-wrapped", wrapped);
  if (textElement instanceof HTMLTextAreaElement) {
    textElement.wrap = wrapped ? "soft" : "off";
  }
  view.classList.toggle("has-line-numbers", numbered);
  gutter.hidden = !numbered;
  setToggle(wrapButton, wrapped);
  setToggle(lineNumbersButton, numbered);
  queueLineNumbers();
  return {refresh: queueLineNumbers};
}
