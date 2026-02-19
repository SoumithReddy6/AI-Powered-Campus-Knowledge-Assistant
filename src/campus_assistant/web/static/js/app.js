const el = {
  statDocuments: document.getElementById("statDocuments"),
  statIndex: document.getElementById("statIndex"),
  statBackend: document.getElementById("statBackend"),
  statHealth: document.getElementById("statHealth"),
  syntheticSize: document.getElementById("syntheticSize"),
  syntheticSizeValue: document.getElementById("syntheticSizeValue"),
  pipelineOutput: document.getElementById("pipelineOutput"),
  btnIngest: document.getElementById("btnIngest"),
  btnBuild: document.getElementById("btnBuild"),
  btnEval: document.getElementById("btnEval"),
  chatMessages: document.getElementById("chatMessages"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  evalMetrics: document.getElementById("evalMetrics"),
  toast: document.getElementById("toast"),
};

const defaultTopK = window.APP_DEFAULT_TOP_K || 5;

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
    const message = data.detail || data.message || `Request failed (${response.status})`;
    throw new Error(message);
  }

  return data;
}

function notify(message) {
  el.toast.textContent = message;
  el.toast.classList.add("show");
  window.clearTimeout(notify._timer);
  notify._timer = window.setTimeout(() => el.toast.classList.remove("show"), 2200);
}

function setBusy(button, busy) {
  button.disabled = busy;
  if (busy) {
    button.dataset.originalText = button.textContent;
    button.textContent = "Working...";
  } else if (button.dataset.originalText) {
    button.textContent = button.dataset.originalText;
  }
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
      .map((source) => `${source.source_type} (${source.score})`)
      .join(", ")}`;
    box.appendChild(evidence);
  }

  el.chatMessages.appendChild(box);
  el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
}

function updateStatus(payload) {
  el.statDocuments.textContent = String(payload.documents ?? "-");
  el.statIndex.textContent = payload.index_exists ? "Ready" : "Missing";
  el.statBackend.textContent = payload.index_backend || "-";
}

function renderEval(report) {
  const metrics = [
    ["Intent Accuracy", report.intent?.accuracy],
    ["Intent F1", report.intent?.f1_macro],
    ["HitRate@5", report.retrieval?.hit_rate_at_5],
    ["MRR", report.retrieval?.mrr],
    ["Avg Latency (ms)", report.response_quality?.avg_latency_ms],
    ["P95 Latency (ms)", report.response_quality?.p95_latency_ms],
  ];

  el.evalMetrics.innerHTML = "";
  for (const [label, value] of metrics) {
    const card = document.createElement("article");
    const p = document.createElement("p");
    p.textContent = label;
    const strong = document.createElement("strong");
    if (typeof value === "number") {
      strong.textContent = value.toFixed(2);
    } else {
      strong.textContent = "-";
    }
    card.appendChild(p);
    card.appendChild(strong);
    el.evalMetrics.appendChild(card);
  }
}

function setPipelineOutput(payload) {
  el.pipelineOutput.textContent = JSON.stringify(payload, null, 2);
}

async function refreshStatus() {
  try {
    const health = await requestJson("/api/health");
    el.statHealth.textContent = health.status === "ok" ? "Online" : "Degraded";

    const status = await requestJson("/api/status");
    updateStatus(status);
  } catch (err) {
    el.statHealth.textContent = "Error";
    notify(err.message);
  }
}

async function onIngest() {
  setBusy(el.btnIngest, true);
  try {
    const syntheticSize = Number(el.syntheticSize.value);
    const payload = await requestJson("/api/pipeline/ingest", "POST", {
      synthetic_size: syntheticSize,
    });
    setPipelineOutput(payload.summary);
    notify("Ingestion complete");
    await refreshStatus();
  } catch (err) {
    setPipelineOutput({ error: err.message });
    notify(err.message);
  } finally {
    setBusy(el.btnIngest, false);
  }
}

async function onBuildIndex() {
  setBusy(el.btnBuild, true);
  try {
    const payload = await requestJson("/api/pipeline/build-index", "POST", {});
    setPipelineOutput(payload);
    notify(`Index built (${payload.index_backend})`);
    await refreshStatus();
  } catch (err) {
    setPipelineOutput({ error: err.message });
    notify(err.message);
  } finally {
    setBusy(el.btnBuild, false);
  }
}

async function onEvaluate() {
  setBusy(el.btnEval, true);
  try {
    const payload = await requestJson("/api/evaluate", "POST", {});
    renderEval(payload.report);
    setPipelineOutput(payload.report);
    notify("Evaluation complete");
  } catch (err) {
    setPipelineOutput({ error: err.message });
    notify(err.message);
  } finally {
    setBusy(el.btnEval, false);
  }
}

async function onChatSubmit(event) {
  event.preventDefault();
  const message = el.chatInput.value.trim();
  if (!message) {
    return;
  }

  appendMessage("user", message);
  el.chatInput.value = "";

  try {
    const payload = await requestJson("/api/chat", "POST", {
      message,
      top_k: defaultTopK,
    });

    const result = payload.result;
    if (result.correction_applied && result.normalized_query) {
      appendMessage("note", `Interpreted as: ${result.normalized_query}`);
    }

    appendMessage("assistant", result.answer, { sources: result.sources || [] });
  } catch (err) {
    appendMessage("error", err.message);
  }
}

function bootstrap() {
  appendMessage("assistant", "Ask a campus question. I auto-correct typos and uneven phrasing before retrieval.");

  el.syntheticSize.addEventListener("input", () => {
    el.syntheticSizeValue.textContent = el.syntheticSize.value;
  });

  el.btnIngest.addEventListener("click", onIngest);
  el.btnBuild.addEventListener("click", onBuildIndex);
  el.btnEval.addEventListener("click", onEvaluate);
  el.chatForm.addEventListener("submit", onChatSubmit);

  refreshStatus();
}

bootstrap();
