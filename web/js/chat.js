import {prettyJson} from "./json.js";
import {formatDateTime, translate} from "./i18n.js";
import {initializeCodeControls} from "./code-controls.js";

export function appendFirstMessageNotice(history) {
  document.querySelector("#welcome-card")?.remove();
  const notice = document.createElement("aside");
  notice.className = "first-message-notice";
  notice.setAttribute("role", "status");
  notice.dataset.i18n = "chat.firstMessageNotice";
  notice.textContent = translate("chat.firstMessageNotice");
  history.append(notice);
  return notice;
}

export function appendChatCard(history, kind, value, timestamp = new Date()) {
  document.querySelector("#welcome-card")?.remove();
  const fragment = document.querySelector("#chat-card-template").content.cloneNode(true);
  const card = fragment.querySelector(".chat-card");
  card.dataset.kind = kind;
  card.querySelector(".card-kind").textContent = translate(`chat.${kind}`);
  const time = card.querySelector(".card-time");
  const instant = new Date(timestamp);
  time.dateTime = instant.toISOString();
  time.textContent = formatDateTime(instant);
  const code = card.querySelector("code");
  code.textContent = prettyJson(value);
  history.append(fragment);
  initializeCodeControls({
    scope: card,
    view: card.querySelector(".card-code-view"),
    textElement: card.querySelector(".json-block"),
  });
  card.scrollIntoView({behavior: "smooth", block: "end"});
  return card;
}
