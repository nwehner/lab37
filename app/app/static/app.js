(function () {
  initUploadForm();
  initPollTrigger();
  initDispatchButton();

  function initUploadForm() {
    const form = document.getElementById("upload-form");
    if (!form) return;

    const fileInput = document.getElementById("csv-file");
    const fileDropLabel = document.getElementById("file-drop-label");
    const resultSection = document.getElementById("upload-result");
    const errorSection = document.getElementById("upload-error");

    fileInput.addEventListener("change", () => {
      const file = fileInput.files && fileInput.files[0];
      fileDropLabel.textContent = file ? file.name : "Choose a CSV file or drag it here";
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      resultSection.hidden = true;
      errorSection.hidden = true;

      const file = fileInput.files && fileInput.files[0];
      if (!file) return;

      const body = new FormData();
      body.append("file", file);

      let response;
      try {
        response = await fetch("/ingest/csv", { method: "POST", body });
      } catch (err) {
        showUploadError("Upload failed: could not reach the server.");
        return;
      }

      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        showUploadError(`Upload failed: ${(detail && detail.detail) || response.statusText}`);
        return;
      }

      const summary = await response.json();
      document.getElementById("upload-result-filename").textContent = summary.filename;
      document.getElementById("upload-rows-ingested").textContent = summary.rows_ingested;
      document.getElementById("upload-rows-warnings").textContent = summary.rows_with_warnings;
      resultSection.hidden = false;
    });

    function showUploadError(message) {
      document.getElementById("upload-error-message").textContent = message;
      errorSection.hidden = false;
    }
  }

  function initPollTrigger() {
    const pollBtn = document.getElementById("trigger-poll-btn");
    if (!pollBtn) return;

    pollBtn.addEventListener("click", async () => {
      const originalLabel = pollBtn.textContent;
      pollBtn.disabled = true;
      pollBtn.textContent = "Polling…";

      try {
        const response = await fetch("/ingest/poll/trigger", { method: "POST" });
        if (!response.ok) throw new Error("poll trigger failed");
        window.location.reload();
      } catch (err) {
        pollBtn.disabled = false;
        pollBtn.textContent = originalLabel;
        alert("Poll trigger failed. Check that a polling upstream is configured.");
      }
    });
  }

  function initDispatchButton() {
    const dispatchBtn = document.getElementById("dispatch-btn");
    if (!dispatchBtn) return;

    const errorEl = document.getElementById("dispatch-error");

    dispatchBtn.addEventListener("click", async () => {
      const orderId = dispatchBtn.dataset.orderId;
      const originalLabel = dispatchBtn.textContent;
      dispatchBtn.disabled = true;
      dispatchBtn.textContent = "Dispatching…";
      if (errorEl) errorEl.hidden = true;

      let response;
      try {
        response = await fetch(`/orders/${orderId}/dispatch`, { method: "POST" });
      } catch (err) {
        dispatchBtn.disabled = false;
        dispatchBtn.textContent = originalLabel;
        if (errorEl) {
          errorEl.textContent = "Dispatch failed: could not reach the server.";
          errorEl.hidden = false;
        }
        return;
      }

      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        dispatchBtn.disabled = false;
        dispatchBtn.textContent = originalLabel;
        if (errorEl) {
          errorEl.textContent = `Dispatch failed: ${(detail && detail.detail) || response.statusText}`;
          errorEl.hidden = false;
        }
        return;
      }

      window.location.reload();
    });
  }
})();
