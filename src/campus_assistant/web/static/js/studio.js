const el = {
  studioStatDocuments: document.getElementById("studioStatDocuments"),
  studioStatEvents: document.getElementById("studioStatEvents"),
  studioStatCalendars: document.getElementById("studioStatCalendars"),
  studioStatClasses: document.getElementById("studioStatClasses"),
  studioStatUpcoming: document.getElementById("studioStatUpcoming"),
  studioStatIndex: document.getElementById("studioStatIndex"),
  syntheticSize: document.getElementById("syntheticSize"),
  syntheticSizeValue: document.getElementById("syntheticSizeValue"),
  btnIngest: document.getElementById("btnIngest"),
  btnBuild: document.getElementById("btnBuild"),
  btnEval: document.getElementById("btnEval"),
  classCsvFile: document.getElementById("classCsvFile"),
  btnUploadClassCsv: document.getElementById("btnUploadClassCsv"),
  manualSourceType: document.getElementById("manualSourceType"),
  manualPayload: document.getElementById("manualPayload"),
  btnManualIngest: document.getElementById("btnManualIngest"),
  btnStudioLogout: document.getElementById("btnStudioLogout"),
  pipelineOutput: document.getElementById("pipelineOutput"),
  evalMetrics: document.getElementById("evalMetrics"),
  toast: document.getElementById("studioToast"),
};

async function requestStudio(url, method = "GET", payload = null) {
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
  if (response.status === 401) {
    window.location.href = "/studio/login";
    throw new Error("Session expired");
  }

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

function setBusy(button, busy) {
  button.disabled = busy;
  if (busy) {
    button.dataset.originalText = button.textContent;
    button.textContent = "Working...";
  } else if (button.dataset.originalText) {
    button.textContent = button.dataset.originalText;
  }
}

function setPipelineOutput(payload) {
  el.pipelineOutput.textContent = JSON.stringify(payload, null, 2);
}

function updateStatusCards(status) {
  const db = status.db_counts || {};
  el.studioStatDocuments.textContent = String(status.documents ?? "-");
  el.studioStatEvents.textContent = String(db.events ?? "-");
  el.studioStatCalendars.textContent = String(db.calendars ?? "-");
  el.studioStatClasses.textContent = String(db.classes ?? "-");
  el.studioStatUpcoming.textContent = db.upcoming_term || "-";
  el.studioStatIndex.textContent = status.index_exists ? "Ready" : "Missing";
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
    const article = document.createElement("article");
    const p = document.createElement("p");
    p.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = typeof value === "number" ? value.toFixed(2) : "-";
    article.appendChild(p);
    article.appendChild(strong);
    el.evalMetrics.appendChild(article);
  }
}

async function refreshStatus() {
  const status = await requestStudio("/api/studio/status");
  updateStatusCards(status);
}

async function onIngest() {
  setBusy(el.btnIngest, true);
  try {
    const payload = await requestStudio("/api/studio/pipeline/ingest", "POST", {
      synthetic_size: Number(el.syntheticSize.value),
    });
    setPipelineOutput(payload);
    notify("Pipeline ingestion complete");
    await refreshStatus();
  } catch (error) {
    setPipelineOutput({ error: error.message });
    notify(error.message);
  } finally {
    setBusy(el.btnIngest, false);
  }
}

async function onBuildIndex() {
  setBusy(el.btnBuild, true);
  try {
    const payload = await requestStudio("/api/studio/pipeline/build-index", "POST", {});
    setPipelineOutput(payload);
    notify(`Index built (${payload.index_backend})`);
    await refreshStatus();
  } catch (error) {
    setPipelineOutput({ error: error.message });
    notify(error.message);
  } finally {
    setBusy(el.btnBuild, false);
  }
}

async function onEvaluate() {
  setBusy(el.btnEval, true);
  try {
    const payload = await requestStudio("/api/studio/evaluate", "POST", {});
    renderEval(payload.report);
    setPipelineOutput(payload.report);
    notify("Evaluation complete");
  } catch (error) {
    setPipelineOutput({ error: error.message });
    notify(error.message);
  } finally {
    setBusy(el.btnEval, false);
  }
}

async function onUploadClassCsv() {
  setBusy(el.btnUploadClassCsv, true);
  try {
    const file = el.classCsvFile.files[0];
    if (!file) {
      throw new Error("Select a CSV file first.");
    }
    const payload = await requestStudio("/api/studio/classes/upload-csv", "POST", {
      csv_text: await file.text(),
    });
    setPipelineOutput(payload);
    notify(`Class CSV ingested (${payload.upserted} rows)`);
    await refreshStatus();
  } catch (error) {
    setPipelineOutput({ error: error.message });
    notify(error.message);
  } finally {
    setBusy(el.btnUploadClassCsv, false);
  }
}

async function onManualIngest() {
  setBusy(el.btnManualIngest, true);
  try {
    const payloadJson = el.manualPayload.value.trim();
    if (!payloadJson) {
      throw new Error("Paste JSON payload first.");
    }
    const payload = await requestStudio("/api/studio/ingestion/manual", "POST", {
      source_type: el.manualSourceType.value,
      payload_json: payloadJson,
    });
    setPipelineOutput(payload);
    notify(`Manual ingestion complete (${payload.upserted} rows to ${payload.source_type})`);
    await refreshStatus();
  } catch (error) {
    setPipelineOutput({ error: error.message });
    notify(error.message);
  } finally {
    setBusy(el.btnManualIngest, false);
  }
}

async function onLogout() {
  try {
    await requestStudio("/api/studio/logout", "POST", {});
  } catch (_error) {
    // best effort logout
  } finally {
    window.location.href = "/studio/login";
  }
}

function bootstrap() {
  el.syntheticSize.addEventListener("input", () => {
    el.syntheticSizeValue.textContent = el.syntheticSize.value;
  });

  el.btnIngest.addEventListener("click", onIngest);
  el.btnBuild.addEventListener("click", onBuildIndex);
  el.btnEval.addEventListener("click", onEvaluate);
  el.btnUploadClassCsv.addEventListener("click", onUploadClassCsv);
  el.btnManualIngest.addEventListener("click", onManualIngest);
  el.btnStudioLogout.addEventListener("click", onLogout);

  refreshStatus().catch((error) => notify(error.message));
}

bootstrap();
