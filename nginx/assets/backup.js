const backupFile = document.getElementById("backupFile");
const backupFileName = document.getElementById("backupFileName");
const exportBtn = document.getElementById("exportBtn");
const importBtn = document.getElementById("importBtn");
const statusBox = document.getElementById("status");
const serverFile = document.getElementById("serverFile");
const serverHint = document.getElementById("serverHint");
const progressBox = document.getElementById("progress");
const progressPhase = document.getElementById("progressPhase");
const progressPercent = document.getElementById("progressPercent");
const progressBar = document.getElementById("progressBar");
const progressMetrics = document.getElementById("progressMetrics");
const periodButtons = document.getElementById("periodButtons");
const spanHint = document.getElementById("spanHint");
const customHint = document.getElementById("customHint");
const fromDate = document.getElementById("fromDate");
const toDate = document.getElementById("toDate");

const POLL_MS = 1000;

function setStatus(message, type) {
  statusBox.textContent = message;
  statusBox.className = "status show" + (type ? " " + type : "");
}

function chosen(name) {
  return document.querySelector(`input[name="${name}"]:checked`).value;
}

/** Filenames come from a directory listing, so they reach the markup as
    text rather than as anything the browser would act on. */
function escapeHtml(value) {
  return String(value).replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character],
  );
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const power = Math.min(
    units.length - 1,
    Math.floor(Math.log(bytes) / Math.log(1024)),
  );
  const value = bytes / Math.pow(1024, power);
  return `${value.toFixed(power === 0 ? 0 : 1)} ${units[power]}`;
}

function formatDuration(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${Math.round(seconds % 60)}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function formatRows(rows) {
  return rows.toLocaleString();
}

/** Shows a bar. A null `percent` means the total is not known yet. */
function showProgress(phase, percent, metrics) {
  progressBox.classList.add("show");
  progressPhase.textContent = phase;
  if (percent == null) {
    progressBar.classList.add("indeterminate");
    progressPercent.textContent = "";
  } else {
    progressBar.classList.remove("indeterminate");
    progressBar.firstElementChild.style.width = `${percent}%`;
    progressPercent.textContent = `${percent.toFixed(1)}%`;
  }
  progressMetrics.innerHTML = (metrics || [])
    .filter(Boolean)
    .map(([label, value]) => `${label} <b>${value}</b>`)
    .join("");
}

/** Remaining time from the rate achieved so far — steady enough to be
    worth showing once a run is properly under way. */
function estimateRemaining(job) {
  if (!job.total || !job.done || job.elapsed < 5) return null;
  const rate = job.done / job.elapsed;
  if (rate <= 0) return null;
  return formatDuration((job.total - job.done) / rate);
}

function renderJob(job) {
  const remaining = estimateRemaining(job);
  const metrics = [
    job.total
      ? ["Read", `${formatBytes(job.done)} of ${formatBytes(job.total)}`]
      : ["Read", formatBytes(job.done)],
    job.kind === "export" && job.bytes_out
      ? ["Downloaded", formatBytes(job.bytes_out)]
      : null,
    job.rows_added
      ? ["Rows added", formatRows(job.rows_added)]
      : null,
    job.rows_skipped
      ? ["Already stored", formatRows(job.rows_skipped)]
      : null,
    ["Elapsed", formatDuration(job.elapsed)],
    remaining ? ["Remaining", `about ${remaining}`] : null,
  ];
  showProgress(job.phase, job.percent, metrics);
}

/** Follows a job to completion, keeping the bar current. */
async function trackJob(id) {
  for (;;) {
    const response = await fetch(`/api/backup/jobs/${id}`, {
      cache: "no-store",
    });
    if (response.status === 404) {
      throw new Error("The job is no longer being tracked");
    }
    const job = await response.json();
    renderJob(job);
    if (job.state === "error") throw new Error(job.error || "Job failed");
    if (job.state === "done") return job;
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
}

async function checkedFetch(path, options) {
  const response = await fetch(path, options);
  if (response.redirected && response.url.includes("/auth/")) {
    window.location.assign(response.url);
    return new Promise(() => {});
  }
  if (!response.ok) {
    let message = response.status + " " + response.statusText;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch (_error) {
      // Keep the HTTP status when the response is not JSON.
    }
    throw new Error(message);
  }
  return response;
}

function setBusy(busy) {
  importBtn.disabled = busy;
  // Export stays governed by whether the chosen period holds anything, so
  // finishing a run hands the decision back rather than simply enabling it.
  exportBtn.disabled = busy;
  if (!busy) renderExportState();
}

backupFile.addEventListener("change", () => {
  const file = backupFile.files && backupFile.files[0];
  backupFileName.textContent = file
    ? `${file.name} (${formatBytes(file.size)})`
    : "No file selected";
  if (file) {
    document.querySelector('input[name="source"][value="upload"]').checked = true;
  }
});

/** Lists the backups the scheduled dump has already written, so a large
    restore never has to travel through the browser. */
async function loadServerFiles() {
  try {
    const response = await checkedFetch("/api/backup/files");
    const { directory, files } = await response.json();
    serverFile.innerHTML = files
      .map(
        (file) =>
          `<option value="${escapeHtml(file.name)}">${escapeHtml(
            file.name,
          )} — ${formatBytes(file.size)}</option>`,
      )
      .join("");
    serverFile.disabled = files.length === 0;
    serverHint.textContent = files.length
      ? `${files.length} backup${files.length === 1 ? "" : "s"} in ${directory}`
      : `No .sql.gz files in ${directory} yet.`;
  } catch (error) {
    serverFile.disabled = true;
    serverHint.textContent = `Could not list server backups: ${error}`;
  }
}

/** What the databases hold, and which periods are worth offering. */
let coverage = null;
let period = "day";
let customCheck = 0;

/** Sensor tables have historically held seconds as well as milliseconds,
    so a stored value is normalised before it is read as a date. */
function asDate(value) {
  if (value == null) return null;
  return new Date(value < 1e11 ? value * 1000 : value);
}

function formatDay(value) {
  const date = asDate(value);
  return date
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date)
    : "—";
}

/** `YYYY-MM-DD` for a date input, in the viewer's own timezone. */
function inputValue(value) {
  const date = asDate(value);
  if (!date) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function dayStart(value) {
  return value ? new Date(`${value}T00:00:00`).getTime() : null;
}

function dayEnd(value) {
  return value ? new Date(`${value}T23:59:59.999`).getTime() : null;
}

function windowFor(anchor, key) {
  return (coverage?.windows || []).find(
    (entry) => entry.anchor === anchor && entry.period === key,
  );
}

/** The period the Export button would send: null means everything. */
function selectedRange() {
  const mode = chosen("period");
  if (mode === "all") return { from: null, to: null, available: !!coverage?.newest };
  if (mode === "recent") {
    const entry = windowFor(chosen("anchor"), period);
    return entry
      ? { from: entry.from, to: entry.to, available: entry.available }
      : { from: null, to: null, available: false };
  }
  const from = dayStart(fromDate.value);
  const to = dayEnd(toDate.value);
  if (from == null || to == null) return { from, to, available: false };
  const known = coverage?.custom;
  const matches =
    known && Math.abs(known.from - Math.min(from, to)) < 1000 &&
    Math.abs(known.to - Math.max(from, to)) < 1000;
  return { from, to, available: matches ? known.available : false };
}

function renderPeriods() {
  const anchor = chosen("anchor");
  periodButtons.innerHTML = (coverage?.windows || [])
    .filter((entry) => entry.anchor === anchor)
    .map(
      (entry) =>
        `<button type="button" data-period="${entry.period}" ` +
        `aria-pressed="${entry.period === period}" ` +
        `${entry.available ? "" : "disabled "}` +
        `title="${entry.available ? `${formatDay(entry.from)} — ${formatDay(entry.to)}` : "No data in this period"}">` +
        `${escapeHtml(entry.label)}</button>`,
    )
    .join("");
}

function renderExportState() {
  renderPeriods();

  if (coverage?.newest) {
    spanHint.textContent =
      `${formatBytes(coverage.total_bytes)} stored, ` +
      `${formatDay(coverage.oldest)} to ${formatDay(coverage.newest)}.`;
  } else if (coverage) {
    spanHint.textContent = "The databases hold no data yet.";
  }

  const mode = chosen("period");
  const range = selectedRange();
  if (mode === "custom") {
    if (!fromDate.value || !toDate.value) {
      customHint.textContent = "Pick the first and last day to include.";
    } else if (range.available) {
      customHint.textContent = `${formatDay(range.from)} to ${formatDay(range.to)} has data.`;
    } else {
      customHint.textContent = "Nothing was recorded in those days.";
    }
  }

  exportBtn.disabled = !range.available;
}

/** Asks the server whether the typed dates hold anything, since a gap in
    the middle of the stored span is not visible from its edges alone. */
async function checkCustomRange() {
  const from = dayStart(fromDate.value);
  const to = dayEnd(toDate.value);
  if (from == null || to == null) {
    renderExportState();
    return;
  }
  const ticket = ++customCheck;
  customHint.textContent = "Checking…";
  exportBtn.disabled = true;
  try {
    const response = await checkedFetch(
      `/api/backup/coverage?from_ts=${from}&to_ts=${to}`,
    );
    const fresh = await response.json();
    if (ticket !== customCheck) return;
    coverage = fresh;
  } catch (error) {
    if (ticket === customCheck) customHint.textContent = String(error);
    return;
  }
  renderExportState();
}

async function loadCoverage() {
  try {
    const response = await checkedFetch("/api/backup/coverage");
    coverage = await response.json();
    if (coverage.oldest && !fromDate.value) {
      fromDate.value = inputValue(coverage.oldest);
      toDate.value = inputValue(coverage.newest);
    }
    // Land on a period that has something in it.
    const usable = coverage.windows.find(
      (entry) => entry.anchor === "data" && entry.available,
    );
    if (usable) period = usable.period;
    renderExportState();
  } catch (error) {
    spanHint.textContent = `Could not read what is stored: ${error}`;
  }
}

periodButtons.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-period]");
  if (!button) return;
  period = button.dataset.period;
  document.querySelector('input[name="period"][value="recent"]').checked = true;
  renderExportState();
});

for (const input of document.querySelectorAll(
  'input[name="period"], input[name="anchor"]',
)) {
  input.addEventListener("change", renderExportState);
}

for (const input of [fromDate, toDate]) {
  input.addEventListener("change", () => {
    document.querySelector('input[name="period"][value="custom"]').checked = true;
    checkCustomRange();
  });
}

exportBtn.addEventListener("click", async () => {
  const range = selectedRange();
  setBusy(true);
  statusBox.className = "status";
  showProgress("Starting export…", null, []);
  try {
    const query =
      range.from != null && range.to != null
        ? `?from_ts=${Math.round(range.from)}&to_ts=${Math.round(range.to)}`
        : "";
    const response = await checkedFetch(`/api/backup/export${query}`, {
      method: "POST",
    });
    const { id, filename } = await response.json();

    // The archive is compressed as it is dumped, so the browser writes it
    // straight to disk while the job reports how far the dump has gone.
    const link = document.createElement("a");
    link.href = `/api/backup/export/${id}/download`;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();

    const job = await trackJob(id);
    setStatus(
      `Exported ${formatBytes(job.bytes_out)} to ${filename} in ${formatDuration(
        job.elapsed,
      )}.`,
      "ok",
    );
  } catch (error) {
    setStatus(String(error), "error");
  } finally {
    setBusy(false);
  }
});

/** Posts the import and reports the upload itself, which is the one phase
    the server cannot see. Resolves to the job id. */
function postImport(form, onUpload) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/api/backup/import");
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onUpload(event.loaded, event.total);
    });
    request.addEventListener("load", () => {
      let body = {};
      try {
        body = JSON.parse(request.responseText);
      } catch (_error) {
        // A non-JSON body leaves the HTTP status to explain itself.
      }
      if (request.status >= 200 && request.status < 300) {
        resolve(body.id);
      } else if (request.responseURL.includes("/auth/")) {
        window.location.assign(request.responseURL);
      } else {
        reject(new Error(body.detail || `${request.status} ${request.statusText}`));
      }
    });
    request.addEventListener("error", () =>
      reject(new Error("The upload could not be completed")),
    );
    request.send(form);
  });
}

importBtn.addEventListener("click", async () => {
  const mode = chosen("mode");
  const source = chosen("source");
  const file = backupFile.files && backupFile.files[0];
  const form = new FormData();
  form.set("mode", mode);

  if (source === "upload") {
    if (!file) {
      setStatus("Choose a .sql.gz backup file to upload first.", "error");
      return;
    }
    form.set("backup", file);
  } else {
    if (!serverFile.value) {
      setStatus("No backup on the server to import.", "error");
      return;
    }
    form.set("filename", serverFile.value);
  }

  const warning =
    mode === "replace"
      ? "Replace everything: every table in this backup will be dropped and " +
        "rebuilt from the file, discarding what is stored now. Continue?"
      : "Add the rows from this backup to what is already stored. Continue?";
  if (!window.confirm(warning)) return;

  setBusy(true);
  statusBox.className = "status";
  showProgress("Preparing…", null, []);
  try {
    const id = await postImport(form, (loaded, total) =>
      showProgress("Uploading the backup", (loaded / total) * 100, [
        ["Sent", `${formatBytes(loaded)} of ${formatBytes(total)}`],
      ]),
    );
    const job = await trackJob(id);
    const summary =
      mode === "merge"
        ? `Added ${formatRows(job.rows_added)} rows and skipped ` +
          `${formatRows(job.rows_skipped)} already stored, in ` +
          `${formatDuration(job.elapsed)}.`
        : `Restored the backup in ${formatDuration(job.elapsed)}.`;
    setStatus(summary, "ok");
  } catch (error) {
    setStatus(String(error), "error");
  } finally {
    setBusy(false);
  }
});

exportBtn.disabled = true;
loadCoverage();
loadServerFiles();
