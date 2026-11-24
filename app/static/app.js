/**
 * Routine Maker Frontend Application
 * Vanilla JS interacting with FastAPI backend.
 */

// Application State
const state = {
  activeTab: "home",
  teachers: [],
  courses: [],
  batches: [],
  assignments: [],
  rooms: [],
  showOnLeave: false,
  editingTeacherId: null,
  editingCourseId: null,
  editingRoomId: null,
  activeBulkEntity: "all",
  timeGridConfig: null,
  timeGridComputed: null,
};

// Curriculum Order Canonical Array
const CURRICULUM_ORDER = ["1-1", "1-2", "2-1", "2-2", "3-1", "3-2", "4-1", "4-2"];

function curriculumSortKey(batchId) {
  const idx = CURRICULUM_ORDER.indexOf(batchId);
  return idx === -1 ? 999 : idx;
}

// -----------------------------------------------------------------------------
// Initialization
// -----------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  setupNavigation();
  setupEventListeners();
  loadAllData();
});

function setupNavigation() {
  document.querySelectorAll(".nav-tab").forEach((tabBtn) => {
    tabBtn.addEventListener("click", () => {
      const tabId = tabBtn.getAttribute("data-tab");
      switchTab(tabId);
    });
  });
}

function switchTab(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll(".nav-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-tab") === tabId);
  });
  document.querySelectorAll(".tab-content").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${tabId}`);
  });

  if (tabId === "home") {
    renderHomeDashboard();
  } else if (tabId === "teachers") {
    loadTeachers();
  } else if (tabId === "courses") {
    loadCourses();
  } else if (tabId === "rooms") {
    loadRooms();
  } else if (tabId === "assignments") {
    loadAssignmentsData();
  } else if (tabId === "master") {
    loadMasterRoutine();
  } else if (tabId === "timeslots") {
    loadTimeGrid();
  } else if (tabId === "generate") {
    checkLatestRoutine();
  }
}

function setupEventListeners() {
  // Teachers filters
  document.getElementById("teacher-search-input")?.addEventListener("input", renderTeachers);
  document.getElementById("teacher-dept-select")?.addEventListener("change", renderTeachers);
  document.getElementById("teacher-status-select")?.addEventListener("change", renderTeachers);
  document.getElementById("btn-add-teacher")?.addEventListener("click", () => openTeacherModal());

  // Courses filters
  document.getElementById("course-search-input")?.addEventListener("input", renderCourses);
  document.getElementById("course-batch-select")?.addEventListener("change", renderCourses);
  document.getElementById("course-category-select")?.addEventListener("change", renderCourses);
  document.getElementById("course-status-select")?.addEventListener("change", renderCourses);
  document.getElementById("btn-add-course")?.addEventListener("click", () => openCourseModal());

  // Assignments filters
  document.getElementById("assign-batch-select")?.addEventListener("change", () => {
    populateAssignCourseDropdown();
    renderAssignments();
  });
  document.getElementById("assign-course-select")?.addEventListener("change", renderAssignments);
  document.getElementById("assign-search-input")?.addEventListener("input", renderAssignments);
  document.getElementById("chk-show-on-leave")?.addEventListener("change", (e) => {
    state.showOnLeave = e.target.checked;
    renderAssignments();
  });

  // Generate Routine
  document.getElementById("btn-generate-routine")?.addEventListener("click", handleGenerateRoutine);
}

async function loadAllData() {
  await Promise.all([loadBatches(), loadTeachers(), loadCourses(), loadRooms(), loadAssignments(), loadTimeGrid()]);
  renderHomeDashboard();
}

// -----------------------------------------------------------------------------
// Home Dashboard Live Snapshot Renderer
// -----------------------------------------------------------------------------

function renderHomeDashboard() {
  // 1. Teachers KPI
  const totalTeachers = state.teachers.length;
  const activeTeachers = state.teachers.filter((t) => t.status === "active").length;
  const onLeaveTeachers = totalTeachers - activeTeachers;
  const tVal = document.getElementById("home-stat-teachers");
  const tSub = document.getElementById("home-stat-teachers-sub");
  if (tVal) tVal.textContent = `${totalTeachers}`;
  if (tSub) {
    tSub.textContent = onLeaveTeachers > 0
      ? `${activeTeachers} Active • ${onLeaveTeachers} On Leave`
      : `${activeTeachers} Active faculty members`;
  }

  // 2. Courses & Active Batches KPI
  const totalCourses = state.courses.length;
  const sortedBatches = [...state.batches].sort((a, b) => curriculumSortKey(a.id) - curriculumSortKey(b.id));
  const activeBatches = sortedBatches.filter((b) => b.status === "on");
  const cVal = document.getElementById("home-stat-courses");
  const cSub = document.getElementById("home-stat-courses-sub");
  if (cVal) cVal.textContent = `${totalCourses}`;
  if (cSub) {
    cSub.textContent = `${activeBatches.length} of ${sortedBatches.length || 8} terms currently ON`;
  }

  // Active terms pills in Hero Snapshot card
  const termsContainer = document.getElementById("home-active-terms");
  if (termsContainer) {
    if (activeBatches.length > 0) {
      termsContainer.innerHTML = activeBatches
        .map((b) => `<span class="term-pill">● ${escapeHtml(b.id)}</span>`)
        .join("");
    } else if (sortedBatches.length > 0) {
      termsContainer.innerHTML = `<span class="term-pill term-pill-off">No terms active (all OFF)</span>`;
    }
  }

  // 3. Rooms & Labs KPI
  const totalRooms = state.rooms.length;
  const theoryRooms = state.rooms.filter((r) => r.kind === "theory" || r.kind === "seminar_501").length;
  const labRooms = totalRooms - theoryRooms;
  const rVal = document.getElementById("home-stat-rooms");
  const rSub = document.getElementById("home-stat-rooms-sub");
  if (rVal) rVal.textContent = `${totalRooms}`;
  if (rSub) rSub.textContent = `${theoryRooms} Theory • ${labRooms} Laboratories`;

  // 4. Department Time Grid KPI & Hero Status
  const comp = state.timeGridComputed;
  const sVal = document.getElementById("home-stat-slots");
  const sSub = document.getElementById("home-stat-slots-sub");
  const winEl = document.getElementById("home-schedule-window");
  const metaEl = document.getElementById("home-schedule-meta");

  if (comp) {
    const ppd = comp.periods_per_day || 9;
    const dur = comp.period_duration_minutes || 50;
    const daysArr = comp.days || ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"];
    const shortDays = daysArr.length >= 2
      ? `${daysArr[0].slice(0, 3)}–${daysArr[daysArr.length - 1].slice(0, 3)}`
      : daysArr.map((d) => d.slice(0, 3)).join(", ");
    const breakCount = (comp.breaks || []).length;

    if (sVal) sVal.textContent = `${ppd} / Day`;
    if (sSub) sSub.textContent = `${dur} min/class • ${breakCount} break(s) • ${daysArr.length} days`;
    if (winEl) winEl.textContent = comp.day_span_formatted || "08:00 AM – 05:00 PM";
    if (metaEl) metaEl.textContent = `${ppd} periods/day • ${dur} min/class • ${shortDays}`;
  }
}

// -----------------------------------------------------------------------------
// Teachers API & Rendering
// -----------------------------------------------------------------------------

async function loadTeachers() {
  try {
    const res = await fetch("/api/teachers");
    if (!res.ok) throw new Error("Failed to load teachers");
    state.teachers = await res.json();
    renderTeachers();
  } catch (err) {
    showToast(`Error loading teachers: ${err.message}`, true);
  }
}

function renderTeachers() {
  const tbody = document.getElementById("teachers-tbody");
  if (!tbody) return;

  const search = (document.getElementById("teacher-search-input")?.value || "").toLowerCase().trim();
  const deptFilter = document.getElementById("teacher-dept-select")?.value || "";
  const statusFilter = document.getElementById("teacher-status-select")?.value || "";

  const filtered = state.teachers.filter((t) => {
    if (deptFilter && t.department !== deptFilter) return false;
    if (statusFilter && t.status !== statusFilter) return false;
    if (search) {
      const matchName = t.full_name.toLowerCase().includes(search);
      const matchCode = t.short_code.toLowerCase().includes(search);
      const matchId = t.id.toLowerCase().includes(search);
      if (!matchName && !matchCode && !matchId) return false;
    }
    return true;
  });

  document.getElementById("teachers-count").textContent = filtered.length;

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">No teachers found matching criteria.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered
    .map((t) => {
      const deptClass = `badge-${t.department.toLowerCase()}`;
      const isActive = t.status === "active";
      const statusBadge = isActive
        ? `<span class="badge badge-active">Active</span>`
        : `<span class="badge badge-leave">On Leave</span>`;

      let availBadge = "";
      if (!isActive) {
        availBadge = `<span class="badge-avail-leave" onclick="openTeacherAvailabilityModal('${t.id}')" title="Teacher on leave (All slots blocked across entire week)">🚫 On Leave</span>`;
      } else if (t.unavailable_count > 0) {
        availBadge = `<button type="button" class="badge-avail-restricted" onclick="openTeacherAvailabilityModal('${t.id}')" title="${escapeHtml(t.unavailable_summary)}">🕒 ${escapeHtml(t.unavailable_summary)}</button>`;
      } else {
        availBadge = `<button type="button" class="badge-avail-free" onclick="openTeacherAvailabilityModal('${t.id}')" title="Full week available. Click to block specific slots.">🕒 Full Week</button>`;
      }

      return `
      <tr>
        <td>
          <div style="font-weight: 600; color: var(--navy-deep);">${escapeHtml(t.full_name)}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted); font-family: monospace;">${escapeHtml(t.id)}</div>
        </td>
        <td><strong style="color: var(--navy);">${escapeHtml(t.short_code)}</strong></td>
        <td><span class="badge ${deptClass}">${escapeHtml(t.department)}</span></td>
        <td>${t.max_periods_per_day} periods/day</td>
        <td>
          <button class="status-toggle" onclick="toggleTeacherStatus('${t.id}', '${t.status}')" title="Click to toggle status (Active / On Leave)">
            ${statusBadge}
          </button>
        </td>
        <td>
          ${availBadge}
        </td>
        <td style="text-align: right; white-space: nowrap;">
          <button class="btn btn-outline btn-sm" onclick="openTeacherAvailabilityModal('${t.id}')" title="Configure custom unavailable slots">🕒 Slots</button>
          <button class="btn btn-outline btn-sm" onclick="openTeacherModal('${t.id}')">Edit</button>
          <button class="btn btn-danger-outline btn-sm" onclick="deleteTeacher('${t.id}')">Delete</button>
        </td>
      </tr>
    `;
    })
    .join("");
}

async function toggleTeacherStatus(teacherId, currentStatus) {
  const newStatus = currentStatus === "active" ? "on_leave" : "active";
  try {
    const res = await fetch(`/api/teachers/${teacherId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    if (!res.ok) throw new Error("Failed to update status");
    const updated = await res.json();

    const idx = state.teachers.findIndex((t) => t.id === teacherId);
    if (idx !== -1) state.teachers[idx] = updated;

    renderTeachers();
    showToast(`Status updated to ${newStatus === "active" ? "Active" : "On Leave"}`);
  } catch (err) {
    showToast(`Error: ${err.message}`, true);
  }
}

function openTeacherModal(teacherId = null) {
  state.editingTeacherId = teacherId;
  const modal = document.getElementById("modal-teacher");
  const title = document.getElementById("modal-teacher-title");
  const form = document.getElementById("form-teacher");

  form.reset();
  document.getElementById("teacher-form-id").value = "";

  if (teacherId) {
    const teacher = state.teachers.find((t) => t.id === teacherId);
    if (teacher) {
      title.textContent = "Edit Teacher";
      document.getElementById("teacher-form-id").value = teacher.id;
      document.getElementById("teacher-fullname").value = teacher.full_name;
      document.getElementById("teacher-shortcode").value = teacher.short_code;
      document.getElementById("teacher-dept").value = teacher.department;
      document.getElementById("teacher-form-status").value = teacher.status;
      document.getElementById("teacher-maxperiods").value = teacher.max_periods_per_day;
    }
  } else {
    title.textContent = "Add Teacher";
  }

  modal.classList.add("open");
}

function closeTeacherModal() {
  document.getElementById("modal-teacher").classList.remove("open");
  state.editingTeacherId = null;
}

async function handleTeacherSubmit(e) {
  e.preventDefault();
  const id = document.getElementById("teacher-form-id").value;
  const full_name = document.getElementById("teacher-fullname").value.trim();
  const short_code = document.getElementById("teacher-shortcode").value.trim();
  const department = document.getElementById("teacher-dept").value;
  const status = document.getElementById("teacher-form-status").value;
  const max_periods_per_day = parseInt(document.getElementById("teacher-maxperiods").value, 10);

  const payload = { full_name, short_code, department, status, max_periods_per_day };

  try {
    let res;
    if (id) {
      // Update
      res = await fetch(`/api/teachers/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      // Create
      res = await fetch("/api/teachers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }

    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || "Failed to save teacher");
    }

    await loadTeachers();
    closeTeacherModal();
    showToast(id ? "Teacher updated successfully" : "Teacher added successfully");
  } catch (err) {
    showToast(`Error: ${err.message}`, true);
  }
}

async function deleteTeacher(teacherId) {
  const teacher = state.teachers.find((t) => t.id === teacherId);
  const name = teacher ? teacher.full_name : teacherId;
  if (!window.DISABLE_CONFIRM && !confirm(`Are you sure you want to delete ${name}? This will also delete any assignments for this teacher.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/teachers/${teacherId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete teacher");

    state.teachers = state.teachers.filter((t) => t.id !== teacherId);
    renderTeachers();
    showToast("Teacher deleted");
  } catch (err) {
    showToast(`Error: ${err.message}`, true);
  }
}

// -----------------------------------------------------------------------------
// Teacher Availability Manager
// -----------------------------------------------------------------------------

const GRID_DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"];
const GRID_PERIODS = [
  { name: "P1", start: "08:00", end: "08:50" },
  { name: "P2", start: "08:50", end: "09:40" },
  { name: "P3", start: "09:40", end: "10:30" },
  { name: "P4", start: "10:40", end: "11:30" },
  { name: "P5", start: "11:30", end: "12:20" },
  { name: "P6", start: "12:20", end: "13:10" },
  { name: "P7", start: "14:30", end: "15:20" },
  { name: "P8", start: "15:20", end: "16:10" },
  { name: "P9", start: "16:10", end: "17:00" },
];

let availState = {
  teacherId: null,
  teacher: null,
  rules: [],
  blockedSlots: new Set(),
};

function formatRuleDescription(day, periods) {
  const d = (day || "").trim();
  const p = (periods || "").trim();
  const dLower = d.toLowerCase();
  const pLower = p.toLowerCase();
  const dayLabel = (dLower === "daily" || dLower === "all" || dLower === "*") ? "Daily" : (d.charAt(0).toUpperCase() + d.slice(1));

  let perLabel = p.toUpperCase();
  if (pLower === "all" || pLower === "*") {
    perLabel = "All Periods (Full Day)";
  } else if (pLower === "p1,p2,p3" || pLower === "p1, p2, p3") {
    perLabel = "08:00 AM – 10:30 AM (P1–P3)";
  } else if (pLower === "p4,p5,p6" || pLower === "p4, p5, p6") {
    perLabel = "10:40 AM – 01:10 PM (P4–P6)";
  } else if (pLower === "p7,p8,p9" || pLower === "p7, p8, p9") {
    perLabel = "02:30 PM – 05:00 PM (P7–P9)";
  }
  return `${dayLabel}: ${perLabel}`;
}

function synthesizeRulesFromSlots() {
  const dayPeriods = {};
  for (let d = 0; d < 5; d++) dayPeriods[d] = [];
  availState.blockedSlots.forEach((s) => {
    const d = Math.floor(s / 9);
    const p = s % 9;
    if (dayPeriods[d]) dayPeriods[d].push(p);
  });
  for (let d = 0; d < 5; d++) {
    dayPeriods[d].sort((a, b) => a - b);
  }

  const p0Str = dayPeriods[0].join(",");
  const allSame = [1, 2, 3, 4].every((d) => dayPeriods[d].join(",") === p0Str);

  const newRules = [];
  if (allSame && dayPeriods[0].length > 0) {
    const pNames = dayPeriods[0].map((p) => GRID_PERIODS[p].name).join(",");
    newRules.push({
      day: "daily",
      periods: dayPeriods[0].length === 9 ? "all" : pNames,
      description: formatRuleDescription("daily", dayPeriods[0].length === 9 ? "all" : pNames),
    });
  } else {
    for (let d = 0; d < 5; d++) {
      if (dayPeriods[d].length > 0) {
        const pNames = dayPeriods[d].map((p) => GRID_PERIODS[p].name).join(",");
        newRules.push({
          day: GRID_DAYS[d],
          periods: dayPeriods[d].length === 9 ? "all" : pNames,
          description: formatRuleDescription(GRID_DAYS[d], dayPeriods[d].length === 9 ? "all" : pNames),
        });
      }
    }
  }
  availState.rules = newRules;
}

async function openTeacherAvailabilityModal(teacherId) {
  availState.teacherId = teacherId;
  const teacher = state.teachers.find((t) => t.id === teacherId);
  availState.teacher = teacher || null;

  const modal = document.getElementById("modal-teacher-availability");
  if (!modal) return;

  // Set teacher info in modal header
  document.getElementById("modal-avail-teacher-name").textContent = teacher ? teacher.full_name : teacherId;
  document.getElementById("modal-avail-shortcode").textContent = teacher ? teacher.short_code : "";
  document.getElementById("modal-avail-id").textContent = teacherId;
  document.getElementById("modal-avail-status-text").textContent = teacher ? (teacher.status === "active" ? "Active" : "On Leave") : "";
  const deptBadge = document.getElementById("modal-avail-dept-badge");
  if (deptBadge && teacher) {
    deptBadge.textContent = teacher.department;
    deptBadge.className = `badge badge-${teacher.department.toLowerCase()}`;
  }

  try {
    const res = await fetch(`/api/teachers/${teacherId}/availability`);
    if (!res.ok) throw new Error("Failed to load teacher availability");
    const data = await res.json();

    availState.rules = (data.rules || []).map((r) => ({
      id: r.id,
      day: r.day,
      periods: r.periods,
      description: r.description || formatRuleDescription(r.day, r.periods),
    }));
    availState.blockedSlots = new Set(data.blocked_slots || []);

    renderAvailabilityGrid();
    renderAvailabilityRulesList();
    updateAvailabilityStats();

    modal.classList.add("open");
  } catch (err) {
    showToast(`Error: ${err.message}`, true);
  }
}

function closeTeacherAvailabilityModal() {
  const modal = document.getElementById("modal-teacher-availability");
  if (modal) modal.classList.remove("open");
  availState.teacherId = null;
  availState.teacher = null;
  availState.rules = [];
  availState.blockedSlots.clear();
}

function updateAvailabilityStats() {
  const countEl = document.getElementById("modal-avail-blocked-count");
  if (countEl) {
    countEl.textContent = `${availState.blockedSlots.size} / 45`;
    countEl.style.color = availState.blockedSlots.size > 0 ? "#DC2626" : "#16A34A";
  }
}

function renderAvailabilityGrid() {
  const table = document.getElementById("avail-interactive-grid");
  if (!table) return;

  // 1. Header
  let headHtml = `
    <tr>
      <th class="th-day-toggle" title="Click a day below to toggle whole day">Day ▾</th>
  `;
  GRID_PERIODS.forEach((p, idx) => {
    headHtml += `
      <th class="th-period-toggle" onclick="togglePeriodAvailability(${idx})" title="Click to toggle ${p.name} for all days">
        <div>${p.name}</div>
        <div style="font-size: 0.65rem; color: #64748B; font-weight: normal;">${p.start}</div>
      </th>
    `;
    if (idx === 2) {
      headHtml += `<th style="background: #FEF3C7; color: #92400E; font-size: 0.65rem; padding: 0.2rem 0.4rem;">☕ Break</th>`;
    } else if (idx === 5) {
      headHtml += `<th style="background: #FEF3C7; color: #92400E; font-size: 0.65rem; padding: 0.2rem 0.4rem;">🍱 Lunch</th>`;
    }
  });
  headHtml += `</tr>`;
  table.querySelector("thead").innerHTML = headHtml;

  // 2. Body: 5 rows
  let bodyHtml = "";
  GRID_DAYS.forEach((day, dIdx) => {
    bodyHtml += `<tr>`;
    bodyHtml += `<th class="th-day-toggle" onclick="toggleDayAvailability(${dIdx})" title="Click to toggle all periods for ${day}">${day}</th>`;

    GRID_PERIODS.forEach((p, pIdx) => {
      const slot = dIdx * 9 + pIdx;
      const isBlocked = availState.blockedSlots.has(slot);
      const cellCls = isBlocked ? "slot-blocked" : "slot-free";
      const cellTxt = isBlocked ? "OFF" : "Free";
      const titleTxt = `${day} ${p.name} (${p.start}-${p.end}): ${isBlocked ? "Blocked (Unavailable)" : "Available"}. Click to toggle.`;

      bodyHtml += `<td class="avail-slot-cell ${cellCls}" onclick="toggleAvailabilitySlot(${slot})" title="${titleTxt}">${cellTxt}</td>`;

      if (pIdx === 2 || pIdx === 5) {
        bodyHtml += `<td style="background: #F8FAFC; border: 1px solid #E2E8F0; width: 8px;"></td>`;
      }
    });

    bodyHtml += `</tr>`;
  });
  table.querySelector("tbody").innerHTML = bodyHtml;
}

function toggleAvailabilitySlot(slot) {
  if (availState.blockedSlots.has(slot)) {
    availState.blockedSlots.delete(slot);
  } else {
    availState.blockedSlots.add(slot);
  }
  synthesizeRulesFromSlots();
  renderAvailabilityGrid();
  renderAvailabilityRulesList();
  updateAvailabilityStats();
}

function toggleDayAvailability(dayIndex) {
  let allBlocked = true;
  for (let p = 0; p < 9; p++) {
    if (!availState.blockedSlots.has(dayIndex * 9 + p)) {
      allBlocked = false;
      break;
    }
  }

  for (let p = 0; p < 9; p++) {
    const slot = dayIndex * 9 + p;
    if (allBlocked) {
      availState.blockedSlots.delete(slot);
    } else {
      availState.blockedSlots.add(slot);
    }
  }

  synthesizeRulesFromSlots();
  renderAvailabilityGrid();
  renderAvailabilityRulesList();
  updateAvailabilityStats();
}

function togglePeriodAvailability(periodIndex) {
  let allBlocked = true;
  for (let d = 0; d < 5; d++) {
    if (!availState.blockedSlots.has(d * 9 + periodIndex)) {
      allBlocked = false;
      break;
    }
  }

  for (let d = 0; d < 5; d++) {
    const slot = d * 9 + periodIndex;
    if (allBlocked) {
      availState.blockedSlots.delete(slot);
    } else {
      availState.blockedSlots.add(slot);
    }
  }

  synthesizeRulesFromSlots();
  renderAvailabilityGrid();
  renderAvailabilityRulesList();
  updateAvailabilityStats();
}

function applyAvailabilityPreset(presetName) {
  if (presetName === "daily_morning") {
    // P1, P2, P3 for all 5 days
    for (let d = 0; d < 5; d++) {
      availState.blockedSlots.add(d * 9 + 0);
      availState.blockedSlots.add(d * 9 + 1);
      availState.blockedSlots.add(d * 9 + 2);
    }
    showToast("Preset applied: Block Daily 8:00 – 10:30 AM (P1–P3)");
  } else if (presetName === "daily_afternoon") {
    // P7, P8, P9 for all 5 days
    for (let d = 0; d < 5; d++) {
      availState.blockedSlots.add(d * 9 + 6);
      availState.blockedSlots.add(d * 9 + 7);
      availState.blockedSlots.add(d * 9 + 8);
    }
    showToast("Preset applied: Block Daily 2:30 – 5:00 PM (P7–P9)");
  } else if (presetName === "daily_midday") {
    // P4, P5, P6 for all 5 days
    for (let d = 0; d < 5; d++) {
      availState.blockedSlots.add(d * 9 + 3);
      availState.blockedSlots.add(d * 9 + 4);
      availState.blockedSlots.add(d * 9 + 5);
    }
    showToast("Preset applied: Block Daily 10:40 AM – 1:10 PM (P4–P6)");
  } else if (presetName === "clear_all") {
    availState.blockedSlots.clear();
    availState.rules = [];
    showToast("All slot restrictions cleared (100% Available)");
  }

  synthesizeRulesFromSlots();
  renderAvailabilityGrid();
  renderAvailabilityRulesList();
  updateAvailabilityStats();
}

function handleAddAvailabilityRule() {
  const day = document.getElementById("rule-select-day").value;
  const periods = document.getElementById("rule-select-period").value;

  const dayMap = {};
  GRID_DAYS.forEach((d, idx) => { dayMap[d.toLowerCase()] = idx; });
  const pMap = {};
  GRID_PERIODS.forEach((p, idx) => { pMap[p.name.toLowerCase()] = idx; });

  let days = [];
  if (day === "daily" || day === "all") {
    days = [0, 1, 2, 3, 4];
  } else if (dayMap[day.toLowerCase()] !== undefined) {
    days = [dayMap[day.toLowerCase()]];
  }

  let pers = [];
  if (periods === "all") {
    pers = [0, 1, 2, 3, 4, 5, 6, 7, 8];
  } else {
    periods.split(",").forEach((tok) => {
      tok = tok.trim().toLowerCase();
      if (pMap[tok] !== undefined) pers.push(pMap[tok]);
    });
  }

  days.forEach((d) => {
    pers.forEach((p) => {
      availState.blockedSlots.add(d * 9 + p);
    });
  });

  synthesizeRulesFromSlots();
  renderAvailabilityGrid();
  renderAvailabilityRulesList();
  updateAvailabilityStats();
  showToast(`Added restriction: ${formatRuleDescription(day, periods)}`);
}

function handleDeleteAvailabilityRule(index) {
  const r = availState.rules[index];
  if (!r) return;

  const dayMap = {};
  GRID_DAYS.forEach((d, idx) => { dayMap[d.toLowerCase()] = idx; });
  const pMap = {};
  GRID_PERIODS.forEach((p, idx) => { pMap[p.name.toLowerCase()] = idx; });

  let days = [];
  if (r.day.toLowerCase() === "daily" || r.day.toLowerCase() === "all") {
    days = [0, 1, 2, 3, 4];
  } else if (dayMap[r.day.toLowerCase()] !== undefined) {
    days = [dayMap[r.day.toLowerCase()]];
  }

  let pers = [];
  if (r.periods.toLowerCase() === "all") {
    pers = [0, 1, 2, 3, 4, 5, 6, 7, 8];
  } else {
    r.periods.split(",").forEach((tok) => {
      tok = tok.trim().toLowerCase();
      if (pMap[tok] !== undefined) pers.push(pMap[tok]);
    });
  }

  days.forEach((d) => {
    pers.forEach((p) => {
      availState.blockedSlots.delete(d * 9 + p);
    });
  });

  availState.rules.splice(index, 1);
  synthesizeRulesFromSlots();
  renderAvailabilityGrid();
  renderAvailabilityRulesList();
  updateAvailabilityStats();
}

function renderAvailabilityRulesList() {
  const container = document.getElementById("modal-avail-rules-list");
  const countEl = document.getElementById("modal-avail-rules-count");
  if (!container) return;

  if (countEl) countEl.textContent = availState.rules.length;

  if (availState.rules.length === 0) {
    container.innerHTML = `
      <div style="font-size: 0.82rem; color: #16A34A; background: #F0FDF4; padding: 0.45rem 0.75rem; border-radius: 6px; border: 1px solid #BBF7D0; width: 100%;">
        ✓ No restrictions configured. Teacher is available across all slots this week.
      </div>
    `;
    return;
  }

  container.innerHTML = availState.rules
    .map((r, idx) => {
      const desc = r.description || formatRuleDescription(r.day, r.periods);
      return `
      <div class="avail-rule-chip">
        <span>🔒 ${escapeHtml(desc)}</span>
        <button type="button" onclick="handleDeleteAvailabilityRule(${idx})" title="Remove this restriction">&times;</button>
      </div>
    `;
    })
    .join("");
}

async function saveTeacherAvailability() {
  if (!availState.teacherId) return;

  synthesizeRulesFromSlots();

  const payload = {
    rules: availState.rules.map((r) => ({
      day: r.day,
      periods: r.periods,
    })),
  };

  try {
    const res = await fetch(`/api/teachers/${availState.teacherId}/availability`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || "Failed to save availability");
    }

    await loadTeachers();
    closeTeacherAvailabilityModal();
    showToast("Teacher availability saved successfully!");
  } catch (err) {
    showToast(`Error: ${err.message}`, true);
  }
}

// -----------------------------------------------------------------------------
// Course Slot Availability & Fixed Slots API (Constraint 3)
// -----------------------------------------------------------------------------

const courseAvailState = {
  courseId: null,
  course: null,
  batch: null,
  section: "ALL", // "ALL", "A", "B"
  mode: "allowed", // "allowed" or "blocked"
  rules: [],
  allowedSlots: new Set(),
  blockedSlots: new Set(),
  sectionAllowed: {},
  sectionBlocked: {},
};

function formatCourseRuleDesc(r) {
  const rtype = (r.rule_type || "allowed").toLowerCase() === "allowed" ? "Allowed" : "Blocked";
  const sec = r.section && r.section !== "ALL" ? `Sec ${r.section}: ` : "";
  let rmStr = "";
  if (r.room_id) {
    const rm = (state.rooms || []).find((x) => x.id === r.room_id);
    rmStr = ` in ${rm ? rm.name : (r.room_name || r.room_id)}`;
  }
  return `[${rtype}] ${sec}${r.day} (${r.periods})${rmStr}`;
}

async function openCourseAvailabilityModal(courseId) {
  courseAvailState.courseId = courseId;
  const course = state.courses.find((c) => c.id === courseId);
  courseAvailState.course = course || null;
  const batch = course ? state.batches.find((b) => b.id === course.batch_id) : null;
  courseAvailState.batch = batch || null;
  courseAvailState.section = "ALL";
  courseAvailState.mode = "allowed";

  const modal = document.getElementById("modal-course-availability");
  if (!modal) return;

  // Header and summary details
  document.getElementById("modal-course-avail-name").textContent = course ? `${course.id}: ${course.title}` : courseId;
  document.getElementById("modal-course-avail-batch").textContent = course ? `Term ${course.batch_id}` : "";
  document.getElementById("modal-course-avail-id").textContent = courseId;

  const kindBadge = document.getElementById("modal-course-avail-kind-badge");
  if (kindBadge && course) {
    if (course.kind === "theory") {
      kindBadge.textContent = `Theory (${course.credit || 3.0} cr · ${course.periods_per_week || 3}/wk)`;
      kindBadge.className = "badge badge-theory";
    } else {
      kindBadge.textContent = `Sessional (${course.credit || 1.5} cr)`;
      kindBadge.className = "badge badge-sessional";
    }
  }

  // Populate sections dropdown
  const secSelect = document.getElementById("course-avail-section-select");
  const ruleSecSelect = document.getElementById("course-rule-select-section");
  if (secSelect && batch) {
    const secList = (batch.sections || []).filter((s) => s);
    let secOpts = `<option value="ALL">All Sections (Default)</option>`;
    secList.forEach((s) => {
      secOpts += `<option value="${s}">Section ${s}</option>`;
    });
    secSelect.innerHTML = secOpts;
    secSelect.value = "ALL";

    if (ruleSecSelect) {
      let rOpts = `<option value="ALL">All Sections</option>`;
      secList.forEach((s) => {
        rOpts += `<option value="${s}">Section ${s}</option>`;
      });
      ruleSecSelect.innerHTML = rOpts;
      ruleSecSelect.value = "ALL";
    }
  }

  setCourseAvailMode("allowed");

  try {
    const res = await fetch(`/api/courses/${courseId}/availability`);
    if (!res.ok) throw new Error("Failed to load course availability");
    const data = await res.json();

    // Populate assigned rooms display bar (from Edit Course modal settings)
    const assignedRoomsEl = document.getElementById("modal-course-avail-assigned-rooms");
    const assignedRoomsTypeEl = document.getElementById("modal-course-avail-assigned-rooms-type");
    if (assignedRoomsEl) {
      if (data.allowed_rooms && data.allowed_rooms.length > 0) {
        const roomNames = data.allowed_rooms.map((rid) => {
          const rObj = (state.rooms || []).find((rm) => rm.id === rid);
          return rObj ? rObj.name : rid;
        });
        assignedRoomsEl.textContent = `🎯 ${roomNames.join(", ")}`;
        if (assignedRoomsTypeEl) {
          assignedRoomsTypeEl.textContent = "Custom Specific Room(s)";
          assignedRoomsTypeEl.style.background = "#EFF6FF";
          assignedRoomsTypeEl.style.color = "#1D4ED8";
        }
      } else {
        if (course && course.kind === "theory") {
          assignedRoomsEl.textContent = "🏢 Category Default (Section Homeroom: CSE Room 101, 102, 105, 306, 401, 402, 501, 502)";
        } else if (course && course.room_kind === "cse_lab") {
          assignedRoomsEl.textContent = "🏢 Category Default (Departmental Software Labs: CSE Lab 103, 104, 201, 202, 305)";
        } else {
          const rk = course ? course.room_kind : (data.room_kind || "theory");
          const rkMeta = getRoomKindMeta(rk);
          assignedRoomsEl.textContent = `🏢 Category Default (${rkMeta ? rkMeta.label : rk})`;
        }
        if (assignedRoomsTypeEl) {
          assignedRoomsTypeEl.textContent = "Category Default";
          assignedRoomsTypeEl.style.background = "#E2E8F0";
          assignedRoomsTypeEl.style.color = "#334155";
        }
      }
    }

    // Populate room dropdown for adding slot rules
    const ruleRoomSelect = document.getElementById("course-rule-select-room");
    if (ruleRoomSelect) {
      let roomOpts = `<option value="">-- Default / Any Feasible Room --</option>`;
      if (data.allowed_rooms && data.allowed_rooms.length > 0) {
        roomOpts += `<optgroup label="⭐ Course Assigned Specific Room(s)">`;
        data.allowed_rooms.forEach((rid) => {
          const rObj = (state.rooms || []).find((rm) => rm.id === rid);
          const rName = rObj ? rObj.name : rid;
          roomOpts += `<option value="${escapeHtml(rid)}">${escapeHtml(rName)} (${escapeHtml(rid)})</option>`;
        });
        roomOpts += `</optgroup>`;
      }
      roomOpts += `<optgroup label="🏢 All Department Classrooms & Labs">`;
      const sortedRooms = [...(state.rooms || [])].sort((a, b) => a.name.localeCompare(b.name));
      sortedRooms.forEach((rm) => {
        roomOpts += `<option value="${escapeHtml(rm.id)}">${escapeHtml(rm.name)} (${escapeHtml(rm.id)})</option>`;
      });
      roomOpts += `</optgroup>`;
      ruleRoomSelect.innerHTML = roomOpts;
      ruleRoomSelect.value = "";
    }

    courseAvailState.rules = (data.rules || []).map((r) => ({
      id: r.id,
      day: r.day,
      periods: r.periods,
      rule_type: (r.rule_type || "allowed").toLowerCase(),
      section: r.section || "ALL",
      room_id: r.room_id || null,
      room_name: r.room_name || null,
      note: r.note,
      description: r.description || formatCourseRuleDesc(r),
    }));

    courseAvailState.allowedSlots = new Set(data.allowed_slots || []);
    courseAvailState.blockedSlots = new Set(data.blocked_slots || []);
    courseAvailState.sectionAllowed = {};
    for (const [sec, slots] of Object.entries(data.section_allowed_slots || {})) {
      courseAvailState.sectionAllowed[sec] = new Set(slots);
    }
    courseAvailState.sectionBlocked = {};
    for (const [sec, slots] of Object.entries(data.section_blocked_slots || {})) {
      courseAvailState.sectionBlocked[sec] = new Set(slots);
    }

    renderCourseAvailabilityGrid();
    renderCourseAvailabilityRulesList();
    updateCourseAvailabilityStats();

    modal.classList.add("open");
  } catch (err) {
    showToast(`Error: ${err.message}`, true);
  }
}

function closeCourseAvailabilityModal() {
  const modal = document.getElementById("modal-course-availability");
  if (modal) modal.classList.remove("open");
  courseAvailState.courseId = null;
  courseAvailState.course = null;
  courseAvailState.batch = null;
  courseAvailState.rules = [];
  courseAvailState.allowedSlots.clear();
  courseAvailState.blockedSlots.clear();
  courseAvailState.sectionAllowed = {};
  courseAvailState.sectionBlocked = {};
}

function setCourseAvailMode(mode) {
  courseAvailState.mode = mode;
  const btnAllowed = document.getElementById("btn-mode-allowed");
  const btnBlocked = document.getElementById("btn-mode-blocked");
  const ruleTypeSelect = document.getElementById("course-rule-select-type");

  if (btnAllowed && btnBlocked) {
    if (mode === "allowed") {
      btnAllowed.className = "btn btn-sm btn-primary";
      btnBlocked.className = "btn btn-sm btn-outline";
      if (ruleTypeSelect) ruleTypeSelect.value = "allowed";
    } else {
      btnAllowed.className = "btn btn-sm btn-outline";
      btnBlocked.className = "btn btn-sm btn-danger";
      if (ruleTypeSelect) ruleTypeSelect.value = "blocked";
    }
  }
  renderCourseAvailabilityGrid();
}

function onCourseAvailSectionChange() {
  const sel = document.getElementById("course-avail-section-select");
  if (sel) {
    courseAvailState.section = sel.value;
    const ruleSec = document.getElementById("course-rule-select-section");
    if (ruleSec) ruleSec.value = sel.value;
    renderCourseAvailabilityGrid();
    updateCourseAvailabilityStats();
  }
}

function getActiveSlotSets() {
  const sec = courseAvailState.section;
  let allowedSet, blockedSet;
  if (sec === "ALL") {
    allowedSet = courseAvailState.allowedSlots;
    blockedSet = courseAvailState.blockedSlots;
  } else {
    if (!courseAvailState.sectionAllowed[sec]) courseAvailState.sectionAllowed[sec] = new Set();
    if (!courseAvailState.sectionBlocked[sec]) courseAvailState.sectionBlocked[sec] = new Set();
    allowedSet = courseAvailState.sectionAllowed[sec];
    blockedSet = courseAvailState.sectionBlocked[sec];
  }
  return { allowedSet, blockedSet };
}

function updateCourseAvailabilityStats() {
  const summaryBadge = document.getElementById("modal-course-avail-summary-badge");
  if (!summaryBadge) return;

  const { allowedSet, blockedSet } = getActiveSlotSets();
  if (allowedSet.size > 0 && blockedSet.size > 0) {
    summaryBadge.textContent = `${allowedSet.size} Fixed, ${blockedSet.size} Blocked`;
    summaryBadge.style.color = "#1D4ED8";
  } else if (allowedSet.size > 0) {
    summaryBadge.textContent = `Fixed (${allowedSet.size} slots)`;
    summaryBadge.style.color = "#1D4ED8";
  } else if (blockedSet.size > 0) {
    summaryBadge.textContent = `Blocked (${blockedSet.size} slots)`;
    summaryBadge.style.color = "#DC2626";
  } else {
    summaryBadge.textContent = "Unrestricted (Any)";
    summaryBadge.style.color = "#16A34A";
  }
}

function renderCourseAvailabilityGrid() {
  const table = document.getElementById("course-avail-interactive-grid");
  if (!table) return;

  const { allowedSet, blockedSet } = getActiveSlotSets();

  let headHtml = `
    <tr>
      <th class="th-day-toggle" title="Click day to toggle entire row">Day ▾</th>
  `;
  GRID_PERIODS.forEach((p, pIdx) => {
    headHtml += `
      <th class="th-period-toggle" onclick="toggleCoursePeriod(${pIdx})" title="Click to toggle entire period across week">
        <div><b>${escapeHtml(p.name)}</b></div>
        <div style="font-size: 0.68rem; opacity: 0.75; font-weight: normal;">${escapeHtml(p.start)}</div>
      </th>
    `;
  });
  headHtml += "</tr>";

  let bodyHtml = "";
  GRID_DAYS.forEach((day, dIdx) => {
    bodyHtml += `<tr>`;
    bodyHtml += `
      <th class="th-day-toggle" onclick="toggleCourseDay(${dIdx})" title="Click to toggle all slots for ${day}">
        <b>${day}</b>
      </th>
    `;
    GRID_PERIODS.forEach((p, pIdx) => {
      const slotIdx = dIdx * 9 + pIdx;
      const isAllowed = allowedSet.has(slotIdx);
      const isBlocked = blockedSet.has(slotIdx);

      let cellClass = "avail-slot-cell";
      let cellText = "Free";
      if (isAllowed) {
        cellClass += " slot-allowed";
        cellText = "📌 Fixed";
      } else if (isBlocked) {
        cellClass += " slot-blocked";
        cellText = "🚫 Block";
      } else {
        cellClass += " slot-free";
      }

      bodyHtml += `
        <td class="${cellClass}" onclick="toggleCourseSlot(${slotIdx})" title="Slot ${day} ${p.name}: click to toggle">
          ${cellText}
        </td>
      `;
    });
    bodyHtml += `</tr>`;
  });

  table.querySelector("thead").innerHTML = headHtml;
  table.querySelector("tbody").innerHTML = bodyHtml;
}

function toggleCourseSlot(slotIdx) {
  const { allowedSet, blockedSet } = getActiveSlotSets();
  const mode = courseAvailState.mode;

  if (mode === "allowed") {
    blockedSet.delete(slotIdx);
    if (allowedSet.has(slotIdx)) {
      allowedSet.delete(slotIdx);
    } else {
      allowedSet.add(slotIdx);
    }
  } else {
    allowedSet.delete(slotIdx);
    if (blockedSet.has(slotIdx)) {
      blockedSet.delete(slotIdx);
    } else {
      blockedSet.add(slotIdx);
    }
  }

  synthesizeCourseRules();
  renderCourseAvailabilityGrid();
  renderCourseAvailabilityRulesList();
  updateCourseAvailabilityStats();
}

function toggleCourseDay(dayIdx) {
  const { allowedSet, blockedSet } = getActiveSlotSets();
  const mode = courseAvailState.mode;
  const targetSet = mode === "allowed" ? allowedSet : blockedSet;
  const otherSet = mode === "allowed" ? blockedSet : allowedSet;

  const daySlots = [0, 1, 2, 3, 4, 5, 6, 7, 8].map((p) => dayIdx * 9 + p);
  const allInTarget = daySlots.every((s) => targetSet.has(s));

  daySlots.forEach((s) => {
    otherSet.delete(s);
    if (allInTarget) {
      targetSet.delete(s);
    } else {
      targetSet.add(s);
    }
  });

  synthesizeCourseRules();
  renderCourseAvailabilityGrid();
  renderCourseAvailabilityRulesList();
  updateCourseAvailabilityStats();
}

function toggleCoursePeriod(periodIdx) {
  const { allowedSet, blockedSet } = getActiveSlotSets();
  const mode = courseAvailState.mode;
  const targetSet = mode === "allowed" ? allowedSet : blockedSet;
  const otherSet = mode === "allowed" ? blockedSet : allowedSet;

  const perSlots = [0, 1, 2, 3, 4].map((d) => d * 9 + periodIdx);
  const allInTarget = perSlots.every((s) => targetSet.has(s));

  perSlots.forEach((s) => {
    otherSet.delete(s);
    if (allInTarget) {
      targetSet.delete(s);
    } else {
      targetSet.add(s);
    }
  });

  synthesizeCourseRules();
  renderCourseAvailabilityGrid();
  renderCourseAvailabilityRulesList();
  updateCourseAvailabilityStats();
}

function synthesizeCourseRules() {
  const customRoomRules = (courseAvailState.rules || []).filter((r) => r.room_id);
  const newRules = [...customRoomRules];

  function rulesForSets(sec, allowedSet, blockedSet) {
    for (let d = 0; d < 5; d++) {
      const hasCustomForDay = customRoomRules.some(
        (cr) => cr.day.toLowerCase() === GRID_DAYS[d].toLowerCase() &&
                (cr.section || "ALL") === (sec || "ALL")
      );
      if (hasCustomForDay) continue;

      const dSlots = [0, 1, 2, 3, 4, 5, 6, 7, 8].filter((p) => allowedSet.has(d * 9 + p));
      if (dSlots.length === 9) {
        newRules.push({
          day: GRID_DAYS[d],
          periods: "all",
          rule_type: "allowed",
          section: sec === "ALL" ? null : sec,
          room_id: null,
          description: `[Allowed] ${sec !== "ALL" ? `Sec ${sec}: ` : ""}${GRID_DAYS[d]} (All Periods)`,
        });
      } else if (dSlots.length > 0) {
        const pNames = dSlots.map((p) => GRID_PERIODS[p].name);
        newRules.push({
          day: GRID_DAYS[d],
          periods: pNames.join(","),
          rule_type: "allowed",
          section: sec === "ALL" ? null : sec,
          room_id: null,
          description: `[Allowed] ${sec !== "ALL" ? `Sec ${sec}: ` : ""}${GRID_DAYS[d]} (${pNames.join(",")})`,
        });
      }
    }

    for (let d = 0; d < 5; d++) {
      const hasCustomForDay = customRoomRules.some(
        (cr) => cr.day.toLowerCase() === GRID_DAYS[d].toLowerCase() &&
                (cr.section || "ALL") === (sec || "ALL")
      );
      if (hasCustomForDay) continue;

      const dSlots = [0, 1, 2, 3, 4, 5, 6, 7, 8].filter((p) => blockedSet.has(d * 9 + p));
      if (dSlots.length === 9) {
        newRules.push({
          day: GRID_DAYS[d],
          periods: "all",
          rule_type: "blocked",
          section: sec === "ALL" ? null : sec,
          room_id: null,
          description: `[Blocked] ${sec !== "ALL" ? `Sec ${sec}: ` : ""}${GRID_DAYS[d]} (All Periods)`,
        });
      } else if (dSlots.length > 0) {
        const pNames = dSlots.map((p) => GRID_PERIODS[p].name);
        newRules.push({
          day: GRID_DAYS[d],
          periods: pNames.join(","),
          rule_type: "blocked",
          section: sec === "ALL" ? null : sec,
          room_id: null,
          description: `[Blocked] ${sec !== "ALL" ? `Sec ${sec}: ` : ""}${GRID_DAYS[d]} (${pNames.join(",")})`,
        });
      }
    }
  }

  // Course-wide (ALL)
  rulesForSets("ALL", courseAvailState.allowedSlots, courseAvailState.blockedSlots);

  // Section-specific
  const allSecs = new Set([
    ...Object.keys(courseAvailState.sectionAllowed || {}),
    ...Object.keys(courseAvailState.sectionBlocked || {}),
  ]);
  allSecs.forEach((sec) => {
    if (sec && sec !== "ALL") {
      const aSet = courseAvailState.sectionAllowed[sec] || new Set();
      const bSet = courseAvailState.sectionBlocked[sec] || new Set();
      rulesForSets(sec, aSet, bSet);
    }
  });

  courseAvailState.rules = newRules;
}

function applyCourseAvailabilityPreset(presetName) {
  const { allowedSet, blockedSet } = getActiveSlotSets();

  if (presetName === "clear_all") {
    allowedSet.clear();
    blockedSet.clear();
    courseAvailState.rules = [];
    showToast("Cleared all restrictions for selected section");
  } else if (presetName === "sunday_morning") {
    setCourseAvailMode("allowed");
    allowedSet.clear();
    blockedSet.clear();
    [0, 1, 2].forEach((p) => allowedSet.add(0 * 9 + p)); // Sunday P1-P3
    showToast("Set fixed slot: Sunday P1–P3 (8:00 – 10:30 AM)");
  } else if (presetName === "tuesday_morning") {
    setCourseAvailMode("allowed");
    allowedSet.clear();
    blockedSet.clear();
    [0, 1, 2].forEach((p) => allowedSet.add(2 * 9 + p)); // Tuesday P1-P3
    showToast("Set fixed slot: Tuesday P1–P3 (8:00 – 10:30 AM)");
  } else if (presetName === "thursday_morning") {
    setCourseAvailMode("allowed");
    allowedSet.clear();
    blockedSet.clear();
    [0, 1, 2].forEach((p) => allowedSet.add(4 * 9 + p)); // Thursday P1-P3
    showToast("Set fixed slot: Thursday P1–P3 (8:00 – 10:30 AM)");
  } else if (presetName === "morning_only") {
    setCourseAvailMode("allowed");
    allowedSet.clear();
    blockedSet.clear();
    for (let d = 0; d < 5; d++) {
      [0, 1, 2].forEach((p) => allowedSet.add(d * 9 + p));
    }
    showToast("Set allowed slots: Daily Morning (P1–P3)");
  } else if (presetName === "afternoon_only") {
    setCourseAvailMode("allowed");
    allowedSet.clear();
    blockedSet.clear();
    for (let d = 0; d < 5; d++) {
      [6, 7, 8].forEach((p) => allowedSet.add(d * 9 + p));
    }
    showToast("Set allowed slots: Daily Afternoon (P7–P9)");
  }

  synthesizeCourseRules();
  renderCourseAvailabilityGrid();
  renderCourseAvailabilityRulesList();
  updateCourseAvailabilityStats();
}

function handleAddCourseAvailabilityRule() {
  const day = document.getElementById("course-rule-select-day").value;
  const periods = document.getElementById("course-rule-select-period").value;
  const ruleType = document.getElementById("course-rule-select-type").value;
  const section = document.getElementById("course-rule-select-section").value;
  const roomSelect = document.getElementById("course-rule-select-room");
  const roomId = (roomSelect ? roomSelect.value : "").trim();

  const dayMap = {};
  GRID_DAYS.forEach((d, idx) => { dayMap[d.toLowerCase()] = idx; });
  const pMap = {};
  GRID_PERIODS.forEach((p, idx) => { pMap[p.name.toLowerCase()] = idx; });

  let days = [];
  if (day === "daily" || day === "all") {
    days = [0, 1, 2, 3, 4];
  } else if (dayMap[day.toLowerCase()] !== undefined) {
    days = [dayMap[day.toLowerCase()]];
  }

  let pers = [];
  if (periods === "all") {
    pers = [0, 1, 2, 3, 4, 5, 6, 7, 8];
  } else {
    periods.split(",").forEach((tok) => {
      tok = tok.trim().toLowerCase();
      if (pMap[tok] !== undefined) pers.push(pMap[tok]);
    });
  }

  let targetSet, otherSet;
  if (section === "ALL") {
    targetSet = ruleType === "allowed" ? courseAvailState.allowedSlots : courseAvailState.blockedSlots;
    otherSet = ruleType === "allowed" ? courseAvailState.blockedSlots : courseAvailState.allowedSlots;
  } else {
    if (!courseAvailState.sectionAllowed[section]) courseAvailState.sectionAllowed[section] = new Set();
    if (!courseAvailState.sectionBlocked[section]) courseAvailState.sectionBlocked[section] = new Set();
    targetSet = ruleType === "allowed" ? courseAvailState.sectionAllowed[section] : courseAvailState.sectionBlocked[section];
    otherSet = ruleType === "allowed" ? courseAvailState.sectionBlocked[section] : courseAvailState.sectionAllowed[section];
  }

  days.forEach((d) => {
    pers.forEach((p) => {
      const s = d * 9 + p;
      otherSet.delete(s);
      targetSet.add(s);
    });
  });

  const rmObj = roomId ? (state.rooms || []).find((x) => x.id === roomId) : null;
  const newRule = {
    day,
    periods,
    rule_type: ruleType,
    section: section === "ALL" ? null : section,
    room_id: roomId || null,
    room_name: rmObj ? rmObj.name : (roomId || null),
    note: null,
    description: formatCourseRuleDesc({
      day,
      periods,
      rule_type: ruleType,
      section: section === "ALL" ? null : section,
      room_id: roomId || null,
    }),
  };

  const existingIdx = courseAvailState.rules.findIndex(
    (r) => r.day.toLowerCase() === day.toLowerCase() &&
           r.periods.toLowerCase() === periods.toLowerCase() &&
           (r.section || "ALL") === (section || "ALL")
  );
  if (existingIdx >= 0) {
    courseAvailState.rules[existingIdx] = newRule;
  } else {
    courseAvailState.rules.push(newRule);
  }

  renderCourseAvailabilityGrid();
  renderCourseAvailabilityRulesList();
  updateCourseAvailabilityStats();
  const roomMsg = roomId ? ` in ${rmObj ? rmObj.name : roomId}` : "";
  showToast(`Added rule: ${ruleType.toUpperCase()} ${section !== 'ALL' ? `Sec ${section}: ` : ''}${day} (${periods})${roomMsg}`);
}

function handleDeleteCourseAvailabilityRule(index) {
  const r = courseAvailState.rules[index];
  if (!r) return;

  const dayMap = {};
  GRID_DAYS.forEach((d, idx) => { dayMap[d.toLowerCase()] = idx; });
  const pMap = {};
  GRID_PERIODS.forEach((p, idx) => { pMap[p.name.toLowerCase()] = idx; });

  let days = [];
  if (r.day.toLowerCase() === "daily" || r.day.toLowerCase() === "all") {
    days = [0, 1, 2, 3, 4];
  } else if (dayMap[r.day.toLowerCase()] !== undefined) {
    days = [dayMap[r.day.toLowerCase()]];
  }

  let pers = [];
  if (r.periods.toLowerCase() === "all") {
    pers = [0, 1, 2, 3, 4, 5, 6, 7, 8];
  } else {
    r.periods.split(",").forEach((tok) => {
      tok = tok.trim().toLowerCase();
      if (pMap[tok] !== undefined) pers.push(pMap[tok]);
    });
  }

  const sec = r.section || "ALL";
  const ruleType = r.rule_type || "allowed";
  let targetSet;
  if (sec === "ALL") {
    targetSet = ruleType === "allowed" ? courseAvailState.allowedSlots : courseAvailState.blockedSlots;
  } else {
    targetSet = ruleType === "allowed" ? (courseAvailState.sectionAllowed[sec] || new Set()) : (courseAvailState.sectionBlocked[sec] || new Set());
  }

  days.forEach((d) => {
    pers.forEach((p) => {
      targetSet.delete(d * 9 + p);
    });
  });

  courseAvailState.rules.splice(index, 1);
  renderCourseAvailabilityGrid();
  renderCourseAvailabilityRulesList();
  updateCourseAvailabilityStats();
}

function renderCourseAvailabilityRulesList() {
  const container = document.getElementById("modal-course-avail-rules-list");
  const countEl = document.getElementById("modal-course-avail-rules-count");
  if (!container) return;

  if (countEl) countEl.textContent = courseAvailState.rules.length;

  if (courseAvailState.rules.length === 0) {
    container.innerHTML = `
      <div style="font-size: 0.82rem; color: #16A34A; background: #F0FDF4; padding: 0.55rem 0.85rem; border-radius: 6px; border: 1px solid #BBF7D0; width: 100%; display: flex; align-items: center; gap: 0.4rem;">
        <span style="font-size: 0.95rem;">✓</span>
        <span>No custom slot restrictions configured. Course can be placed in any feasible slot.</span>
      </div>
    `;
    return;
  }

  container.innerHTML = courseAvailState.rules
    .map((r, idx) => {
      const isAllowed = (r.rule_type || "allowed").toLowerCase() === "allowed";
      const chipClass = isAllowed ? "avail-rule-chip chip-allowed" : "avail-rule-chip chip-blocked";
      const icon = isAllowed ? "📌" : "🚫";
      const typeLabel = isAllowed ? "Allowed" : "Blocked";
      const secLabel = r.section && r.section !== "ALL" ? `Sec ${r.section}` : "All Sections";

      let periodLabel = r.periods;
      if (r.periods === "P1,P2,P3") periodLabel = "08:00 – 10:30 (P1–P3)";
      else if (r.periods === "P4,P5,P6") periodLabel = "10:40 – 01:10 (P4–P6)";
      else if (r.periods === "P7,P8,P9") periodLabel = "02:30 – 05:00 (P7–P9)";
      else if (r.periods === "all") periodLabel = "Full Day (P1–P9)";

      const roomObj = r.room_id ? (state.rooms || []).find((x) => x.id === r.room_id) : null;
      const roomName = roomObj ? roomObj.name : (r.room_name || r.room_id || null);

      return `
      <div class="${chipClass}" style="display: inline-flex; align-items: center; gap: 0.45rem; padding: 0.35rem 0.65rem; border-radius: 6px; font-size: 0.8rem; box-shadow: 0 1px 2px rgba(0,0,0,0.04);">
        <span style="font-weight: 700; display: inline-flex; align-items: center; gap: 0.25rem;">
          ${icon} [${typeLabel}]
        </span>
        <span style="background: rgba(0,0,0,0.06); padding: 0.1rem 0.45rem; border-radius: 4px; font-weight: 700; font-size: 0.74rem;">
          ${escapeHtml(secLabel)}
        </span>
        <span style="font-weight: 600;">
          ${escapeHtml(r.day)}: ${escapeHtml(periodLabel)}
        </span>
        ${roomName ? `
          <span style="background: #DBEAFE; color: #1E40AF; padding: 0.12rem 0.45rem; border-radius: 4px; font-weight: 700; font-size: 0.75rem; border: 1px solid #BFDBFE; display: inline-flex; align-items: center; gap: 0.25rem;">
            🏢 ${escapeHtml(roomName)}
          </span>` : ""
        }
        <button type="button" onclick="handleDeleteCourseAvailabilityRule(${idx})" title="Remove this rule" style="margin-left: 0.25rem; font-size: 1.15rem; line-height: 1; opacity: 0.75; cursor: pointer; border: none; background: transparent;">&times;</button>
      </div>
    `;
    })
    .join("");
}

async function saveCourseAvailability() {
  if (!courseAvailState.courseId) return;

  const payload = {
    rules: courseAvailState.rules.map((r) => ({
      day: r.day,
      periods: r.periods,
      rule_type: r.rule_type,
      section: r.section === "ALL" ? null : r.section,
      room_id: r.room_id || null,
      note: r.note || null,
    })),
  };

  try {
    const res = await fetch(`/api/courses/${courseAvailState.courseId}/availability`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to save course slot availability");
    }

    await res.json();
    showToast(`✓ Slot rules saved for ${courseAvailState.courseId}`);
    closeCourseAvailabilityModal();

    // Refresh courses list in state
    await loadCourses();
    renderCourses();
  } catch (err) {
    showToast(`Error: ${err.message}`, true);
  }
}

// -----------------------------------------------------------------------------
// Courses API & Rendering
// -----------------------------------------------------------------------------

async function loadBatches() {
  try {
    const res = await fetch("/api/batches");
    if (!res.ok) throw new Error("Failed to load batches");
    state.batches = await res.json();
    state.batches.sort((a, b) => curriculumSortKey(a.id) - curriculumSortKey(b.id));

    // Populate course batch dropdown (All Batches filter)
    const courseBatchEl = document.getElementById("course-batch-select");
    if (courseBatchEl) {
      const cur = courseBatchEl.value;
      let html = '<option value="">All Batches / Terms</option>';
      state.batches.forEach((b) => {
        const tag = b.status === "on" ? "🟢 ON" : "⚪ OFF";
        html += `<option value="${b.id}">${b.name} (${b.id}) [${tag}]</option>`;
      });
      courseBatchEl.innerHTML = html;
      if (cur) courseBatchEl.value = cur;
    }

    // Populate course modal batch select
    const modalBatchEl = document.getElementById("course-batch");
    if (modalBatchEl) {
      modalBatchEl.innerHTML = state.batches
        .map((b) => `<option value="${b.id}">${b.name} (${b.id}) [Status: ${b.status.toUpperCase()}]</option>`)
        .join("");
    }

    // Populate assignment batch dropdown (ONLY running batches with status='on', in CURRICULUM_ORDER)
    const assignBatchEl = document.getElementById("assign-batch-select");
    if (assignBatchEl) {
      const cur = assignBatchEl.value;
      const activeBatches = state.batches.filter((b) => b.status === "on");
      let html = `<option value="">All Running Terms (${activeBatches.length})</option>`;
      activeBatches.forEach((b) => {
        html += `<option value="${b.id}">${b.name} (${b.id})</option>`;
      });
      assignBatchEl.innerHTML = html;
      if (cur && activeBatches.some((b) => b.id === cur)) {
        assignBatchEl.value = cur;
      } else {
        assignBatchEl.value = "";
      }
    }

    populateAssignCourseDropdown();
    renderFreezeBatchSelector();
  } catch (err) {
    showToast(`Error loading batches: ${err.message}`, true);
  }
}

function populateAssignCourseDropdown() {
  const courseSelectEl = document.getElementById("assign-course-select");
  if (!courseSelectEl) return;

  const selectedBatchId = document.getElementById("assign-batch-select")?.value || "";
  const curVal = courseSelectEl.value;

  // Only courses from running/active batches
  const activeBatchIds = new Set(state.batches.filter((b) => b.status === "on").map((b) => b.id));
  let availableCourses = state.courses.filter((c) => activeBatchIds.has(c.batch_id));

  if (selectedBatchId) {
    availableCourses = availableCourses.filter((c) => c.batch_id === selectedBatchId);
  }

  // Sort available courses by CURRICULUM_ORDER then course code
  availableCourses.sort(
    (a, b) => curriculumSortKey(a.batch_id) - curriculumSortKey(b.batch_id) || a.id.localeCompare(b.id)
  );

  let html = `<option value="">All Courses in Selected Term (${availableCourses.length})</option>`;
  availableCourses.forEach((c) => {
    const kindTag = c.kind === "theory" ? "Theory" : `${c.credit} cr Lab`;
    html += `<option value="${c.id}">${c.id}: ${escapeHtml(c.title)} [${kindTag}] (${c.batch_id})</option>`;
  });
  courseSelectEl.innerHTML = html;
  if (curVal && availableCourses.some((c) => c.id === curVal)) {
    courseSelectEl.value = curVal;
  } else {
    courseSelectEl.value = "";
  }
}

async function toggleBatchStatus(batchId, currentStatus) {
  const newStatus = currentStatus === "on" ? "off" : "on";
  try {
    const res = await fetch(`/api/batches/${batchId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    if (!res.ok) throw new Error("Failed to update term status");
    const updated = await res.json();

    const idx = state.batches.findIndex((b) => b.id === batchId);
    if (idx !== -1) {
      state.batches[idx].status = updated.status;
    }

    await loadBatches();
    renderCourses();
    renderAssignments();

    const statusLabel = newStatus === "on" ? "🟢 ON (Running Term)" : "⚪ OFF (Inactive Term)";
    showToast(`Term ${batchId} status set to ${statusLabel}`);
  } catch (err) {
    showToast(`Error updating term status: ${err.message}`, true);
  }
}

async function loadCourses() {
  try {
    const res = await fetch("/api/courses");
    if (!res.ok) throw new Error("Failed to load courses");
    state.courses = await res.json();
    populateAssignCourseDropdown();
    renderCourses();
  } catch (err) {
    showToast(`Error loading courses: ${err.message}`, true);
  }
}

const ROOM_KIND_META = {
  theory: {
    category: "Theory Classrooms",
    type: "Theory Class",
    label: "Theory Classrooms (Section Homeroom)",
    shortLabel: "Theory (Homeroom)",
    rooms: "CSE Room 101, 102, 105, 306, 401, 402, 501, 502",
    hint: "Automatically allocated to the section's designated homeroom lecture hall.",
    badgeBg: "#EFF6FF",
    badgeColor: "#1E40AF",
    badgeBorder: "#DBEAFE",
  },
  seminar_501: {
    category: "Theory Classrooms",
    type: "Theory Class",
    label: "CSE Room 501 (Technical Writing & Seminar)",
    shortLabel: "CSE Room 501",
    rooms: "CSE Room 501",
    hint: "Dedicated room allocation for Technical Writing & Seminar in CSE Room 501.",
    badgeBg: "#EFF6FF",
    badgeColor: "#1E40AF",
    badgeBorder: "#DBEAFE",
  },
  cse_lab: {
    category: "Departmental Labs",
    type: "Software Lab",
    label: "Departmental Software Lab (CSE Lab 103, 104, 201, 202, 305)",
    shortLabel: "Software Lab",
    rooms: "CSE Lab 103, 104, 201, 202, 305",
    hint: "Automatically allocated across Departmental Software Labs (CSE Lab 103, 104, 201, 202, 305).",
    badgeBg: "#FEF3C7",
    badgeColor: "#92400E",
    badgeBorder: "#FDE68A",
  },
  hardware_lab_107: {
    category: "Departmental Labs",
    type: "Hardware Lab",
    label: "CSE Lab 107 (Hardware / Embedded Systems & IoT Lab)",
    shortLabel: "CSE Lab 107",
    rooms: "CSE Lab 107",
    hint: "Dedicated Departmental Hardware Lab: Embedded Systems, Interfacing & IoT (CSE Lab 107).",
    badgeBg: "#FEF3C7",
    badgeColor: "#92400E",
    badgeBorder: "#FDE68A",
  },
  hardware_lab_108: {
    category: "Departmental Labs",
    type: "Hardware Lab",
    label: "CSE Lab 108 (Digital Logic Design Lab)",
    shortLabel: "CSE Lab 108",
    rooms: "CSE Lab 108",
    hint: "Dedicated Departmental Hardware Lab: Digital Logic Design (CSE Lab 108).",
    badgeBg: "#FEF3C7",
    badgeColor: "#92400E",
    badgeBorder: "#FDE68A",
  },
  chem_lab: {
    category: "Non-Departmental Labs",
    type: "Non-Dept Lab",
    label: "Chemistry Lab (CHEM-LAB)",
    shortLabel: "Chemistry Lab",
    rooms: "Chemistry Lab (CHEM-LAB)",
    hint: "Non-Departmental laboratory facility: Chemistry Lab.",
    badgeBg: "#F0FDF4",
    badgeColor: "#166534",
    badgeBorder: "#BBF7D0",
  },
  hum_lab: {
    category: "Non-Departmental Labs",
    type: "Non-Dept Lab",
    label: "English Language Lab (HUM-LAB)",
    shortLabel: "English Lang Lab",
    rooms: "English Language Lab (HUM-LAB)",
    hint: "Non-Departmental laboratory facility: English Language Lab (HUM-LAB).",
    badgeBg: "#F0FDF4",
    badgeColor: "#166534",
    badgeBorder: "#BBF7D0",
  },
  phy_lab: {
    category: "Non-Departmental Labs",
    type: "Non-Dept Lab",
    label: "Physics Lab (PHY-LAB)",
    shortLabel: "Physics Lab",
    rooms: "Physics Lab (PHY-LAB)",
    hint: "Non-Departmental laboratory facility: Physics Lab (PHY-LAB).",
    badgeBg: "#F0FDF4",
    badgeColor: "#166534",
    badgeBorder: "#BBF7D0",
  },
  ece_lab: {
    category: "Non-Departmental Labs",
    type: "Non-Dept Lab",
    label: "ECE Lab (ECE-104)",
    shortLabel: "ECE Lab",
    rooms: "ECE Lab (ECE-104)",
    hint: "Non-Departmental laboratory facility: ECE Lab (ECE-104).",
    badgeBg: "#F0FDF4",
    badgeColor: "#166534",
    badgeBorder: "#BBF7D0",
  },
  eee_lab: {
    category: "Non-Departmental Labs",
    type: "Non-Dept Lab",
    label: "EEE Lab (EEE-LAB)",
    shortLabel: "EEE Lab",
    rooms: "EEE Lab (EEE-LAB)",
    hint: "Non-Departmental laboratory facility: EEE Lab (EEE-LAB).",
    badgeBg: "#F0FDF4",
    badgeColor: "#166534",
    badgeBorder: "#BBF7D0",
  },
  mecha_lab: {
    category: "Non-Departmental Labs",
    type: "Non-Dept Lab",
    label: "Mecha Lab (MECHA-LAB)",
    shortLabel: "Mecha Lab",
    rooms: "Mecha Lab (MECHA-LAB)",
    hint: "Non-Departmental laboratory facility: Mecha Lab (MECHA-LAB).",
    badgeBg: "#F0FDF4",
    badgeColor: "#166534",
    badgeBorder: "#BBF7D0",
  },
  no_room: {
    category: "Project & Thesis",
    type: "Individual Supervision",
    label: "No Physical Room Needed (Individual Faculty Supervision)",
    shortLabel: "No Room Needed",
    rooms: "Individual Faculty Supervision (CSE 3200 / CSE 4000)",
    hint: "No physical classroom or lab required. Supervised individually by faculty members.",
    badgeBg: "#F1F5F9",
    badgeColor: "#475569",
    badgeBorder: "#CBD5E1",
  },
};

function getRoomKindMeta(kind) {
  let k = (kind || "theory").toLowerCase();
  if (k === "seminar") k = "seminar_501";
  if (k === "year1_theory") k = "theory";
  if (k === "year1_cse_lab" || k === "ai_lab" || k === "network_lab") k = "cse_lab";
  if (k === "none" || k === "") k = "no_room";
  return (
    ROOM_KIND_META[k] || {
      category: "Other Facility",
      type: "Classroom / Lab",
      label: kind,
      shortLabel: kind,
      rooms: kind,
      hint: `Allocated to ${kind}`,
      badgeBg: "#F1F5F9",
      badgeColor: "#334155",
      badgeBorder: "#E2E8F0",
    }
  );
}

// -----------------------------------------------------------------------------
// Specific Room Assignment State & UI for Course Modal
// -----------------------------------------------------------------------------

let courseRoomState = {
  mode: "default", // "default" or "custom"
  showAll: false,
  selectedRooms: new Set(),
};

function setCourseRoomMode(mode) {
  courseRoomState.mode = mode;
  const btnDefault = document.getElementById("btn-room-mode-default");
  const btnCustom = document.getElementById("btn-room-mode-custom");
  const defaultDesc = document.getElementById("room-mode-default-desc");
  const customContainer = document.getElementById("room-mode-custom-container");

  if (mode === "custom") {
    if (btnDefault) {
      btnDefault.classList.remove("active");
      btnDefault.style.background = "transparent";
      btnDefault.style.color = "#475569";
      btnDefault.style.boxShadow = "none";
    }
    if (btnCustom) {
      btnCustom.classList.add("active");
      btnCustom.style.background = "#FFFFFF";
      btnCustom.style.color = "#1E40AF";
      btnCustom.style.boxShadow = "0 1px 3px rgba(0,0,0,0.12)";
    }
    if (defaultDesc) defaultDesc.style.display = "none";
    if (customContainer) customContainer.style.display = "block";
    renderCourseRoomSelection(document.getElementById("course-room-kind")?.value || "theory");
  } else {
    if (btnCustom) {
      btnCustom.classList.remove("active");
      btnCustom.style.background = "transparent";
      btnCustom.style.color = "#475569";
      btnCustom.style.boxShadow = "none";
    }
    if (btnDefault) {
      btnDefault.classList.add("active");
      btnDefault.style.background = "#FFFFFF";
      btnDefault.style.color = "#1E40AF";
      btnDefault.style.boxShadow = "0 1px 3px rgba(0,0,0,0.12)";
    }
    if (customContainer) customContainer.style.display = "none";
    if (defaultDesc) defaultDesc.style.display = "block";
  }
  updateCourseRoomsSummary();
}

function toggleShowAllDepartmentRooms() {
  courseRoomState.showAll = !courseRoomState.showAll;
  const btn = document.getElementById("btn-toggle-all-rooms");
  if (btn) {
    btn.innerHTML = courseRoomState.showAll ? "🎯 Category Only" : "🌐 Show All Rooms";
  }
  const heading = document.getElementById("course-specific-rooms-heading");
  if (heading) {
    heading.textContent = courseRoomState.showAll ? "All Department Rooms & Labs:" : "Available Category Rooms:";
  }
  renderCourseRoomSelection(document.getElementById("course-room-kind")?.value || "theory");
}

function renderCourseRoomSelection(roomKind = "theory", initialSelected = null) {
  const container = document.getElementById("group-course-room-selection");
  const grid = document.getElementById("course-specific-rooms-grid");
  if (!grid) return;

  let rk = (roomKind || "theory").toLowerCase();
  if (rk === "seminar") rk = "seminar_501";
  if (rk === "year1_theory") rk = "theory";
  if (rk === "year1_cse_lab" || rk === "ai_lab" || rk === "network_lab") rk = "cse_lab";

  if (rk === "no_room") {
    if (container) container.style.display = "none";
    return;
  }
  if (container) container.style.display = "block";

  if (initialSelected !== null) {
    courseRoomState.selectedRooms = new Set(initialSelected);
  }

  const allRooms = (state.rooms || []).filter((r) => r.id !== "NO_ROOM");
  let filteredRooms = [];

  if (courseRoomState.showAll) {
    filteredRooms = allRooms;
  } else {
    if (rk === "theory") {
      filteredRooms = allRooms.filter((r) => r.kind === "theory");
    } else if (rk === "seminar_501") {
      filteredRooms = allRooms.filter((r) => r.id === "CSE-501" || r.kind === "theory");
    } else if (rk === "cse_lab") {
      filteredRooms = allRooms.filter((r) =>
        ["CSE-103", "CSE-104", "CSE-201", "CSE-202", "CSE-305", "CSE-306"].includes(r.id) || r.kind === "cse_lab"
      );
    } else if (rk === "hardware_lab_107" || rk === "hardware_lab_108") {
      filteredRooms = allRooms.filter((r) =>
        ["CSE-107", "CSE-108"].includes(r.id) || (r.kind && r.kind.includes("hardware"))
      );
    } else if (["chem_lab", "hum_lab", "phy_lab", "ece_lab", "eee_lab", "mecha_lab"].includes(rk)) {
      filteredRooms = allRooms.filter((r) => r.kind === rk || (r.kind && r.kind.includes("lab")));
    } else {
      filteredRooms = allRooms.filter((r) => r.kind === rk);
    }
    if (filteredRooms.length === 0) {
      filteredRooms = allRooms;
    }
  }

  // Preserve any currently selected rooms in display even if not in the category filter
  const currentSelectedSet = courseRoomState.selectedRooms;
  const roomMap = new Map();
  filteredRooms.forEach((r) => roomMap.set(r.id, r));
  allRooms.forEach((r) => {
    if (currentSelectedSet.has(r.id) && !roomMap.has(r.id)) {
      roomMap.set(r.id, r);
    }
  });

  const displayRooms = Array.from(roomMap.values());
  displayRooms.sort((a, b) => a.id.localeCompare(b.id));

  grid.innerHTML = displayRooms
    .map((r) => {
      const isSel = currentSelectedSet.has(r.id);
      return `
        <div class="room-checkbox-pill ${isSel ? "selected" : ""}" id="room-pill-${r.id}" onclick="toggleRoomPill(event, '${r.id}')">
          <input type="checkbox" id="cr-room-${r.id}" value="${r.id}" ${isSel ? "checked" : ""} onclick="event.stopPropagation(); onRoomCheckboxToggle('${r.id}', this.checked)">
          <div class="room-pill-info">
            <div class="room-pill-name" title="${escapeHtml(r.name)}">${escapeHtml(r.name)}</div>
            <div class="room-pill-sub">
              <span class="room-cap-badge">Cap: ${r.capacity}</span>
              <span>${escapeHtml(r.id)}</span>
            </div>
          </div>
        </div>
      `;
    })
    .join("");

  updateCourseRoomsSummary();
}

function toggleRoomPill(event, roomId) {
  const cb = document.getElementById(`cr-room-${roomId}`);
  if (!cb) return;
  cb.checked = !cb.checked;
  onRoomCheckboxToggle(roomId, cb.checked);
}

function onRoomCheckboxToggle(roomId, isChecked) {
  if (isChecked) {
    courseRoomState.selectedRooms.add(roomId);
  } else {
    courseRoomState.selectedRooms.delete(roomId);
  }
  const pill = document.getElementById(`room-pill-${roomId}`);
  if (pill) {
    if (isChecked) pill.classList.add("selected");
    else pill.classList.remove("selected");
  }
  updateCourseRoomsSummary();
}

function selectAllCourseRooms(checkAll) {
  const cbs = document.querySelectorAll("#course-specific-rooms-grid input[type='checkbox']");
  cbs.forEach((cb) => {
    cb.checked = checkAll;
    const rid = cb.value;
    if (checkAll) courseRoomState.selectedRooms.add(rid);
    else courseRoomState.selectedRooms.delete(rid);
    const pill = document.getElementById(`room-pill-${rid}`);
    if (pill) {
      if (checkAll) pill.classList.add("selected");
      else pill.classList.remove("selected");
    }
  });
  updateCourseRoomsSummary();
}

function updateCourseRoomsSummary() {
  const summaryEl = document.getElementById("course-rooms-selection-summary");
  if (!summaryEl) return;

  if (courseRoomState.mode !== "custom") {
    summaryEl.innerHTML = "";
    return;
  }

  const selectedIds = Array.from(courseRoomState.selectedRooms);
  if (selectedIds.length === 0) {
    summaryEl.innerHTML = `
      <span style="color: #DC2626; display: inline-flex; align-items: center; gap: 0.25rem;">
        ⚠️ No rooms selected! Please select at least 1 room, or switch back to "All Category Rooms".
      </span>
    `;
    return;
  }

  const names = selectedIds.map((id) => {
    const r = (state.rooms || []).find((rm) => rm.id === id);
    return r ? r.name : id;
  });

  summaryEl.innerHTML = `
    <span style="color: #1D4ED8; display: inline-flex; align-items: center; gap: 0.25rem;">
      ✓ Assigned (${selectedIds.length} room${selectedIds.length > 1 ? "s" : ""}): <b>${escapeHtml(names.join(", "))}</b>
    </span>
  `;
}

function getSelectedCourseRooms() {
  return Array.from(courseRoomState.selectedRooms);
}

// Ensure global accessibility for inline HTML onclick handlers
window.courseRoomState = courseRoomState;
window.setCourseRoomMode = setCourseRoomMode;
window.toggleShowAllDepartmentRooms = toggleShowAllDepartmentRooms;
window.renderCourseRoomSelection = renderCourseRoomSelection;
window.selectAllCourseRooms = selectAllCourseRooms;
window.onRoomCheckboxToggle = onRoomCheckboxToggle;
window.toggleRoomPill = toggleRoomPill;
window.getSelectedCourseRooms = getSelectedCourseRooms;

document.addEventListener("DOMContentLoaded", () => {
  const btnDef = document.getElementById("btn-room-mode-default");
  const btnCust = document.getElementById("btn-room-mode-custom");
  if (btnDef) btnDef.addEventListener("click", () => setCourseRoomMode("default"));
  if (btnCust) btnCust.addEventListener("click", () => setCourseRoomMode("custom"));
});

function updateRoomKindHint() {
  const select = document.getElementById("course-room-kind");
  const hintEl = document.getElementById("course-room-hint");
  if (!select || !hintEl) return;
  const meta = getRoomKindMeta(select.value);
  hintEl.innerHTML = `
    <span style="font-weight: 600; color: var(--navy-deep);">Category:</span> <b>${escapeHtml(meta.category)}</b> &bull;
    <span style="font-weight: 600; color: var(--navy-deep);">Type:</span> <b>${escapeHtml(meta.type)}</b><br>
    <span style="color: var(--text-muted);">${escapeHtml(meta.hint)}</span>
  `;
  renderCourseRoomSelection(select.value);
}

function renderCourses() {
  const container = document.getElementById("courses-container");
  if (!container) return;

  const search = (document.getElementById("course-search-input")?.value || "").toLowerCase().trim();
  const batchFilter = document.getElementById("course-batch-select")?.value || "";
  const categoryFilter = document.getElementById("course-category-select")?.value || "";
  const statusFilter = document.getElementById("course-status-select")?.value || "";

  const filtered = state.courses.filter((c) => {
    if (batchFilter && c.batch_id !== batchFilter) return false;
    if (categoryFilter && c.category !== categoryFilter) return false;
    if (search) {
      const matchCode = c.id.toLowerCase().includes(search);
      const matchTitle = c.title.toLowerCase().includes(search);
      if (!matchCode && !matchTitle) return false;
    }
    return true;
  });

  // Group by batch
  const byBatch = {};
  state.batches.forEach((b) => (byBatch[b.id] = []));
  filtered.forEach((c) => {
    if (!byBatch[c.batch_id]) byBatch[c.batch_id] = [];
    byBatch[c.batch_id].push(c);
  });

  let html = "";
  for (const b of state.batches) {
    if (batchFilter && b.id !== batchFilter) continue;
    if (statusFilter && b.status !== statusFilter) continue;

    const list = byBatch[b.id] || [];
    if (list.length === 0 && (search || categoryFilter)) continue;

    const isRunning = b.status === "on";
    const statusBtn = isRunning
      ? `<button type="button" class="term-status-btn on" onclick="toggleBatchStatus('${b.id}', 'on')" title="Click to toggle status to OFF"><span class="status-dot dot-on"></span> Term: <b>ON (Running)</b></button>`
      : `<button type="button" class="term-status-btn off" onclick="toggleBatchStatus('${b.id}', 'off')" title="Click to toggle status to ON"><span class="status-dot dot-off"></span> Term: <b>OFF (Inactive)</b></button>`;

    const inactiveBanner = !isRunning
      ? `<div class="batch-inactive-banner"><span>⚪</span> <span>This term is currently <b>OFF (Inactive)</b>. Only course details (code, title, credit) are displayed with <b>no teachers assigned</b>. Courses are hidden from Assignments. Click status to turn ON.</span></div>`
      : "";

    // Build table rows (with optional category grouping for 4-2)
    let tbodyHtml = "";
    if (list.length === 0) {
      tbodyHtml = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No courses in this batch.</td></tr>`;
    } else if (b.id === "4-2" && !categoryFilter) {
      const coreCourses = list.filter((c) => c.category === "core" || !c.category);
      const opt2Courses = list.filter((c) => c.category === "optional_ii");
      const opt3Courses = list.filter((c) => c.category === "optional_iii");

      if (coreCourses.length > 0) {
        tbodyHtml += `<tr><td colspan="8" class="category-subheader"><span>📌 Core Compulsory Courses (${coreCourses.length})</span></td></tr>`;
        tbodyHtml += coreCourses.map((c) => renderCourseRow(b, c)).join("");
      }
      if (opt2Courses.length > 0) {
        tbodyHtml += `<tr><td colspan="8" class="category-subheader" style="color: #6B21A8; background: #FAF5FF;"><span>💡 Optional-II Elective Courses (${opt2Courses.length} Theory Courses)</span></td></tr>`;
        tbodyHtml += opt2Courses.map((c) => renderCourseRow(b, c)).join("");
      }
      if (opt3Courses.length > 0) {
        tbodyHtml += `<tr><td colspan="8" class="category-subheader" style="color: #0F766E; background: #F0FDFA;"><span>🔬 Optional-III Elective Courses (${opt3Courses.length} Theory + Lab Courses)</span></td></tr>`;
        tbodyHtml += opt3Courses.map((c) => renderCourseRow(b, c)).join("");
      }
    } else {
      tbodyHtml = list.map((c) => renderCourseRow(b, c)).join("");
    }

    html += `
      <div class="batch-section-card">
        <div class="batch-card-header">
          <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
            <h2>${escapeHtml(b.name)} <span style="font-size: 0.9rem; opacity: 0.85;">(${b.id})</span></h2>
            ${statusBtn}
          </div>
          <span class="badge" style="background: rgba(255,255,255,0.2); color: #FFF; font-weight: 600;">${list.length} courses</span>
        </div>
        ${inactiveBanner}
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width: 120px;">Code</th>
                <th>Course Title</th>
                <th style="width: 130px;">Type / Credit</th>
                <th style="width: 170px;">Assigned Teachers</th>
                <th style="width: 170px;">Slot Availability</th>
                <th style="width: 170px;">Room / Facility</th>
                <th style="width: 120px;">Weekly Load</th>
                <th style="text-align: right; width: 130px;">Actions</th>
              </tr>
            </thead>
            <tbody>
              ${tbodyHtml}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  container.innerHTML = html || `<div style="text-align: center; color: var(--text-muted); padding: 3rem;">No courses match the criteria.</div>`;
}

function renderCourseRow(batch, course) {
  const isTheory = course.kind === "theory";
  const is075 = course.credit === 0.75;
  const isOff = batch.status === "off";

  let kindBadge = "";
  if (isTheory) {
    kindBadge = `<span class="badge badge-theory">Theory</span>`;
  } else if (is075) {
    kindBadge = `<span class="badge" style="background: #FEF3C7; color: #92400E; font-weight: 700;">0.75 cr (bi-weekly)</span>`;
  } else {
    kindBadge = `<span class="badge badge-sessional">Sessional (${course.credit || 1.5} cr)</span>`;
  }

  let catBadge = "";
  if (course.category === "optional_ii") {
    catBadge = `<span class="badge badge-optional-ii" style="font-size: 0.7rem; margin-left: 0.35rem;">Optional-II</span>`;
  } else if (course.category === "optional_iii") {
    catBadge = `<span class="badge badge-optional-iii" style="font-size: 0.7rem; margin-left: 0.35rem;">Optional-III</span>`;
  } else if (course.category === "core") {
    catBadge = `<span class="badge badge-core" style="font-size: 0.7rem; margin-left: 0.35rem;">Core</span>`;
  }

  const pairedInfo = course.paired_course_id
    ? `<div style="font-size: 0.75rem; color: #5B21B6; font-weight: 600; margin-top: 0.2rem;">🔗 Paired: ${escapeHtml(course.paired_course_id)}</div>`
    : "";

  const isProject = course.id.replace(/[^a-zA-Z0-9]/g, "").toUpperCase().startsWith("CSE3200") || course.id.replace(/[^a-zA-Z0-9]/g, "").toUpperCase().startsWith("CSE4000");

  let teachersStr = "";
  if (isProject) {
    teachersStr = `<span class="badge" style="background: #EFF6FF; color: #1D4ED8; font-weight: 600;">Individual Supervision</span>`;
  } else if (isOff) {
    teachersStr = `<span class="badge" style="background: #F1F5F9; color: #64748B; border: 1px dashed #CBD5E1; font-weight: 500;">No Teacher Assigned (Term OFF)</span>`;
  } else {
    const t1 = state.teachers.find((t) => t.id === course.teacher1_id);
    const t2 = state.teachers.find((t) => t.id === course.teacher2_id);
    if (t1 && t2) {
      teachersStr = `<span style="font-weight: 600; color: var(--navy-deep);">${escapeHtml(t1.short_code)}</span> & <span style="font-weight: 600; color: var(--navy-deep);">${escapeHtml(t2.short_code)}</span>`;
    } else if (t1) {
      teachersStr = `<span style="font-weight: 600; color: var(--navy-deep);">${escapeHtml(t1.short_code)}</span>`;
    } else {
      teachersStr = '<span style="color: var(--text-muted); font-style: italic;">Unassigned</span>';
    }
  }

  // Slot Availability Button (Constraint 3)
  let availBtn = "";
  const hasRules = (course.slot_rule_count || 0) > 0;
  if (hasRules) {
    availBtn = `<button type="button" class="badge-avail-fixed" onclick="openCourseAvailabilityModal('${course.id}')" title="Configured: ${escapeHtml(course.slot_rule_summary || '')}"><span>📌</span> <span>${escapeHtml(course.slot_rule_summary || 'Fixed Slots')}</span></button>`;
  } else {
    availBtn = `<button type="button" class="btn btn-outline btn-sm" onclick="openCourseAvailabilityModal('${course.id}')" title="Click to fix or restrict slots for this course" style="font-size: 0.76rem; padding: 0.2rem 0.5rem; color: var(--navy);">⚡ Any Slot</button>`;
  }

  const loadStr = isProject
    ? `${course.blocks_per_week || 1} weekly slot(s) [Section-wide]`
    : (isTheory
        ? `${course.periods_per_week || 3} periods / wk`
        : (is075 ? `1 block / 2 wks` : `${course.blocks_per_week || 1} block / wk`));

  const displayCode = course.display_code || course.id;
  const meta = getRoomKindMeta(course.room_kind);

  return `
    <tr>
      <td><strong style="color: var(--navy-deep);">${escapeHtml(displayCode)}</strong></td>
      <td>
        <div style="font-weight: 600; display: flex; align-items: center; flex-wrap: wrap;">
          ${escapeHtml(course.title)}
          ${catBadge}
        </div>
        ${pairedInfo}
      </td>
      <td>${kindBadge}</td>
      <td>${teachersStr}</td>
      <td>${availBtn}</td>
      <td>
        ${(() => {
          if (course.allowed_rooms && course.allowed_rooms.length > 0) {
            const roomNames = course.allowed_rooms.map((rid) => {
              const r = (state.rooms || []).find((rm) => rm.id === rid);
              return r ? r.name : rid;
            });
            let shortDisplay = roomNames.join(", ");
            if (shortDisplay.length > 32) {
              shortDisplay = `${roomNames[0]} +${roomNames.length - 1} more`;
            }
            return `
              <span class="badge" style="background: #EEF2FF; color: #3730A3; border: 1px solid #C7D2FE; font-weight: 700; display: inline-flex; align-items: center; gap: 0.25rem;" title="Specific Assigned Rooms: ${escapeHtml(roomNames.join(', '))}">
                🎯 ${escapeHtml(shortDisplay)}
              </span>
              <div style="font-size: 0.72rem; color: #4F46E5; margin-top: 3px; font-weight: 600;">Specific Room Assignment</div>
            `;
          }
          return `
            <span class="badge" style="background: ${meta.badgeBg}; color: ${meta.badgeColor}; border: 1px solid ${meta.badgeBorder}; font-weight: 600;" title="${escapeHtml(meta.category)} • ${escapeHtml(meta.type)} (${escapeHtml(meta.rooms)})">
              ${escapeHtml(meta.shortLabel)}
            </span>
            <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 3px; font-weight: 500;">${escapeHtml(meta.category)}</div>
          `;
        })()}
      </td>
      <td style="color: var(--text-muted); font-size: 0.85rem;">${loadStr}</td>
      <td style="text-align: right;">
        <button class="btn btn-outline btn-sm" onclick="openCourseModal('${course.id}')">Edit</button>
        <button class="btn btn-danger-outline btn-sm" onclick="deleteCourse('${course.id}')">Delete</button>
      </td>
    </tr>
  `;
}

function toggleCourseKindFields(isUserSwitch = false) {
  const kind = document.getElementById("course-kind").value;
  const pGroup = document.getElementById("group-periods");
  const lGroup = document.getElementById("group-lab-credit");
  const roomKindSelect = document.getElementById("course-room-kind");

  if (kind === "theory") {
    pGroup.style.display = "block";
    if (lGroup) lGroup.style.display = "none";
    document.getElementById("group-paired-course").style.display = "none";
    if (isUserSwitch) {
      if (roomKindSelect.value !== "theory" && roomKindSelect.value !== "seminar_501" && roomKindSelect.value !== "no_room") {
        roomKindSelect.value = "theory";
      }
    }
  } else {
    pGroup.style.display = "none";
    if (lGroup) lGroup.style.display = "block";
    toggleLabCreditFields();
    if (isUserSwitch) {
      if (roomKindSelect.value === "theory") {
        roomKindSelect.value = "cse_lab";
      }
    }
  }
  updateRoomKindHint();
}

function toggleLabCreditFields() {
  const credit = document.getElementById("course-credit")?.value || "1.5";
  const pairedGroup = document.getElementById("group-paired-course");
  if (!pairedGroup) return;

  if (credit === "0.75") {
    pairedGroup.style.display = "block";
    populatePairedCourseOptions();
  } else {
    pairedGroup.style.display = "none";
  }
}

function populatePairedCourseOptions(selectedPairedId = "") {
  const pairedSelect = document.getElementById("course-paired-id");
  if (!pairedSelect) return;

  const currentBatch = document.getElementById("course-batch")?.value || "";
  const currentCid = document.getElementById("course-code")?.value.trim().toUpperCase() || "";

  const available = state.courses.filter(
    (c) => c.batch_id === currentBatch && c.kind === "sessional" && c.id !== currentCid
  );

  let html = '<option value="">-- None (Standalone alternating) --</option>';
  available.forEach((c) => {
    const isSelected = c.id === selectedPairedId || c.id === document.getElementById("course-paired-id")?.value;
    html += `<option value="${escapeHtml(c.id)}" ${isSelected ? "selected" : ""}>${escapeHtml(c.id)} - ${escapeHtml(c.title)}</option>`;
  });
  pairedSelect.innerHTML = html;
}

function handleModalBatchChange() {
  const batchId = document.getElementById("course-batch")?.value || "";
  const batch = state.batches.find((b) => b.id === batchId);
  const isOff = batch && batch.status === "off";

  const noticeEl = document.getElementById("course-modal-off-notice");
  const t1Select = document.getElementById("course-teacher1");
  const t2Select = document.getElementById("course-teacher2");

  if (noticeEl) noticeEl.style.display = isOff ? "block" : "none";
  if (t1Select) {
    t1Select.disabled = isOff;
    if (isOff) t1Select.value = "";
  }
  if (t2Select) {
    t2Select.disabled = isOff;
    if (isOff) t2Select.value = "";
  }
}

function openCourseModal(courseId = null) {
  state.editingCourseId = courseId;
  const modal = document.getElementById("modal-course");
  const title = document.getElementById("modal-course-title");
  const form = document.getElementById("form-course");
  const codeInput = document.getElementById("course-code");

  form.reset();

  const t1Select = document.getElementById("course-teacher1");
  const t2Select = document.getElementById("course-teacher2");

  if (courseId) {
    const course = state.courses.find((c) => c.id === courseId);
    if (course) {
      title.textContent = "Edit Course";
      codeInput.value = course.id;
      codeInput.disabled = true;
      document.getElementById("course-title").value = course.title;
      document.getElementById("course-batch").value = course.batch_id;
      if (document.getElementById("course-category")) {
        document.getElementById("course-category").value = course.category || "core";
      }
      document.getElementById("course-kind").value = course.kind;
      let rk = course.room_kind || "theory";
      if (rk === "seminar") rk = "seminar_501";
      if (rk === "year1_theory") rk = "theory";
      if (rk === "year1_cse_lab" || rk === "ai_lab" || rk === "network_lab") rk = "cse_lab";
      if (rk === "none" || rk === "") rk = "no_room";
      document.getElementById("course-room-kind").value = rk;
      document.getElementById("course-periods").value = course.periods_per_week || 3;
      if (document.getElementById("course-credit")) {
        document.getElementById("course-credit").value = String(course.credit || (course.blocks_per_week === 2 ? 3.0 : 1.5));
      }

      toggleCourseKindFields();
      updateRoomKindHint();
      populatePairedCourseOptions(course.paired_course_id);
      handleModalBatchChange();

      if (course.allowed_rooms && course.allowed_rooms.length > 0) {
        setCourseRoomMode("custom");
        renderCourseRoomSelection(rk, course.allowed_rooms);
      } else {
        setCourseRoomMode("default");
        renderCourseRoomSelection(rk, []);
      }

      if (t1Select) t1Select.innerHTML = '<option value="">-- Select Teacher 1 --</option>' + buildTeacherOptionsHtml(course.teacher1_id);
      if (t2Select) t2Select.innerHTML = '<option value="">-- Select Teacher 2 --</option>' + buildTeacherOptionsHtml(course.teacher2_id);
    }
  } else {
    title.textContent = "Add Course";
    codeInput.disabled = false;
    document.getElementById("course-periods").value = 3;
    if (document.getElementById("course-credit")) {
      document.getElementById("course-credit").value = "1.5";
    }
    if (document.getElementById("course-category")) {
      document.getElementById("course-category").value = "core";
    }
    document.getElementById("course-kind").value = "theory";
    document.getElementById("course-room-kind").value = "theory";

    toggleCourseKindFields();
    updateRoomKindHint();
    populatePairedCourseOptions("");
    handleModalBatchChange();

    setCourseRoomMode("default");
    renderCourseRoomSelection("theory", []);

    if (t1Select) t1Select.innerHTML = '<option value="">-- Select Teacher 1 --</option>' + buildTeacherOptionsHtml("");
    if (t2Select) t2Select.innerHTML = '<option value="">-- Select Teacher 2 --</option>' + buildTeacherOptionsHtml("");
  }

  modal.classList.add("open");
}

function closeCourseModal() {
  document.getElementById("modal-course").classList.remove("open");
  state.editingCourseId = null;
}

async function handleCourseSubmit(e) {
  e.preventDefault();
  const id = document.getElementById("course-code").value.trim().toUpperCase();
  const title = document.getElementById("course-title").value.trim();
  const batch_id = document.getElementById("course-batch").value;
  const category = document.getElementById("course-category")?.value || "core";
  const kind = document.getElementById("course-kind").value;
  let room_kind = document.getElementById("course-room-kind").value;
  if (room_kind === "seminar") room_kind = "seminar_501";
  if (room_kind === "year1_theory") room_kind = "theory";
  if (room_kind === "year1_cse_lab" || room_kind === "ai_lab" || room_kind === "network_lab") room_kind = "cse_lab";
  if (room_kind === "none" || !room_kind) room_kind = "no_room";
  const periods_per_week = kind === "theory" ? parseInt(document.getElementById("course-periods").value, 10) : null;

  let credit = 3.0;
  let blocks_per_week = null;
  let paired_course_id = null;

  if (kind === "sessional") {
    credit = parseFloat(document.getElementById("course-credit")?.value || "1.5");
    blocks_per_week = credit === 3.0 ? 2 : 1;
    paired_course_id = credit === 0.75 ? (document.getElementById("course-paired-id")?.value || null) : null;
  }

  const batch = state.batches.find((b) => b.id === batch_id);
  const isOff = batch && batch.status === "off";

  const teacher1_id = isOff ? null : (document.getElementById("course-teacher1")?.value || null);
  const teacher2_id = isOff ? null : (document.getElementById("course-teacher2")?.value || null);

  let allowed_rooms = null;
  if (room_kind === "no_room") {
    allowed_rooms = [];
  } else if (courseRoomState.mode === "custom") {
    allowed_rooms = getSelectedCourseRooms();
    if (allowed_rooms.length === 0) {
      showToast("Please select at least one specific room or switch to 'All Category Rooms' mode.", true);
      return;
    }
  } else {
    allowed_rooms = [];
  }

  const payload = {
    id,
    title,
    batch_id,
    category,
    kind,
    room_kind,
    allowed_rooms,
    periods_per_week,
    blocks_per_week,
    credit,
    paired_course_id,
    teacher1_id,
    teacher2_id,
  };

  try {
    let res;
    if (state.editingCourseId) {
      res = await fetch(`/api/courses/${state.editingCourseId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      res = await fetch("/api/courses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }

    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || "Failed to save course");
    }

    await loadCourses();
    closeCourseModal();
    showToast(state.editingCourseId ? "Course updated" : "Course added");
  } catch (err) {
    showToast(`Error: ${err.message}`, true);
  }
}

async function deleteCourse(courseId) {
  if (!window.DISABLE_CONFIRM && !confirm(`Are you sure you want to delete course ${courseId}? This will remove its assignments.`)) {
    return;
  }
  try {
    const res = await fetch(`/api/courses/${courseId}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Failed to delete course");

    state.courses = state.courses.filter((c) => c.id !== courseId);
    populateAssignCourseDropdown();
    renderCourses();
    renderAssignments();
    showToast("Course deleted");
  } catch (err) {
    showToast(`Error: ${err.message}`, true);
  }
}

// -----------------------------------------------------------------------------
// Rooms & Laboratories API & Management
// -----------------------------------------------------------------------------

async function loadRooms() {
  try {
    const res = await fetch("/api/rooms");
    if (!res.ok) throw new Error("Failed to load rooms");
    state.rooms = await res.json();
    renderRooms();
  } catch (err) {
    showToast(`Error loading rooms: ${err.message}`, true);
  }
}

function renderRooms() {
  const tbody = document.getElementById("rooms-tbody");
  if (!tbody) return;

  const search = (document.getElementById("room-search-input")?.value || "").toLowerCase().trim();
  const categoryFilter = document.getElementById("room-category-filter")?.value || "";
  const kindFilter = document.getElementById("room-kind-filter")?.value || "";

  const filtered = state.rooms.filter((r) => {
    if (categoryFilter && r.category !== categoryFilter) return false;
    if (kindFilter && r.kind !== kindFilter) return false;
    if (search) {
      const matchCode = (r.room_code || "").toLowerCase().includes(search);
      const matchName = (r.name || "").toLowerCase().includes(search);
      const matchKind = (r.kind || "").toLowerCase().includes(search);
      if (!matchCode && !matchName && !matchKind) return false;
    }
    return true;
  });

  const countEl = document.getElementById("rooms-count");
  if (countEl) countEl.textContent = filtered.length;

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; color: var(--text-dim); padding: 2rem;">
          No classrooms or laboratories found matching your criteria.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered
    .map((room) => {
      let catClass = "badge-cse";
      if (room.category === "Theory Classrooms") catClass = "badge-navy";
      else if (room.category === "Departmental Labs") catClass = "badge-primary";
      else if (room.category === "Non-Departmental Labs") catClass = "badge-warning";
      const roomCode = room.room_code || room.id || "";

      return `
        <tr>
          <td><b>${escapeHtml(roomCode)}</b></td>
          <td>${escapeHtml(room.name)}</td>
          <td><span class="badge ${catClass}">${escapeHtml(room.category || "")}</span></td>
          <td><code>${escapeHtml(room.kind)}</code></td>
          <td><span style="font-weight: 600; color: #334155;">${room.capacity || 70}</span> seats</td>
          <td style="text-align: right; white-space: nowrap;">
            <button class="btn btn-sm btn-outline" onclick="openRoomModal('${room.id}')" title="Edit Room">
              Edit
            </button>
            <button class="btn btn-sm btn-danger" onclick="deleteRoom('${room.id}', '${escapeHtml(roomCode)}')" title="Delete Room" style="margin-left: 0.35rem;">
              Delete
            </button>
          </td>
        </tr>
      `;
    })
    .join("");
}

function filterRooms() {
  renderRooms();
}

function handleRoomCategoryChange() {
  const cat = document.getElementById("room-category")?.value;
  const kindSelect = document.getElementById("room-kind");
  const capInput = document.getElementById("room-capacity");
  if (!cat || !kindSelect || !capInput) return;

  if (cat === "Theory Classrooms") {
    kindSelect.value = "theory";
    capInput.value = 70;
  } else if (cat === "Departmental Labs") {
    kindSelect.value = "cse_lab";
    capInput.value = 35;
  } else if (cat === "Non-Departmental Labs") {
    kindSelect.value = "chem_lab";
    capInput.value = 35;
  }
}

function openRoomModal(roomId = null) {
  state.editingRoomId = roomId;
  const modal = document.getElementById("modal-room");
  const title = document.getElementById("modal-room-title");
  if (!modal) return;

  if (roomId) {
    const room = state.rooms.find((r) => r.id === roomId);
    if (!room) return;
    if (title) title.textContent = "Edit Room / Laboratory";
    document.getElementById("room-code").value = room.room_code || room.id || "";
    document.getElementById("room-name").value = room.name;
    document.getElementById("room-category").value = room.category || "Theory Classrooms";
    document.getElementById("room-kind").value = room.kind;
    document.getElementById("room-capacity").value = room.capacity || 70;
  } else {
    if (title) title.textContent = "Add Classroom or Laboratory";
    document.getElementById("room-code").value = "";
    document.getElementById("room-name").value = "";
    document.getElementById("room-category").value = "Theory Classrooms";
    document.getElementById("room-kind").value = "theory";
    document.getElementById("room-capacity").value = 70;
  }

  modal.classList.add("open");
}

function closeRoomModal() {
  const modal = document.getElementById("modal-room");
  if (modal) modal.classList.remove("open");
  state.editingRoomId = null;
}

async function handleSaveRoom(event) {
  event.preventDefault();
  const room_code = document.getElementById("room-code").value.trim();
  const name = document.getElementById("room-name").value.trim();
  const category = document.getElementById("room-category").value;
  const kind = document.getElementById("room-kind").value;
  const capacity = parseInt(document.getElementById("room-capacity").value, 10) || 70;

  if (!room_code || !name) {
    showToast("Please enter both Room Code and Display Name", true);
    return;
  }

  try {
    let res;
    if (state.editingRoomId) {
      res = await fetch(`/api/rooms/${state.editingRoomId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, kind, capacity }),
      });
    } else {
      res = await fetch("/api/rooms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: room_code, name, kind, capacity }),
      });
    }

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "Failed to save room");
    }

    closeRoomModal();
    await loadRooms();
    showToast(`✓ Room "${room_code}" saved successfully`);
  } catch (err) {
    showToast(`Error: ${err.message}`, true);
  }
}

async function deleteRoom(roomId, roomCode) {
  if (!confirm(`Are you sure you want to delete room "${roomCode}"?`)) {
    return;
  }
  try {
    const res = await fetch(`/api/rooms/${roomId}`, { method: "DELETE" });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "Failed to delete room");
    }
    await loadRooms();
    showToast(`Room "${roomCode}" deleted successfully`);
  } catch (err) {
    showToast(`Error: ${err.message}`, true);
  }
}

// -----------------------------------------------------------------------------
// Assignments (The Core Screen)
// -----------------------------------------------------------------------------

async function loadAssignments() {
  try {
    const res = await fetch("/api/assignments");
    if (!res.ok) throw new Error("Failed to load assignments");
    state.assignments = await res.json();
  } catch (err) {
    showToast(`Error loading assignments: ${err.message}`, true);
  }
}

async function loadAssignmentsData() {
  await Promise.all([loadTeachers(), loadCourses(), loadAssignments()]);
  renderAssignments();
}

function renderAssignments() {
  const container = document.getElementById("assignments-container");
  if (!container) return;

  const batchFilter = document.getElementById("assign-batch-select")?.value || "";
  const courseFilter = document.getElementById("assign-course-select")?.value || "";
  const search = (document.getElementById("assign-search-input")?.value || "").toLowerCase().trim();

  // Index assignments by key: `${course_id}|${section}|${group || ''}`
  const assignMap = {};
  state.assignments.forEach((a) => {
    const key = `${a.course_id}|${a.section}|${a.group || ""}`;
    if (!assignMap[key]) assignMap[key] = [];
    assignMap[key].push(a);
  });

  // ONLY render batches where status == 'on'! Inactive terms are hidden per requirements.
  const activeBatches = state.batches.filter((b) => b.status === "on");

  let html = "";
  for (const b of activeBatches) {
    if (batchFilter && b.id !== batchFilter) continue;

    const batchCourses = state.courses.filter((c) => {
      if (c.batch_id !== b.id) return false;
      if (courseFilter && c.id !== courseFilter) return false;
      if (search) {
        const matchCode = c.id.toLowerCase().includes(search);
        const matchTitle = c.title.toLowerCase().includes(search);
        const t1 = state.teachers.find((t) => t.id === c.teacher1_id);
        const t2 = state.teachers.find((t) => t.id === c.teacher2_id);
        const matchT1 = t1 && (t1.full_name.toLowerCase().includes(search) || t1.short_code.toLowerCase().includes(search));
        const matchT2 = t2 && (t2.full_name.toLowerCase().includes(search) || t2.short_code.toLowerCase().includes(search));
        return matchCode || matchTitle || matchT1 || matchT2;
      }
      return true;
    });

    if (batchCourses.length === 0) continue;

    html += `
      <div class="batch-section-card" id="assign-card-${b.id}">
        <div class="batch-card-header">
          <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
            <h2>${escapeHtml(b.name)} (${b.id}) — Course Assignments</h2>
            <span class="badge" style="background: #ECFDF5; color: #065F46; border: 1px solid #A7F3D0; font-weight: 700;">🟢 Running Term</span>
          </div>
          <span class="badge" style="background: rgba(255,255,255,0.2); color: #FFF; font-weight: 600;">${batchCourses.length} courses</span>
        </div>
        <div>
          ${batchCourses
            .map((c) => renderCourseAssignmentCard(b, c, assignMap))
            .join("")}
        </div>
      </div>
    `;
  }

  container.innerHTML = html || `<div style="text-align: center; color: var(--text-muted); padding: 3rem;">No active courses match the criteria. (Note: Only running terms with Status 'ON' appear in Assignments).</div>`;
}

function renderCourseAssignmentCard(batch, course, assignMap) {
  const isTheory = course.kind === "theory";
  const is075 = course.credit === 0.75;
  let kindBadge = "";
  if (isTheory) {
    kindBadge = `<span class="badge badge-theory">Theory (${course.periods_per_week || 3}/wk)</span>`;
  } else if (is075) {
    kindBadge = `<span class="badge" style="background: #FEF3C7; color: #92400E; font-weight: 700;">Sessional (0.75 cr · Bi-weekly)</span>`;
  } else {
    kindBadge = `<span class="badge badge-sessional">Sessional (${course.credit || 1.5} cr)</span>`;
  }

  let catBadge = "";
  if (course.category === "optional_ii") {
    catBadge = `<span class="badge badge-optional-ii">Optional-II</span>`;
  } else if (course.category === "optional_iii") {
    catBadge = `<span class="badge badge-optional-iii">Optional-III</span>`;
  } else if (course.category === "core") {
    catBadge = `<span class="badge badge-core">Core</span>`;
  }

  const pairedBadge = course.paired_course_id
    ? `<span class="badge" style="background: #EDE9FE; color: #5B21B6; font-weight: 600;">🔗 Paired with ${escapeHtml(course.paired_course_id)}</span>`
    : "";

  const t1 = course.teacher1_id || "";
  const t2 = course.teacher2_id || "";

  const teacher1 = state.teachers.find((t) => t.id === t1);
  const teacher2 = state.teachers.find((t) => t.id === t2);
  const isLeave1 = teacher1?.status === "on_leave";
  const isLeave2 = teacher2?.status === "on_leave";

  const opts1 = buildTeacherOptionsHtml(t1);
  const opts2 = buildTeacherOptionsHtml(t2);

  const warn1 = isLeave1
    ? `<div class="warning-box"><span>⚠️</span> <span>Warning: <b>${escapeHtml(teacher1.full_name)}</b> is marked <b>ON LEAVE</b>!</span></div>`
    : "";
  const warn2 = isLeave2
    ? `<div class="warning-box"><span>⚠️</span> <span>Warning: <b>${escapeHtml(teacher2.full_name)}</b> is marked <b>ON LEAVE</b>!</span></div>`
    : "";

  const safeCid = course.id.replace(/[^a-zA-Z0-9]/g, "_");
  const isProject = course.id.replace(/[^a-zA-Z0-9]/g, "").toUpperCase().startsWith("CSE3200") || course.id.replace(/[^a-zA-Z0-9]/g, "").toUpperCase().startsWith("CSE4000");

  if (isProject) {
    const dispCode = course.display_code || (course.id.includes("3200") ? "CSE 3200" : "CSE 4000");
    const weeklySlotCount = course.blocks_per_week || (course.credit === 3.0 ? 2 : 1);
    return `
      <div class="course-card" id="assign-card-${safeCid}">
        <div class="course-card-header">
          <div class="course-title-group" style="display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;">
            <span class="course-code">${escapeHtml(dispCode)}</span>
            <span class="course-name">${escapeHtml(course.title)}</span>
            ${catBadge}
            <span class="badge" style="background: #EFF6FF; color: #1D4ED8; font-weight: 700;">${course.credit || 1.5} cr · ${weeklySlotCount} weekly slot(s)</span>
            <span class="badge" style="background: #ECFDF5; color: #047857; font-weight: 700;">Section-Wide (Not Group-Wise)</span>
          </div>
        </div>
        <div style="margin-top: 0.75rem; padding: 0.85rem 1rem; background: #F0FDF4; border-radius: var(--radius); border-left: 4px solid #10B981; font-size: 0.85rem; color: #065F46; line-height: 1.5;">
          🎓 <b>Individual Faculty Supervision (No Room Needed):</b> This course is conducted by individually assigned faculty supervisors (1–2 students per supervisor). No classroom teachers or physical rooms are assigned. The scheduler automatically allocates ${weeklySlotCount} weekly 3-period slot(s) for each section (Section A and Section B, both groups combinedly) with no room assigned. In the timetable, only the course code <b>${escapeHtml(dispCode)}</b> is displayed without teacher names or rooms.
        </div>
      </div>
    `;
  }

  const pw = course.periods_per_week || 3;
  const theoryHint =
    pw === 2
      ? `<b>Co-teaching Model (Both Section A & B):</b> Teachers are assigned to the whole course, not per-section. Both sections receive 2 periods/week: 1 personal class by Teacher 1 and 1 personal class by Teacher 2 (if assigned) for each section.`
      : pw === 1
        ? `<b>Co-teaching Model (Both Section A & B):</b> Both sections receive 1 period/week taught by Teacher 1.`
        : `<b>Co-teaching Model (Both Section A & B):</b> Teachers are assigned to the whole course, not per-section. Both sections receive ${pw} periods/week: 1 personal class by Teacher 1, 1 personal class by Teacher 2, and ${pw - 2} shared class(es) (T1/T2) for each section.`;

  const ruleHint = isTheory
    ? theoryHint
    : (is075
        ? `<b>0.75 Credit Bi-weekly Lab:</b> Co-taught by Teacher 1 + Teacher 2. Students attend 1 session every 2 weeks${course.paired_course_id ? ` (alternating with ${escapeHtml(course.paired_course_id)})` : ''}.`
        : `<b>Co-teaching Model:</b> Both teachers co-teach laboratory sessions across all sections and groups.`);

  const roomMeta = getRoomKindMeta(course.room_kind);

  return `
    <div class="course-card" id="assign-card-${safeCid}">
      <div class="course-card-header">
        <div class="course-title-group" style="display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;">
          <span class="course-code">${escapeHtml(course.id)}</span>
          <span class="course-name">${escapeHtml(course.title)}</span>
          ${catBadge}
          ${kindBadge}
          ${pairedBadge}
          <span class="badge" style="background: ${roomMeta.badgeBg}; color: ${roomMeta.badgeColor}; border: 1px solid ${roomMeta.badgeBorder}; font-weight: 600;" title="${escapeHtml(roomMeta.category)} • ${escapeHtml(roomMeta.type)} (${escapeHtml(roomMeta.rooms)})">🏛️ ${escapeHtml(roomMeta.label)}</span>
        </div>
      </div>

      <div class="slot-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-top: 0.75rem;">
        <div class="slot-box">
          <div class="slot-box-header">
            <span class="slot-tag">Teacher 1 (Primary)</span>
            <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600;">
              ${isTheory ? '1st Personal Theory Class' : 'Lab Co-Teacher'}
            </span>
          </div>
          <select id="sel1_${safeCid}" onchange="handleCourseTeachersChange('${escapeHtml(course.id)}')">
            <option value="">-- Unassigned --</option>
            ${opts1}
          </select>
          ${warn1}
        </div>

        <div class="slot-box">
          <div class="slot-box-header">
            <span class="slot-tag">Teacher 2 (Co-Teacher)</span>
            <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600;">
              ${isTheory ? '2nd Personal Theory Class' : 'Lab Co-Teacher'}
            </span>
          </div>
          <select id="sel2_${safeCid}" onchange="handleCourseTeachersChange('${escapeHtml(course.id)}')">
            <option value="">-- None / Unassigned --</option>
            ${opts2}
          </select>
          ${warn2}
        </div>
      </div>

      <div style="margin-top: 0.75rem; padding: 0.6rem 0.85rem; background: #F8FAFC; border-radius: var(--radius); border-left: 3px solid var(--navy); font-size: 0.8rem; color: var(--navy-deep);">
        ℹ️ ${ruleHint}
      </div>
    </div>
  `;
}

async function handleCourseTeachersChange(courseId) {
  const safeCid = courseId.replace(/[^a-zA-Z0-9]/g, "_");
  const sel1 = document.getElementById(`sel1_${safeCid}`);
  const sel2 = document.getElementById(`sel2_${safeCid}`);
  const t1 = sel1?.value || "";
  let t2 = sel2?.value || "";
  if (t1 && t2 && t1 === t2) {
    t2 = "";
    if (sel2) sel2.value = "";
    showToast("Teacher 1 and Teacher 2 cannot be the same person; cleared Teacher 2.", true);
  }

  try {
    const res = await fetch(`/api/courses/${courseId}/assign-teachers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ teacher1_id: t1, teacher2_id: t2 }),
    });

    if (!res.ok) throw new Error("Failed to save teachers");
    const saved = await res.json();

    // Update in local state
    const c = state.courses.find((item) => item.id === courseId);
    if (c) {
      c.teacher1_id = saved.teacher1_id || null;
      c.teacher2_id = saved.teacher2_id || null;
    }

    flashSaveIndicator();
    showToast(`Saved teachers for ${courseId}`);
  } catch (err) {
    showToast(`Error saving assignment: ${err.message}`, true);
  }
}

function buildTeacherOptionsHtml(selectedTid) {
  // Group teachers by department
  const depts = ["CSE", "ECE", "EEE", "ME", "MATH", "PHY", "HUM"];
  const byDept = {};
  depts.forEach((d) => (byDept[d] = []));

  state.teachers.forEach((t) => {
    const d = t.department || "CSE";
    if (!byDept[d]) byDept[d] = [];
    byDept[d].push(t);
  });

  let html = "";
  for (const dept of Object.keys(byDept)) {
    const teachersInDept = byDept[dept] || [];
    const deptOpts = teachersInDept
      .filter((t) => {
        // Always include currently selected teacher, even if on-leave and checkbox unchecked!
        if (t.id === selectedTid) return true;
        // If checkbox is checked, show all
        if (state.showOnLeave) return true;
        // Default: active teachers only
        return t.status === "active";
      })
      .map((t) => {
        const isSelected = t.id === selectedTid ? "selected" : "";
        const leaveNote = t.status === "on_leave" ? " [ON LEAVE]" : "";
        return `<option value="${t.id}" ${isSelected}>${escapeHtml(t.full_name)} (${t.short_code})${leaveNote}</option>`;
      })
      .join("");

    if (deptOpts) {
      html += `<optgroup label="${dept}">${deptOpts}</optgroup>`;
    }
  }
  return html;
}

async function handleAssignmentChange(courseId, section, group, teacherId) {
  const teacherIds = teacherId ? [teacherId] : [];
  await saveSlotTeachers(courseId, section, group, teacherIds);
}

async function handleLabAssignmentChange(courseId, section, group, selId1, selId2) {
  const val1 = document.getElementById(selId1)?.value || "";
  const val2 = document.getElementById(selId2)?.value || "";
  const teacherIds = [];
  if (val1) teacherIds.push(val1);
  if (val2 && val2 !== val1) teacherIds.push(val2);

  await saveSlotTeachers(courseId, section, group, teacherIds);
}

async function saveSlotTeachers(courseId, section, group, teacherIds) {
  try {
    const payload = {
      course_id: courseId,
      section: section,
      group: group,
      teacher_ids: teacherIds,
    };

    const res = await fetch("/api/assignments/save-slot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error("Failed to save assignment");

    // Flash save status indicator
    flashSaveIndicator();

    // Reload assignments in state and re-render
    await loadAssignments();
    renderAssignments();
    showToast("Assignment updated successfully");
  } catch (err) {
    showToast(`Error saving assignment: ${err.message}`, true);
  }
}

function flashSaveIndicator() {
  const ind = document.getElementById("assign-save-status");
  if (ind) {
    ind.style.display = "inline-block";
    setTimeout(() => {
      ind.style.display = "none";
    }, 2500);
  }
}

// -----------------------------------------------------------------------------
// Generate Routine Tab & Incremental Freeze Controls
// -----------------------------------------------------------------------------

function onGenModeChange(mode) {
  const incLabel = document.getElementById("mode-incremental-label");
  const fullLabel = document.getElementById("mode-full-label");
  const freezeCard = document.getElementById("freeze-batches-card");
  const btnText = document.getElementById("gen-btn-text");

  if (mode === "incremental") {
    incLabel?.classList.add("selected");
    fullLabel?.classList.remove("selected");
    if (freezeCard) freezeCard.style.display = "block";
    if (btnText) btnText.textContent = "🚀 Schedule Routine (Preserve Selected Terms)";
  } else {
    fullLabel?.classList.add("selected");
    incLabel?.classList.remove("selected");
    if (freezeCard) freezeCard.style.display = "none";
    if (btnText) btnText.textContent = "🚀 Generate Full Routine (Rebuild All)";
  }
}

async function renderFreezeBatchSelector() {
  const container = document.getElementById("freeze-batches-list");
  if (!container) return;

  const activeBatches = state.batches.filter((b) => b.status === "on");
  activeBatches.sort((a, b) => curriculumSortKey(a.id) - curriculumSortKey(b.id));

  if (activeBatches.length === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem; padding: 1rem;">No active running terms. Turn ON running terms in Courses tab first.</div>`;
    return;
  }

  let html = "";
  for (const b of activeBatches) {
    const hasScheduled = !!b.has_routine;
    // By default, if the batch already has a saved schedule, freeze it (checked); if not, leave unchecked
    const isChecked = hasScheduled;
    const badgeHtml = hasScheduled
      ? `<span class="freeze-badge-locked">🔒 Keep Unchanged</span>`
      : `<span class="freeze-badge-fresh">⚡ Schedule Fresh</span>`;

    html += `
      <label class="freeze-item ${isChecked ? "frozen" : "unfrozen"}" id="freeze-item-${b.id}">
        <input type="checkbox" class="freeze-batch-chk" value="${b.id}" ${isChecked ? "checked" : ""} onchange="onFreezeCheckboxToggle('${b.id}', this.checked)">
        <div class="freeze-item-info">
          <div class="freeze-item-title">
            <span class="freeze-batch-tag">${b.id}</span>
            ${badgeHtml}
          </div>
          <div class="freeze-item-desc">${escapeHtml(b.name)}</div>
        </div>
      </label>
    `;
  }

  container.innerHTML = html;
}

function onFreezeCheckboxToggle(batchId, isChecked) {
  const item = document.getElementById(`freeze-item-${batchId}`);
  if (item) {
    item.classList.toggle("frozen", isChecked);
    item.classList.toggle("unfrozen", !isChecked);
  }
}

function freezeAllScheduledBatches() {
  document.querySelectorAll(".freeze-batch-chk").forEach((chk) => {
    chk.checked = true;
    onFreezeCheckboxToggle(chk.value, true);
  });
}

function unfreezeAllBatches() {
  document.querySelectorAll(".freeze-batch-chk").forEach((chk) => {
    chk.checked = false;
    onFreezeCheckboxToggle(chk.value, false);
  });
}

async function handleGenerateRoutine() {
  const btn = document.getElementById("btn-generate-routine");
  const spinner = document.getElementById("gen-btn-spinner");
  const btnText = document.getElementById("gen-btn-text");

  const seconds = parseFloat(document.getElementById("solve-seconds")?.value || "180");
  const modeRadio = document.querySelector('input[name="gen-mode"]:checked');
  const mode = modeRadio ? modeRadio.value : "incremental";

  let frozenBatches = [];
  if (mode === "incremental") {
    frozenBatches = Array.from(document.querySelectorAll(".freeze-batch-chk:checked")).map((el) => el.value);
  }

  btn.disabled = true;
  spinner.style.display = "inline-block";
  btnText.textContent = mode === "incremental"
    ? `Solving with ${frozenBatches.length} terms frozen...`
    : "Re-solving all terms with CP-SAT...";

  try {
    const res = await fetch("/api/generate-routine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        seconds: seconds,
        mode: mode,
        frozen_batches: frozenBatches,
      }),
    });

    const data = await res.json();
    renderGenerateResult(data);
    await loadBatches(); // Refresh scheduled status on batches
  } catch (err) {
    showToast(`Solve error: ${err.message}`, true);
  } finally {
    btn.disabled = false;
    spinner.style.display = "none";
    btnText.textContent = mode === "incremental"
      ? "🚀 Schedule Routine (Preserve Selected Terms)"
      : "🚀 Generate Full Routine (Rebuild All)";
  }
}

function renderGenerateResult(data) {
  const container = document.getElementById("generate-results-container");
  container.style.display = "block";

  const badge = document.getElementById("result-status-badge");
  const modeBadge = document.getElementById("result-mode-badge");
  const timestamp = document.getElementById("result-timestamp");
  const penalty = document.getElementById("result-penalty");
  const time = document.getElementById("result-time");
  const faultsCount = document.getElementById("result-faults-count");
  const faultsBox = document.getElementById("result-faults-box");
  const faultsUl = document.getElementById("result-faults-ul");
  const warningsBox = document.getElementById("result-warnings-box");
  const warningsUl = document.getElementById("result-warnings-ul");
  const iframe = document.getElementById("routine-preview-frame");

  badge.textContent = data.status || "UNKNOWN";
  if (data.status === "OPTIMAL" || data.status === "FEASIBLE" || data.status === "CACHED") {
    badge.className = "badge badge-active";
  } else {
    badge.className = "badge badge-leave";
  }

  if (modeBadge) {
    if (data.mode === "incremental") {
      const fCount = data.frozen_batches?.length || 0;
      const sCount = data.scheduled_batches?.length || 0;
      modeBadge.textContent = `🔒 Incremental (${fCount} terms frozen, ${sCount} scheduled)`;
      modeBadge.style.background = "#EFF6FF";
      modeBadge.style.color = "#1E40AF";
      modeBadge.style.borderColor = "#BFDBFE";
    } else {
      modeBadge.textContent = "🔄 Full Generation";
      modeBadge.style.background = "#F8FAFC";
      modeBadge.style.color = "#334155";
      modeBadge.style.borderColor = "#CBD5E1";
    }
  }

  timestamp.textContent = data.timestamp ? `Generated at ${data.timestamp}` : "";
  penalty.textContent = data.objective !== null && data.objective !== undefined ? data.objective : "—";
  time.textContent = data.solve_time_seconds ? `${data.solve_time_seconds}s` : "—";

  const consecCount = document.getElementById("result-consec-count");
  if (consecCount) {
    consecCount.textContent = data.same_course_consecutive_count !== undefined && data.same_course_consecutive_count !== null
      ? `${data.same_course_consecutive_count} pairs`
      : "—";
  }

  const maxLabsEl = document.getElementById("result-max-labs-day");
  if (maxLabsEl) {
    if (data.max_teacher_labs_day !== undefined && data.max_teacher_labs_day !== null) {
      const doubleDays = data.double_lab_teacher_days ?? data.extra_lab_days ?? 0;
      maxLabsEl.textContent = `≤ ${data.max_teacher_labs_day}/day (${doubleDays}×2-lab days)`;
    } else {
      maxLabsEl.textContent = "—";
    }
  }

  const errors = data.errors || [];
  const faults = [...errors, ...(data.faults || [])];
  faultsCount.textContent = faults.length;
  if (faults.length > 0) {
    faultsBox.style.display = "block";
    faultsUl.innerHTML = faults.map((f) => `<li>${escapeHtml(f)}</li>`).join("");
  } else {
    faultsBox.style.display = "none";
  }

  // Warnings
  const warnings = data.warnings || [];
  if (warnings.length > 0) {
    warningsBox.style.display = "block";
    warningsUl.innerHTML = warnings.map((w) => `<li>Warning: ${escapeHtml(w)}</li>`).join("");
  } else {
    warningsBox.style.display = "none";
  }

  // Load preview iframes
  const masterFrame = document.getElementById("master-routine-frame");
  const routineSrc = data.html_url ? `${data.html_url}?t=${Date.now()}` : (data.ok && !errors.length ? `/out/routine.html?t=${Date.now()}` : null);
  if (routineSrc) {
    if (iframe) iframe.src = routineSrc;
    if (masterFrame) masterFrame.src = routineSrc;
  }

  if (data.ok && faults.length === 0) {
    showToast("Routine successfully generated with ZERO verification faults!");
  } else if (data.status === "VALIDATION_FAILED") {
    showToast("Data validation failed. Please check warnings/errors above.", true);
  } else {
    showToast(`Solver finished with status ${data.status}`, true);
  }
}

function loadMasterRoutine() {
  const masterFrame = document.getElementById("master-routine-frame");
  if (masterFrame) {
    masterFrame.src = `/out/routine.html?t=${Date.now()}`;
  }
}

function downloadMasterFromMain() {
  const masterFrame = document.getElementById("master-routine-frame") || document.getElementById("routine-preview-frame");
  if (masterFrame && masterFrame.contentWindow && typeof masterFrame.contentWindow.downloadCurrentMasterPDF === "function") {
    masterFrame.contentWindow.downloadCurrentMasterPDF();
  } else {
    const win = window.open("/out/routine.html", "_blank");
    if (win) {
      win.focus();
    }
  }
}

function switchMasterIframeTab(subview) {
  const masterFrame = document.getElementById("master-routine-frame");
  if (masterFrame && masterFrame.contentWindow) {
    try {
      masterFrame.contentWindow.showMasterSubView(subview);
      ["teachers", "labs", "batches"].forEach((v) => {
        const btn = document.getElementById(`btn-master-view-${v}`);
        if (btn) btn.classList.toggle("active", v === subview);
      });
    } catch (e) {
      console.warn("Could not switch subview inside iframe:", e);
    }
  }
}

async function checkLatestRoutine() {
  try {
    const res = await fetch("/api/routine/latest");
    const data = await res.json();
    if (data.ok) {
      renderGenerateResult(data);
    }
  } catch (err) {
    console.warn("No latest routine cached:", err);
  }
}

// -----------------------------------------------------------------------------
// Utilities
// -----------------------------------------------------------------------------

function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  const msg = document.getElementById("toast-message");
  if (!toast || !msg) return;

  msg.textContent = message;
  toast.style.borderLeftColor = isError ? "var(--danger-border)" : "var(--gold)";
  toast.classList.add("show");

  setTimeout(() => {
    toast.classList.remove("show");
  }, 3500);
}

function escapeHtml(text) {
  if (text === null || text === undefined) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// -----------------------------------------------------------------------------
// Time Slots & Class Schedule Customizer
// -----------------------------------------------------------------------------

async function loadTimeGrid() {
  try {
    const res = await fetch("/api/time-grid");
    if (!res.ok) throw new Error("Failed to load time grid configuration");
    const data = await res.json();
    state.timeGridConfig = data.config;
    state.timeGridComputed = data.computed;

    renderTimeGridForm(state.timeGridConfig, state.timeGridComputed);
    renderTimeGridPreview(state.timeGridComputed);
    populateAllPeriodSelectDropdowns(state.timeGridComputed);
  } catch (err) {
    showToast(`Error loading time grid: ${err.message}`, true);
  }
}

function renderTimeGridForm(config, computed) {
  if (!config) return;

  const dayStartInput = document.getElementById("cfg-day-start");
  const periodDurationInput = document.getElementById("cfg-period-duration");
  const periodsPerDayInput = document.getElementById("cfg-periods-per-day");
  const labPeriodsInput = document.getElementById("cfg-lab-periods");

  if (dayStartInput) dayStartInput.value = config.day_start || "08:00";
  if (periodDurationInput) periodDurationInput.value = config.period_duration_minutes || 50;
  if (periodsPerDayInput) periodsPerDayInput.value = config.periods_per_day || 9;
  if (labPeriodsInput) labPeriodsInput.value = config.lab_periods || 3;

  // Working days pills
  const workingDays = config.days || ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"];
  document.querySelectorAll("#working-days-container input[type='checkbox']").forEach((chk) => {
    const isChecked = workingDays.includes(chk.value);
    chk.checked = isChecked;
    chk.closest(".day-pill")?.classList.toggle("selected", isChecked);
  });

  // Render breaks
  renderBreakRows(config.breaks || [], config.periods_per_day || 9);

  // Active summary
  updateActiveScheduleSummary(computed);
}

function updateActiveScheduleSummary(computed) {
  const el = document.getElementById("active-schedule-summary");
  if (!el || !computed) return;
  const breakCount = (computed.breaks || []).length;
  const daysCount = (computed.days || []).length;
  const breakMins = computed.total_break_minutes || 0;
  el.innerHTML = `Active Schedule: <strong>${escapeHtml(computed.day_span_formatted)}</strong> • ${computed.periods_per_day} classes/day (${computed.period_duration_minutes}m each) • ${breakCount} break(s) (${breakMins}m) • ${daysCount} working days`;
}

function renderBreakRows(breaks, periodsCount) {
  const container = document.getElementById("breaks-list-container");
  if (!container) return;

  if (breaks.length === 0) {
    container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 1.25rem; border: 1px dashed #CBD5E1; border-radius: var(--radius); font-size: 0.85rem; background: #F8FAFC;">No breaks configured. Academic classes run continuously without pauses. Click <b>＋ Add Break</b> above to add one.</div>`;
    return;
  }

  let html = "";
  breaks.forEach((b, idx) => {
    const afterPeriod = (b.after_period || "P3").toUpperCase();
    const duration = b.duration_minutes || b.length_minutes || 15;
    const name = b.name || `Break ${idx + 1}`;

    let opts = "";
    for (let p = 1; p < periodsCount; p++) {
      const pName = `P${p}`;
      opts += `<option value="${pName}" ${afterPeriod === pName ? "selected" : ""}>After Period ${p} (${pName})</option>`;
    }

    html += `
      <div class="break-row-card" data-break-index="${idx}">
        <div>
          <label class="break-field-label">Break Name</label>
          <input type="text" class="break-name-input time-grid-input" value="${escapeHtml(name)}" placeholder="e.g. Snack break, Lunch" oninput="onTimeGridInputChange()" />
        </div>
        <div>
          <label class="break-field-label">Scheduled Position</label>
          <select class="break-after-select time-grid-input" onchange="onTimeGridInputChange()">
            ${opts}
          </select>
        </div>
        <div>
          <label class="break-field-label">Duration (min)</label>
          <div class="input-with-unit">
            <input type="number" class="break-duration-input time-grid-input" min="5" max="180" step="5" value="${duration}" oninput="onTimeGridInputChange()" />
            <span class="input-unit">min</span>
          </div>
        </div>
        <div style="padding-top: 18px;">
          <button type="button" class="btn btn-danger-outline btn-sm" onclick="removeBreakRow(${idx})" title="Delete this break" style="padding: 0.45rem 0.65rem; border-radius: 6px;">
            🗑️
          </button>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

function addNewBreakRow() {
  const currentConfig = collectTimeGridFormData();
  const periodsCount = currentConfig.periods_per_day || 9;
  const breaks = currentConfig.breaks || [];

  // Pick a sensible default after_period
  let nextP = "P3";
  if (breaks.length === 1) nextP = "P6";
  else if (breaks.length >= 2) nextP = `P${Math.min(periodsCount - 1, breaks.length * 2 + 1)}`;

  breaks.push({
    name: breaks.length === 0 ? "Snack break" : (breaks.length === 1 ? "Lunch & prayer" : "Recess"),
    after_period: nextP,
    duration_minutes: breaks.length === 1 ? 80 : 15,
  });

  currentConfig.breaks = breaks;
  renderBreakRows(breaks, periodsCount);
  onTimeGridInputChange();
}

function removeBreakRow(idx) {
  const currentConfig = collectTimeGridFormData();
  const breaks = currentConfig.breaks || [];
  if (idx >= 0 && idx < breaks.length) {
    breaks.splice(idx, 1);
    currentConfig.breaks = breaks;
    renderBreakRows(breaks, currentConfig.periods_per_day);
    onTimeGridInputChange();
  }
}

function onPeriodsPerDayChange() {
  const currentConfig = collectTimeGridFormData();
  const periodsCount = currentConfig.periods_per_day;
  renderBreakRows(currentConfig.breaks, periodsCount);
  onTimeGridInputChange();
}

function collectTimeGridFormData() {
  const day_start = document.getElementById("cfg-day-start")?.value || "08:00";
  const period_duration_minutes = parseInt(document.getElementById("cfg-period-duration")?.value, 10) || 50;
  const periods_per_day = parseInt(document.getElementById("cfg-periods-per-day")?.value, 10) || 9;
  const lab_periods = parseInt(document.getElementById("cfg-lab-periods")?.value, 10) || 3;

  const days = [];
  document.querySelectorAll("#working-days-container input[type='checkbox']").forEach((chk) => {
    if (chk.checked) days.push(chk.value);
    chk.closest(".day-pill")?.classList.toggle("selected", chk.checked);
  });

  const breaks = [];
  document.querySelectorAll("#breaks-list-container .break-row-card").forEach((card) => {
    const name = card.querySelector(".break-name-input")?.value.trim() || "Break";
    const after_period = card.querySelector(".break-after-select")?.value || "P3";
    const duration_minutes = parseInt(card.querySelector(".break-duration-input")?.value, 10) || 15;
    breaks.push({ name, after_period, duration_minutes });
  });

  return {
    day_start,
    period_duration_minutes,
    periods_per_day,
    lab_periods,
    days: days.length > 0 ? days : ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"],
    breaks,
  };
}

let previewDebounceTimer = null;
function onTimeGridInputChange() {
  clearTimeout(previewDebounceTimer);
  previewDebounceTimer = setTimeout(async () => {
    const formData = collectTimeGridFormData();
    try {
      const res = await fetch("/api/time-grid/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });
      if (res.ok) {
        const data = await res.json();
        renderTimeGridPreview(data.computed);
      }
    } catch (e) {
      console.warn("Live preview calculation error:", e);
    }
  }, 100);
}

function renderTimeGridPreview(computed) {
  if (!computed) return;

  const spanEl = document.getElementById("prev-day-span");
  const activeTimeEl = document.getElementById("prev-active-time");
  const breakTimeEl = document.getElementById("prev-break-time");
  const blocksCountEl = document.getElementById("prev-blocks-count");
  const tbody = document.getElementById("preview-timeline-tbody");

  if (spanEl) spanEl.textContent = computed.day_span_formatted;
  if (activeTimeEl) {
    const activeHrs = (computed.total_active_minutes / 60).toFixed(1);
    activeTimeEl.textContent = `${computed.total_active_minutes} min (${activeHrs} hrs)`;
  }
  if (breakTimeEl) {
    const breakHrs = (computed.total_break_minutes / 60).toFixed(1);
    breakTimeEl.textContent = `${computed.total_break_minutes} min (${breakHrs} hrs)`;
  }
  if (blocksCountEl) {
    blocksCountEl.textContent = `${(computed.blocks || []).length} Block(s)`;
  }

  if (!tbody) return;

  // Build row list mixing periods and breaks in sequence
  const breakMap = {};
  (computed.breaks || []).forEach((b) => {
    breakMap[b.after_period] = b;
  });

  // Map each period to its containing block
  const periodToBlock = {};
  (computed.blocks || []).forEach((blk) => {
    blk.period_names.forEach((pName) => {
      periodToBlock[pName] = blk;
    });
  });

  let rowsHtml = "";
  (computed.periods || []).forEach((p) => {
    const blk = periodToBlock[p.name];
    const labBadge = blk && blk.can_fit_lab
      ? `<span class="lab-fit-badge">🔬 Fits ${computed.lab_periods}-period Lab</span>`
      : "";

    rowsHtml += `
      <tr>
        <td><span class="period-badge">${escapeHtml(p.name)}</span></td>
        <td><span class="time-window-chip"><span style="color:#2563EB;">🕒</span> ${escapeHtml(p.start)} – ${escapeHtml(p.end)}</span></td>
        <td><span style="font-weight: 600; color: #475569;">${p.duration_minutes} min</span></td>
        <td>
          <div class="block-tag">
            <span style="font-weight: 700; color: #1E3A8A;">Block ${blk ? blk.block_index : 1}</span>
            <span style="font-size: 0.76rem; color: #64748B;">(${blk ? blk.period_names.join(', ') : p.name})</span>
            ${labBadge}
          </div>
        </td>
      </tr>
    `;

    if (breakMap[p.name]) {
      const br = breakMap[p.name];
      rowsHtml += `
        <tr class="timeline-break-tr">
          <td><span class="break-badge">☕ ${escapeHtml(br.name)}</span></td>
          <td><span class="time-window-chip" style="background: #FEF3C7; border-color: #FDE68A; color: #92400E;">🕒 ${escapeHtml(br.start)} – ${escapeHtml(br.end)}</span></td>
          <td><strong style="color: #B45309;">${br.duration_minutes} min</strong></td>
          <td><span style="font-size: 0.8rem; font-weight: 600; color: #92400E; display: inline-flex; align-items: center; gap: 0.3rem;">✂️ Academic Block Divider · Sessional labs cannot cross</span></td>
        </tr>
      `;
    }
  });

  tbody.innerHTML = rowsHtml;
}

async function handleSaveTimeGrid() {
  const formData = collectTimeGridFormData();
  try {
    const res = await fetch("/api/time-grid", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formData),
    });
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || "Failed to save time slots");
    }
    const data = await res.json();
    state.timeGridConfig = data.config;
    state.timeGridComputed = data.computed;

    renderTimeGridForm(state.timeGridConfig, state.timeGridComputed);
    renderTimeGridPreview(state.timeGridComputed);
    populateAllPeriodSelectDropdowns(state.timeGridComputed);

    showToast("✓ Department time slots successfully saved and applied department-wide!");
  } catch (err) {
    showToast(`Error: ${err.message}`, true);
  }
}

async function handleResetTimeGrid() {
  if (!confirm("Are you sure you want to reset department time slots back to standard default configuration (08:00 AM – 05:00 PM, 9 periods, 50m each)?")) {
    return;
  }
  try {
    const res = await fetch("/api/time-grid/reset", { method: "POST" });
    if (!res.ok) throw new Error("Failed to reset time slots");
    const data = await res.json();
    state.timeGridConfig = data.config;
    state.timeGridComputed = data.computed;

    renderTimeGridForm(state.timeGridConfig, state.timeGridComputed);
    renderTimeGridPreview(state.timeGridComputed);
    populateAllPeriodSelectDropdowns(state.timeGridComputed);

    showToast("✓ Time slots successfully reset to default schedule (08:00 AM – 05:00 PM).");
  } catch (err) {
    showToast(`Error: ${err.message}`, true);
  }
}

function populateAllPeriodSelectDropdowns(computed) {
  if (!computed) return;

  const teacherSelect = document.getElementById("rule-select-period");
  const courseSelect = document.getElementById("course-rule-select-period");

  const buildOptions = (isCourse) => {
    let html = "";
    // Blocks options
    (computed.blocks || []).forEach((blk) => {
      const pList = blk.period_names.join(",");
      const pDisplay = blk.period_names.join(", ");
      html += `<option value="${pList}">${blk.start} – ${blk.end} (Block ${blk.block_index}: ${pDisplay})</option>`;
    });

    // Full day option
    html += `<option value="all">Full Day (All Periods P1–P${computed.periods_per_day})</option>`;

    // Individual periods
    (computed.periods || []).forEach((p, idx) => {
      html += `<option value="${p.name}">Period ${idx + 1} (${p.start} – ${p.end})</option>`;
    });

    return html;
  };

  const optionsHtml = buildOptions(false);
  if (teacherSelect) teacherSelect.innerHTML = optionsHtml;
  if (courseSelect) courseSelect.innerHTML = buildOptions(true);
}

// =============================================================================
// Dropdown Menus
// =============================================================================

function toggleDropdown(menuId) {
  const menu = document.getElementById(menuId);
  if (!menu) return;
  const isShown = menu.classList.contains("show");
  // Close any other open dropdowns
  document.querySelectorAll(".dropdown-menu").forEach((el) => el.classList.remove("show"));
  if (!isShown) {
    menu.classList.add("show");
  }
}

// Global click outside listener to close dropdowns
document.addEventListener("click", (e) => {
  if (!e.target.closest(".dropdown")) {
    document.querySelectorAll(".dropdown-menu").forEach((el) => el.classList.remove("show"));
  }
});

// =============================================================================
// Bulk Import & Export Hub
// =============================================================================

function openBulkImportModal(entity = "all") {
  const modal = document.getElementById("modal-bulk-import");
  if (!modal) return;
  switchBulkTab(entity);
  modal.classList.add("open");
}

function closeBulkImportModal() {
  const modal = document.getElementById("modal-bulk-import");
  if (modal) modal.classList.remove("open");
}

function switchBulkTab(entity) {
  state.activeBulkEntity = entity;
  const entities = ["all", "teachers", "courses", "rooms"];
  entities.forEach((ent) => {
    const btn = document.getElementById(`btn-bulk-tab-${ent}`);
    const pane = document.getElementById(`bulk-pane-${ent}`);
    if (btn) btn.classList.toggle("active", ent === entity);
    if (pane) pane.classList.toggle("active", ent === entity);
  });
}

function triggerFileInput(entity) {
  const input = document.getElementById(`bulk-file-${entity}`);
  if (input) input.click();
}

function handleBulkFileChosen(entity, input) {
  const fileNameBadge = document.getElementById(`dropzone-file-name-${entity}`);
  const uploadBtn = document.getElementById(`btn-upload-${entity}`);
  const resultCard = document.getElementById(`bulk-result-${entity}`);

  if (resultCard) {
    resultCard.style.display = "none";
    resultCard.innerHTML = "";
  }

  if (input && input.files && input.files[0]) {
    const file = input.files[0];
    if (fileNameBadge) {
      fileNameBadge.textContent = `📄 Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
      fileNameBadge.style.display = "inline-flex";
    }
    if (uploadBtn) {
      uploadBtn.disabled = false;
    }
  } else {
    if (fileNameBadge) {
      fileNameBadge.style.display = "none";
    }
    if (uploadBtn) {
      uploadBtn.disabled = true;
    }
  }
}

// Set up drag-and-drop on all dropzones
function setupBulkDropzones() {
  ["all", "teachers", "courses", "rooms"].forEach((ent) => {
    const dropzone = document.getElementById(`dropzone-${ent}`);
    const fileInput = document.getElementById(`bulk-file-${ent}`);
    if (!dropzone || !fileInput) return;

    ["dragenter", "dragover"].forEach((evt) => {
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add("dragover");
      });
    });

    ["dragleave", "drop"].forEach((evt) => {
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove("dragover");
      });
    });

    dropzone.addEventListener("drop", (e) => {
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        fileInput.files = e.dataTransfer.files;
        handleBulkFileChosen(ent, fileInput);
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setupBulkDropzones();
});

async function handleBulkUpload(entity) {
  const fileInput = document.getElementById(`bulk-file-${entity}`);
  const uploadBtn = document.getElementById(`btn-upload-${entity}`);
  const resultCard = document.getElementById(`bulk-result-${entity}`);

  if (!fileInput || !fileInput.files || !fileInput.files[0]) {
    showToast("Please choose a file to upload first.", true);
    return;
  }

  const file = fileInput.files[0];
  const formData = new FormData();
  formData.append("file", file);

  const origBtnHtml = uploadBtn ? uploadBtn.innerHTML : "";
  if (uploadBtn) {
    uploadBtn.disabled = true;
    uploadBtn.innerHTML = `<span>⏳</span> Uploading &amp; Validating...`;
  }

  try {
    const res = await fetch(`/api/import/${entity}`, {
      method: "POST",
      body: formData,
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || `Upload failed with status ${res.status}`);
    }

    if (resultCard) {
      resultCard.style.display = "block";
      const isSuccess = data.status === "success";
      const hasErrors = data.errors && data.errors.length > 0;

      resultCard.className = `bulk-result-card ${isSuccess && !hasErrors ? "bulk-result-success" : (hasErrors ? "bulk-result-warning" : "bulk-result-error")}`;

      let html = `<div style="font-weight: 700; font-size: 0.95rem; margin-bottom: 0.35rem;">
        ${isSuccess ? "✓ Import Processed Successfully" : "⚠️ Import Finished with Warnings"}
      </div>`;
      html += `<div style="margin-bottom: 0.5rem;">${escapeHtml(data.message || "")}</div>`;

      // Stat pills
      if (entity === "all" && data.summary) {
        html += `<div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
          <span class="bulk-stat-pill" style="background:#DBEAFE; color:#1E40AF;">🏫 Rooms: ${data.summary.rooms?.created || 0} new, ${data.summary.rooms?.updated || 0} updated</span>
          <span class="bulk-stat-pill" style="background:#D1FAE5; color:#065F46;">👨‍🏫 Teachers: ${data.summary.teachers?.created || 0} new, ${data.summary.teachers?.updated || 0} updated</span>
          <span class="bulk-stat-pill" style="background:#FEF3C7; color:#92400E;">📚 Courses: ${data.summary.courses?.created || 0} new, ${data.summary.courses?.updated || 0} updated</span>
        </div>`;
      } else if (data.created !== undefined || data.updated !== undefined) {
        html += `<div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
          <span class="bulk-stat-pill" style="background:#D1FAE5; color:#065F46;">Created: ${data.created || 0}</span>
          <span class="bulk-stat-pill" style="background:#DBEAFE; color:#1E40AF;">Updated: ${data.updated || 0}</span>
          ${data.skipped ? `<span class="bulk-stat-pill" style="background:#F3F4F6; color:#4B5563;">Skipped: ${data.skipped}</span>` : ""}
        </div>`;
      }

      // Errors listing
      if (hasErrors) {
        html += `<div style="margin-top: 0.5rem; border-top: 1px dashed rgba(0,0,0,0.15); padding-top: 0.5rem;">
          <b>⚠️ Notes & Warnings (${data.errors.length}):</b>
          <ul style="margin: 0.25rem 0 0 1.25rem; font-size: 0.8rem;">
            ${data.errors.slice(0, 10).map((err) => `<li>${escapeHtml(err)}</li>`).join("")}
            ${data.errors.length > 10 ? `<li>...and ${data.errors.length - 10} more</li>` : ""}
          </ul>
        </div>`;
      }

      resultCard.innerHTML = html;
    }

    // Refresh live client data
    if (entity === "all") {
      await Promise.all([loadRooms(), loadTeachers(), loadCourses(), loadAssignments()]);
      renderAssignments();
    } else if (entity === "teachers") {
      await loadTeachers();
    } else if (entity === "courses") {
      await loadCourses();
      await loadAssignments();
      renderAssignments();
    } else if (entity === "rooms") {
      await loadRooms();
    }

    showToast(`✓ Import successful! Records synchronized.`);
  } catch (err) {
    if (resultCard) {
      resultCard.style.display = "block";
      resultCard.className = "bulk-result-card bulk-result-error";
      resultCard.innerHTML = `
        <div style="font-weight: 700; font-size: 0.95rem; margin-bottom: 0.35rem;">❌ Import Failed</div>
        <div>${escapeHtml(err.message)}</div>
      `;
    }
    showToast(`Import error: ${err.message}`, true);
  } finally {
    if (uploadBtn) {
      uploadBtn.disabled = false;
      uploadBtn.innerHTML = origBtnHtml;
    }
  }
}
