"use strict";
const $ = (id) => document.getElementById(id);
const stages = ["analyzing", "converting", "postprocessing", "validating"];
const messages = {
  queued: ["변환 순서를 기다리고 있어요", "앞선 작업이 끝나면 자동으로 시작합니다."],
  analyzing: ["문서를 살펴보고 있어요", "텍스트와 표, 문서 구조를 확인합니다."],
  converting: ["Word 문서로 변환하고 있어요", "텍스트와 표를 편집 가능한 문서 개체로 옮깁니다."],
  postprocessing: ["문서 정보를 정리하고 있어요", "변환된 문서의 속성을 정리합니다."],
  validating: ["변환 결과를 확인하고 있어요", "텍스트 누락과 Word 표 구조를 검사합니다."],
};
let file = null;
let csrf = "";
let jobId = sessionStorage.getItem("pdfdocx_job");
let busy = false;
let timer = null;
let generation = 0;
let currentJob = null;
let engineReady = false;
let formats = {};
let selectedFormat = "pdf";
let canOpenDownloads = false;
let nativeAvailable = false;
const selectedModes = { pdf: "balanced", hwp: "native_embedded" };
let referenceFile = null;
let referenceCached = false;

function mode() { return selectedModes[selectedFormat]; }

function referenceReady() {
  return selectedFormat !== "hwp" || mode() !== "native_embedded" || referenceFile || referenceCached;
}

async function updateReferenceStatus() {
  if (!file || selectedFormat !== "hwp" || mode() !== "native_embedded") return;
  const token = generation;
  if (referenceFile) {
    $("reference-status").textContent = "선택한 기준 PDF의 전체 페이지를 사용합니다. 원본 HWP의 본문과 대조합니다.";
    return;
  }
  $("reference-status").textContent = "이 HWP에 등록된 기준 PDF가 있는지 확인하고 있어요.";
  referenceCached = false;
  setBusy(busy);
  try {
    const hash = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    const digest = Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("");
    const status = await (await request(`/api/v1/native/references/${digest}`)).json();
    if (token !== generation || mode() !== "native_embedded" || referenceFile) return;
    referenceCached = status.available;
    $("reference-status").textContent = status.available
      ? `이 HWP의 기준 PDF ${status.pages}쪽이 등록되어 있어요. 파일을 추가하지 않고 native-embedded로 변환할 수 있어요. 등록 시점부터 24시간 동안 보관해요.`
      : "기준 PDF가 필요해요. 한글 뷰어에서 원본 전체를 PDF로 저장한 뒤 아래에서 선택하세요. 초안 변환으로 자동 전환하지 않아요.";
  } catch {
    if (token === generation) $("reference-status").textContent = "등록 PDF를 확인하지 못했어요. 원본의 기준 PDF를 직접 선택하거나 서버 연결을 확인하세요.";
  }
  if (token === generation) setBusy(busy);
}

function documentLabel(format) {
  return format === "hwp" ? "HWP 한글 문서" : "PDF 문서";
}

function applyFormat(format) {
  selectedFormat = format;
  engineReady = Boolean(formats[format] && formats[format].availability !== "unavailable" && (mode() !== "native_embedded" || nativeAvailable));
  const name = format.toUpperCase();
  $("pdf-format").setAttribute("aria-pressed", String(format === "pdf"));
  $("hwp-format").setAttribute("aria-pressed", String(format === "hwp"));
  $("paper-format").textContent = name;
  $("selected-format").textContent = name;
  $("source-format").textContent = name;
  $("source-format").classList.toggle("hwp-label", format === "hwp");
  $("format-flow").setAttribute("aria-label", `${name}에서 DOCX로 변환`);
  $("drop-title").textContent = `${name} 파일을 여기에 놓으세요`;
  $("upload-limit").textContent = format === "hwp" ? "HWP 5 · 최대 30 MiB · 실험 기능" : "PDF · 최대 30 MiB · 100페이지";
  $("mode-title").textContent = format === "hwp" ? "편집용 초안 변환" : "균형 있게 변환";
  $("mode-description").textContent = format === "hwp" ? "텍스트와 표를 편집할 수 있어요. 원본 배치 보존은 아직 미완성이에요." : "문단과 표의 구조, 원본 배치를 함께 고려해요.";
  $("native-mode-option").hidden = !nativeAvailable && format !== "hwp";
  $("native-mode").checked = mode() === "native_embedded";
  $("balanced-mode").checked = mode() === "balanced";
  $("reference-panel").hidden = format !== "hwp" || mode() !== "native_embedded" || currentJob?.state === "succeeded";
  const notes = mode() === "native_embedded"
    ? ["native-embedded와 같은 PDF 기준 변환·글꼴 포함 경로예요.", "HWP는 같은 문서의 전체 출력 PDF가 필요해요. 등록되어 있으면 자동으로 사용해요.", "원본 HWP와 기준 PDF의 본문을 대조하고, 기준 PDF 전체 페이지를 변환해요.", "글꼴 포함으로 파일이 커질 수 있고 Word 페이지 수는 달라질 수 있어요."]
    : format === "hwp"
    ? ["HWP 직접 변환은 편집용 초안을 만들어요. 원본 레이아웃 보존은 아직 미완성이에요.", "글꼴·줄바꿈·페이지 수가 크게 달라질 수 있어요.", "기본 쪽 번호를 지원해요. Word에서 필드를 업데이트해 주세요.", "암호·배포용 문서와 HWPX는 지원하지 않아요.", "머리말·수식·도형 등 미지원 요소가 있으면 중단해요."]
    : ["텍스트 기반 PDF를 지원해요.", "스캔 PDF와 암호화된 PDF는 지원하지 않아요.", "복잡한 표와 다단 편집은 결과 확인이 필요해요."];
  $("conversion-notes").replaceChildren(...notes.map((text) => {
    const li = document.createElement("li"); li.textContent = text; return li;
  }));
  $("engine-notice").textContent = engineReady
    ? `${name} 파일을 ${file ? "확인했어요. 변환을 시작해 보세요." : "먼저 선택해 주세요."}`
    : `${name} 변환 엔진을 사용할 수 없습니다. 서버 설치 상태를 확인해 주세요.`;
}

async function chooseFormat(format) {
  if (busy || selectedFormat === format) return;
  await reset();
  applyFormat(format);
  setBusy(false);
}

function fileSize(bytes) {
  return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KiB` : `${(bytes / 1024 / 1024).toFixed(2)} MiB`;
}

async function request(url, options = {}) {
  const response = await fetch(url, { credentials: "same-origin", signal: AbortSignal.timeout(15000), ...options });
  if (!response.ok) {
    let data;
    try { data = await response.json(); } catch { data = {}; }
    const error = new Error(data.error?.message || "서버에 연결하지 못했습니다.");
    error.info = data.error || { code: "REQUEST_FAILED", suggestion: "잠시 후 다시 시도하세요." };
    throw error;
  }
  return response;
}

function setBusy(value) {
  busy = value;
  $("file-input").disabled = value;
  $("choose-button").disabled = value;
  $("remove-file").disabled = value;
  $("pdf-format").disabled = value;
  $("hwp-format").disabled = value;
  $("convert-button").disabled = value || !file || !engineReady || !referenceReady();
  $("native-mode").disabled = value || !nativeAvailable;
  $("balanced-mode").disabled = value;
  $("reference-input").disabled = value;
  $("reference-choose").disabled = value || !file;
  $("reference-remove").disabled = value;
  $("cancel-button").hidden = !value || !jobId;
}

function showStatus(title, description, kind = "working") {
  $("status-panel").hidden = false;
  $("status-panel").className = `status-panel ${kind}`;
  $("status-title").textContent = title;
  $("status-description").textContent = description;
  $("activity").hidden = kind !== "working";
  $("stage-list").hidden = kind !== "working";
}

function showError(error) {
  showStatus(error.message || "변환을 완료하지 못했어요", "아래 내용을 확인한 뒤 다시 시도해 주세요.", "error");
  $("error-detail").hidden = false;
  $("error-code").textContent = error.info?.code || "NETWORK_ERROR";
  $("error-suggestion").textContent = error.info?.suggestion || "서버 실행 상태와 연결을 확인한 뒤 다시 시도하세요.";
  // 이전 버전에서 저장된 실패 작업도 실제로 감지한 요소를 보여 준다.
  const legacyLabels = { pgnp: "쪽 번호 위치 설정", head: "머리말", foot: "꼬리말" };
  const features = error.info?.details?.features;
  if (error.info?.code === "UNSUPPORTED_FEATURE" && !error.info.details?.reason && Array.isArray(features) && features.length) {
    const labels = error.info.details.feature_labels || features.map((feature) => legacyLabels[feature] || "미지원 문서 요소");
    $("error-suggestion").textContent = `감지된 미지원 요소: ${[...new Set(labels)].join(" · ")}. 이 요소를 보존하는 변환은 아직 지원하지 않습니다. 같은 파일을 다시 시도해도 해결되지 않습니다.`;
  }
  $("result-actions").hidden = true;
  $("reset-button").hidden = false;
  $("engine-notice").textContent = "변환이 완료되지 않았습니다. 오류 원인을 확인해 주세요.";
}

function clearStatus() {
  for (const id of ["status-panel", "error-detail", "result-actions", "quality-detail", "warnings", "expiry", "reset-button", "open-downloads-button", "download-notice"]) $(id).hidden = true;
  $("quality-detail").replaceChildren();
}

async function selectFile(selected) {
  if (busy || !selected) return;
  const extension = selected.name.toLowerCase().split(".").pop();
  if (!["pdf", "hwp"].includes(extension)) {
    showError({ message: "PDF 또는 HWP 파일을 선택해 주세요.", info: { code: "UNSUPPORTED_FORMAT", suggestion: "현재 PDF와 HWP 5 형식을 지원합니다. HWPX는 아직 지원하지 않습니다." } });
    return;
  }
  if (!selected.size || selected.size > 30 * 1024 * 1024) {
    showError({ message: "파일 크기를 확인해 주세요.", info: { code: "FILE_SIZE_INVALID", suggestion: "비어 있지 않은 30 MiB 이하 PDF 또는 HWP를 선택하세요." } });
    return;
  }
  await discardJob();
  file = selected;
  // 이전 직접 초안 작업을 복원했더라도 새 HWP는 선호 경로로 시작한다.
  if (extension === "hwp") selectedModes.hwp = "native_embedded";
  referenceFile = null;
  referenceCached = false;
  $("reference-input").value = "";
  $("reference-name").textContent = "";
  $("reference-remove").hidden = true;
  applyFormat(extension);
  clearStatus();
  $("drop-zone").hidden = true;
  $("selected-file").hidden = false;
  $("file-name").textContent = selected.name;
  $("file-name").title = selected.name;
  $("file-meta").textContent = `${documentLabel(extension)} · ${fileSize(selected.size)}`;
  setBusy(false);
  await updateReferenceStatus();
}

async function discardJob() {
  generation += 1;
  clearTimeout(timer);
  const previous = jobId;
  jobId = null;
  currentJob = null;
  sessionStorage.removeItem("pdfdocx_job");
  if (previous && csrf) {
    try { await request(`/api/v1/jobs/${previous}`, { method: "DELETE", headers: { "X-CSRF-Token": csrf } }); }
    catch { /* 서버의 TTL 정리 정책은 유지된다. */ }
  }
}

async function reset() {
  await discardJob();
  selectedModes.hwp = "native_embedded";
  file = null;
  referenceFile = null;
  referenceCached = false;
  $("reference-input").value = "";
  $("reference-name").textContent = "";
  $("reference-remove").hidden = true;
  $("file-input").value = "";
  $("selected-file").hidden = true;
  $("drop-zone").hidden = false;
  applyFormat(selectedFormat);
  clearStatus();
  setBusy(false);
  $("choose-button").focus();
}

async function poll(id, token) {
  if (token !== generation || id !== jobId) return;
  try {
    const job = await (await request(`/api/v1/jobs/${id}`)).json();
    if (token !== generation || id !== jobId) return;
    currentJob = job;
    selectedModes[job.format] = job.mode;
    applyFormat(job.format);
    $("file-meta").textContent = `${documentLabel(job.format)} · ${fileSize(job.size_bytes)}${job.progress.total_pages ? ` · ${job.mode === "native_embedded" && job.format === "hwp" ? "기준 PDF " : ""}${job.progress.total_pages}쪽` : job.format === "hwp" ? " · 페이지 수는 측정하지 않음" : ""}`;
    $("error-detail").hidden = true;
    if (job.state === "succeeded") {
      setBusy(false);
      $("convert-button").disabled = true;
      showStatus(job.mode === "native_embedded" ? "글꼴 포함 Word 문서가 준비되었어요" : job.format === "hwp" ? "편집용 Word 초안이 준비되었어요" : "Word 문서가 준비되었어요",
        job.mode === "native_embedded" ? "native-embedded 경로로 기준 PDF의 전체 페이지를 변환하고 본문·표 구조를 검사했습니다." : job.format === "hwp" ? "텍스트·표 구조를 검사했습니다. 원본 글꼴·줄바꿈·페이지 배치 보존은 아직 미완성입니다." : "편집 가능한 텍스트와 기본 구조 검사를 통과했습니다.", "success");
      $("download-button").href = job.links.download;
      $("result-actions").hidden = false;
      $("reset-button").hidden = false;
      $("engine-notice").textContent = "다운로드 후 중요한 내용과 서식을 확인해 주세요.";
      $("expiry").textContent = `${new Date(job.expires_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}까지 다운로드할 수 있어요. 결과 파일명: converted.docx`;
      $("expiry").hidden = false;
      $("warnings").replaceChildren(...job.warnings.map((text) => {
        const li = document.createElement("li"); li.textContent = text; return li;
      }));
      $("warnings").hidden = job.warnings.length === 0;
      return;
    }
    if (["failed", "cancelled", "expired"].includes(job.state)) {
      setBusy(false);
      showError({ message: job.error?.message || "작업이 종료되었습니다.", info: job.error });
      return;
    }
    const [title, description] = messages[job.state] || ["작업을 정리하고 있어요", "잠시만 기다려 주세요."];
    showStatus(title, description);
    document.querySelectorAll("#stage-list li").forEach((node, i) => {
      const index = stages.indexOf(job.stage);
      node.className = i === index ? "current" : i < index ? "done" : "";
    });
    timer = setTimeout(() => poll(id, token), document.hidden ? 5000 : 1000);
  } catch (error) {
    if (token !== generation) return;
    if (["JOB_NOT_FOUND", "JOB_EXPIRED"].includes(error.info?.code)) {
      setBusy(false); showError(error); return;
    }
    showStatus("연결을 다시 확인하고 있어요", "서버의 작업 상태를 확인하는 중입니다. 자동으로 다시 연결합니다.");
    timer = setTimeout(() => poll(id, token), 5000);
  }
}

async function convert() {
  if (!file || busy || !engineReady || !referenceReady()) return;
  await discardJob();
  clearStatus();
  setBusy(true);
  showStatus("파일을 전송하고 있어요", "이 컴퓨터의 로컬 변환 서버로 전달합니다.");
  const form = new FormData();
  form.append("file", file);
  const native = mode() === "native_embedded";
  if (native && selectedFormat === "hwp" && referenceFile) form.append("reference", referenceFile);
  if (!native) { form.append("mode", "balanced"); form.append("ocr", "off"); }
  try {
    const response = await request(native ? "/api/v1/native/jobs" : "/api/v1/jobs", { method: "POST", body: form, headers: { "X-CSRF-Token": csrf } });
    const job = await response.json();
    jobId = job.job_id;
    sessionStorage.setItem("pdfdocx_job", jobId);
    $("cancel-button").hidden = false;
    await poll(jobId, generation);
  } catch (error) {
    setBusy(false); showError(error);
  }
}

$("choose-button").addEventListener("click", () => $("file-input").click());
$("pdf-format").addEventListener("click", () => chooseFormat("pdf"));
$("hwp-format").addEventListener("click", () => chooseFormat("hwp"));
$("file-input").addEventListener("change", (event) => selectFile(event.target.files[0]));
$("remove-file").addEventListener("click", reset);
$("reset-button").addEventListener("click", reset);
$("convert-button").addEventListener("click", convert);
for (const id of ["native-mode", "balanced-mode"]) $(id).addEventListener("change", async event => {
  if (busy) return;
  const selected = event.target.value;
  await discardJob(); clearStatus();
  selectedModes[selectedFormat] = selected;
  applyFormat(selectedFormat); setBusy(false);
  await updateReferenceStatus();
});
$("reference-choose").addEventListener("click", () => $("reference-input").click());
$("reference-input").addEventListener("change", async event => {
  const selected = event.target.files[0];
  if (!selected || busy) return;
  if (!selected.name.toLowerCase().endsWith(".pdf") || !selected.size || selected.size > 30 * 1024 * 1024) {
    $("reference-status").textContent = "비어 있지 않은 30 MiB 이하 PDF를 선택하세요."; return;
  }
  referenceFile = selected;
  $("reference-name").textContent = selected.name;
  $("reference-remove").hidden = false;
  await updateReferenceStatus(); setBusy(false);
});
$("reference-remove").addEventListener("click", async () => {
  referenceFile = null; $("reference-input").value = ""; $("reference-name").textContent = "";
  $("reference-remove").hidden = true; await updateReferenceStatus(); setBusy(false);
});
$("cancel-button").addEventListener("click", async () => {
  $("cancel-button").disabled = true;
  try {
    if (jobId) await request(`/api/v1/jobs/${jobId}`, { method: "DELETE", headers: { "X-CSRF-Token": csrf } });
    await reset();
  } catch (error) { showError(error); }
  finally { $("cancel-button").disabled = false; }
});
for (const event of ["dragenter", "dragover"]) $("drop-zone").addEventListener(event, (e) => { e.preventDefault(); if (!busy) $("drop-zone").classList.add("dragging"); });
for (const event of ["dragleave", "drop"]) $("drop-zone").addEventListener(event, (e) => { e.preventDefault(); $("drop-zone").classList.remove("dragging"); });
$("drop-zone").addEventListener("drop", (event) => {
  if (event.dataTransfer.files.length !== 1) {
    showError({ message: "파일을 한 개씩 선택해 주세요.", info: { code: "ONE_FILE_REQUIRED", suggestion: "한 번에 하나의 문서를 변환합니다." } }); return;
  }
  selectFile(event.dataTransfer.files[0]);
});
// 브라우저가 드롭한 문서로 페이지를 이동하지 않도록 한다.
window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());
$("quality-button").addEventListener("click", async () => {
  if (!currentJob) return;
  try {
    const report = await (await request(currentJob.links.quality)).json();
    const details = ["확인됨: DOCX 재열기 · 텍스트 개체 · 본문 문자 보존 검사", `실제 Word 표: ${report.metrics.word_table_count.value}개`, "미검증: 실제 Word 편집 · 시각 유사도 · 복잡한 문서 품질"];
    if (report.embedded_fonts) details.splice(2, 0, `포함된 글꼴: ${report.embedded_fonts.embedded_font_count}개 · 편집 허용 플래그 확인`);
    if (report.metrics.hwp_reference_text_coverage) details.splice(2, 0, `원본 HWP → 기준 PDF 본문 문자 포함률: ${(report.metrics.hwp_reference_text_coverage.value * 100).toFixed(1)}% · 읽기 순서·시각 배치 일치율과는 달라요.`, `변환한 기준 PDF: ${report.metrics.reference_pdf_page_count.value}쪽 · Word 페이지 수는 다를 수 있어요.`);
    $("quality-detail").replaceChildren(...details.map((text) => { const p = document.createElement("p"); p.textContent = text; return p; }));
    $("quality-detail").hidden = !$("quality-detail").hidden;
  } catch (error) { showError(error); }
});
$("download-button").addEventListener("click", async (event) => {
  event.preventDefault();
  if (!currentJob) return;
  const token = generation;
  try {
    const response = await request(currentJob.links.download);
    const blob = await response.blob();
    if (token !== generation) return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = "converted.docx"; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    $("open-downloads-button").hidden = !canOpenDownloads;
    $("download-notice").textContent = canOpenDownloads
      ? "다운로드를 요청했습니다. 폴더 열기는 기본 다운로드 폴더를 엽니다. 다른 위치로 저장했다면 브라우저 다운로드 목록에서 확인하세요."
      : "다운로드를 요청했습니다. 브라우저의 다운로드 목록에서 저장 폴더를 열 수 있습니다.";
    $("download-notice").hidden = false;
  } catch (error) { showError(error); }
});

$("open-downloads-button").addEventListener("click", async () => {
  const token = generation;
  const button = $("open-downloads-button");
  button.disabled = true;
  try {
    await request("/api/v1/desktop/open-downloads", { method: "POST", headers: { "X-CSRF-Token": csrf } });
    if (token === generation) $("download-notice").textContent = "Finder로 기본 다운로드 폴더를 열었습니다. 다른 위치로 저장했다면 브라우저 다운로드 목록에서 확인하세요.";
  } catch (error) {
    if (token === generation) $("download-notice").textContent = `${error.message} ${error.info?.suggestion || "브라우저 다운로드 목록에서 저장 위치를 확인하세요."}`;
  } finally { button.disabled = false; }
});

async function initialize() {
  try {
    const [session, capability] = await Promise.all([request("/api/v1/session"), request("/api/v1/capabilities")]);
    csrf = (await session.json()).csrf_token;
    const capabilities = await capability.json();
    formats = capabilities.formats;
    nativeAvailable = Boolean(capabilities.native_embedded?.available);
    canOpenDownloads = Boolean(capabilities.desktop?.open_downloads_folder);
    applyFormat(selectedFormat);
    setBusy(false);
    if (jobId) {
      $("drop-zone").hidden = true; $("selected-file").hidden = false;
      $("file-name").textContent = "이전 변환 작업";
      setBusy(true); await poll(jobId, generation);
    }
  } catch (error) { showError(error); $("engine-notice").textContent = "서버 연결 또는 변환 엔진을 확인해 주세요."; }
}
initialize();
