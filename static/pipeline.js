const runPipelineBtn = document.getElementById("runPipelineBtn");
const pipelinePanel = document.getElementById("pipelinePanel");
const pipelineProgressBar = document.getElementById("pipelineProgressBar");
const pipelineLog = document.getElementById("pipelineLog");

if (!runPipelineBtn) {
  // Not on the wizard session page — nothing to do.
} else {
  let currentRecordId = null;
  let activeSource = null;

  /** Called by sidebar-upload.js whenever audio is loaded/cleared. */
  window.onPipelineAudioLoaded = function (recordId) {
    currentRecordId = recordId || null;
    runPipelineBtn.hidden = !currentRecordId;
    if (!currentRecordId) {
      resetPanel();
    }
  };

  function resetPanel() {
    pipelinePanel.hidden = true;
    pipelineProgressBar.style.width = "0%";
    pipelineLog.textContent = "";
  }

  function appendLog(message) {
    const line = document.createElement("div");
    line.textContent = message;
    pipelineLog.appendChild(line);
    pipelineLog.scrollTop = pipelineLog.scrollHeight;
  }

  function setProgress(done, total, subDone, subTotal) {
    const STEPS_TOTAL = total || 5;
    let pct;
    if (subDone != null && subTotal > 0) {
      // Within a step: interpolate between step boundaries
      const stepSize = 100 / STEPS_TOTAL;
      const stepBase = (done / STEPS_TOTAL) * 100;
      pct = stepBase + stepSize * (subDone / subTotal);
    } else {
      pct = total > 0 ? Math.round((done / total) * 100) : 0;
    }
    pipelineProgressBar.style.width = `${Math.min(100, Math.round(pct))}%`;
  }

  runPipelineBtn.addEventListener("click", () => {
    if (!currentRecordId) return;
    if (activeSource) {
      activeSource.close();
      activeSource = null;
    }

    runPipelineBtn.disabled = true;
    pipelinePanel.hidden = false;
    pipelineProgressBar.style.width = "0%";
    pipelineLog.textContent = "";
    appendLog("Starting pipeline…");

    const source = new EventSource(`/api/pipeline/run/${encodeURIComponent(currentRecordId)}`);
    activeSource = source;

    source.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(event.data);
        setProgress(data.progress ?? 0, data.total ?? 5, data.sub_progress, data.sub_total);
        if (data.message) {
          // Only log step-level messages, not every segment tick
          if (data.sub_progress == null || data.sub_progress === data.sub_total) {
            appendLog(data.message);
          }
        }
        if (data.error) {
          source.close();
          activeSource = null;
          runPipelineBtn.disabled = false;
        }
      } catch {
        appendLog(event.data);
      }
    });

    source.addEventListener("done", () => {
      setProgress(1, 1);
      source.close();
      activeSource = null;
      runPipelineBtn.disabled = false;
    });

    source.addEventListener("error", () => {
      appendLog("Connection error — pipeline may still be running.");
      source.close();
      activeSource = null;
      runPipelineBtn.disabled = false;
    });
  });
}
