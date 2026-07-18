const workflowConfig = {
  pickup: {
    title: "Monitoring Pickup",
    breadcrumb: "Pickup / Monitoring Pickup",
    description: "Export monitoring pickup dengan rentang panjang yang dipecah otomatis.",
    batchDays: 7,
    exports: [
      ["report_monitoring_xlsx", "Monitoring XLSX"],
      ["report_monitoring", "Monitoring XLS"],
      ["report_monitoring_zilingo_xlsx", "Report Pickup XLSX"],
      ["report", "Report Pickup XLS"],
    ],
    fields: [
      ["date_pickup", "Berdasarkan tanggal", "select"], ["pilih_status", "Status pickup", "select"],
      ["customers", "Customer", "select"], ["branch_area_asal", "Area asal", "select"],
      ["branch_ori", "Cabang asal", "select"], ["branch_area_tujuan", "Area tujuan", "select"],
      ["branch_dest", "Cabang tujuan", "select"], ["is_cod", "COD", "select"],
      ["pilih_pickup_place", "Tempat pickup", "select"], ["pilih_rowstate", "Rowstate", "select"],
      ["koli", "Jumlah koli", "number"], ["kilo", "Berat (kg)", "number"],
    ],
  },
  pickup_manual: {
    title: "Monitoring Pickup Manual",
    breadcrumb: "Pickup Manual / Monitoring Pickup",
    description: "Export pickup manual dengan filter portal dan pembagian tanggal otomatis.",
    batchDays: 7,
    exports: [["report_monitoring_v2", "Pickup Manual Produktivitas"], ["report_monitoring", "Pickup Manual Outstanding"]],
    fields: [
      ["date_pickup", "Berdasarkan tanggal", "select"], ["pilih_status", "Status pickup", "select"],
      ["customers", "Kode customer", "text"], ["origin_area_branch_code", "Area asal", "select"],
      ["branch_ori", "Cabang asal", "select"], ["branch_dest", "Cabang tujuan", "select"],
      ["counter_type", "Tipe counter", "select"], ["koli", "Jumlah koli", "number"],
      ["kilo", "Berat (kg)", "number"],
    ],
  },
  pod_v2: {
    title: "Export Laporan POD V2",
    breadcrumb: "Laporan POD / Export Laporan POD V2",
    description: "Buat antrean laporan POD untuk setiap batch tanggal dan ambil file saat server selesai.",
    batchDays: 7,
    exports: [["pod_v2", "Excel POD V2"]],
    fields: [
      ["export_date_type", "Jenis tanggal export", "select"], ["awb_master_id", "No. master AWB", "text"],
      ["origin_area_branch_code", "Area asal", "select"], ["origin_branch_code", "Cabang asal", "select"],
      ["destination_area_branch_code", "Area tujuan", "select"], ["destination_branch_code", "Cabang tujuan", "select"],
      ["customer_code", "Kode customer", "text"], ["tgl_terima", "Tanggal terima", "date"],
      ["report_type_code", "Tipe laporan", "select"], ["pod_status_code", "Status POD", "select"],
      ["transaction_type_code", "Tipe transaksi", "select"], ["service_type_code", "Jenis layanan", "select"],
      ["courier_code", "Kurir", "select"], ["transportation_code", "Transportasi", "select"],
      ["opt_insurance", "Asuransi", "select"], ["customer_div", "Divisi customer", "select"],
      ["flag_return", "Status return", "select"], ["flag_rowstate", "Rowstate", "select"],
      ["shipment_type_code", "Jenis barang", "select"], ["awb_type", "Tipe AWB", "select"],
    ],
  },
  pod_awb: {
    title: "Laporan POD by AWB",
    breadcrumb: "Laporan POD / Laporan POD by AWB",
    description: "Tempel daftar AWB tanpa batas; aplikasi membagi maksimal 10.000 AWB per file.",
    exports: [["pod_awb", "Export Data"]],
    fields: [],
  },
};

const workflowLabels = {
  pickup: "Monitoring Pickup",
  pickup_manual: "Pickup Manual",
  pod_v2: "Laporan POD V2",
  pod_awb: "POD by AWB",
};

const AUTO_JOBS_KEY = "coresys-auto-download-jobs";
const DOWNLOADED_BATCHES_KEY = "coresys-downloaded-batches";

function storedSet(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "[]");
    return new Set(Array.isArray(value) ? value : []);
  } catch {
    return new Set();
  }
}

function persistDownloadState() {
  localStorage.setItem(AUTO_JOBS_KEY, JSON.stringify([...state.autoDownloadJobs]));
  localStorage.setItem(DOWNLOADED_BATCHES_KEY, JSON.stringify([...state.downloadedBatches]));
}

const state = {
  workflow: "pickup",
  options: {},
  authenticated: false,
  poller: null,
  autoDownloadJobs: storedSet(AUTO_JOBS_KEY),
  downloadedBatches: storedSet(DOWNLOADED_BATCHES_KEY),
};
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || "Permintaan gagal.");
  return data;
}

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(element.timer);
  element.timer = setTimeout(() => element.classList.remove("show"), 3500);
}

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons({ attrs: { "stroke-width": 1.8 } });
}

function setSession(authenticated, username = "") {
  state.authenticated = authenticated;
  $("#session-user").textContent = authenticated ? username : "Belum login";
  $("#session-state").textContent = authenticated ? "Sesi portal aktif" : "Portal tidak terhubung";
  $("#avatar").textContent = authenticated ? username.slice(0, 2).toUpperCase() : "-";
  $("#logout-button").hidden = !authenticated;
  $(".connection").classList.toggle("online", authenticated);
  $("#connection-text").textContent = authenticated ? "Terhubung ke portal" : "Belum terhubung";
}

function showLogin() {
  const dialog = $("#login-dialog");
  if (!dialog.open) dialog.showModal();
}

function parseAwbs() {
  const seen = new Set();
  return $("#awb_text").value.toUpperCase().split(/[\s,;]+/).map(v => v.trim()).filter(v => v && !seen.has(v) && seen.add(v));
}

function updateAwbPreview() {
  const count = parseAwbs().length;
  const size = Math.max(1, Math.min(10000, Number($("#batch_size").value) || 10000));
  const batches = count ? Math.ceil(count / size) : 0;
  $("#awb-count").textContent = `${count.toLocaleString("id-ID")} AWB unik`;
  $("#awb-preview span").textContent = count
    ? `${count.toLocaleString("id-ID")} AWB akan menghasilkan ${batches} file, maksimal ${size.toLocaleString("id-ID")} AWB per file.`
    : "Daftar akan otomatis dipecah maksimal 10.000 AWB per file.";
}

function dateDiffDays(start, end) {
  const a = new Date(`${start}T00:00:00`);
  const b = new Date(`${end}T00:00:00`);
  return Math.floor((b - a) / 86400000) + 1;
}

function updateBatchPreview() {
  const start = $("#date_from").value;
  const end = $("#date_to").value;
  const days = Number($("#batch_days").value) || 1;
  const preview = $("#batch-preview span");
  if (!start || !end) {
    preview.textContent = "Tentukan rentang tanggal untuk melihat pembagian batch.";
    return;
  }
  const total = dateDiffDays(start, end);
  if (total < 1) {
    preview.textContent = "Tanggal akhir harus sama atau setelah tanggal awal.";
    return;
  }
  const batches = Math.ceil(total / days);
  preview.textContent = `${total} hari akan dipecah menjadi ${batches} batch, masing-masing maksimal ${days} hari.`;
}

function renderExports(config) {
  $("#export-options").innerHTML = config.exports.map(([value, label], index) => `
    <label class="segment"><input type="radio" name="export" value="${value}" ${index === 0 ? "checked" : ""}><span>${label}</span></label>
  `).join("");
}

function optionMarkup(field, options) {
  const values = options?.length ? options : [{ value: "", label: "Semua" }];
  return values.map(option => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label || option.value || "Semua")}</option>`).join("");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function renderFields(config) {
  $("#filter-grid").innerHTML = config.fields.map(([name, label, type]) => {
    const id = `filter-${name}`;
    if (type === "select") {
      return `<label class="field"><span>${label}</span><select id="${id}" data-filter="${name}">${optionMarkup(name, state.options[name])}</select></label>`;
    }
    return `<label class="field"><span>${label}</span><input id="${id}" data-filter="${name}" type="${type}" ${type === "number" ? 'min="0"' : ""}></label>`;
  }).join("");
}

async function loadOptions(workflow) {
  $("#option-state").textContent = "Memuat opsi dari portal...";
  try {
    const result = await api(`/api/options/${workflow}`);
    state.options = result.options;
    if (state.workflow === workflow) renderFields(workflowConfig[workflow]);
    $("#option-state").textContent = "Opsi portal aktif";
  } catch (error) {
    $("#option-state").textContent = "Opsi tidak tersedia";
    if (/login|sesi/i.test(error.message)) showLogin();
    toast(error.message);
  }
}

function showWorkflow(workflow) {
  state.workflow = workflow;
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.workflow === workflow));
  const jobsMode = workflow === "jobs";
  $("#form-view").hidden = jobsMode;
  $("#jobs-view").hidden = !jobsMode;
  if (jobsMode) {
    $("#page-title").textContent = "Antrean Download";
    $("#breadcrumb").textContent = "Aktivitas / Antrean Download";
    loadJobs();
    return;
  }

  const config = workflowConfig[workflow];
  const awbMode = workflow === "pod_awb";
  $("#page-title").textContent = config.title;
  $("#breadcrumb").textContent = config.breadcrumb;
  $("#workflow-description").textContent = config.description;
  $("#date-section").hidden = awbMode;
  $("#awb-section").hidden = !awbMode;
  ["#date_from", "#date_to", "#batch_days", "#delay_seconds", "#parallel_workers"].forEach(selector => {
    $(selector).disabled = awbMode;
  });
  ["#awb_text", "#batch_size", "#awb_delay_seconds", "#awb_parallel_workers"].forEach(selector => {
    $(selector).disabled = !awbMode;
  });
  $("#awb_text").required = awbMode;
  $("#filter-section").hidden = config.fields.length === 0;
  $("#export-section").hidden = awbMode;
  $("#start-button span").textContent = awbMode ? "Export & download" : "Mulai download";
  $("#batch_days").value = config.batchDays || 7;
  $("#batch_days").max = workflow === "pod_v2" ? "31" : "366";
  state.options = {};
  renderFields(config);
  renderExports(config);
  updateBatchPreview();
  if (config.fields.length && state.authenticated) loadOptions(workflow);
  refreshIcons();
}

function collectFilters() {
  return Object.fromEntries($$("[data-filter]").map(element => [element.dataset.filter, element.value]));
}

async function startJob(event) {
  event.preventDefault();
  const button = $("#start-button");
  button.disabled = true;
  try {
    const payload = {
      workflow: state.workflow,
      export: document.querySelector('input[name="export"]:checked')?.value || "",
      filters: collectFilters(),
    };
    if (state.workflow === "pod_awb") {
      payload.awb_text = $("#awb_text").value;
      payload.batch_size = Number($("#batch_size").value);
      payload.delay_seconds = Number($("#awb_delay_seconds").value);
      payload.parallelism = Number($("#awb_parallel_workers").value);
    } else {
      payload.date_from = $("#date_from").value;
      payload.date_to = $("#date_to").value;
      payload.batch_days = Number($("#batch_days").value);
      payload.delay_seconds = Number($("#delay_seconds").value);
      payload.parallelism = Number($("#parallel_workers").value);
    }
    const result = await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
    state.autoDownloadJobs.add(result.job.id);
    persistDownloadState();
    toast(`Pekerjaan ${result.job.id} masuk antrean.`);
    showWorkflow("jobs");
  } catch (error) {
    if (/login|sesi/i.test(error.message)) showLogin();
    toast(error.message);
  } finally {
    button.disabled = false;
  }
}

function bytes(value) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const level = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / 1024 ** level).toFixed(level > 1 ? 1 : 0)} ${units[level]}`;
}

function statusLabel(status) {
  return ({ queued: "Menunggu", running: "Berjalan", waiting_server: "Diproses server", downloading: "Mengunduh", complete: "Selesai", failed: "Gagal", cancelled: "Dibatalkan", complete_with_errors: "Selesai dengan error" })[status] || status;
}

function renderJobs(jobs) {
  $("#jobs-empty").hidden = jobs.length > 0;
  $("#jobs-list").innerHTML = jobs.map(job => {
    const done = job.completed + job.failed;
    const progress = job.batch_count ? Math.round(done / job.batch_count * 100) : 0;
    const active = ["queued", "running"].includes(job.status);
    return `<article class="job">
      <div class="job-summary">
        <div class="job-title"><span class="job-icon"><i data-lucide="${job.workflow === "pod_awb" ? "scan-line" : "download"}"></i></span><div><strong>${workflowLabels[job.workflow]}</strong><small>${job.id} · ${job.batch_count} batch · ${job.created_at.replace("T", " ")}</small></div></div>
        <span class="status ${job.status}">${statusLabel(job.status)}</span>
        <div class="job-progress"><div class="progress-track"><div class="progress-fill" style="width:${progress}%"></div></div><small>${done}/${job.batch_count} batch selesai</small></div>
        <div class="job-actions">${active ? `<button class="button danger cancel-job" data-id="${job.id}"><i data-lucide="square"></i>Batalkan</button>` : ""}</div>
      </div>
      <table class="batch-table"><thead><tr><th>Batch</th><th>Status</th><th>Progres</th><th>Hasil</th></tr></thead><tbody>
        ${job.batches.map(batch => {
          const progressText = batch.total ? `${bytes(batch.downloaded)} / ${bytes(batch.total)}` : (batch.downloaded ? bytes(batch.downloaded) : "-");
          const warning = batch.warning ? `<small class="warning-text">${escapeHtml(batch.warning)}</small>` : "";
          const result = batch.file ? `<a class="download-link" href="/api/jobs/${job.id}/batches/${batch.index}/download">Unduh file</a>${warning}` : (batch.error ? `<span class="error-text" title="${escapeHtml(batch.error)}">${escapeHtml(batch.error.slice(0, 80))}</span>` : "-");
          return `<tr><td>${escapeHtml(batch.label)}</td><td><span class="status ${batch.status}">${statusLabel(batch.status)}</span></td><td>${progressText}</td><td>${result}</td></tr>`;
        }).join("")}
      </tbody></table>
    </article>`;
  }).join("");
  $("#active-count").textContent = jobs.length > 99 ? "99+" : String(jobs.length);
  $("#active-count").title = `${jobs.length} pekerjaan download`;
  refreshIcons();
  autoDownloadCompleted(jobs);
}

function autoDownloadCompleted(jobs) {
  const visibleJobIds = new Set(jobs.map(job => job.id));
  let stateChanged = false;
  for (const jobId of [...state.autoDownloadJobs]) {
    if (!visibleJobIds.has(jobId)) {
      state.autoDownloadJobs.delete(jobId);
      stateChanged = true;
    }
  }

  let downloadDelay = 0;
  for (const job of jobs) {
    if (!state.autoDownloadJobs.has(job.id)) continue;
    for (const batch of job.batches) {
      const key = `${job.id}:${batch.index}`;
      if (!batch.file || state.downloadedBatches.has(key)) continue;
      state.downloadedBatches.add(key);
      stateChanged = true;
      const url = `/api/jobs/${job.id}/batches/${batch.index}/download?auto=1`;
      setTimeout(() => triggerBackgroundDownload(url, batch.index), downloadDelay);
      downloadDelay += 1200;
    }
    if (["complete", "complete_with_errors", "cancelled"].includes(job.status)) {
      state.autoDownloadJobs.delete(job.id);
      stateChanged = true;
    }
  }
  if (stateChanged) persistDownloadState();
}

function triggerBackgroundDownload(url, batchIndex) {
  const frame = document.createElement("iframe");
  frame.hidden = true;
  frame.setAttribute("aria-hidden", "true");
  frame.src = url;
  document.body.appendChild(frame);
  setTimeout(() => frame.remove(), 60000);
  toast(`Batch ${batchIndex} selesai. Download otomatis dimulai.`);
}

async function loadJobs() {
  if (!state.authenticated) return;
  try {
    const result = await api("/api/jobs");
    renderJobs(result.jobs);
  } catch (error) {
    toast(error.message);
  }
}

async function login(event) {
  event.preventDefault();
  const button = $("#login-button");
  const error = $("#login-error");
  button.disabled = true;
  error.hidden = true;
  try {
    const result = await api("/api/login", { method: "POST", body: JSON.stringify({
      username: $("#login-username").value,
      password: $("#login-password").value,
      pin: $("#login-pin").value,
    }) });
    setSession(true, result.profile.username);
    $("#login-password").value = "";
    $("#login-pin").value = "";
    $("#login-dialog").close();
    showWorkflow(state.workflow === "jobs" ? "pickup" : state.workflow);
    loadJobs();
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
}

async function logout() {
  await api("/api/logout", { method: "POST", body: "{}" });
  setSession(false);
  showLogin();
}

function bindEvents() {
  $$(".nav-item").forEach(item => item.addEventListener("click", () => showWorkflow(item.dataset.workflow)));
  $("#workflow-form").addEventListener("submit", startJob);
  $("#login-form").addEventListener("submit", login);
  $("#logout-button").addEventListener("click", logout);
  $("#refresh-jobs").addEventListener("click", loadJobs);
  $("#date_from").addEventListener("change", updateBatchPreview);
  $("#date_to").addEventListener("change", updateBatchPreview);
  $("#batch_days").addEventListener("input", updateBatchPreview);
  $("#awb_text").addEventListener("input", updateAwbPreview);
  $("#batch_size").addEventListener("input", updateAwbPreview);
  $("#reset-button").addEventListener("click", () => {
    $("#workflow-form").reset();
    $("#batch_days").value = workflowConfig[state.workflow]?.batchDays || 7;
    $("#batch_days").max = state.workflow === "pod_v2" ? "31" : "366";
    updateBatchPreview();
    updateAwbPreview();
  });
  $("#jobs-list").addEventListener("click", async event => {
    const button = event.target.closest(".cancel-job");
    if (!button) return;
    try {
      await api(`/api/jobs/${button.dataset.id}/cancel`, { method: "POST", body: "{}" });
      loadJobs();
    } catch (error) { toast(error.message); }
  });
}

async function init() {
  bindEvents();
  showWorkflow("pickup");
  refreshIcons();
  try {
    const current = await api("/api/session");
    setSession(current.authenticated, current.username || "");
    if (!current.authenticated) showLogin();
    else loadOptions("pickup");
  } catch { showLogin(); }
  state.poller = setInterval(() => {
    if (state.authenticated) loadJobs();
  }, 3000);
}

document.addEventListener("DOMContentLoaded", init);
