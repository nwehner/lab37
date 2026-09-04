(function () {
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
      showError("Upload failed: could not reach the server.");
      return;
    }

    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      showError(`Upload failed: ${(detail && detail.detail) || response.statusText}`);
      return;
    }

    const summary = await response.json();
    document.getElementById("upload-result-filename").textContent = summary.filename;
    document.getElementById("upload-rows-ingested").textContent = summary.rows_ingested;
    document.getElementById("upload-rows-warnings").textContent = summary.rows_with_warnings;
    resultSection.hidden = false;
  });

  function showError(message) {
    document.getElementById("upload-error-message").textContent = message;
    errorSection.hidden = false;
  }
})();
