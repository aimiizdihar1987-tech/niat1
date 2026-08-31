"use strict";

// ====================== Fixed options ======================
const STRATEGIES = ["Think-Pair-Share", "Gallery Walk", "Round Table", "Hot Seat",
  "Project-Based Learning", "Inquiry-Based Learning", "Jigsaw", "Role-Play"];
const CCE = ["Language", "Values", "Patriotism & Citizenship", "Creativity & Innovation",
  "Entrepreneurship", "ICT", "Science & Technology", "Sustainability & Global Citizenship"];

// ====================== State ======================
let DSKP = null;
let currentForm = 3;        // selected Form (1-5); drives which DSKP is loaded
let availableForms = [3];   // forms that actually have a data file on the server
let lastPlan = null;        // generated lesson plan (object)
let lastWorksheet = null;   // generated worksheet (object)
let lastContext = null;
let lastInputs = null;      // Agent-1 inputs used (for saving / duplicating)
let STUDENTS = [];          // pilot students from "Email Student Prototype.txt"
let lastMaterials = null;   // generated teaching materials (slides object)
let materialsUsed = false;  // did the teacher choose to use the materials?

const $ = (id) => document.getElementById(id);

// ====================== Start ======================
init();

async function init() {
  try {
    availableForms = ((await (await fetch("/api/dskp-forms")).json()).forms) || [3];
  } catch (e) { availableForms = [3]; }
  if (!availableForms.includes(currentForm)) currentForm = availableForms[0] || 3;
  buildFormSelector();
  if (!(await loadDskp(currentForm))) return;   // loads DSKP + builds theme/unit/skill
  buildChips($("strategi"), STRATEGIES);
  buildChips($("emk"), CCE);
  $("tarikh").value = new Date().toISOString().slice(0, 10);
  fillDay();
  wireEvents();
  updateBankBadge();
  loadStudents();        // pilot student emails (for quiz distribution)
  await loadProfile();   // teacher/school + tomorrow's class(es) from the timetable
  await prefillFromLink(); // if arrived from a reminder link, auto-fill that class
}

async function loadStudents() {
  try {
    STUDENTS = ((await (await fetch("/api/students")).json()).students) || [];
  } catch (e) { STUDENTS = []; }
}

// ---- Auto-fill from the timetable profile (teacher, school, class, time, duration, pupils) ----
let profile = { teacher: "", school: "", date: "", day: "", classes: [] };

function setSelect(id, val, addIfMissing) {
  const el = $(id);
  if (!el || val == null || val === "") return;
  if (el.tagName === "SELECT") {
    let opt = [...el.options].find((o) => o.value === String(val) || o.text === String(val));
    if (!opt && addIfMissing) { opt = new Option(String(val), String(val)); el.add(opt); }
    if (opt) el.value = opt.value;
  } else {
    el.value = val;
  }
}
function setTeacherSchool() {
  if ($("teacher") && profile.teacher) $("teacher").value = profile.teacher;
  if ($("school") && profile.school) $("school").value = profile.school;
}
function updateClassSummary(slot, date) {
  const el = $("class-summary");
  if (!el) return;
  if (!slot || !slot.class) {
    el.innerHTML = '<span class="muted">Class details auto-fill from your timetable — tap "Prepare this lesson" above.</span>';
    return;
  }
  const who = [profile.teacher, profile.school].filter(Boolean).join(" · ");
  const what = [slot.class, ($("hari") && $("hari").value) || "", date || "", slot.time,
    (slot.pupils ? slot.pupils + " pupils" : "")].filter(Boolean).join(" · ");
  el.innerHTML = "👩‍🏫 " + esc(who) + "<br>📅 " + esc(what);
}
// Derive the Form from a class name (e.g. "1 Amanah", "Form 4 Bestari" -> 1 / 4)
// and switch the loaded DSKP to match, if that form's data is available.
async function autoSelectForm(className) {
  if (!className) return;
  const m = String(className).match(/\b([1-5])\b/);
  if (!m) return;
  const n = Number(m[1]);
  if (n === currentForm || !availableForms.includes(n)) return;
  const sel = $("tingkatan");
  if (sel) sel.value = String(n);
  await loadDskp(n);
}

function applySlot(slot, date) {
  if (!slot) return;
  setSelect("nama_kelas", slot.class, true);
  autoSelectForm(slot.class);
  if (date) { setSelect("tarikh", date); fillDay(); }
  if (slot.time) setSelect("masa", slot.time, true);
  if (slot.duration) setSelect("tempoh", String(slot.duration), true);
  if (slot.pupils) setSelect("bil_murid", String(slot.pupils));
  setTeacherSchool();
  updateClassSummary(slot, date);
}

async function loadProfile() {
  try {
    const d = await (await fetch("/api/next-class")).json();
    profile = { teacher: d.teacher || "", school: d.school || "", date: d.date || "", day: d.day || "", classes: d.classes || [] };
    setTeacherSchool();
    updateClassSummary(null);
    const b = $("next-class-banner");
    if (b && profile.classes.length) {
      const c = profile.classes[0];
      b.innerHTML = `📅 Tomorrow (${esc(profile.day)}): <b>${esc(c.class)}</b>` +
        (c.time ? " at " + esc(c.time) : "") +
        ` <button id="btn-prep-next" class="mini primary">Prepare this lesson →</button>`;
      b.classList.remove("hidden");
      $("btn-prep-next").onclick = () => {
        applySlot(c, profile.date);
        toast("Auto-filled " + c.class + " — now choose theme & standards 👋");
      };
    }
  } catch (e) { /* offline / no timetable — fields stay manual */ }
}

// If opened from a reminder link (…?class=3%20Delima&date=YYYY-MM-DD), auto-fill that class.
async function prefillFromLink() {
  const params = new URLSearchParams(location.search);
  const pClass = params.get("class");
  const pDate = params.get("date");
  if (!pClass) return;
  try {
    const r = await (await fetch("/api/class-info?class=" + encodeURIComponent(pClass))).json();
    if (r.teacher) profile.teacher = r.teacher;
    if (r.school) profile.school = r.school;
    if (r.found && r.slot) applySlot(r.slot, pDate || profile.date);
    else { setSelect("nama_kelas", pClass, true); autoSelectForm(pClass); if (pDate) { setSelect("tarikh", pDate); fillDay(); } setTeacherSchool(); }
    toast("Auto-filled " + pClass + " — now choose theme & standards 👋");
  } catch (e) { setSelect("nama_kelas", pClass, true); }
}

// Show the number of questions in the Question Bank on the header badge.
async function updateBankBadge() {
  try {
    const s = await (await fetch("/api/bank-stats")).json();
    const el = $("bank-count");
    if (el) el.textContent = s.jumlah ?? 0;
  } catch (e) {
    const el = $("bank-count");
    if (el) el.textContent = "—";
  }
}

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
function fillDay() {
  const v = $("tarikh").value;
  if (!v) return;
  const d = new Date(v + "T00:00:00");
  if (!isNaN(d)) $("hari").value = DAYS[d.getDay()];
}

// ============ Step 1 (UI — NOT an agent): build the setup form ============
// The teacher fills these dropdowns (from DSKP) themselves — this IS the prompt.
// Clicking "generate" sends the inputs straight to Agent 1 (Lesson Plan).
// Load the DSKP data file for a given Form (1-5) and rebuild the dependent
// dropdowns. Returns true on success. The Form selector calls this on change.
async function loadDskp(form) {
  try {
    DSKP = await (await fetch("/dskp_english_f" + form + ".json")).json();
  } catch (e) {
    toast("Failed to load DSKP for Form " + form, true);
    return false;
  }
  currentForm = Number(DSKP.form) || Number(form) || 3;
  buildThemes();
  buildUnits();
  buildSkills();
  buildRpt();
  updateFormBadge();
  return true;
}

// Build the RPT (yearly scheme of work) quick-fill dropdown from DSKP.rpt.
// Picking a week auto-fills Week + Theme + Topic/Unit so the teacher starts
// from the planned pacing. All fields stay editable.
function buildRpt() {
  const wrap = $("rpt-wrap"), sel = $("rpt-week");
  if (!sel || !wrap) return;
  const rows = (DSKP && DSKP.rpt) || [];
  if (!rows.length) { wrap.style.display = "none"; return; }
  wrap.style.display = "";
  sel.innerHTML = '<option value="">— pick a week —</option>';
  rows.forEach((r, i) => {
    const label = "Minggu " + (r.minggu || (i + 1)) +
      (r.tema ? " · " + r.tema : "") + (r.unit ? " · " + r.unit : "");
    sel.add(new Option(label, String(i)));
  });
  sel.onchange = () => {
    const r = rows[+sel.value];
    if (!r) return;
    // Form 4's RPT pages a range per row ("2-3"); #minggu is <input type=number>,
    // which silently blanks on a non-numeric value. Fill the first week of the range.
    const wk = String(r.minggu || "").match(/\d+/);
    if (wk) setSelect("minggu", wk[0]);
    if (r.tema && $("theme")) { setSelect("theme", r.tema, true); buildUnits(); }
    if (r.unit && $("topic")) setSelect("topic", r.unit, true);
    toast("Filled from RPT — adjust the standards & pedagogy as needed 📅");
  };
}

// Build the Form (Tingkatan) selector, showing only forms that have data.
function buildFormSelector() {
  const sel = $("tingkatan");
  if (!sel) return;
  sel.innerHTML = "";
  availableForms.forEach((n) => sel.add(new Option("Tingkatan " + n, String(n))));
  sel.value = String(currentForm);
  sel.onchange = async () => { await loadDskp(sel.value); };
}

// Show the loaded curriculum's CEFR target / textbook next to the selector.
function updateFormBadge() {
  const el = $("form-badge");
  if (!el || !DSKP) return;
  const bits = [];
  if (DSKP.cefr_target) bits.push("CEFR " + DSKP.cefr_target);
  if (DSKP.textbook) bits.push(DSKP.textbook);
  el.textContent = bits.join(" · ");
}

function buildThemes() {
  const sel = $("theme");
  if (!sel) return;
  sel.innerHTML = '<option value="">— select —</option>';
  (DSKP.themes || []).forEach((t) => sel.add(new Option(t, t)));
  // When the theme changes, refresh the Topic/Unit list to only the related units.
  sel.onchange = buildUnits;
}

// Topic/Unit is filtered by the chosen Theme: each DSKP theme maps to only its
// related Close-Up units (see "theme_topics" in dskp_english_f3.json).
function buildUnits() {
  const sel = $("topic");
  if (!sel || sel.tagName !== "SELECT") return;
  const theme = $("theme") ? $("theme").value : "";
  const map = (DSKP && DSKP.theme_topics) || {};
  const units = theme ? (map[theme] || DSKP.textbook_units || []) : [];
  sel.innerHTML = theme
    ? '<option value="">— select unit —</option>'
    : '<option value="">— select a theme first —</option>';
  units.forEach((u) => sel.add(new Option(u, u)));
  sel.disabled = !theme; // locked until a theme is picked
}

function buildSkills() {
  const sel = $("bidang");
  sel.innerHTML = '<option value="">— select —</option>';
  DSKP.bidang.forEach((b) => {
    sel.add(new Option(`${b.kod} ${b.nama}`, b.kod));
  });
  sel.onchange = buildContentStandards;
}

function buildContentStandards() {
  const b = DSKP.bidang.find((x) => x.kod === $("bidang").value);
  const sel = $("sk");
  sel.innerHTML = '<option value="">— select —</option>';
  if (b) b.standard_kandungan.forEach((s) => sel.add(new Option(`${s.kod} ${s.nama}`, s.kod)));
  sel.onchange = buildLearningStandards;
  buildLearningStandards();
}

function buildLearningStandards() {
  const b = DSKP.bidang.find((x) => x.kod === $("bidang").value);
  const sk = b && b.standard_kandungan.find((x) => x.kod === $("sk").value);
  const box = $("sp-list");
  box.innerHTML = "";
  if (!sk) return;
  sk.standard_pembelajaran.forEach((sp) => {
    const lbl = document.createElement("label");
    lbl.innerHTML =
      `<input type="checkbox" value="${sp.kod}"><span><span class="kod">${sp.kod}</span>${esc(sp.huraian)}</span>`;
    box.appendChild(lbl);
  });
}

function buildChips(container, items) {
  container.innerHTML = "";
  items.forEach((t) => {
    const c = document.createElement("span");
    c.className = "chip";
    c.textContent = t;
    c.onclick = () => c.classList.toggle("on");
    container.appendChild(c);
  });
}

function chipValues(container) {
  return [...container.querySelectorAll(".chip.on")].map((c) => c.textContent);
}

// ====================== Collect inputs ======================
function collectInputs() {
  const sp_kods = [...document.querySelectorAll("#sp-list input:checked")].map((c) => c.value);
  return {
    minggu: $("minggu").value.trim(),
    hari: $("hari").value.trim(),
    nama_kelas: $("nama_kelas").value.trim(),
    tarikh: $("tarikh").value,
    masa: $("masa").value.trim(),
    tempoh: $("tempoh").value,
    bil_murid: $("bil_murid").value,
    tahap_murid: $("tahap_murid").value,
    form: currentForm,
    theme: $("theme").value,
    topic: $("topic").value.trim(),
    bidang_kod: $("bidang").value,
    sk_kod: $("sk").value,
    sp_kods,
    strategi: chipValues($("strategi")),
    emk: chipValues($("emk")),
    kbat: $("kbat").value,
    worksheet: {
      bil_soalan: +$("bil_soalan").value,
      lots: +$("lots").value,
      mots: +$("mots").value,
      hots: +$("hots").value,
    },
  };
}

function validate(inp) {
  if (!inp.nama_kelas) return "Please select a class.";
  if (!inp.bidang_kod || !inp.sk_kod) return "Please select a Skill and a Content Standard.";
  if (inp.sp_kods.length === 0) return "Please select at least one Learning Standard.";
  const w = inp.worksheet;
  if (w.lots + w.mots + w.hots !== 100) return "The worksheet level distribution must total 100%.";
  return null;
}

// ====================== API call ======================
async function api(path, body, msg) {
  showOverlay(msg);
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.ralat || "Server error");
    return data;
  } finally {
    hideOverlay();
  }
}

// Tell the teacher when the offline local model was used instead of Gemini.
function engineNotice(d) {
  if (d && d._enjin === "local") {
    toast("⚡ Generated OFFLINE with the local model (Gemini unreachable) — output may be simpler; please review carefully.");
  }
}

// Show what the Guardrail/Validator agent fixed or removed (quality gate).
function guardrailNotice(g) {
  if (!g) return;
  const fixed = (g.repairs || []).length;
  const removed = (g.dropped || []).length;
  const vocab = g.vocab || [];
  if (vocab.length) {
    const qs = vocab.map(v => `Q${v.no}: ${v.words.join(', ')}`).join(' | ');
    toast(`📖 Vocabulary above B1 level — ${qs}. Review before sending.`, true);
  }
  if (removed) {
    toast(`🛡️ Guardrail: ${removed} item(s) removed (invalid), ${fixed} auto-fixed — review before approving.`, true);
  } else if (fixed) {
    toast(`🛡️ Guardrail: ${fixed} small issue(s) auto-fixed for you.`);
  }
}

// ====================== Agent 1: Lesson Plan (RPH) ======================
async function genLessonPlan(note = "") {
  const inp = collectInputs();
  const err = validate(inp);
  if (err) return toast(err, true);
  lastInputs = inp;
  if (note) inp.nota_guru = note;
  try {
    const data = await api("/api/generate-rph", inp, "Crafting your lesson plan — objectives, activities and all…");
    lastPlan = data.rph;
    lastContext = data.konteks;
    renderPlan(lastPlan);
    goto(2);
    guardrailNotice(data._guardrail);
    engineNotice(data);
  } catch (e) {
    toast(e.message, true);
  }
}

function renderPlan(r) {
  $("rph-output").innerHTML = `
    <p class="editable-hint">✎ Click any text to edit before you approve.</p>
    <div contenteditable="true">${planTableHTML(r)}</div>`;
}

// Build the lesson-plan table in the official JPN Perlis RPH format.
function planTableHTML(r) {
  const objektif = (r.objektif_pembelajaran || []).map((o, i) => `${i + 1}. ${esc(o)}`).join("<br>");
  const aktiviti = (r.aktiviti_pembelajaran || []).map((a, i) => `${i + 1}. ${esc(a)}`).join("<br>");
  const sp = (r.standard_pembelajaran || []).map((s) => esc(s)).join("<br>");
  return `
  <table class="rph">
    <tr><th>MINGGU</th><td>${esc(r.minggu)}</td><th>TARIKH</th><td>${esc(r.tarikh)}</td></tr>
    <tr><th>HARI</th><td>${esc(r.hari)}</td><th>MASA</th><td>${esc(r.masa) || "-"}</td></tr>
    <tr><th>TINGKATAN / KELAS</th><td>${esc(r.tingkatan_kelas)}</td><th>MINIMUM JAM SETAHUN</th><td>${esc(r.minimum_jam_setahun)}</td></tr>
    <tr><th>MATA PELAJARAN</th><td colspan="3">${esc(r.mata_pelajaran)}</td></tr>
    <tr><th>TEMA / BIDANG</th><td colspan="3">${esc(r.tema_bidang)}</td></tr>
    <tr><th>TAJUK</th><td colspan="3">${esc(r.tajuk)}</td></tr>
    <tr><th>STANDARD KANDUNGAN</th><td colspan="3">${esc(r.standard_kandungan)}</td></tr>
    <tr><th>STANDARD PEMBELAJARAN</th><td colspan="3">${sp}</td></tr>
    <tr><th>OBJEKTIF PEMBELAJARAN</th><td colspan="3"><i>Pada akhir PdPc, murid boleh :</i><br>${objektif}</td></tr>
    <tr><th>AKTIVITI PEMBELAJARAN</th><td colspan="3">${aktiviti}</td></tr>
    <tr><th>REFLEKSI</th><td colspan="3">${r.refleksi ? esc(r.refleksi) : '<span class="muted">— diisi guru selepas PdP —</span>'}</td></tr>
  </table>`;
}

// ====================== Agent 2: Teaching Materials / Slides ======================
async function genMaterials(note = "") {
  if (!lastPlan) return toast("Generate the lesson plan first.", true);
  const inp = collectInputs();
  inp.plan = lastPlan;
  if (note) inp.nota_guru = note;
  try {
    const data = await api("/api/generate-materials", inp, "Designing your teaching slides, one big idea at a time…");
    lastMaterials = data.materials;
    materialsUsed = false;
    renderMaterials(lastMaterials);
    goto(3);
  } catch (e) {
    toast(e.message, true);
  }
}

function renderMaterials(m) {
  const slides = (m.slides || []).map((s, i) => {
    const isi = (s.isi || []).map((p) => `<li contenteditable="true">${esc(p)}</li>`).join("");
    const kind = esc(s.jenis || "slide");
    return `<div class="slide-card" data-jenis="${kind}">
      <div class="slide-num">Slide ${i + 1} · ${kind}</div>
      <div class="slide-title" contenteditable="true">${esc(s.tajuk || "")}</div>
      <ul class="slide-isi">${isi}</ul>
      <div class="slide-notes"><b>🗣 Teacher notes:</b> <span contenteditable="true">${esc(s.nota_guru || "")}</span></div>
    </div>`;
  }).join("");
  $("mat-output").innerHTML = `
    <p class="editable-hint">✎ Click any text to edit. ${(m.slides || []).length} slides — present them or download as a file.</p>
    <div id="slides-wrap">${slides}</div>`;
}

// Read back the (possibly edited) slides from the DOM.
function scrapeMaterials() {
  const wrap = $("mat-output");
  if (!wrap) return lastMaterials;
  const cards = [...wrap.querySelectorAll(".slide-card")];
  if (!cards.length) return lastMaterials;
  const slides = cards.map((c) => ({
    jenis: c.dataset.jenis || "slide",
    tajuk: (c.querySelector(".slide-title")?.innerText || "").trim(),
    isi: [...c.querySelectorAll(".slide-isi li")].map((li) => li.innerText.trim()).filter(Boolean),
    nota_guru: (c.querySelector(".slide-notes span")?.innerText || "").trim(),
  }));
  return { ...(lastMaterials || {}), slides };
}

// Download a binary export produced by the server (docx/pptx).
async function downloadBinary(url, payload, filename, okMsg) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error("Export failed (" + resp.status + ")");
  const blob = await resp.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
  toast(okMsg);
}

async function exportPlanDocx() {
  if (!lastPlan) return toast("Generate a lesson plan first.", true);
  try {
    await downloadBinary("/api/export-docx",
      { plan: lastPlan, school: (profile && profile.school) || "" },
      `RPH_${slug((lastContext && lastContext.kelas) || "kelas")}.docx`,
      "Word (.docx) downloaded \u{1F4DD}");
  } catch (e) { toast(e.message, true); }
}

async function exportSlidesPptx() {
  const m = scrapeMaterials();
  if (!m || !(m.slides || []).length) return toast("No materials to download.", true);
  try {
    await downloadBinary("/api/export-pptx",
      { materials: m, footer: "Niat \u2014 AI-Powered Classroom" },
      `Slides_${slug((lastContext && lastContext.kelas) || "kelas")}.pptx`,
      "PowerPoint (.pptx) downloaded \u{1F4FD}\uFE0F");
  } catch (e) { toast(e.message, true); }
}

// Printable worksheet: pupil paper (no answers) + answer key on its own page.
function printWorksheet() {
  const w = lastWorksheet;
  if (!w || !(w.soalan || []).length) return toast("Generate a worksheet first.", true);
  const kelas = (lastContext && lastContext.kelas) || "";
  const qHTML = w.soalan.map((q) => `
    <div class="q"><p class="qt"><b>${q.no}.</b> ${esc(q.soalan).replace(/\n/g, "<br>")}</p>
    <ol type="A">${(q.pilihan || []).map((p) => `<li>${esc(p)}</li>`).join("")}</ol></div>`).join("");
  const keyCells = w.soalan.map((q) =>
    `<td><b>${q.no}.</b> ${esc(q.jawapan_betul)}</td>`);
  const keyRows = [];
  for (let i = 0; i < keyCells.length; i += 5) keyRows.push(`<tr>${keyCells.slice(i, i + 5).join("")}</tr>`);
  const win = window.open("", "_blank");
  win.document.write(`<!DOCTYPE html><html><head><title>${esc(w.tajuk || "Worksheet")}</title><style>
    body{font-family:'Times New Roman',serif;font-size:12pt;margin:14mm;color:#000;}
    h1{font-size:14pt;text-align:center;margin:0 0 2px;} .sub{text-align:center;margin:0 0 14px;font-size:11pt;}
    .meta{display:flex;justify-content:space-between;border-bottom:1.5px solid #000;padding-bottom:8px;margin-bottom:14px;}
    .q{margin-bottom:12px;page-break-inside:avoid;} .qt{margin:0 0 4px;}
    ol{margin:0 0 0 22px;padding:0;} li{margin:2px 0;}
    .key{page-break-before:always;} .key h2{font-size:13pt;}
    .key table{border-collapse:collapse;} .key td{border:1px solid #000;padding:5px 14px;}
  </style></head><body>
    <h1>${esc(w.tajuk || "English Worksheet")}</h1>
    <p class="sub">${esc(kelas)} \u00B7 ${w.jumlah_soalan} questions \u00B7 ${w.jumlah_markah} marks</p>
    <div class="meta"><span>Name: ______________________________</span><span>Class: __________</span><span>Date: __________</span></div>
    ${qHTML}
    <div class="key"><h2>ANSWER KEY (teacher\u2019s copy) \u2014 ${esc(w.tajuk || "")}</h2><table>${keyRows.join("")}</table></div>
  </body></html>`);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 300);
}

// Agent 2 → Gamma AI: turn the plan + slides into a designed deck / page.
async function createWithGamma() {
  if (!lastPlan) return toast("Generate a lesson plan first.", true);
  const fmt = $("gamma-format") ? $("gamma-format").value : "presentation";
  showOverlay("Polishing your " + fmt + " with a touch of Gamma magic… (30–90 s)");
  try {
    const r = await fetch("/api/gamma-generate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ plan: lastPlan, materials: scrapeMaterials(), format: fmt }),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || "Gamma failed.");
    if (d.url) window.open(d.url, "_blank");
    toast("✨ Gamma " + fmt + " ready" + (d.export_url ? " — PPTX export included" : "") + "!");
    if (d.export_url) window.open(d.export_url, "_blank");
    // Slides created — NOW offer sending them to Google Classroom.
    const cc = $("mat-classroom-card");
    if (cc) cc.classList.remove("hidden");
  } catch (e) {
    toast(e.message, true);
  } finally {
    hideOverlay();
  }
}

function downloadMaterials() {
  const m = scrapeMaterials();
  if (!m || !(m.slides || []).length) return toast("No materials to download.", true);
  downloadBlob(buildMaterialsDeckHTML(m),
    `Slides_${slug((lastContext && lastContext.kelas) || "kelas")}.html`, "text/html");
  toast("Slides downloaded — open the file to present, or Ctrl+P to save as PDF.");
}

// Teacher chose: use these materials (true) or skip them (false). Either way → worksheet.
function proceedFromMaterials(use) {
  materialsUsed = !!use;
  lastMaterials = scrapeMaterials();
  genWorksheet();
}

// Build a self-contained HTML slide deck (presents offline; Ctrl+P → PDF).
function buildMaterialsDeckHTML(m) {
  const title = esc(m.tajuk || "Lesson");
  const kelas = esc(m.kelas || (lastContext && lastContext.kelas) || "");
  const arr = m.slides || [];
  const slidesHTML = arr.map((s, i) => {
    const isi = (s.isi || []).map((p) => `<li>${esc(p)}</li>`).join("");
    const notes = s.nota_guru ? `<div class="notes"><b>Teacher notes:</b> ${esc(s.nota_guru)}</div>` : "";
    const isTitle = s.jenis === "title";
    return `<section class="slide${isTitle ? " title" : ""}"><div class="si">
      <h2>${esc(s.tajuk || "")}</h2>${isi ? `<ul>${isi}</ul>` : ""}${notes}
      </div><div class="pageno">${i + 1} / ${arr.length}</div></section>`;
  }).join("");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title}${kelas ? " — " + kelas : ""}</title><style>
:root{--teal:#0d9488;--teal7:#0f766e;--ink:#0f172a;--mut:#64748b}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Segoe UI,system-ui,sans-serif;color:var(--ink);background:#0b3b38}
.slide{display:none;min-height:100vh;padding:6vh 8vw;flex-direction:column;justify-content:center;background:linear-gradient(135deg,#f0fdfa,#fff)}
.slide.active{display:flex}
.slide.title{background:linear-gradient(135deg,var(--teal7),var(--teal));color:#fff;text-align:center;align-items:center}
.si{max-width:900px;margin:0 auto;width:100%}
h2{font-size:clamp(26px,4.4vw,46px);line-height:1.15;margin-bottom:.6em}
ul{font-size:clamp(18px,2.6vw,28px);line-height:1.55;padding-left:1.2em}
li{margin:.35em 0}
.notes{margin-top:1.4em;padding:14px 16px;background:rgba(13,148,136,.08);border-left:4px solid var(--teal);border-radius:8px;font-size:15px;color:var(--mut)}
.title .notes{display:none}
.pageno{position:fixed;bottom:14px;right:18px;font-size:13px;color:var(--mut)}
.nav{position:fixed;bottom:14px;left:18px;font-size:13px;color:var(--mut)}
@media print{body{background:#fff}.slide{display:flex!important;page-break-after:always;min-height:96vh}.nav{display:none}}
</style></head><body>${slidesHTML}
<div class="nav">← → navigate · F11 full screen · Ctrl+P → PDF</div>
<script>
var sl=document.querySelectorAll('.slide'),i=0;
function show(n){i=Math.max(0,Math.min(sl.length-1,n));sl.forEach(function(s,k){s.classList.toggle('active',k===i)})}
document.addEventListener('keydown',function(e){if(e.key==='ArrowRight'||e.key===' '||e.key==='PageDown')show(i+1);if(e.key==='ArrowLeft'||e.key==='PageUp')show(i-1)});
document.addEventListener('click',function(e){if(!e.target.closest('a'))show(i+1)});
show(0);
<\/script></body></html>`;
}

// ====================== Agent 3: Worksheet ======================
async function genWorksheet(note = "") {
  const inp = collectInputs();
  lastInputs = inp;
  if (note) inp.nota_guru = note;
  if (materialsUsed && lastMaterials) inp.materials = lastMaterials;
  if (lastPlan) inp.plan = lastPlan;  // keep questions aligned to THIS lesson
  try {
    const data = await api("/api/generate-worksheet", inp, "Building your worksheet — bank questions first, AI fills the rest…");
    lastWorksheet = data.worksheet;
    renderWorksheet(lastWorksheet);
    prefillSendCard();
    goto(4);
    guardrailNotice(data._guardrail);
    engineNotice(data);
  } catch (e) {
    toast(e.message, true);
  }
}

function renderWorksheet(w) {
  const questions = (w.soalan || []).map((q) => {
    const opts = (q.pilihan || []).map((p, i) => {
      const letter = "ABCD"[i];
      const correct = letter === q.jawapan_betul ? " correct" : "";
      return `<div class="opt${correct}">${letter}. ${esc(p)}</div>`;
    }).join("");
    return `<div class="q">
      <div class="qhead"><span>Question ${q.no} · LS ${esc(q.sp_rujukan)}</span><span class="badge">${esc(q.aras)}</span></div>
      <div><b>${esc(q.soalan)}</b></div>
      ${opts}
      <div class="fb">Answer: ${esc(q.jawapan_betul)} · ${esc(q.maklum_balas)}</div>
    </div>`;
  }).join("");
  const s = w._sumber || {};
  const source = (s.dari_bank || s.dijana_ai)
    ? ` · 🗄️ ${num(s.dari_bank)} from question bank · 🤖 ${num(s.dijana_ai)} AI-generated`
    : "";
  $("ws-output").innerHTML = `
    <h3>${esc(w.tajuk)}</h3>
    <p class="muted small">${esc(w.jumlah_soalan)} questions · ${esc(w.jumlah_markah)} marks · answer key included${source}</p>
    ${questions}`;
}

// ====================== Save & export ======================
async function approveAndSave() {
  const planEdited = readEditedPlan();
  try {
    const r1 = await api("/api/save",
      { jenis: "lessonplan", kelas: lastContext.kelas, kandungan: planEdited }, "Saving lesson plan…");
    const r2 = await api("/api/save",
      { jenis: "worksheet", kelas: lastContext.kelas, kandungan: lastWorksheet,
        topic: (lastInputs && lastInputs.topic) || "",
        theme: (lastInputs && lastInputs.theme) || "" }, "Saving worksheet…");
    const b = r2.bank || {};
    const bankNote = (b.ditambah || b.diguna_semula)
      ? `<li>🗄️ Question Bank: <b>${num(b.ditambah)}</b> new questions added · <b>${num(b.diguna_semula)}</b> reused</li>`
      : "";
    // Save the teaching materials too, if the teacher chose to use them.
    let matNote = "";
    if (materialsUsed && lastMaterials) {
      try {
        const r3 = await api("/api/save",
          { jenis: "materials", kelas: lastContext.kelas, kandungan: lastMaterials }, "Saving teaching materials…");
        matNote = `<li>📊 Teaching Materials: <code>${esc(r3.fail)}</code></li>`;
      } catch (e) { /* non-fatal */ }
    }
    // Save the full lesson (plan + worksheet + inputs) to the Lesson Library.
    let libNote = "";
    try {
      await api("/api/save-lesson",
        { plan: lastPlan, worksheet: lastWorksheet, materials: materialsUsed ? lastMaterials : null, inputs: lastInputs }, "Saving to library…");
      libNote = `<li>📚 Saved to <b>My Lessons</b> library</li>`;
    } catch (e) { /* non-fatal — files are already saved */ }
    $("saved-list").innerHTML =
      `<li>📄 Lesson Plan: <code>${esc(r1.fail)}</code></li><li>📝 Worksheet: <code>${esc(r2.fail)}</code></li>${matNote}${bankNote}${libNote}`;
    updateBankBadge();
    goto(5);
  } catch (e) {
    toast(e.message, true);
  }
}

// Capture the (possibly edited) lesson plan view; save both structured + display versions.
function readEditedPlan() {
  const editable = $("rph-output").querySelector("[contenteditable]");
  return { struktur: lastPlan, paparan_html: editable ? editable.innerHTML : "" };
}

// Build a polished, A4-formatted lesson-plan document (shared by .doc export & print/PDF).
function buildPlanDocHTML() {
  const editable = $("rph-output").querySelector("[contenteditable]");
  const inner = editable ? editable.innerHTML : planTableHTML(lastPlan);
  const school = ($("school") ? $("school").value : "").trim();
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
  <title>Rancangan Pelajaran Harian</title>
  <style>
    @page { size: A4; margin: 1.4cm; }
    body { font-family: Arial, sans-serif; font-size: 11pt; color:#000; margin:0; }
    .doc-head { text-align:center; margin-bottom:12px; }
    .doc-head .school { font-size:13pt; font-weight:bold; text-transform:uppercase; }
    .doc-head .title { font-size:16pt; font-weight:bold; margin-top:4px; letter-spacing:.5px; }
    table.rph { border-collapse:collapse; width:100%; font-size:10.5pt; }
    table.rph th, table.rph td { border:1px solid #000; padding:6px 9px; vertical-align:top; text-align:left; }
    table.rph th { background:#f0f0f0; width:24%; font-weight:bold; }
    .editable-hint { display:none; }
  </style></head>
  <body>
    <div class="doc-head">
      ${school ? `<div class="school">${esc(school)}</div>` : ""}
      <div class="title">RANCANGAN PELAJARAN HARIAN</div>
    </div>
    ${inner}
  </body></html>`;
}

function exportPlanDoc() {
  if (!lastPlan) return;
  downloadBlob(buildPlanDocHTML(), `RPH_${slug(lastContext.kelas)}.doc`, "application/msword");
}

// Open a clean print view; the browser's print dialog can "Save as PDF".
function printPlan() {
  if (!lastPlan) return;
  const w = window.open("", "_blank");
  if (!w) return toast("Please allow pop-ups to print / save as PDF.", true);
  w.document.write(buildPlanDocHTML());
  w.document.close();
  w.focus();
  setTimeout(() => w.print(), 300);
}

// ---- Export format menu (PDF / Word) ----
function toggleExportMenu(e) {
  if (e) e.stopPropagation();
  const m = $("export-menu");
  if (m) m.classList.toggle("hidden");
}
function closeExportMenu() { const m = $("export-menu"); if (m) m.classList.add("hidden"); }

// ---- Save lesson plan to Google Drive (Apps Script, plan only) ----
function buildDriveScript() {
  if (!lastPlan) return "";
  const ctx = lastContext || {};
  const planTitle = "RPH — " + (ctx.kelas || "Class") + (ctx.tarikh ? " (" + ctx.tarikh + ")" : "");
  const data = JSON.stringify({ planTitle, planRows: planRows(lastPlan) }, null, 2);
  return `/**
 * Niat → Save to Google Drive + Upload to Google Classroom
 *
 * ONE-TIME SETUP:
 *   In the script editor, click "Services" (the + on the left) →
 *   "Google Classroom API" → Add.
 *
 * STEP 1 — find your Classroom:
 *   Leave COURSE_ID = "" below and Run "niatToClassroom" once.
 *   Click "Review permissions" → Allow. Open the Execution log to see the list
 *   of your Classrooms and their IDs.
 * STEP 2 — post it:
 *   Copy the ID of your designated RPH Classroom into COURSE_ID below, then Run again.
 *   The lesson plan is saved to your Google Drive AND posted to that Classroom.
 */
var COURSE_ID = "";  // <-- paste your designated RPH Classroom course ID here, then Run again

function niatToClassroom() {
  var DATA = ${data};

  // STEP 1: list the Classrooms you teach, so you can copy the right ID.
  if (!COURSE_ID) {
    var list = Classroom.Courses.list({ teacherId: "me", courseStates: ["ACTIVE"] });
    var courses = (list && list.courses) || [];
    if (!courses.length) { Logger.log("No active Classrooms found where you are a teacher."); return; }
    Logger.log("=== Your Google Classrooms — copy the ID of your designated RPH class ===");
    courses.forEach(function (c) { Logger.log(c.name + "   ->   COURSE_ID = \\"" + c.id + "\\""); });
    Logger.log("Paste the correct ID into COURSE_ID at the top, then Run again.");
    return;
  }

  // STEP 2a: create the lesson plan as a Google Doc in your Drive.
  var doc = DocumentApp.create(DATA.planTitle);
  var body = doc.getBody();
  body.appendParagraph("RANCANGAN PELAJARAN HARIAN").setHeading(DocumentApp.ParagraphHeading.HEADING1);
  if (DATA.planRows.length) {
    var table = body.appendTable(DATA.planRows);
    for (var i = 0; i < DATA.planRows.length; i++) { table.getCell(i, 0).editAsText().setBold(true); }
  }
  doc.saveAndClose();

  // STEP 2b: post the Doc to the designated Classroom as a Material.
  Classroom.Courses.CourseWorkMaterials.create({
    title: DATA.planTitle,
    description: "Daily Lesson Plan (RPH) — uploaded by Niat.",
    materials: [{ driveFile: { driveFile: { id: doc.getId() }, shareMode: "VIEW" } }],
    state: "PUBLISHED"
  }, COURSE_ID);

  Logger.log("Saved to Drive: " + doc.getUrl());
  Logger.log("Posted to Classroom course ID: " + COURSE_ID);
}
`;
}
function openDriveModal() {
  if (!lastPlan) return toast("Generate a lesson plan first.", true);
  $("drive-script").value = buildDriveScript();
  $("drive-modal").classList.remove("hidden");
}
function closeDriveModal() { $("drive-modal").classList.add("hidden"); }
async function copyDriveScript() {
  const ta = $("drive-script");
  try { await navigator.clipboard.writeText(ta.value); toast("Script copied to clipboard ✓"); }
  catch (e) { ta.focus(); ta.select(); try { document.execCommand("copy"); toast("Script copied ✓"); } catch (_) { toast("Press Ctrl+C to copy", true); } }
}
function downloadDriveScript() {
  if (!lastPlan) return;
  downloadBlob(buildDriveScript(), `NiatClassroom_${slug(lastContext && lastContext.kelas)}.gs`, "text/plain");
}

function downloadWorksheetJSON() {
  if (!lastWorksheet) return;
  downloadBlob(JSON.stringify(lastWorksheet, null, 2),
    `Worksheet_${slug(lastContext.kelas)}.json`, "application/json");
}

function downloadBlob(content, filename, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ====================== Distribute via Google (Apps Script) ======================
// Builds ONE Google Apps Script that, run under the teacher's own moe-dl account:
//   1. creates the worksheet as a Google Form QUIZ (MCQ, auto-graded) and emails its link,
//   2. creates the lesson plan as a Google Doc in Drive and emails its link.
// No Google Cloud project or admin approval needed.

// Lesson plan → rows of [label, value] for the Google Doc table (JPN Perlis RPH format).
function planRows(r) {
  if (!r) return [];
  const S = (x) => String(x == null ? "" : x);
  const num = (a) => (a || []).map((x, i) => (i + 1) + ". " + x).join("\n");
  const sp = (r.standard_pembelajaran || []).join("\n");
  return [
    ["MINGGU", S(r.minggu)], ["TARIKH", S(r.tarikh)],
    ["HARI", S(r.hari)], ["MASA", S(r.masa)],
    ["TINGKATAN / KELAS", S(r.tingkatan_kelas)], ["MINIMUM JAM SETAHUN", S(r.minimum_jam_setahun)],
    ["MATA PELAJARAN", S(r.mata_pelajaran)],
    ["TEMA / BIDANG", S(r.tema_bidang)],
    ["TAJUK", S(r.tajuk)],
    ["STANDARD KANDUNGAN", S(r.standard_kandungan)],
    ["STANDARD PEMBELAJARAN", sp],
    ["OBJEKTIF PEMBELAJARAN", "Pada akhir PdPc, murid boleh :\n" + num(r.objektif_pembelajaran)],
    ["AKTIVITI PEMBELAJARAN", num(r.aktiviti_pembelajaran)],
    ["REFLEKSI", ""],
  ];
}

function buildDistributeScript() {
  const w = lastWorksheet;
  if (!w) return "";
  const ctx = lastContext || {};
  const wsTitle = (w.tajuk || "Niat Worksheet").replace(/\s+/g, " ").trim();
  const wsDesc = [ctx.kelas ? "Class: " + ctx.kelas : "", ctx.tarikh ? "Date: " + ctx.tarikh : "", "Generated by Niat"].filter(Boolean).join("  •  ");
  const questions = (w.soalan || []).map((q) => ({
    q: q.soalan || "", opts: q.pilihan || [],
    answerIndex: "ABCD".indexOf(q.jawapan_betul),
    points: (+q.markah || 1), feedback: q.maklum_balas || "",
  }));
  const totalPoints = questions.reduce((s, q) => s + (q.points || 1), 0);
  const planTitle = "Lesson Plan — " + (ctx.kelas || "Class") + (ctx.tarikh ? " (" + ctx.tarikh + ")" : "");
  const planEmail = ($("rcpt-plan") ? $("rcpt-plan").value : "").trim();
  const className = ($("classroom-class") ? $("classroom-class").value : "").trim();
  const dDate = ($("due-date") ? $("due-date").value : "").trim();   // yyyy-mm-dd
  const dTime = ($("due-time") ? $("due-time").value : "").trim();   // HH:MM
  const dueIso = (dDate && dTime) ? (dDate + "T" + dTime + ":00+08:00") : "";  // Malaysia time (UTC+8)
  const dueLocal = (dDate && dTime) ? (dDate + " " + dTime) : "";

  // Student-friendly Classroom assignment title + instructions.
  // Prefer the AI-written title (w.tajuk) and instructions (w.arahan_murid); else compose.
  const topic = (lastPlan && (lastPlan.tajuk || lastPlan.tema_bidang)) || "today's English lesson";
  const cwTitle = wsTitle;  // AI-written student-facing title, e.g. "English Quiz: ..."
  const aiInstr = (w.arahan_murid || "").trim();
  const cwDescription =
    (aiInstr ||
      ("Hi everyone! Here is your English quiz on \"" + topic + "\".\n\n" +
       "Instructions:\n" +
       "1. This quiz has " + questions.length + " multiple-choice questions.\n" +
       "2. Read each question carefully and choose the ONE best answer.\n" +
       "3. Answer every question, then click Submit.\n" +
       "4. You will see the correct answers and feedback after you submit.")) +
    (dueLocal ? "\n\nDue date: " + dueLocal + " — please submit before then." : "");

  const lp = lastPlan || {};
  const slides = [
    { heading: lp.tajuk || "English Lesson", body: [lp.tema_bidang, ctx.kelas, lp.tarikh].filter(Boolean) },
    { heading: "Learning Objectives", body: lp.objektif_pembelajaran || [] },
    { heading: "Lesson Activities", body: lp.aktiviti_pembelajaran || [] },
  ];
  const data = JSON.stringify({
    planTitle, planRows: planRows(lastPlan), planEmail, slides,
    students: STUDENTS,
    ws: { title: wsTitle, desc: wsDesc, questions, points: totalPoints },
    classroom: { className, dueIso, dueLocal, title: cwTitle, description: cwDescription },
  }, null, 2);
  return `/**
 * Niat → Distribute
 *
 * HOW TO USE:
 *  1. Go to  https://script.google.com  and click "New project".
 *  2. Delete the sample code, then paste ALL of this in.
 *  3. Enable the Classroom service: in the left sidebar click "Services +",
 *     choose "Google Classroom API", click Add.
 *  4. Click Save (disk icon), then Run the function "niatDistribute".
 *  5. Click "Review permissions" and Allow (first time only).
 *  6. Check the Execution log. It will:
 *       • save the LESSON PLAN as a Google Doc in your Drive + email it to you,
 *       • create the WORKSHEET as a Google Form quiz, and
 *       • post that quiz to your Google Classroom class as an assignment with a due date.
 */
function niatDistribute() {
  var DATA = ${data};

  // ---- 1) Lesson plan -> Google Doc in Drive + email the teacher ----
  var doc = DocumentApp.create(DATA.planTitle);
  var body = doc.getBody();
  body.appendParagraph(DATA.planTitle).setHeading(DocumentApp.ParagraphHeading.HEADING1);
  if (DATA.planRows.length) {
    var table = body.appendTable(DATA.planRows);
    for (var i = 0; i < DATA.planRows.length; i++) {
      table.getCell(i, 0).editAsText().setBold(true);
    }
  }
  doc.saveAndClose();
  var docUrl = doc.getUrl();
  // Convert the lesson plan to PDF and save it in Drive.
  var pdfBlob = DriveApp.getFileById(doc.getId()).getAs("application/pdf").setName(DATA.planTitle + ".pdf");
  var pdfFile = DriveApp.createFile(pdfBlob);
  var pdfUrl = pdfFile.getUrl();
  if (DATA.planEmail) {
    MailApp.sendEmail({
      to: DATA.planEmail,
      subject: "[Niat] Lesson Plan (PDF) — " + DATA.planTitle,
      htmlBody: "Your lesson plan is attached as a PDF and saved to your Google Drive.<br><br>" +
                "PDF: <a href=\\"" + pdfUrl + "\\">" + pdfUrl + "</a><br>" +
                "Editable Doc: <a href=\\"" + docUrl + "\\">" + docUrl + "</a>",
      attachments: [pdfBlob]
    });
  }

  // ---- 2) Worksheet -> Google Form quiz ----
  var form = FormApp.create(DATA.ws.title);
  form.setIsQuiz(true);
  form.setDescription(DATA.classroom.description);
  form.setCollectEmail(true);
  DATA.ws.questions.forEach(function (item) {
    var mc = form.addMultipleChoiceItem();
    var choices = item.opts.map(function (opt, i) {
      return mc.createChoice(opt, i === item.answerIndex);
    });
    mc.setTitle(item.q).setChoices(choices).setPoints(item.points).setRequired(true);
    if (item.feedback) {
      var fb = FormApp.createFeedback().setText(item.feedback).build();
      mc.setFeedbackForCorrect(fb);
      mc.setFeedbackForIncorrect(fb);
    }
  });
  var formUrl = form.getPublishedUrl();

  // QR code (students scan to open the quiz; the teacher can project or print it).
  var qrUrl = "https://quickchart.io/qr?size=320&margin=2&text=" + encodeURIComponent(formUrl);
  if (DATA.planEmail) {
    MailApp.sendEmail({
      to: DATA.planEmail,
      subject: "[Niat] Quiz QR — " + DATA.ws.title,
      htmlBody: "Show or print this QR code for pupils to open the quiz:<br><br>" +
                "<img src=\\"" + qrUrl + "\\" width=\\"260\\" height=\\"260\\"><br><br>" +
                "Or share this link: <a href=\\"" + formUrl + "\\">" + formUrl + "</a>"
    });
  }

  // ---- 2c) Email the quiz link directly to the pilot students ----
  var studentsSent = 0;
  (DATA.students || []).forEach(function (st) {
    try {
      MailApp.sendEmail({
        to: st.email,
        subject: "[Niat] " + DATA.ws.title,
        htmlBody: "Hi " + (st.name || "there") + "!<br><br>" +
                  DATA.classroom.description.replace(/\\n/g, "<br>") + "<br><br>" +
                  "Open the quiz here: <a href=\\"" + formUrl + "\\">" + formUrl + "</a><br><br>" +
                  "Good luck!<br>— Niat, your class assistant"
      });
      studentsSent++;
    } catch (e) { Logger.log("Student email FAILED for " + st.email + ": " + e); }
  });
  Logger.log("Quiz emailed to " + studentsSent + " of " + (DATA.students || []).length + " pilot student(s).");

  // ---- 3) Post the worksheet to Google Classroom (assignment + due date) ----
  var classroomStatus = "not posted";
  try {
    var courses = (Classroom.Courses.list({ courseStates: ["ACTIVE"] }).courses) || [];
    var want = (DATA.classroom.className || "").toLowerCase();
    var target = null;
    for (var j = 0; j < courses.length; j++) {
      var nm = (courses[j].name || "").toLowerCase();
      if (want && (nm === want || nm.indexOf(want) > -1)) { target = courses[j]; break; }
    }
    if (!target) {
      classroomStatus = 'NO active Classroom class matching "' + DATA.classroom.className +
        '". Share this quiz link manually: ' + formUrl;
    } else {
      var work = {
        title: DATA.classroom.title,
        description: DATA.classroom.description,
        materials: [{ link: { url: formUrl, title: DATA.ws.title } }],
        workType: "ASSIGNMENT",
        state: "PUBLISHED",
        maxPoints: DATA.ws.points || 100
      };
      if (DATA.classroom.dueIso) {
        var dd = new Date(DATA.classroom.dueIso);  // due time is in Malaysia time (UTC+8)
        work.dueDate = { year: dd.getUTCFullYear(), month: dd.getUTCMonth() + 1, day: dd.getUTCDate() };
        work.dueTime = { hours: dd.getUTCHours(), minutes: dd.getUTCMinutes() };
      }
      var cw = Classroom.Courses.CourseWork.create(work, target.id);
      classroomStatus = 'posted to "' + target.name + '"' +
        (DATA.classroom.dueLocal ? " (due " + DATA.classroom.dueLocal + ")" : "") +
        " -> " + cw.alternateLink;
    }
  } catch (e) {
    classroomStatus = "Classroom step failed: " + e + " | Quiz link to share manually: " + formUrl;
  }

  // ---- 4) Lesson plan -> Google Slides teaching deck ----
  var slidesUrl = "";
  try {
    var deck = SlidesApp.create("Slides — " + DATA.planTitle);
    var existing = deck.getSlides();
    DATA.slides.forEach(function (s, idx) {
      var slide = (idx === 0) ? existing[0] : deck.appendSlide(SlidesApp.PredefinedLayout.BLANK);
      var h = slide.insertTextBox(s.heading, 36, 28, 648, 70);
      h.getText().getTextStyle().setBold(true).setFontSize(26);
      if (s.body && s.body.length) {
        var lines = s.body.map(function (x) { return "•  " + x; }).join("\\n\\n");
        var b = slide.insertTextBox(lines, 44, 110, 632, 300);
        b.getText().getTextStyle().setFontSize(15);
      }
    });
    deck.saveAndClose();
    slidesUrl = deck.getUrl();
    if (DATA.planEmail) {
      MailApp.sendEmail({
        to: DATA.planEmail,
        subject: "[Niat] Teaching Slides — " + DATA.planTitle,
        htmlBody: "Your teaching slides are ready in Google Slides:<br><br>" +
                  "<a href=\\"" + slidesUrl + "\\">" + slidesUrl + "</a>"
      });
    }
  } catch (e) {
    slidesUrl = "Slides step skipped: " + e;
  }

  Logger.log("Lesson plan doc (Drive + emailed): " + docUrl);
  Logger.log("Lesson plan PDF: " + pdfUrl);
  Logger.log("Teaching slides: " + slidesUrl);
  Logger.log("Worksheet form: " + formUrl);
  Logger.log("Quiz QR: " + qrUrl);
  Logger.log("Classroom: " + classroomStatus);
}
`;
}

// One-click Classroom posting via the Niat Hub (no Apps Script visits).
async function directLessonPlan() {
  if (!lastPlan) return toast("Generate a lesson plan first.", true);
  showOverlay("Posting the lesson plan to Google Classroom…");
  try {
    const r = await fetch("/api/classroom-lessonplan", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ plan: lastPlan, school: (profile && profile.school) || "" }),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || "Failed.");
    toast("✅ Lesson plan posted to Classroom + saved to Drive!");
    if (d.classroom_url) window.open(d.classroom_url, "_blank");
    else if (d.doc_url) window.open(d.doc_url, "_blank");
  } catch (e) { toast(e.message, true); } finally { hideOverlay(); }
}

// Fill the Send-to-Classroom card with smart defaults (class from the lesson,
// due tomorrow 8:00 PM). The teacher can change any of them.
function prefillSendCard() {
  if ($("classroom-class") && !$("classroom-class").value) {
    $("classroom-class").value = (lastContext && lastContext.kelas) || "";
  }
  if ($("due-date") && !$("due-date").value) {
    const t = new Date(Date.now() + 86400000);
    $("due-date").value = t.toISOString().slice(0, 10);
  }
  if ($("due-time") && !$("due-time").value) $("due-time").value = "20:00";
}

async function directMaterials() {
  const m = scrapeMaterials();
  if (!m || !(m.slides || []).length) return toast("Generate the teaching slides first.", true);
  const target = $("mat-target") ? $("mat-target").value : "lesson_plan";
  showOverlay("Creating Google Slides + posting to Classroom…");
  try {
    const r = await fetch("/api/classroom-materials", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ materials: m, plan: lastPlan, target }),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || "Failed.");
    toast("✅ Slides posted to Classroom!");
    if (d.classroom_url) window.open(d.classroom_url, "_blank");
    else if (d.slides_url) window.open(d.slides_url, "_blank");
  } catch (e) { toast(e.message, true); } finally { hideOverlay(); }
}

async function directWorksheet() {
  if (!lastWorksheet) return toast("Generate a worksheet first.", true);
  const className = ($("classroom-class") ? $("classroom-class").value : "").trim()
    || ((lastContext && lastContext.kelas) || "");
  showOverlay("Creating the Form quiz + posting to Classroom…");
  try {
    const r = await fetch("/api/classroom-worksheet", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({
        worksheet: lastWorksheet, class_name: className,
        due_date: ($("due-date") ? $("due-date").value : ""),
        due_time: ($("due-time") ? $("due-time").value : ""),
      }),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || "Failed.");
    toast("✅ Quiz posted to Classroom (" + className + ") — " +
          (d.students_emailed || 0) + " pupil(s) emailed!");
    if (d.classroom_url) window.open(d.classroom_url, "_blank");
    else if (d.form_url) window.open(d.form_url, "_blank");
  } catch (e) { toast(e.message, true); } finally { hideOverlay(); }
}

function refreshScript() {
  if (!$("form-script")) return;
  $("form-script").value = buildDistributeScript();
}

function openFormModal() {
  if (!lastWorksheet) return toast("Generate a worksheet first.", true);
  if ($("rcpt-plan") && !$("rcpt-plan").value) $("rcpt-plan").value = "aimiizdihar1987@gmail.com";
  if ($("classroom-class") && !$("classroom-class").value) $("classroom-class").value = (lastContext && lastContext.kelas) || "";
  // Sensible defaults: due tomorrow at 8:00 PM (teacher can change).
  if ($("due-date") && !$("due-date").value) {
    const t = new Date(Date.now() + 86400000);
    $("due-date").value = t.toISOString().slice(0, 10);
  }
  if ($("due-time") && !$("due-time").value) $("due-time").value = "20:00";
  refreshScript();
  $("form-modal").classList.remove("hidden");
}
function closeFormModal() { $("form-modal").classList.add("hidden"); }

async function copyFormScript() {
  const ta = $("form-script");
  try {
    await navigator.clipboard.writeText(ta.value);
    toast("Script copied to clipboard ✓");
  } catch (e) {
    ta.focus(); ta.select();
    try { document.execCommand("copy"); toast("Script copied ✓"); }
    catch (_) { toast("Press Ctrl+C to copy", true); }
  }
}
function downloadFormScript() {
  if (!lastWorksheet) return;
  downloadBlob(buildDistributeScript(),
    `NiatDistribute_${slug(lastContext && lastContext.kelas)}.gs`, "text/plain");
}

// ====================== Lesson Library ======================
async function openLibrary() {
  $("library-modal").classList.remove("hidden");
  $("library-search").value = "";
  await loadLessonList("");
}
function closeLibrary() { $("library-modal").classList.add("hidden"); }

async function loadLessonList(q) {
  const box = $("library-list");
  box.innerHTML = '<p class="muted small">Loading…</p>';
  try {
    const items = await (await fetch("/api/lessons?q=" + encodeURIComponent(q || ""))).json();
    box.innerHTML = items.length
      ? items.map(libRow).join("")
      : '<p class="muted small">No saved lessons yet. Approve a lesson to save it here.</p>';
  } catch (e) {
    box.innerHTML = '<p class="warn">Failed to load lessons.</p>';
  }
}

function libRow(l) {
  const meta = [l.kelas, l.tarikh, l.skill].filter(Boolean).join(" · ");
  return `<div class="lib-item">
    <div class="lib-main">
      <div class="lib-title">${esc(l.title || "Lesson")}</div>
      <div class="lib-meta">${esc(meta)}${l.theme ? " · " + esc(l.theme) : ""}</div>
    </div>
    <div class="lib-actions">
      <button class="ghost mini" data-act="open" data-id="${l.id}">Open</button>
      <button class="ghost mini" data-act="reflect" data-id="${l.id}">Reflect</button>
      <button class="ghost mini" data-act="doc" data-id="${l.id}">.doc</button>
      <button class="ghost mini" data-act="dup" data-id="${l.id}">Duplicate</button>
      <button class="ghost mini danger" data-act="del" data-id="${l.id}">Delete</button>
    </div>
  </div>`;
}

async function fetchLesson(id) {
  const rec = await (await fetch("/api/lesson?id=" + id)).json();
  if (!rec || rec.ralat) { toast("Lesson not found.", true); return null; }
  return rec;
}

async function libClick(e) {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const id = +btn.dataset.id;
  const act = btn.dataset.act;
  if (act === "open") {
    const rec = await fetchLesson(id); if (!rec) return;
    lastPlan = rec.plan; lastWorksheet = rec.worksheet; lastInputs = rec.inputs;
    lastContext = { kelas: rec.kelas, tarikh: rec.tarikh };
    renderPlan(lastPlan);
    if (lastWorksheet && lastWorksheet.soalan) renderWorksheet(lastWorksheet);
    closeLibrary(); goto(2);
    toast("Lesson opened — you can export or distribute it.");
  } else if (act === "doc") {
    const rec = await fetchLesson(id); if (!rec) return;
    lastPlan = rec.plan; lastContext = { kelas: rec.kelas, tarikh: rec.tarikh };
    exportPlanDoc();
  } else if (act === "dup") {
    const rec = await fetchLesson(id); if (!rec) return;
    restoreInputs(rec.inputs || {});
    closeLibrary(); goto(1);
    toast("Settings loaded — adjust and generate a new version.");
  } else if (act === "del") {
    if (!confirm("Delete this saved lesson? This cannot be undone.")) return;
    try { await api("/api/delete-lesson", { id }, "Deleting…"); }
    catch (e) { return toast(e.message, true); }
    loadLessonList($("library-search").value);
  } else if (act === "reflect") {
    const rec = await fetchLesson(id); if (!rec) return;
    openReflectModal(rec);
  }
}

// ---- Reflect & Report (agent #6 / loop close) ----
let reflectLesson = null;
function openReflectModal(rec) {
  reflectLesson = rec;
  $("reflect-title").textContent = rec.title || "Lesson";
  $("reflect-score").value = "";
  $("reflect-results").value = "";
  if ($("reflect-quick")) $("reflect-quick").value = "";
  if ($("results-box")) { $("results-box").classList.add("hidden"); $("results-box").innerHTML = ""; }
  $("reflect-output").classList.add("hidden");
  $("reflect-output").innerHTML = "";
  $("btn-save-reflection").classList.add("hidden");
  $("reflect-modal").classList.remove("hidden");
}
function closeReflectModal() { $("reflect-modal").classList.add("hidden"); reflectLesson = null; }

// #4 Auto-pull results: read the Form's responses via the Niat Hub, fill the
// score + notes automatically, and show a class report. No copy-paste scripts.
async function fetchResults() {
  if (!reflectLesson) return;
  const title = (reflectLesson.worksheet && reflectLesson.worksheet.tajuk) || "";
  const formId = reflectLesson.form_id ||
    (reflectLesson.worksheet && reflectLesson.worksheet.form_id) || "";
  const box = $("results-box");
  const btn = $("btn-get-results");
  box.classList.remove("hidden");
  box.textContent = "Fetching results from Google Forms…";
  btn.disabled = true;
  try {
    // Pass the class so the server banks each pupil's score into their
    // cumulative history (feeds Agent 5's differentiation decision).
    const className = (reflectLesson.plan && reflectLesson.plan.tingkatan_kelas) || "";
    const topic = (reflectLesson.inputs && reflectLesson.inputs.topic) ||
      (reflectLesson.plan && reflectLesson.plan.tajuk) || "";
    const r = await fetch("/api/quiz-results", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ title, form_id: formId, class_name: className,
        topic, lesson_id: reflectLesson.id || "" }),
    });
    const d = await r.json();
    if (!d.ok) {
      box.innerHTML = "⚠️ " + esc(d.error || "Could not read results. Make sure the quiz was distributed and the Niat Hub is deployed.");
      return;
    }
    if (!d.respondents) {
      box.innerHTML = "No responses yet for “" + esc(d.title || title) + "”. Ask pupils to submit, then try again.";
      return;
    }
    reflectLesson._results = d;  // keep for the standalone report / email
    const weak = (d.weakest || []).map((w) => "Q" + w.q + " (" + w.correct_percent + "% correct)").join(", ");
    $("reflect-score").value = d.average_percent;
    $("reflect-quick").value = d.respondents + " pupils responded";
    const notes = "Average " + d.average_percent + "%. Weakest: " + (weak || "—") + ".";
    if (!$("reflect-results").value.trim()) $("reflect-results").value = notes;
    const rows = (d.per_student || []).map((s) =>
      "<tr><td>" + esc(s.email) + "</td><td style='text-align:right'>" + s.score + "/" + s.max + " (" + s.percent + "%)</td></tr>").join("");
    box.innerHTML =
      "<b>" + esc(d.title || title) + "</b><br>" + d.respondents + " responses · average <b>" + d.average_percent + "%</b>"
      + (weak ? "<br>Weakest: " + esc(weak) : "")
      + (rows ? "<table class='g-table' style='margin-top:8px'><tr><th>Pupil</th><th style='text-align:right'>Score</th></tr>" + rows + "</table>" : "");
    toast("Results loaded — average " + d.average_percent + "%.");
  } catch (e) {
    box.innerHTML = "⚠️ Could not reach the Niat Hub. Check APPSCRIPT_HUB_URL in reminder_config.txt.";
  } finally {
    btn.disabled = false;
  }
}

async function generateReflectionUI() {
  if (!reflectLesson) return;
  try {
    const quick = $("reflect-quick") ? $("reflect-quick").value.trim() : "";
    const notes = $("reflect-results").value.trim();
    const results = [quick, notes].filter(Boolean).join(". ");
    const data = await api("/api/reflect",
      { plan: reflectLesson.plan, results, score_avg: $("reflect-score").value.trim() },
      "Writing reflection & report…");
    reflectLesson._refleksi = data.refleksi || "";
    reflectLesson._report = data.report || "";
    $("reflect-output").innerHTML =
      `<h4>Reflection (for the RPH) — edit or add to it, then Save</h4>` +
      `<textarea id="reflect-edit" class="reflect-edit">${esc(data.refleksi || "")}</textarea>` +
      `<h4>Class report</h4><pre class="reflect-box">${esc(data.report || "")}</pre>` +
      `<div class="actions" style="justify-content:flex-start;margin-top:8px;flex-wrap:wrap;gap:8px">` +
        `<button id="btn-download-report" class="ghost">📄 Save report (.md)</button>` +
        `<input id="reflect-email" type="email" placeholder="teacher@email.com" style="max-width:190px" />` +
        `<button id="btn-email-report" class="ghost">✉️ Email report</button>` +
        `<button id="btn-remedial" class="ghost">🎯 Generate remedial worksheet for weak areas</button>` +
        `<button id="btn-differentiate" class="ghost">🧩 Differentiate by performance (Agent 5)</button>` +
      `</div>` +
      `<div id="diff-output" class="hidden" style="margin-top:10px"></div>`;
    $("reflect-output").classList.remove("hidden");
    $("btn-save-reflection").classList.remove("hidden");
    const rb = $("btn-remedial"); if (rb) rb.onclick = generateRemedial;
    const xb = $("btn-differentiate"); if (xb) xb.onclick = differentiateAndDistribute;
    const db = $("btn-download-report"); if (db) db.onclick = downloadReport;
    const eb = $("btn-email-report"); if (eb) eb.onclick = emailReport;
  } catch (e) { toast(e.message, true); }
}

async function saveReflectionUI() {
  if (!reflectLesson) return;
  // Save the teacher's edited text (auto-filled by AI, then editable) — human-in-the-loop.
  const text = $("reflect-edit") ? $("reflect-edit").value.trim() : (reflectLesson._refleksi || "");
  if (!text) return toast("Nothing to save — generate or write a reflection first.", true);
  try {
    await api("/api/lesson-reflection",
      { id: reflectLesson.id, refleksi: text, score: $("reflect-score").value.trim() },
      "Saving reflection…");
    // Keep the open lesson plan in sync so the REFLEKSI row updates live.
    if (lastPlan && reflectLesson.plan &&
        (lastPlan === reflectLesson.plan || lastPlan.tajuk === reflectLesson.plan.tajuk)) {
      lastPlan.refleksi = text;
    }
    // Auto-save a standalone .md report into output/ (no extra click). The
    // reflection itself is already saved, so a failure here is non-fatal.
    let saved = "";
    try {
      const rr = await fetch("/api/reflection-report", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify(reflectPayload()),
      });
      const rd = await rr.json();
      if (rd && rd.ok) saved = rd.saved || "";
    } catch (e) { /* keep going — the lesson reflection is saved regardless */ }
    toast("Reflection saved into the lesson plan ✓" + (saved ? " — report written to " + saved : ""));
    closeReflectModal();
  } catch (e) { toast(e.message, true); }
}

// #2 Adaptive remediation — generate an easier worksheet focused on the weak areas.
async function generateRemedial() {
  if (!reflectLesson) return;
  const inp = Object.assign({}, reflectLesson.inputs || {});
  const weak = [$("reflect-score").value, $("reflect-quick") ? $("reflect-quick").value : "", $("reflect-results").value]
    .filter(Boolean).join(". ");
  inp.nota_guru = "REMEDIAL worksheet: generate EASIER questions (mostly LOTS/MOTS, no HOTS) focusing ONLY on the areas pupils struggled with. Class results/notes: " + (weak || "general support");
  inp.worksheet = { bil_soalan: 6, lots: 60, mots: 40, hots: 0 };
  try {
    const data = await api("/api/generate-worksheet", inp, "Generating remedial worksheet…");
    lastWorksheet = data.worksheet; lastContext = data.konteks; lastInputs = inp; lastPlan = reflectLesson.plan;
    renderWorksheet(lastWorksheet);
    closeReflectModal(); closeLibrary(); goto(3);
    toast("🎯 Remedial worksheet ready — review and distribute it.");
  } catch (e) { toast(e.message, true); }
}

// #3 Differentiated learning (Agent 5) — decide a worksheet LEVEL per pupil from
// their cumulative performance, generate one worksheet per level, and (fully
// automatic) post each level to its own pupils in Google Classroom.
const BANDS = ["remedial", "core", "extension"];
const BAND_CEFR = { remedial: "A2", core: "B1", extension: "B1+" };
const BAND_COLOR = { remedial: "#e57373", core: "#64b5f6", extension: "#81c784" };

function diffBasePayload() {
  const className = (reflectLesson.plan && reflectLesson.plan.tingkatan_kelas) || "";
  const inp = reflectLesson.inputs || {};
  // Pitch differentiation to the class's Form. Prefer the saved input; else
  // derive it from the class name digit (e.g. "4 Bestari" -> 4); else default 3.
  let form = inp.form;
  if (!form) { const m = String(className).match(/\b([1-5])\b/); form = m ? Number(m[1]) : 3; }
  return Object.assign({}, inp, {
    class_name: className,
    form: form,
    plan: reflectLesson.plan,
    worksheet: Object.assign({ bil_soalan: 10 },
      (inp && inp.worksheet) || {}),
  });
}

// Step 1: ask Agent 5 to PROPOSE a level per pupil (nothing generated/posted yet),
// then show an editable table so the teacher can override before distributing.
async function differentiateAndDistribute() {
  if (!reflectLesson) return;
  const className = (reflectLesson.plan && reflectLesson.plan.tingkatan_kelas) || "";
  if (!className) return toast("This lesson has no class set, so pupils can't be matched.", true);
  const out = $("diff-output");
  try {
    const payload = Object.assign(diffBasePayload(), { decide_only: true });
    const d = await api("/api/differentiate", payload,
      "Agent 5: reading performance & proposing levels…");
    if (!d.ok) { if (out) { out.classList.remove("hidden"); out.innerHTML = "⚠️ " + esc(d.error || "Could not differentiate."); } return; }
    const rows = (d.assignments || []).map((a) => {
      const sel = "<select data-emel='" + esc(a.emel) + "' class='diff-band " + esc(a.band) + "'>" +
        BANDS.map((b) => "<option value='" + b + "'" + (b === a.band ? " selected" : "") +
          ">" + b + " (" + BAND_CEFR[b] + ")</option>").join("") + "</select>";
      const pct = a.purata != null ? a.purata : 0;
      const avg = a.purata != null
        ? "<span class='diff-avg'>" + a.purata + "%<span class='diff-bar'><i style='width:"
          + Math.max(4, Math.min(100, pct)) + "%;background:var(--" + esc(a.band) + ")'></i></span></span>"
        : "—";
      return "<tr><td>" + esc(a.nama || a.emel) + "</td>"
        + "<td style='text-align:right'>" + avg + "</td>"
        + "<td>" + sel + "</td>"
        + "<td class='why'>" + esc(a.sebab || "") + "</td></tr>";
    }).join("");
    if (out) {
      out.classList.remove("hidden");
      out.innerHTML =
        "<h4>🧩 Proposed levels</h4>"
        + "<p class='diff-ringkasan'>" + esc(d.ringkasan || "") + "</p>"
        + "<p class='diff-hint'>Agent 5's suggestion — change any pupil's level, then post.</p>"
        + "<table class='g-table'><tr><th>Pupil</th><th style='text-align:right'>Average</th><th>Level</th><th>Why</th></tr>"
        + rows + "</table>"
        + "<div class='actions' style='justify-content:flex-start;margin-top:8px'>"
        + "<button id='btn-diff-post' class='primary'>✅ Generate & post to Classroom</button></div>";
      const pb = $("btn-diff-post"); if (pb) pb.onclick = postDifferentiation;
      // Keep the dropdown colour in sync when the teacher changes a level.
      document.querySelectorAll("#diff-output .diff-band").forEach((s) => {
        s.onchange = () => { s.className = "diff-band " + s.value; };
      });
    }
  } catch (e) { toast(e.message, true); }
}

// Step 2: read the (possibly edited) levels, then generate one worksheet per
// level and post each to its own pupils.
async function postDifferentiation() {
  if (!reflectLesson) return;
  const out = $("diff-output");
  const className = (reflectLesson.plan && reflectLesson.plan.tingkatan_kelas) || "";
  const assignments = Array.from(document.querySelectorAll(".diff-band")).map((s) => ({
    emel: s.getAttribute("data-emel"), band: s.value,
  }));
  try {
    const payload = Object.assign(diffBasePayload(), { assignments });
    const d = await api("/api/differentiate", payload,
      "Generating a worksheet per level & posting to Classroom…");
    if (!d.ok) { toast(d.error || "Could not distribute.", true); return; }
    const dist = d.distribute || {};
    let distMsg = "";
    if (dist.ok) {
      const per = (dist.bands || []).map((b) =>
        "<div class='row'><span class='dot' style='background:var(--" + esc(b.band) + ")'></span> "
        + esc(b.band) + " (" + esc(b.cefr) + "): " + (b.count || 0) + " pupil(s)"
        + (b.link ? " — <a href='" + esc(b.link) + "' target='_blank'>open in Classroom ↗</a>" : "") + "</div>").join("");
      distMsg = "<div class='diff-posted'><b>✅ Posted to " + esc(dist.course || className) + "</b>" + per
        + ((dist.unmatched && dist.unmatched.length) ? "<div class='unmatched'>Not on roster: " + esc(dist.unmatched.join(", ")) + "</div>" : "") + "</div>";
      toast("🧩 Differentiated worksheets posted to Google Classroom ✓");
    } else {
      distMsg = "<div class='diff-posted' style='background:none;padding:0'>ℹ️ " + esc(dist.error || "Not posted.")
        + (dist.dry_run ? " <b style='color:inherit'>(preview only — levels decided & worksheets generated, nothing sent)</b>" : "") + "</div>";
      toast(dist.dry_run ? "Worksheets generated (preview) — Google not set up, nothing posted." : "Posting failed.", true);
    }
    const bands = (d.bands || []).map((b) =>
      "<li><span class='pill " + esc(b.band) + "'>" + esc(b.band) + " · " + esc(b.cefr) + "</span>"
      + "<span class='meta'>" + b.bil_murid + " pupil(s) · "
      + ((b.worksheet && b.worksheet.jumlah_soalan) || "?") + " questions</span></li>").join("");
    if (out) out.innerHTML =
      "<h4>🧩 Differentiation done</h4>"
      + "<p class='diff-ringkasan'>" + esc(d.ringkasan || "") + "</p>"
      + (bands ? "<ul class='diff-list'>" + bands + "</ul>" : "") + distMsg;
  } catch (e) { toast(e.message, true); }
}

// ---- Standalone report file (.md) + email the report ----
// Gather everything the report needs: the edited reflection, the class report,
// the score/notes, and the fetched per-pupil results (if any).
function reflectPayload() {
  const r = (reflectLesson && reflectLesson._results) || {};
  return {
    plan: reflectLesson.plan,
    refleksi: $("reflect-edit") ? $("reflect-edit").value.trim() : (reflectLesson._refleksi || ""),
    report: reflectLesson._report || "",
    score: $("reflect-score").value.trim(),
    results: $("reflect-results").value.trim(),
    respondents: r.respondents || "",
    weakest: r.weakest || [],
    per_student: r.per_student || [],
    school: (profile && profile.school) || "",
  };
}

async function downloadReport() {
  if (!reflectLesson) return;
  try {
    // The server saves a copy into output/ and returns the Markdown text,
    // which we also hand to the browser as a download.
    const data = await api("/api/reflection-report", reflectPayload(), "Building report…");
    const blob = new Blob([data.markdown || ""], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = data.filename || "reflection.md";
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast("Report saved to " + (data.saved || "output/") + " and downloaded ✓");
  } catch (e) { toast(e.message, true); }
}

async function emailReport() {
  if (!reflectLesson) return;
  const to = $("reflect-email") ? $("reflect-email").value.trim() : "";
  if (to.indexOf("@") < 0) return toast("Enter a recipient email address first.", true);
  try {
    const payload = reflectPayload(); payload.to = to;
    const data = await api("/api/email-reflection", payload, "Emailing report…");
    if (data.ok) toast("Report emailed to " + to + " ✓");
    else toast(data.error || "Could not send the email.", true);
  } catch (e) { toast(e.message, true); }
}

// ====================== Agent 6: Reminder (non-submitters) ======================
function openRemindModal() {
  // Pre-fill the class from the current lesson / profile if we have one.
  const cls = (lastPlan && lastPlan.tingkatan_kelas) ||
    (reflectLesson && reflectLesson.plan && reflectLesson.plan.tingkatan_kelas) || "";
  if (cls && !$("remind-class").value) $("remind-class").value = cls;
  if (profile && profile.email && !$("remind-teacher").value) $("remind-teacher").value = profile.email;
  if (profile && profile.teacher && !$("remind-name").value) $("remind-name").value = profile.teacher;
  $("remind-output").classList.add("hidden");
  $("remind-output").innerHTML = "";
  $("btn-do-remind").classList.add("hidden");   // send only unlocks after a preview
  $("remind-modal").classList.remove("hidden");
}
function closeRemindModal() { $("remind-modal").classList.add("hidden"); }

// These emails go to real pupils, so the teacher previews them first: the
// Preview run drafts the messages without sending or counting a reminder,
// and only then does the Send button appear.
async function runRemind(dryRun) {
  const className = $("remind-class").value.trim();
  if (!className) return toast("Enter the class first.", true);
  const out = $("remind-output");
  const arasColor = { gentle: "#7fce9a", firm: "#f0b45a", notify_teacher: "#f39a94" };
  const arasLabel = { gentle: "gentle nudge", firm: "firmer", notify_teacher: "see them in person" };
  try {
    const d = await api("/api/remind", {
      class_name: className,
      coursework_title: $("remind-title").value.trim(),
      teacher_email: $("remind-teacher").value.trim(),
      teacher_name: $("remind-name").value.trim(),
      dry_run: !!dryRun,
    }, dryRun ? "Agent 6: checking Classroom & drafting messages…"
              : "Agent 6: sending the nudges…");
    if (!d.ok) {
      out.classList.remove("hidden");
      out.innerHTML = "⚠️ " + esc(d.error || "Could not run reminders.");
      $("btn-do-remind").classList.add("hidden");
      return;
    }
    const rows = (d.reminders || []).map((r) =>
      "<tr><td>" + esc(r.nama || r.emel) + "</td>"
      + "<td><b style='color:" + (arasColor[r.aras] || "#888") + "'>" + esc(arasLabel[r.aras] || r.aras || "") + "</b></td>"
      + "<td>" + (r.hantar ? (d.dry_run ? "✏️ draft" : (r.sent ? "✅ sent" : "⚠️ " + esc(r.error || "failed"))) : "— skipped") + "</td>"
      + "<td style='font-size:.85em;opacity:.85;white-space:pre-wrap'>" + esc(r.mesej || "") + "</td></tr>").join("");
    out.classList.remove("hidden");
    out.innerHTML =
      "<h4 style='margin:.2em 0'>" + esc(d.ringkasan || "") + "</h4>"
      + "<p class='muted small'>" + esc(d.coursework || "") + (d.overdue_days ? " · " + d.overdue_days + " day(s) overdue" : "") + "</p>"
      + (rows ? "<table class='g-table'><tr><th>Pupil</th><th>Tone</th><th>Status</th><th>Message</th></tr>" + rows + "</table>" : "");

    const anyToSend = (d.reminders || []).some((r) => r.hantar);
    if (d.dry_run) {
      $("btn-do-remind").classList.toggle("hidden", !anyToSend);
      toast(anyToSend ? "Read the drafts, then press “Send these to pupils”."
                      : "Nothing to send — " + esc(d.ringkasan || "everyone submitted."));
    } else {
      $("btn-do-remind").classList.add("hidden");
      if (d.sent) toast("⏰ " + d.sent + " reminder email(s) sent.");
      else toast("No reminders sent — " + esc(d.ringkasan || "everyone submitted."));
    }
  } catch (e) { toast(e.message, true); }
}
const previewRemind = () => runRemind(true);
const doRemind = () => runRemind(false);

// ====================== #5 CEFR progress dashboard ======================
async function openProgress() {
  $("progress-modal").classList.remove("hidden");
  $("progress-body").innerHTML = '<p class="muted small">Loading…</p>';
  try {
    const data = await (await fetch("/api/progress")).json();
    $("progress-body").innerHTML = renderProgress(data.items || []);
  } catch (e) { $("progress-body").innerHTML = '<p class="warn">Failed to load progress.</p>'; }
}
function closeProgress() { $("progress-modal").classList.add("hidden"); }
function renderProgress(items) {
  if (!items.length) {
    return '<p class="muted small">No scored lessons yet. Use <b>Reflect</b> on a lesson and enter the class score (%) — your progress chart builds itself.</p>';
  }
  const byClass = {};
  items.forEach((it) => { (byClass[it.kelas || "—"] = byClass[it.kelas || "—"] || []).push(it); });
  return Object.keys(byClass).sort().map((cls) => {
    const pts = byClass[cls];
    const avg = Math.round(pts.reduce((s, p) => s + (+p.score || 0), 0) / pts.length);
    const cefr = avg >= 75 ? "B1+" : avg >= 55 ? "B1" : avg >= 40 ? "B1 Low" : "A2+";
    const bars = pts.map((p) => {
      const v = Math.round(+p.score || 0);
      return `<div class="pg-bar" title="${esc(p.tarikh)}: ${v}%"><span style="height:${Math.max(4, v)}px"></span><em>${v}</em></div>`;
    }).join("");
    return `<div class="pg-class"><div class="pg-head"><b>${esc(cls)}</b> · avg ${avg}% · ~${cefr} CEFR <span class="muted">(${pts.length} quizzes)</span></div><div class="pg-chart">${bars}</div></div>`;
  }).join("");
}

// ====================== #6 One-tap prepare from timetable ======================
// (Auto-fill/banner logic now lives in loadProfile/applySlot near the top.)

// Re-populate the setup form from a saved lesson's inputs (for Duplicate).
function restoreInputs(inp) {
  const set = (id, v) => { if ($(id) && v != null) $(id).value = v; };
  set("minggu", inp.minggu); set("nama_kelas", inp.nama_kelas); set("tarikh", inp.tarikh);
  fillDay(); set("hari", inp.hari); set("masa", inp.masa); set("tempoh", inp.tempoh);
  set("bil_murid", inp.bil_murid); set("tahap_murid", inp.tahap_murid);
  set("theme", inp.theme); set("topic", inp.topic);
  if (inp.bidang_kod) { $("bidang").value = inp.bidang_kod; buildContentStandards(); }
  if (inp.sk_kod) { $("sk").value = inp.sk_kod; buildLearningStandards(); }
  (inp.sp_kods || []).forEach((k) => {
    const cb = document.querySelector('#sp-list input[value="' + k + '"]');
    if (cb) cb.checked = true;
  });
  setChips($("strategi"), inp.strategi || []);
  setChips($("emk"), inp.emk || []);
  set("kbat", inp.kbat);
  const w = inp.worksheet || {};
  set("bil_soalan", w.bil_soalan); set("lots", w.lots); set("mots", w.mots); set("hots", w.hots);
  checkLevels();
}
function setChips(container, values) {
  if (!container) return;
  const vset = new Set(values);
  [...container.querySelectorAll(".chip")].forEach((c) => c.classList.toggle("on", vset.has(c.textContent)));
}

// ====================== Textbook reader ======================
// Form 1/2/5 are PDFs served by the backend; Form 3/4 are link-only (hosted
// flipbook) — see /api/textbook-list and TEXTBOOK_SOURCES in server.py.
let textbookMeta = null;
async function loadTextbookMeta() {
  if (textbookMeta) return textbookMeta;
  try {
    const res = await fetch("/api/textbook-list");
    if (res.ok) textbookMeta = (await res.json()).forms || [];
  } catch (e) {}
  return textbookMeta || [];
}

function textbookShowPicker() {
  $("textbook-title-text").textContent = "Textbook";
  $("textbook-picker").classList.remove("hidden");
  $("textbook-missing").classList.add("hidden");
  $("textbook-frame").classList.add("hidden");
  $("textbook-open-link").classList.add("hidden");
  $("btn-textbook-back").classList.add("hidden");
}

async function openTextbookModal() {
  $("textbook-modal").classList.remove("hidden");
  textbookShowPicker();
  await loadTextbookMeta();
}

async function selectTextbookForm(form) {
  const meta = (await loadTextbookMeta()).find((m) => m.form === String(form));
  if (!meta || meta.type === "missing") return;
  if (meta.type === "link") {
    window.open(meta.url, "_blank", "noopener"); // hosted flipbook — stays on the picker
    return;
  }
  $("textbook-picker").classList.add("hidden");
  $("btn-textbook-back").classList.remove("hidden");
  await showTextbookPdf(form, meta);
}

async function showTextbookPdf(form, meta) {
  const frame = $("textbook-frame");
  const missing = $("textbook-missing");
  const link = $("textbook-open-link");
  const url = `/textbook.pdf?form=${form}`;
  $("textbook-title-text").textContent = meta.label || `Textbook — Form ${form}`;
  link.href = url;
  link.classList.remove("hidden");
  missing.classList.add("hidden");
  frame.classList.add("hidden");
  if (!meta.available) {
    missing.textContent = `Buku teks ${meta.label || "Form " + form} belum dimuat naik ke dalam sistem. Sila hubungi admin.`;
    missing.classList.remove("hidden");
    return;
  }
  if (frame.dataset.loadedForm === String(form)) {
    frame.classList.remove("hidden");
    return;
  }
  frame.removeAttribute("src");
  frame.dataset.loadedForm = "";
  try {
    const res = await fetch(url);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      missing.textContent = data.mesej || `Buku teks Form ${form} belum dimuat naik ke sistem.`;
      missing.classList.remove("hidden");
      return;
    }
    const blob = await res.blob();
    frame.src = URL.createObjectURL(blob);
    frame.dataset.loadedForm = String(form);
    frame.classList.remove("hidden");
  } catch (e) {
    missing.textContent = "Tidak dapat memuatkan buku teks. Sila cuba lagi.";
    missing.classList.remove("hidden");
  }
}

// ====================== Question bank (read-only browse) ======================
let bankViewTimer;
async function loadBankView(q) {
  const tbody = $("bank-view-body");
  tbody.innerHTML = `<tr><td colspan="3" class="muted small">Loading…</td></tr>`;
  let data;
  try {
    data = await (await fetch("/api/bank-list?q=" + encodeURIComponent(q || ""))).json();
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" class="muted small">Could not load the question bank.</td></tr>`;
    return;
  }
  const rows = data.questions || [];
  $("bank-view-count").textContent = data.stats && data.stats.jumlah != null ? data.stats.jumlah + " total" : "";
  tbody.innerHTML = rows.length
    ? rows.map((r) => `<tr><td>${esc(r.soalan)}</td><td>${esc(r.sp_kod)}</td><td>${esc(r.aras)}</td></tr>`).join("")
    : `<tr><td colspan="3" class="muted small">No questions match.</td></tr>`;
}

function openBankModal() {
  $("bank-modal").classList.remove("hidden");
  $("bank-view-search").value = "";
  loadBankView("");
}

// ====================== Navigation & events ======================
function wireEvents() {
  ["lots", "mots", "hots"].forEach((id) => $(id).addEventListener("input", checkLevels));
  $("tarikh").addEventListener("change", fillDay);
  $("btn-gen-rph").onclick = () => genLessonPlan();
  $("btn-back-1").onclick = () => goto(1);
  $("btn-regen-rph").onclick = () => genLessonPlan($("nota-rph").value.trim());
  $("btn-export").onclick = toggleExportMenu;
  $("btn-export-pdf").onclick = () => { closeExportMenu(); printPlan(); };
  $("btn-export-doc").onclick = () => { closeExportMenu(); exportPlanDoc(); };
  $("btn-export-docx").onclick = () => { closeExportMenu(); exportPlanDocx(); };
  if ($("btn-drive-rph")) $("btn-drive-rph").onclick = openDriveModal;
  $("btn-print-rph").onclick = printPlan;
  $("btn-copy-drive").onclick = copyDriveScript;
  $("btn-dl-drive").onclick = downloadDriveScript;
  $("btn-close-drive").onclick = closeDriveModal;
  document.addEventListener("click", closeExportMenu);
  $("btn-approve-rph").onclick = () => genMaterials();
  // Step 3 — Teaching Materials
  $("btn-back-mat").onclick = () => goto(2);
  $("btn-regen-mat").onclick = () => genMaterials($("nota-mat").value.trim());
  const lo = $("btn-logout");
  if (lo) lo.onclick = async () => {
    try { await fetch("/api/logout", { method: "POST" }); } catch (e) {}
    location.href = "/login.html";
  };
  if ($("btn-dl-mat")) $("btn-dl-mat").onclick = downloadMaterials;
  if ($("btn-dl-pptx")) $("btn-dl-pptx").onclick = exportSlidesPptx;
  if ($("btn-gamma")) $("btn-gamma").onclick = createWithGamma;
  if ($("btn-direct-ws")) $("btn-direct-ws").onclick = directWorksheet;
  if ($("btn-direct-rph")) $("btn-direct-rph").onclick = directLessonPlan;
  if ($("btn-direct-mat")) $("btn-direct-mat").onclick = directMaterials;
  if ($("btn-textbook")) $("btn-textbook").onclick = openTextbookModal;
  if ($("btn-textbook-back")) $("btn-textbook-back").onclick = textbookShowPicker;
  document.querySelectorAll(".textbook-pick").forEach((btn) =>
    btn.addEventListener("click", () => selectTextbookForm(btn.dataset.form)));
  if ($("sb-bank")) $("sb-bank").onclick = openBankModal;
  if ($("btn-close-bank")) $("btn-close-bank").onclick = () => $("bank-modal").classList.add("hidden");
  if ($("bank-view-search")) $("bank-view-search").addEventListener("input", (e) => {
    clearTimeout(bankViewTimer);
    bankViewTimer = setTimeout(() => loadBankView(e.target.value), 250);
  });
  if ($("btn-close-textbook")) $("btn-close-textbook").onclick = () =>
    $("textbook-modal").classList.add("hidden");
  $("btn-skip-mat").onclick = () => proceedFromMaterials(false);
  $("btn-use-mat").onclick = () => proceedFromMaterials(true);
  $("btn-back-2").onclick = () => goto(3);
  $("btn-regen-ws").onclick = () => genWorksheet($("nota-ws").value.trim());
  $("btn-approve-ws").onclick = approveAndSave;
  $("btn-google-form").onclick = openFormModal;
  $("btn-dl-rph").onclick = exportPlanDoc;
  $("btn-print-done").onclick = printPlan;
  $("btn-print-ws").onclick = printWorksheet;
  $("btn-dl-ws").onclick = downloadWorksheetJSON;
  $("btn-google-form-done").onclick = openFormModal;
  $("btn-restart").onclick = () => location.reload();
  $("btn-copy-script").onclick = copyFormScript;
  $("btn-dl-script").onclick = downloadFormScript;
  $("btn-close-modal").onclick = closeFormModal;
  ["rcpt-plan", "classroom-class", "due-date", "due-time"].forEach((id) => {
    if ($(id)) $(id).oninput = refreshScript;
  });
  $("btn-library").onclick = openLibrary;
  $("btn-close-library").onclick = closeLibrary;
  $("library-list").onclick = libClick;
  $("library-search").oninput = (e) => loadLessonList(e.target.value);
  $("btn-gen-reflection").onclick = generateReflectionUI;
  $("btn-save-reflection").onclick = saveReflectionUI;
  $("btn-close-reflect").onclick = closeReflectModal;
  if ($("btn-get-results")) $("btn-get-results").onclick = fetchResults;
  if ($("btn-edit-ctx")) $("btn-edit-ctx").onclick = () => { const c = $("ctx-card"); if (c) c.classList.toggle("hidden"); };
  // Header ☰ menu: click/tap toggles; hover handled by CSS; closes on outside click or item pick.
  const tm = $("tools-menu"), tt = $("tools-trigger");
  if (tm && tt) {
    tt.onclick = (e) => { e.stopPropagation(); tm.classList.toggle("open"); };
    document.addEventListener("click", (e) => { if (!tm.contains(e.target)) tm.classList.remove("open"); });
    tm.querySelectorAll(".pop-item").forEach((b) => b.addEventListener("click", () => tm.classList.remove("open")));
  }
  $("btn-progress").onclick = openProgress;
  $("btn-close-progress").onclick = closeProgress;
  if ($("btn-remind")) $("btn-remind").onclick = openRemindModal;
  if ($("btn-preview-remind")) $("btn-preview-remind").onclick = previewRemind;
  if ($("btn-do-remind")) $("btn-do-remind").onclick = doRemind;
  if ($("btn-close-remind")) $("btn-close-remind").onclick = closeRemindModal;
}

function checkLevels() {
  const sum = +$("lots").value + +$("mots").value + +$("hots").value;
  $("aras-warn").classList.toggle("hidden", sum === 100);
  $("btn-gen-rph").disabled = sum !== 100;
}

const PANELS = { 1: "panel-orchestrator", 2: "panel-rph", 3: "panel-materials", 4: "panel-worksheet", 5: "panel-done" };
function goto(step) {
  Object.values(PANELS).forEach((id) => $(id).classList.remove("active"));
  $(PANELS[step]).classList.add("active");
  document.querySelectorAll(".steps li").forEach((li) => {
    const s = +li.dataset.step;
    li.classList.toggle("active", s === step);
    li.classList.toggle("done", s < step);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
  positionAgentBot();
}

// Park the idle robot on top of the currently active step. Skipped while it's
// running (working), so the run-across animation covers the whole bar.
function positionAgentBot() {
  const steps = document.querySelector(".steps");
  if (!steps || steps.classList.contains("working")) return;
  const active = steps.querySelector("li.active");
  const bot = steps.querySelector(".agent-bot");
  if (!active || !bot) return;
  const left = active.offsetLeft + active.offsetWidth / 2 - 23;
  bot.style.left = Math.max(2, left) + "px";
}
window.addEventListener("load", positionAgentBot);
window.addEventListener("resize", positionAgentBot);

// ====================== UI utilities ======================
function showOverlay(msg) {
  $("overlay-msg").textContent = msg || "Generating…";
  $("overlay").classList.remove("hidden");
  const steps = document.querySelector(".steps");
  const tracker = document.querySelector(".tracker");
  if (steps) { steps.classList.add("working"); steps.setAttribute("data-msg", msg || "Working…"); }
  if (tracker) tracker.classList.add("working-pin");
}
function hideOverlay() {
  $("overlay").classList.add("hidden");
  const steps = document.querySelector(".steps");
  const tracker = document.querySelector(".tracker");
  if (steps) { steps.classList.remove("working"); steps.removeAttribute("data-msg"); }
  if (tracker) tracker.classList.remove("working-pin");
  positionAgentBot();
}
let toastTimer;
function toast(msg, isErr) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.toggle("err", !!isErr);
  t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 4000);
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function num(n) { return n == null ? "?" : n; }
function slug(s) { return String(s || "class").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, ""); }
