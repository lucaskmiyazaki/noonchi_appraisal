const runPipelineBtn = document.getElementById("runPipelineBtn");
const pipelinePanel = document.getElementById("pipelinePanel");
const pipelineProgressBar = document.getElementById("pipelineProgressBar");
const pipelineLog = document.getElementById("pipelineLog");

if (!runPipelineBtn) {
  // Not on the wizard session page — nothing to do.
} else {
  let currentRecordId = null;

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
      const stepSize = 100 / STEPS_TOTAL;
      const stepBase = (done / STEPS_TOTAL) * 100;
      pct = stepBase + stepSize * (subDone / subTotal);
    } else {
      pct = total > 0 ? Math.round((done / total) * 100) : 0;
    }
    pipelineProgressBar.style.width = `${Math.min(100, Math.round(pct))}%`;
  }

  /** Connect to a pipeline job SSE stream. Returns a promise that resolves when done/error/dropped. */
  function followPipelineJob(jobId) {
    return new Promise((resolve) => {
      pipelinePanel.hidden = false;
      const es = new EventSource(`/api/pipeline/job/${encodeURIComponent(jobId)}/stream`);
      let settled = false;

      function finish() {
        if (!settled) { settled = true; es.close(); resolve(); }
      }

      es.addEventListener("message", (event) => {
        try {
          const data = JSON.parse(event.data);
          setProgress(data.progress ?? 0, data.total ?? 5, data.sub_progress, data.sub_total);
          if (data.message && (data.sub_progress == null || data.sub_progress === data.sub_total)) {
            appendLog(data.message);
          }
          if (data.status === "done") {
            setProgress(data.total ?? 5, data.total ?? 5);
            finish();
          } else if (data.status === "error" || data.error) {
            finish();
          }
        } catch { /* ignore */ }
      });

      es.addEventListener("done", () => {
        setProgress(1, 1);
        finish();
      });

      // Connection dropped — resolve so callers can re-enable the button.
      // On next page load the init IIFE will reconnect if the job is still running.
      es.addEventListener("error", () => {
        finish();
      });
    });
  }

  // On page load, check if a pipeline job is already running and reconnect.
  (async () => {
    try {
      const res = await fetch("/api/pipeline/jobs/active");
      if (res.ok) {
        const job = await res.json();
        if (job.job_id && job.record_id) {
          currentRecordId = job.record_id;
          runPipelineBtn.hidden = false;
        }
        if (job.job_id && job.status === "running") {
          setProgress(job.progress ?? 0, job.total ?? 5);
          appendLog("Reconnecting to pipeline\u2026");
          runPipelineBtn.disabled = true;
          await followPipelineJob(job.job_id);
          runPipelineBtn.disabled = false;
        } else if (job.job_id && job.status === "done") {
          pipelinePanel.hidden = false;
          setProgress(job.total ?? 5, job.total ?? 5);
          appendLog("Pipeline complete.");
        } else if (job.job_id && job.status === "error") {
          pipelinePanel.hidden = false;
          appendLog(job.message || "Pipeline error.");
        }
      }
    } catch { /* server unreachable — skip */ }
  })();

  runPipelineBtn.addEventListener("click", async () => {
    if (!currentRecordId) return;
    runPipelineBtn.disabled = true;
    pipelinePanel.hidden = false;
    pipelineProgressBar.style.width = "0%";
    pipelineLog.textContent = "";
    appendLog("Starting pipeline\u2026");

    let jobId;
    try {
      const resp = await fetch(`/api/pipeline/run/${encodeURIComponent(currentRecordId)}`, { method: "POST" });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        appendLog(`Failed to start pipeline: ${err.error || resp.statusText}`);
        runPipelineBtn.disabled = false;
        return;
      }
      const data = await resp.json();
      jobId = data.job_id;
    } catch (err) {
      appendLog(`Failed to start pipeline: ${err}`);
      runPipelineBtn.disabled = false;
      return;
    }

    await followPipelineJob(jobId);
    runPipelineBtn.disabled = false;
  });
}
