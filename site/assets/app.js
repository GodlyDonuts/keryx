"use strict";

const PAGE_SIZE = 40;
const STORAGE_KEY = "keryx:saved-role-ids:v1";
const categoryLabels = {
  "software": "Software",
  "data-ml": "Data / ML",
  "quant": "Quant",
  "security": "Security",
  "hardware": "Hardware",
  "product-design": "Product / Design",
  "other-tech": "Other tech",
};
const visaLabels = {
  "citizenship-required": "Citizenship / clearance restriction",
  "no-sponsorship": "No sponsorship",
  "sponsorship-available": "Sponsorship stated",
  "unknown": "Not determined",
};
const workplaceLabels = {
  "remote": "Remote stated",
  "hybrid": "Hybrid stated",
  "onsite": "On-site stated",
  "unspecified": "Not stated",
};
const trustLabels = {
  "ats-verified": "Direct ATS · current",
  "cross-source": "Cross-checked · current",
  "platform-structured": "Structured employer platform",
  "unverified": "Destination withheld",
};
const controls = [
  "search", "sort", "program", "cycle", "category", "skill", "workplace", "visa",
  "graduation", "academic", "compensation", "clickable", "saved-only",
];
const state = { jobs: [], filtered: [], visible: PAGE_SIZE, saved: loadSaved() };

function byId(id) { return document.getElementById(id); }

function loadSaved() {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    return new Set(Array.isArray(value) ? value.filter((item) => typeof item === "string") : []);
  } catch (_) {
    return new Set();
  }
}

function persistSaved() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify([...state.saved].sort())); } catch (_) { /* Storage may be disabled. */ }
  byId("saved-count").textContent = `${state.saved.size.toLocaleString()} saved locally`;
}

function addOption(select, value, label = value) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  select.append(option);
}

function fillOptions(id, values, labels = {}) {
  const select = byId(id);
  for (const value of [...values].filter(Boolean).sort((a, b) => a.localeCompare(b))) {
    addOption(select, value, labels[value] || value);
  }
}

function intelligence(job) {
  return job.intelligence && typeof job.intelligence === "object" ? job.intelligence : {};
}

function academic(job) {
  return job.academic_eligibility && typeof job.academic_eligibility === "object"
    ? job.academic_eligibility : {};
}

function initializeFilters() {
  const cycles = new Set();
  const categories = new Set();
  const skills = new Set();
  const workplaces = new Set();
  const visas = new Set();
  const years = new Set();
  for (const job of state.jobs) {
    cycles.add(String(job.cycle || "unscheduled"));
    const data = intelligence(job);
    categories.add(String(data.category || "other-tech"));
    if (Array.isArray(data.skills)) data.skills.forEach((skill) => skills.add(String(skill)));
    if (data.workplace?.value) workplaces.add(String(data.workplace.value));
    if (data.visa?.status) visas.add(String(data.visa.status));
    const eligibility = academic(job);
    if (Array.isArray(eligibility.graduation_years)) {
      eligibility.graduation_years.forEach((year) => years.add(String(year)));
    }
  }
  fillOptions("cycle", cycles);
  fillOptions("category", categories, categoryLabels);
  fillOptions("skill", skills);
  fillOptions("workplace", workplaces, workplaceLabels);
  fillOptions("visa", visas, visaLabels);
  fillOptions("graduation", years);
}

function value(id) { return byId(id).value; }
function checked(id) { return byId(id).checked; }

function academicGroup(job) {
  const status = String(academic(job).status || "unavailable");
  return status.startsWith("explicit-") || status === "student-status" ? "detected" : status;
}

function searchable(job) {
  const data = intelligence(job);
  return [job.company, job.title, job.location, job.program, job.cycle, data.category,
    ...(Array.isArray(data.skills) ? data.skills : [])].filter(Boolean).join(" ").toLocaleLowerCase();
}

function matches(job) {
  const query = value("search").trim().toLocaleLowerCase();
  const data = intelligence(job);
  const eligibility = academic(job);
  if (query && !searchable(job).includes(query)) return false;
  if (value("program") && job.program !== value("program")) return false;
  if (value("cycle") && String(job.cycle || "unscheduled") !== value("cycle")) return false;
  if (value("category") && data.category !== value("category")) return false;
  if (value("skill") && !(data.skills || []).includes(value("skill"))) return false;
  if (value("workplace") && data.workplace?.value !== value("workplace")) return false;
  if (value("visa") && data.visa?.status !== value("visa")) return false;
  if (value("graduation") && !(eligibility.graduation_years || []).map(String).includes(value("graduation"))) return false;
  if (value("academic") && academicGroup(job) !== value("academic")) return false;
  if (checked("compensation") && !data.compensation) return false;
  if (checked("clickable") && !job.url) return false;
  if (checked("saved-only") && !state.saved.has(job.id)) return false;
  return true;
}

function compareJobs(a, b) {
  const sort = value("sort");
  if (sort === "company") return String(a.company).localeCompare(String(b.company)) || String(a.title).localeCompare(String(b.title));
  if (sort === "role") return String(a.title).localeCompare(String(b.title)) || String(a.company).localeCompare(String(b.company));
  return String(b.posted_at || b.first_seen || "").localeCompare(String(a.posted_at || a.first_seen || "")) || String(a.company).localeCompare(String(b.company));
}

function createTag(text, kind = "") {
  const tag = document.createElement("span");
  tag.className = `tag${kind ? ` ${kind}` : ""}`;
  tag.textContent = text;
  return tag;
}

function addFact(list, term, detail) {
  if (!detail) return;
  const wrapper = document.createElement("div");
  wrapper.className = "fact";
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = term;
  dd.textContent = detail;
  wrapper.append(dt, dd);
  list.append(wrapper);
}

function academicLabel(eligibility) {
  if (!eligibility.status || eligibility.status === "unavailable") return "Text unavailable";
  if (eligibility.status === "not-found") return "No condition detected";
  const modality = eligibility.requirement_level ? ` · ${eligibility.requirement_level}` : "";
  return `${eligibility.summary || "Condition detected"}${modality}`;
}

function formatTimestamp(value) {
  if (!value) return "unknown";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return String(value);
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", timeZoneName: "short",
  }).format(parsed);
}

function buildCard(job) {
  const card = byId("job-template").content.firstElementChild.cloneNode(true);
  const data = intelligence(job);
  const eligibility = academic(job);
  card.querySelector(".company").textContent = job.company || "Unknown company";
  card.querySelector(".title").textContent = job.title || "Untitled role";
  card.querySelector(".location").textContent = job.location || "Location not stated";

  const tags = card.querySelector(".tags");
  tags.append(createTag(trustLabels[job.link_status] || "Evidence unknown", "trust"));
  tags.append(createTag(categoryLabels[data.category] || "Other tech", "category"));
  for (const skill of (Array.isArray(data.skills) ? data.skills.slice(0, 5) : [])) tags.append(createTag(skill));

  const facts = card.querySelector(".facts");
  addFact(facts, "Program", job.program === "new-grad" ? "New graduate" : "Internship");
  addFact(facts, "Cycle", job.cycle === "unscheduled" ? "Not stated" : job.cycle);
  addFact(facts, "Workplace", workplaceLabels[data.workplace?.value] || "Not stated");
  addFact(facts, "Visa language", visaLabels[data.visa?.status] || "Not determined");
  addFact(facts, "Compensation", data.compensation?.summary || "Not stated");
  const currentSources = Array.isArray(job.current_source_ids) ? job.current_source_ids.length : 0;
  const historicalSources = Array.isArray(job.historical_source_ids) ? job.historical_source_ids.length : 0;
  addFact(facts, "Source evidence", `${currentSources} current${historicalSources ? ` · ${historicalSources} historical` : ""}`);

  const academicDetail = card.querySelector(".academic-detail");
  const academicTitle = document.createElement("strong");
  academicTitle.textContent = "Academic evidence";
  const academicText = document.createElement("span");
  academicText.textContent = academicLabel(eligibility);
  academicDetail.append(academicTitle, academicText);
  academicDetail.hidden = false;

  const dates = card.querySelector(".dates");
  const posted = job.posted_at ? `Posted ${job.posted_at}` : "Posting date unavailable";
  dates.textContent = `${posted} · first detected ${formatTimestamp(job.first_seen_at || job.first_seen)}`;

  const apply = card.querySelector(".apply");
  const withheld = card.querySelector(".withheld");
  if (job.url) {
    apply.href = job.url;
    apply.setAttribute("aria-label", `Apply to ${job.title} at ${job.company}; opens employer site`);
  } else {
    apply.hidden = true;
    withheld.hidden = false;
    withheld.title = "Keryx did not have enough evidence to publish this destination safely.";
  }

  const save = card.querySelector(".save");
  const updateSave = () => {
    const isSaved = state.saved.has(job.id);
    save.setAttribute("aria-pressed", String(isSaved));
    save.setAttribute("aria-label", `${isSaved ? "Remove" : "Save"} ${job.title} at ${job.company}`);
    save.title = isSaved ? "Remove saved role" : "Save locally";
  };
  updateSave();
  save.addEventListener("click", () => {
    if (state.saved.has(job.id)) state.saved.delete(job.id); else state.saved.add(job.id);
    persistSaved();
    updateSave();
    if (checked("saved-only")) applyFilters();
  });
  return card;
}

function render() {
  const results = byId("results");
  results.replaceChildren();
  const visible = state.filtered.slice(0, state.visible);
  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No opportunities match these filters. Try broadening your search.";
    results.append(empty);
  } else {
    const fragment = document.createDocumentFragment();
    visible.forEach((job) => fragment.append(buildCard(job)));
    results.append(fragment);
  }
  results.setAttribute("aria-busy", "false");
  byId("result-count").textContent = `Showing ${visible.length.toLocaleString()} of ${state.filtered.length.toLocaleString()} matching roles`;
  const showMore = byId("show-more");
  showMore.hidden = visible.length >= state.filtered.length;
  if (!showMore.hidden) showMore.textContent = `Show ${Math.min(PAGE_SIZE, state.filtered.length - visible.length)} more roles`;
}

function activeFilterCount() {
  return controls.filter((id) => id !== "sort" && (byId(id).type === "checkbox" ? checked(id) : Boolean(value(id)))).length;
}

function applyFilters() {
  state.visible = PAGE_SIZE;
  state.filtered = state.jobs.filter(matches).sort(compareJobs);
  const count = activeFilterCount();
  byId("active-filter-count").textContent = count ? `· ${count} active` : "";
  render();
}

function resetFilters() {
  for (const id of controls) {
    const control = byId(id);
    if (control.type === "checkbox") control.checked = false;
    else control.value = id === "sort" ? "newest" : "";
  }
  applyFilters();
}

async function start() {
  try {
    const response = await fetch("api/jobs.json", { cache: "no-cache", credentials: "omit" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    if (!Array.isArray(payload.jobs)) throw new Error("Invalid jobs payload");
    const health = await fetch("api/source-health.json", {
      cache: "no-cache", credentials: "omit",
    }).then((result) => result.ok ? result.json() : null).catch(() => null);
    state.jobs = payload.jobs;
    byId("metric-roles").textContent = state.jobs.length.toLocaleString();
    byId("metric-companies").textContent = new Set(state.jobs.map((job) => job.company).filter(Boolean)).size.toLocaleString();
    const sourceRecords = health?.sources && typeof health.sources === "object"
      ? Object.values(health.sources) : [];
    byId("metric-sources").textContent = sourceRecords.filter((source) => source?.outcome === "complete").length.toLocaleString();
    byId("metric-updated").textContent = health?.generated_at
      ? formatTimestamp(health.generated_at) : "Not recorded yet";
    initializeFilters();
    persistSaved();
    applyFilters();
  } catch (error) {
    console.error("Keryx data load failed", error);
    byId("results").setAttribute("aria-busy", "false");
    byId("result-count").textContent = "Opportunity index unavailable";
    byId("load-error").hidden = false;
  }
}

for (const id of controls) byId(id).addEventListener(id === "search" ? "input" : "change", applyFilters);
byId("reset-filters").addEventListener("click", resetFilters);
byId("show-more").addEventListener("click", () => { state.visible += PAGE_SIZE; render(); });
document.addEventListener("keydown", (event) => {
  if (event.key === "/" && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName)) {
    event.preventDefault();
    byId("search").focus();
  }
});

start();
