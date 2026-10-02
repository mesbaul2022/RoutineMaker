/**
 * Routine Maker Frontend Application
 * Vanilla JS interacting with FastAPI backend.
 */

// Application State
const state = {
  activeTab: "teachers",
  teachers: [],
  courses: [],
  batches: [],
  assignments: [],
  showOnLeave: false,
  editingTeacherId: null,
  editingCourseId: null,
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

  if (tabId === "teachers") {
    loadTeachers();
  } else if (tabId === "courses") {
    loadCourses();
  } else if (tabId === "assignments") {
    loadAssignmentsData();
  } else if (tabId === "master") {
    loadMasterRoutine();
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
  await Promise.all([loadBatches(), loadTeachers(), loadCourses(), loadAssignments()]);
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
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">No teachers found matching criteria.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered
    .map((t) => {
      const deptClass = `badge-${t.department.toLowerCase()}`;
      const isActive = t.status === "active";
      const statusBadge = isActive
        ? `<span class="badge badge-active">Active</span>`
        : `<span class="badge badge-leave">On Leave</span>`;

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
          <button class="status-toggle" onclick="toggleTeacherStatus('${t.id}', '${t.status}')" title="Click to toggle status">
            ${statusBadge}
          </button>
        </td>
        <td style="text-align: right;">
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
      tbodyHtml = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No courses in this batch.</td></tr>`;
    } else if (b.id === "4-2" && !categoryFilter) {
      const coreCourses = list.filter((c) => c.category === "core" || !c.category);
      const opt2Courses = list.filter((c) => c.category === "optional_ii");
      const opt3Courses = list.filter((c) => c.category === "optional_iii");

      if (coreCourses.length > 0) {
        tbodyHtml += `<tr><td colspan="7" class="category-subheader"><span>📌 Core Compulsory Courses (${coreCourses.length})</span></td></tr>`;
        tbodyHtml += coreCourses.map((c) => renderCourseRow(b, c)).join("");
      }
      if (opt2Courses.length > 0) {
        tbodyHtml += `<tr><td colspan="7" class="category-subheader" style="color: #6B21A8; background: #FAF5FF;"><span>💡 Optional-II Elective Courses (${opt2Courses.length} Theory Courses)</span></td></tr>`;
        tbodyHtml += opt2Courses.map((c) => renderCourseRow(b, c)).join("");
      }
      if (opt3Courses.length > 0) {
        tbodyHtml += `<tr><td colspan="7" class="category-subheader" style="color: #0F766E; background: #F0FDFA;"><span>🔬 Optional-III Elective Courses (${opt3Courses.length} Theory + Lab Courses)</span></td></tr>`;
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
                <th style="width: 130px;">Code</th>
                <th>Course Title</th>
                <th style="width: 140px;">Type / Credit</th>
                <th style="width: 200px;">Assigned Teachers</th>
                <th style="width: 150px;">Room Kind</th>
                <th style="width: 140px;">Weekly Load</th>
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

  let teachersStr = "";
  if (isOff) {
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

  const loadStr = isTheory
    ? `${course.periods_per_week || 3} periods / wk`
    : (is075 ? `1 block / 2 wks` : `${course.blocks_per_week || 1} block / wk`);

  return `
    <tr>
      <td><strong style="color: var(--navy-deep);">${escapeHtml(course.id)}</strong></td>
      <td>
        <div style="font-weight: 600; display: flex; align-items: center; flex-wrap: wrap;">
          ${escapeHtml(course.title)}
          ${catBadge}
        </div>
        ${pairedInfo}
      </td>
      <td>${kindBadge}</td>
      <td>${teachersStr}</td>
      <td><span class="badge" style="background: #F1F5F9; color: var(--text-main);">${escapeHtml(course.room_kind)}</span></td>
      <td style="color: var(--text-muted); font-size: 0.85rem;">${loadStr}</td>
      <td style="text-align: right;">
        <button class="btn btn-outline btn-sm" onclick="openCourseModal('${course.id}')">Edit</button>
        <button class="btn btn-danger-outline btn-sm" onclick="deleteCourse('${course.id}')">Delete</button>
      </td>
    </tr>
  `;
}

function toggleCourseKindFields() {
  const kind = document.getElementById("course-kind").value;
  const pGroup = document.getElementById("group-periods");
  const lGroup = document.getElementById("group-lab-credit");
  const roomKindSelect = document.getElementById("course-room-kind");
  const batchId = document.getElementById("course-batch")?.value || "";

  if (kind === "theory") {
    pGroup.style.display = "block";
    if (lGroup) lGroup.style.display = "none";
    document.getElementById("group-paired-course").style.display = "none";
    if (roomKindSelect.value.includes("lab")) {
      roomKindSelect.value = batchId === "1-1" ? "year1_theory" : "theory";
    }
  } else {
    pGroup.style.display = "none";
    if (lGroup) lGroup.style.display = "block";
    toggleLabCreditFields();
    if (roomKindSelect.value === "theory" || roomKindSelect.value === "year1_theory") {
      roomKindSelect.value = batchId === "1-1" ? "year1_cse_lab" : "cse_lab";
    }
  }
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
      document.getElementById("course-room-kind").value = course.room_kind;
      document.getElementById("course-periods").value = course.periods_per_week || 3;
      if (document.getElementById("course-credit")) {
        document.getElementById("course-credit").value = String(course.credit || (course.blocks_per_week === 2 ? 3.0 : 1.5));
      }

      toggleCourseKindFields();
      populatePairedCourseOptions(course.paired_course_id);
      handleModalBatchChange();

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

    toggleCourseKindFields();
    populatePairedCourseOptions("");
    handleModalBatchChange();

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
  const room_kind = document.getElementById("course-room-kind").value;
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

  const payload = {
    id,
    title,
    batch_id,
    category,
    kind,
    room_kind,
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

  const ruleHint = isTheory
    ? `<b>Co-teaching Model (Both Section A & B):</b> Teachers are assigned to the whole course, not per-section. Both sections receive 3 periods/week: 1 personal class by Teacher 1, 1 personal class by Teacher 2, and 1 shared class (T1/T2) for each section.`
    : (is075
        ? `<b>0.75 Credit Bi-weekly Lab:</b> Co-taught by Teacher 1 + Teacher 2. Students attend 1 session every 2 weeks${course.paired_course_id ? ` (alternating with ${escapeHtml(course.paired_course_id)})` : ''}.`
        : `<b>Co-teaching Model:</b> Both teachers co-teach laboratory sessions across all sections and groups.`);

  const safeCid = course.id.replace(/[^a-zA-Z0-9]/g, "_");

  return `
    <div class="course-card" id="assign-card-${safeCid}">
      <div class="course-card-header">
        <div class="course-title-group" style="display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;">
          <span class="course-code">${escapeHtml(course.id)}</span>
          <span class="course-name">${escapeHtml(course.title)}</span>
          ${catBadge}
          ${kindBadge}
          ${pairedBadge}
          <span class="badge" style="background: #F8FAFC; color: var(--text-muted); border: 1px solid #E2E8F0;">Room: ${escapeHtml(course.room_kind)}</span>
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
  const t1 = document.getElementById(`sel1_${safeCid}`)?.value || "";
  const t2 = document.getElementById(`sel2_${safeCid}`)?.value || "";

  try {
    const res = await fetch(`/api/courses/${courseId}/assign-teachers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ teacher1_id: t1, teacher2_id: t2 }),
    });

    if (!res.ok) throw new Error("Failed to save teachers");

    // Update in local state
    const c = state.courses.find((item) => item.id === courseId);
    if (c) {
      c.teacher1_id = t1 || null;
      c.teacher2_id = t2 || null;
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

  const faults = data.faults || [];
  faultsCount.textContent = faults.length;
  if (faults.length > 0) {
    faultsBox.style.display = "block";
    faultsUl.innerHTML = faults.map((f) => `<li>${escapeHtml(f)}</li>`).join("");
  } else {
    faultsBox.style.display = "none";
  }

  // Errors / Warnings
  const errors = data.errors || [];
  const warnings = data.warnings || [];
  if (errors.length > 0 || warnings.length > 0) {
    warningsBox.style.display = "block";
    const combined = [
      ...errors.map((e) => `<li style="color: var(--danger-text); font-weight: 700;">Error: ${escapeHtml(e)}</li>`),
      ...warnings.map((w) => `<li>Warning: ${escapeHtml(w)}</li>`),
    ];
    warningsUl.innerHTML = combined.join("");
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
