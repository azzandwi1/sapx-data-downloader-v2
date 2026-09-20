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
    exports: [["report_monitoring", "Pickup Manual Outstanding"], ["report_monitoring_v2", "Pickup Manual Produktifitas"]],
    fields: [
      ["date_pickup", "Berdasarkan tanggal", "select"], ["pilih_status", "Status pickup", "select"],
      ["customers", "Kode customer", "text"], ["origin_area_branch_code", "Area asal", "select"],
      ["branch_ori", "Cabang asal", "select"], ["destination_area_branch_code", "Area tujuan", "select"],
      ["branch_dest", "Cabang tujuan", "select"],
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
  tracking_focus: {
    title: "Tracing Referensi / Focus",
    breadcrumb: "Trace & Tracking / Tracing Referensi / Focus",
    description: "Cari riwayat dan status SLA berdasarkan No. Referensi atau No. AWB, lalu export ke Excel.",
    exports: [["tracking_focus", "Excel Tracing"]],
    fields: [],
  },
  tracking_history: {
    title: "Export History AWB",
    breadcrumb: "Trace & Tracking / Export History AWB",
    description: "Ambil seluruh riwayat banyak AWB dan gabungkan ke dalam satu file Excel.",
    exports: [["tracking_history", "Excel History"]],
    fields: [],
  },
};

const workflowLabels = {
  pickup: "Monitoring Pickup",
  pickup_manual: "Pickup Manual",
  pod_v2: "Laporan POD V2",
  pod_awb: "POD by AWB",
  tracking_focus: "Tracing Referensi",
  tracking_history: "History AWB",
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
  trackingTargets: [],
  trackingFileName: "",
  trackingMode: "milestone",
  focusTargets: [],
  focusFileName: "",
  focusInputType: "excel",
  focusSearchBy: "a.reference_no",
  autoDownloadJobs: storedSet(AUTO_JOBS_KEY),
  downloadedBatches: storedSet(DOWNLOADED_BATCHES_KEY),
};
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
  } catch {
    throw new Error("Backend lokal terputus. Jalankan ulang aplikasi, lalu muat ulang halaman ini.");
  }
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

function setupSecretToggles() {
  ["login-password", "login-pin"].forEach(id => {
    const input = document.getElementById(id);
    if (!input || input.parentElement?.classList.contains("secret-input")) return;

    const wrapper = document.createElement("div");
    wrapper.className = "secret-input";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "secret-toggle";
    button.title = "Tampilkan";
    button.setAttribute("aria-label", `Tampilkan ${id === "login-pin" ? "PIN" : "password"}`);
    button.innerHTML = '<i data-lucide="eye"></i>';
    button.addEventListener("click", () => {
      const visible = input.type === "text";
      input.type = visible ? "password" : "text";
      button.title = visible ? "Tampilkan" : "Sembunyikan";
      button.setAttribute("aria-label", `${visible ? "Tampilkan" : "Sembunyikan"} ${id === "login-pin" ? "PIN" : "password"}`);
      button.innerHTML = `<i data-lucide="${visible ? "eye" : "eye-off"}"></i>`;
      refreshIcons();
      input.focus();
    });
    wrapper.appendChild(button);
  });
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
  const focusMode = state.workflow === "tracking_focus";
  const historyMode = state.workflow === "tracking_history";
  
  if (focusMode) {
    const count = state.focusInputType === "excel" ? state.focusTargets.length : parseAwbs().length;
    $("#awb-count").textContent = `${count.toLocaleString("id-ID")} nomor unik`;
    $("#awb-preview span").textContent = state.focusInputType === "excel"
      ? (count
        ? `${state.focusFileName}: ${count.toLocaleString("id-ID")} nomor siap diproses.`
        : "Pilih file Excel daftar referensi/AWB (contoh: TRACING.xlsx).")
      : (count
        ? `${count.toLocaleString("id-ID")} nomor siap diproses.`
        : "Tempel nomor referensi atau AWB di area teks (satu per baris).");
    return;
  }

  const count = parseAwbs().length;
  $("#awb-count").textContent = `${count.toLocaleString("id-ID")} AWB unik`;

  if (historyMode) {
    $("#awb-preview span").textContent = count
      ? `${count.toLocaleString("id-ID")} AWB akan digabungkan ke satu file Excel.`
      : (state.trackingMode === "milestone"
        ? "Tempel daftar AWB (bisa AWB saja atau AWB dan TLC tujuan, pisahkan spasi/tab)."
        : "Tempel daftar nomor AWB, satu nomor per baris.");
    return;
  }

  const size = Math.max(1, Math.min(10000, Number($("#batch_size").value) || 10000));
  const batches = count ? Math.ceil(count / size) : 0;
  $("#awb-preview span").textContent = count
    ? `${count.toLocaleString("id-ID")} AWB akan menghasilkan ${batches} file, maksimal ${size.toLocaleString("id-ID")} AWB per file.`
    : "Daftar akan otomatis dipecah maksimal 10.000 AWB per file.";
}

function dateDiffDays(start, end) {
  const a = new Date(`${start}T00:00:00`);
  const b = new Date(`${end}T00:00:00`);
  return Math.floor((b - a) / 86400000) + 1;
}

function calculateDateBatches(startStr, endStr, batchDays) {
  const startDate = new Date(`${startStr}T00:00:00`);
  const endDate = new Date(`${endStr}T00:00:00`);
  if (startDate > endDate) return [];
  const batches = [];
  let cursor = new Date(startDate.getTime());
  while (cursor <= endDate) {
    const year = cursor.getFullYear();
    const month = cursor.getMonth();
    const lastDayOfMonth = new Date(year, month + 1, 0);

    const targetEnd = new Date(cursor.getTime());
    targetEnd.setDate(targetEnd.getDate() + (batchDays - 1));

    let batchEnd = targetEnd;
    if (batchEnd > lastDayOfMonth) batchEnd = lastDayOfMonth;
    if (batchEnd > endDate) batchEnd = endDate;

    batches.push({ start: new Date(cursor.getTime()), end: new Date(batchEnd.getTime()) });
    cursor = new Date(batchEnd.getTime());
    cursor.setDate(cursor.getDate() + 1);
  }
  return batches;
}

function updateBatchPreview() {
  const start = $("#date_from").value;
  const end = $("#date_to").value;
  const days = Number($("#batch_days").value) || 1;
  const delay = Number($("#delay_seconds")?.value ?? 30);
  const workers = Number($("#parallel_workers")?.value ?? 1);
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
  const batches = calculateDateBatches(start, end, days);
  const modeText = workers === 1
    ? (delay > 0 ? `1 request per waktu dengan jeda ${delay} dtk` : "1 request per waktu tanpa jeda")
    : `${workers} request paralel dengan jeda ${delay} dtk`;
  preview.textContent = `${total} hari akan dipecah menjadi ${batches.length} batch (maks. ${days} hari per batch, tidak menyebrang bulan, ${modeText}).`;
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
  const awbMode = ["pod_awb", "tracking_history", "tracking_focus"].includes(workflow);
  const historyMode = workflow === "tracking_history";
  const focusMode = workflow === "tracking_focus";
  $("#page-title").textContent = config.title;
  $("#breadcrumb").textContent = config.breadcrumb;
  $("#workflow-description").textContent = config.description;
  $("#date-section").hidden = awbMode;
  $("#awb-section").hidden = !awbMode;
  ["#date_from", "#date_to", "#batch_days", "#delay_seconds", "#parallel_workers"].forEach(selector => {
    const element = $(selector);
    if (element) element.disabled = awbMode;
  });
  ["#awb_text", "#batch_size", "#awb_delay_seconds", "#awb_parallel_workers"].forEach(selector => {
    const element = $(selector);
    if (element) element.disabled = !awbMode;
  });
  $("#awb_text").required = false;
  $("#focus-search-options").hidden = !focusMode;
  $("#focus-input-options").hidden = !focusMode;
  $("#focus-file-field").hidden = !focusMode || state.focusInputType !== "excel";
  const trackingFileField = $("#tracking-file-field");
  if (trackingFileField) trackingFileField.hidden = true;
  $("#tracking-mode-options").hidden = !historyMode;
  $("#tracking-output-options").hidden = !historyMode;
  $("#awb-text-field").hidden = focusMode && state.focusInputType === "excel";

  if (focusMode) {
    $("#awb-section-title").textContent = "Daftar Nomor Referensi / AWB";
    $("#awb_text").placeholder = "Tempel nomor, satu per baris";
  } else if (historyMode) {
    $("#awb-section-title").textContent = state.trackingMode === "pickup_attempt"
      ? "Daftar nomor AWB untuk verifikasi pickup"
      : (state.trackingMode === "courier_pod" ? "Daftar nomor AWB untuk ID kurir POD" : "Daftar nomor AWB (dan TLC tujuan)");
    $("#awb_text").placeholder = state.trackingMode === "milestone"
      ? "Tempel nomor AWB (bisa AWB saja atau AWB dan TLC tujuan, pisahkan spasi/tab):\nCGK1234567890\nCGK0987654321 BDO"
      : "Tempel nomor AWB, satu nomor per baris";
  } else {
    $("#awb-section-title").textContent = "Daftar nomor AWB";
    $("#awb_text").placeholder = "Tempel nomor AWB, satu nomor per baris";
  }

  $("#batch_size").closest(".field").hidden = historyMode || focusMode;
  $("#awb_parallel_workers").closest(".field").hidden = focusMode;
  $("#awb_delay_seconds").value = (historyMode || focusMode) ? "0" : "1";
  $("#awb_parallel_workers").max = historyMode ? "12" : "3";
  $("#awb_parallel_workers").value = historyMode ? "9" : "2";
  $("#filter-section").hidden = config.fields.length === 0;
  $("#export-section").hidden = awbMode;
  $("#start-button span").textContent = awbMode ? "Export & download" : "Mulai download";
  $("#batch_days").value = config.batchDays || 7;
  $("#batch_days").max = workflow === "pod_v2" ? "31" : "366";
  state.options = {};
  renderFields(config);
  renderExports(config);
  updateBatchPreview();
  updateAwbPreview();
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
    if (state.workflow === "tracking_focus") {
      payload.search_by = state.focusSearchBy;
      if (state.focusInputType === "excel") {
        if (!state.focusTargets.length) throw new Error("Unggah file Excel terlebih dahulu.");
        payload.targets = state.focusTargets;
      } else {
        const awbs = parseAwbs();
        if (!awbs.length) throw new Error("Tempel minimal satu nomor pada area teks.");
        payload.targets = awbs;
      }
      payload.delay_seconds = Number($("#awb_delay_seconds").value) || 0;
      payload.parallelism = 1;
    } else if (state.workflow === "tracking_history") {
      const awbText = $("#awb_text").value.trim();
      if (!awbText) throw new Error("Tempel minimal satu nomor AWB terlebih dahulu.");
      payload.awb_text = awbText;
      payload.tracking_mode = state.trackingMode;
      payload.delay_seconds = Number($("#awb_delay_seconds").value);
      payload.parallelism = Number($("#awb_parallel_workers")?.value || 1);
      payload.include_summary = $("#include_summary").checked;
      payload.include_history = $("#include_history").checked;
    } else if (state.workflow === "pod_awb") {
      payload.awb_text = $("#awb_text").value;
      payload.batch_size = Number($("#batch_size").value);
      payload.delay_seconds = Number($("#awb_delay_seconds").value);
      payload.parallelism = Number($("#awb_parallel_workers")?.value || 1);
    } else {
      payload.date_from = $("#date_from").value;
      payload.date_to = $("#date_to").value;
      payload.batch_days = Number($("#batch_days").value);
      payload.delay_seconds = Number($("#delay_seconds").value);
      payload.parallelism = Number($("#parallel_workers")?.value || 1);
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
    const itemBatch = job.workflow === "tracking_history" ? job.batches[0] : null;
    const progress = itemBatch?.item_total
      ? Math.round((itemBatch.processed || 0) / itemBatch.item_total * 100)
      : (job.batch_count ? Math.round(done / job.batch_count * 100) : 0);
    const active = ["queued", "running"].includes(job.status);
    return `<article class="job">
      <div class="job-summary">
        <div class="job-title"><span class="job-icon"><i data-lucide="${job.workflow === "pod_awb" ? "scan-line" : (job.workflow === "tracking_history" ? "route" : "download")}"></i></span><div><strong>${workflowLabels[job.workflow]}</strong><small>${job.id} · ${job.batch_count} batch · ${job.created_at.replace("T", " ")}</small></div></div>
        <span class="status ${job.status}">${statusLabel(job.status)}</span>
        <div class="job-progress"><div class="progress-track"><div class="progress-fill" style="width:${progress}%"></div></div><small>${itemBatch?.item_total ? `${itemBatch.processed || 0}/${itemBatch.item_total} AWB diproses` : `${done}/${job.batch_count} batch selesai`}</small></div>
        <div class="job-actions">${active ? `<button class="button danger cancel-job" data-id="${job.id}"><i data-lucide="square"></i>Batalkan</button>` : ""}</div>
      </div>
      <table class="batch-table"><thead><tr><th>Batch</th><th>Status</th><th>Progres</th><th>Hasil</th></tr></thead><tbody>
        ${job.batches.map(batch => {
          const progressText = batch.progress_unit === "awb"
            ? `${batch.processed || 0} / ${batch.item_total || 0} AWB`
            : (batch.total ? `${bytes(batch.downloaded)} / ${bytes(batch.total)}` : (batch.downloaded ? bytes(batch.downloaded) : "-"));
          const warning = batch.warning ? `<small class="warning-text">${escapeHtml(batch.warning)}</small>` : "";
          const retryBtn = batch.status === "failed"
            ? `<button type="button" class="button secondary btn-xs retry-batch" data-job-id="${job.id}" data-batch-index="${batch.index}" title="Coba lagi batch ini"><i data-lucide="rotate-cw"></i>Coba Lagi</button>`
            : "";
          const result = batch.file
            ? `<a class="download-link" href="/api/jobs/${job.id}/batches/${batch.index}/download">Unduh file</a>${warning}`
            : (batch.error
              ? `<div class="batch-result-failed"><span class="error-text" title="${escapeHtml(batch.error)}">${escapeHtml(batch.error.slice(0, 80))}</span>${retryBtn}</div>`
              : (retryBtn || "-"));
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

async function importTrackingFile(event) {
  const file = event.target.files?.[0];
  state.trackingTargets = [];
  state.trackingFileName = "";
  updateAwbPreview();
  if (!file) return;
  event.target.disabled = true;
  $("#awb-preview span").textContent = "Membaca file Excel...";
  try {
    const form = new FormData();
    form.append("file", file);
    form.append("mode", state.trackingMode);
    const response = await fetch("/api/tracking-history/import", { method: "POST", body: form });
    const result = await response.json();
    if (!response.ok || result.ok === false) throw new Error(result.error || "File Excel tidak dapat dibaca.");
    state.trackingTargets = result.targets;
    state.trackingFileName = result.filename;
    updateAwbPreview();
  } catch (error) {
    event.target.value = "";
    toast(error.message);
    updateAwbPreview();
  } finally {
    event.target.disabled = false;
  }
}

async function importFocusFile(event) {
  const file = event.target.files?.[0];
  state.focusTargets = [];
  state.focusFileName = "";
  updateAwbPreview();
  if (!file) return;
  event.target.disabled = true;
  $("#awb-preview span").textContent = "Membaca file Excel...";
  try {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch("/api/tracking-focus/import", { method: "POST", body: form });
    const result = await response.json();
    if (!response.ok || result.ok === false) throw new Error(result.error || "File Excel tidak dapat dibaca.");
    state.focusTargets = result.targets;
    state.focusFileName = result.filename;
    updateAwbPreview();
  } catch (error) {
    event.target.value = "";
    toast(error.message);
    updateAwbPreview();
  } finally {
    event.target.disabled = false;
  }
}

function changeTrackingMode(event) {
  state.trackingMode = event.target.value;
  if (state.workflow === "tracking_history") {
    $("#awb-section-title").textContent = state.trackingMode === "pickup_attempt"
      ? "Daftar nomor AWB untuk verifikasi pickup"
      : (state.trackingMode === "courier_pod" ? "Daftar nomor AWB untuk ID kurir POD" : "Daftar nomor AWB (dan TLC tujuan)");
    $("#awb_text").placeholder = state.trackingMode === "milestone"
      ? "Tempel nomor AWB (bisa AWB saja atau AWB dan TLC tujuan, pisahkan spasi/tab):\nCGK1234567890\nCGK0987654321 BDO"
      : "Tempel nomor AWB, satu nomor per baris";
  }
  updateAwbPreview();
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
  $("#delay_seconds")?.addEventListener("input", updateBatchPreview);
  $("#parallel_workers")?.addEventListener("input", updateBatchPreview);
  $("#awb_text").addEventListener("input", updateAwbPreview);
  const trackingFileInput = $("#tracking_file");
  if (trackingFileInput) trackingFileInput.addEventListener("change", importTrackingFile);
  $("#focus_file").addEventListener("change", importFocusFile);
  $$("input[name='focus_search_by']").forEach(input => input.addEventListener("change", e => {
    state.focusSearchBy = e.target.value;
  }));
  $$("input[name='focus_input_type']").forEach(input => input.addEventListener("change", e => {
    state.focusInputType = e.target.value;
    showWorkflow("tracking_focus");
  }));
  $$("input[name='tracking_mode']").forEach(input => input.addEventListener("change", changeTrackingMode));
  $("#batch_size").addEventListener("input", updateAwbPreview);
  $("#reset-button").addEventListener("click", () => {
    $("#workflow-form").reset();
    $("#batch_days").value = workflowConfig[state.workflow]?.batchDays || 7;
    $("#batch_days").max = state.workflow === "pod_v2" ? "31" : "366";
    if ($("#delay_seconds")) $("#delay_seconds").value = "30";
    if ($("#parallel_workers")) $("#parallel_workers").value = "1";
    if (state.workflow === "tracking_focus") {
      state.focusTargets = [];
      state.focusFileName = "";
      state.focusInputType = "excel";
      state.focusSearchBy = "a.reference_no";
      $("#focus_file").value = "";
      document.querySelector("input[name='focus_search_by'][value='a.reference_no']").checked = true;
      document.querySelector("input[name='focus_input_type'][value='excel']").checked = true;
      showWorkflow("tracking_focus");
    } else if (state.workflow === "tracking_history") {
      state.trackingMode = "milestone";
      const milestoneRadio = document.querySelector("input[name='tracking_mode'][value='milestone']");
      if (milestoneRadio) milestoneRadio.checked = true;
      $("#include_summary").checked = false;
      $("#include_history").checked = false;
      showWorkflow("tracking_history");
    }
    updateBatchPreview();
    updateAwbPreview();
  });
  $("#jobs-list").addEventListener("click", async event => {
    const cancelBtn = event.target.closest(".cancel-job");
    if (cancelBtn) {
      try {
        await api(`/api/jobs/${cancelBtn.dataset.id}/cancel`, { method: "POST", body: "{}" });
        loadJobs();
      } catch (error) { toast(error.message); }
      return;
    }
    const retryBtn = event.target.closest(".retry-batch");
    if (retryBtn) {
      retryBtn.disabled = true;
      try {
        await api(`/api/jobs/${retryBtn.dataset.jobId}/batches/${retryBtn.dataset.batchIndex}/retry`, { method: "POST", body: "{}" });
        toast(`Batch ${retryBtn.dataset.batchIndex} sedang dicoba ulang...`);
        loadJobs();
      } catch (error) {
        toast(error.message);
        retryBtn.disabled = false;
      }
      return;
    }
  });
}

async function init() {
  bindEvents();
  setupSecretToggles();
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
