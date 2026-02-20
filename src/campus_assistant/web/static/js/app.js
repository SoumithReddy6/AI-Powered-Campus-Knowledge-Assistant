const el = {
  chatMessages: document.getElementById("chatMessages"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  relatedInfoList: document.getElementById("relatedInfoList"),
  promotionList: document.getElementById("promotionList"),
  btnRefreshPromotions: document.getElementById("btnRefreshPromotions"),
  toast: document.getElementById("toast"),
};

const defaultTopK = window.APP_DEFAULT_TOP_K || 5;

const localPromotionFallback = [
  {
    title: "Explore Featured UMBC Events",
    summary: "Career fairs, research talks, and student life events are listed on myUMBC.",
    when: "Updated daily",
    location: "myUMBC",
    url: "https://my.umbc.edu/events",
  },
  {
    title: "Track Academic Deadlines",
    summary: "Use registrar calendars for add/drop, graduation, and enrollment milestones.",
    when: "Current and future terms",
    location: "Registrar Office",
    url: "https://registrar.umbc.edu/calendars/academic-calendars/",
  },
];

async function requestJson(url, method = "GET", payload = null) {
  const options = {
    method,
    headers: {
      "Content-Type": "application/json",
    },
  };
  if (payload) {
    options.body = JSON.stringify(payload);
  }

  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.message || `Request failed (${response.status})`);
  }
  return data;
}

function notify(message) {
  el.toast.textContent = message;
  el.toast.classList.add("show");
  window.clearTimeout(notify._timer);
  notify._timer = window.setTimeout(() => el.toast.classList.remove("show"), 2600);
}

function compactText(text, maxLen = 150) {
  if (!text) {
    return "";
  }
  const normalized = String(text).replace(/\s+/g, " ").trim();
  return normalized.length <= maxLen ? normalized : `${normalized.slice(0, maxLen - 1)}...`;
}

function sourceMetaLine(source) {
  const meta = source.metadata || {};
  const bits = [];
  if (meta.term) bits.push(meta.term);
  if (meta.department) bits.push(meta.department);
  if (meta.section) bits.push(`Sec ${meta.section}`);
  if (meta.instructor) bits.push(meta.instructor);

  const meeting = [];
  if (meta.meeting_days) meeting.push(meta.meeting_days);
  if (meta.start_time || meta.end_time) {
    meeting.push([meta.start_time, meta.end_time].filter(Boolean).join("-"));
  }
  if (meeting.length > 0) bits.push(meeting.join(" "));

  const location = [meta.building, meta.room].filter(Boolean).join(" ");
  if (location) bits.push(location);
  return bits.join(" | ");
}

function appendMessage(kind, text, meta = {}) {
  const box = document.createElement("div");
  box.className = `msg ${kind}`;
  box.textContent = text;

  if (meta.sources && meta.sources.length > 0) {
    const evidence = document.createElement("div");
    evidence.className = "evidence";
    evidence.innerHTML = `<strong>Evidence:</strong> ${meta.sources
      .slice(0, 3)
      .map((source) => `${source.source_type || "source"} (${typeof source.score === "number" ? source.score.toFixed(2) : "-"})`)
      .join(", ")}`;
    box.appendChild(evidence);
  }

  el.chatMessages.appendChild(box);
  el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
}

function renderRelatedInfo(payload = {}) {
  const route = payload.route || "unknown";
  const routeMeta = payload.route_metadata || {};
  const result = payload.result || {};
  const sources = Array.isArray(result.sources) ? result.sources : [];
  const cards = [];

  if (result.correction_applied && result.normalized_query) {
    cards.push({
      tag: "Normalized",
      title: "Interpreted Query",
      detail: result.normalized_query,
      meta: "Spelling / phrase normalization applied",
    });
  }

  if (route === "class_database") {
    const bits = [];
    if (routeMeta.term) bits.push(`Term: ${routeMeta.term}`);
    if (routeMeta.department) bits.push(`Department: ${routeMeta.department}`);
    if (routeMeta.count !== undefined) bits.push(`Matches: ${routeMeta.count}`);
    cards.push({
      tag: "Class DB",
      title: "Direct Database Route",
      detail: "Class question answered directly from Class Database.",
      meta: bits.join(" | "),
    });
  } else if (route === "rag") {
    cards.push({
      tag: "RAG",
      title: "Indexed Retrieval Route",
      detail: "Answer used indexed institutional documents.",
      meta: "Events + Calendars + Class docs",
    });
  }

  for (const source of sources.slice(0, 7)) {
    cards.push({
      tag: source.source_type || "Source",
      title: source.title || source.doc_id || "Related context",
      detail: compactText(source.text || source.snippet || ""),
      meta: sourceMetaLine(source),
      url: source.url || source.metadata?.url || "",
    });
  }

  el.relatedInfoList.innerHTML = "";
  if (cards.length === 0) {
    const empty = document.createElement("article");
    empty.className = "related-card empty";
    empty.innerHTML = "<p class='related-title'>No query context yet</p><p class='related-meta'>Ask a question to populate related information.</p>";
    el.relatedInfoList.appendChild(empty);
    return;
  }

  for (const card of cards) {
    const item = document.createElement("article");
    item.className = "related-card";

    const tag = document.createElement("span");
    tag.className = "related-tag";
    tag.textContent = String(card.tag || "Info").toUpperCase();
    item.appendChild(tag);

    const title = document.createElement("p");
    title.className = "related-title";
    title.textContent = card.title || "Related information";
    item.appendChild(title);

    if (card.detail) {
      const detail = document.createElement("p");
      detail.className = "related-detail";
      detail.textContent = card.detail;
      item.appendChild(detail);
    }
    if (card.meta) {
      const meta = document.createElement("p");
      meta.className = "related-meta";
      meta.textContent = card.meta;
      item.appendChild(meta);
    }
    if (card.url) {
      const link = document.createElement("a");
      link.className = "related-link";
      link.href = card.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = "Open source";
      item.appendChild(link);
    }
    el.relatedInfoList.appendChild(item);
  }
}

function renderPromotions(items, sourceLabel = "events_db") {
  el.promotionList.innerHTML = "";
  if (!items || items.length === 0) {
    const empty = document.createElement("article");
    empty.className = "promo-card empty";
    empty.innerHTML = "<p class='promo-title'>No promotions available</p><p class='promo-meta'>Refresh later.</p>";
    el.promotionList.appendChild(empty);
    return;
  }

  for (const item of items) {
    const card = document.createElement("article");
    card.className = "promo-card";

    const source = document.createElement("span");
    source.className = "promo-source";
    source.textContent = sourceLabel === "events_db" ? "REAL EVENT" : "PROMO";
    card.appendChild(source);

    const title = document.createElement("p");
    title.className = "promo-title";
    title.textContent = item.title || "Campus update";
    card.appendChild(title);

    if (item.summary) {
      const summary = document.createElement("p");
      summary.className = "promo-summary";
      summary.textContent = compactText(item.summary, 150);
      card.appendChild(summary);
    }

    const metaBits = [item.when, item.location].filter(Boolean);
    if (metaBits.length > 0) {
      const meta = document.createElement("p");
      meta.className = "promo-meta";
      meta.textContent = metaBits.join(" | ");
      card.appendChild(meta);
    }

    if (item.url) {
      const link = document.createElement("a");
      link.className = "promo-link";
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = "View details";
      card.appendChild(link);
    }
    el.promotionList.appendChild(card);
  }
}

async function loadPromotions() {
  try {
    const payload = await requestJson("/api/promotions?limit=6");
    renderPromotions(payload.items || [], payload.source || "events_db");
  } catch (err) {
    renderPromotions(localPromotionFallback, "fallback");
    notify(`Promotions unavailable: ${err.message}`);
  }
}

async function onChatSubmit(event) {
  event.preventDefault();
  const message = el.chatInput.value.trim();
  if (!message) return;

  appendMessage("user", message);
  el.chatInput.value = "";

  try {
    const payload = await requestJson("/api/chat", "POST", { message, top_k: defaultTopK });
    const result = payload.result || {};

    if (result.correction_applied && result.normalized_query) {
      appendMessage("note", `Interpreted as: ${result.normalized_query}`);
    }
    if (payload.route === "class_database") {
      const meta = payload.route_metadata || {};
      const routeBits = [];
      if (meta.department) routeBits.push(`department=${meta.department}`);
      if (meta.term) routeBits.push(`term=${meta.term}`);
      if (meta.count !== undefined) routeBits.push(`count=${meta.count}`);
      if (routeBits.length > 0) {
        appendMessage("note", `Class DB route: ${routeBits.join(" | ")}`);
      }
    }

    appendMessage("assistant", result.answer || "No answer produced.", { sources: result.sources || [] });
    renderRelatedInfo(payload);
  } catch (err) {
    appendMessage("error", err.message);
  }
}

function bootstrap() {
  appendMessage(
    "assistant",
    "I am your campus-only assistant. Ask about classes, deadlines, buildings, events, and services."
  );
  renderRelatedInfo();
  renderPromotions(localPromotionFallback, "fallback");

  el.chatForm.addEventListener("submit", onChatSubmit);
  el.btnRefreshPromotions.addEventListener("click", loadPromotions);
  loadPromotions();
}

bootstrap();
