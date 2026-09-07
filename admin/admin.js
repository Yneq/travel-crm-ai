const state = {
  token: localStorage.getItem("voyageops_token"),
  user: null,
  members: [],
  requests: [],
  tasks: [],
  reminders: [],
  communicationDrafts: [],
  communicationTemplates: [],
  communicationVersions: {},
  jobs: [],
  workerStatus: null,
  trips: [],
  quotes: [],
  orders: [],
  paymentsByOrder: {},
  aiPlans: [],
  aiProviderStatus: null,
  latestAgentRun: null,
  staffUsers: [],
  auditPage: { items: [], total: 0, limit: 50, offset: 0 },
  auditFacets: { entity_types: [], actions: [], actors: [] },
  auditFilters: {},
  selectedTripId: null,
  selectedTrip: null,
  taskFilter: "active",
};

const requestStatuses = [
  "new", "qualified", "planning", "proposal_ready", "client_review",
  "approved", "booked", "completed", "cancelled",
];

const requestTransitions = {
  new: ["qualified", "cancelled"],
  qualified: ["planning", "cancelled"],
  planning: ["proposal_ready", "cancelled"],
  proposal_ready: ["planning", "client_review", "cancelled"],
  client_review: ["planning", "approved", "cancelled"],
  approved: ["booked", "cancelled"],
  booked: ["completed", "cancelled"],
  completed: [],
  cancelled: [],
};

const taskTransitions = {
  open: ["in_progress", "completed", "cancelled"],
  in_progress: ["open", "completed", "cancelled"],
  completed: ["open"],
  cancelled: ["open"],
};

const tripTransitions = {
  draft: ["review", "cancelled"],
  review: ["draft", "confirmed", "cancelled"],
  confirmed: ["cancelled"],
  cancelled: [],
};

const quoteTransitions = {
  draft: ["pending_approval", "cancelled"],
  pending_approval: ["approved", "rejected", "cancelled"],
  rejected: ["draft", "cancelled"],
  approved: [],
  cancelled: [],
};

const labels = {
  new: "新需求", qualified: "已確認", planning: "規劃中",
  proposal_ready: "提案完成", client_review: "客戶審閱",
  approved: "已核准", booked: "已訂購", completed: "已完成",
  cancelled: "已取消", open: "待處理", in_progress: "進行中",
  standard: "Standard", premium: "Premium", vip: "VIP",
  low: "低", normal: "一般", high: "高", urgent: "緊急",
  draft: "草稿", review: "審閱中", confirmed: "已確認",
  pending_approval: "待核准", rejected: "已退回",
  pending_payment: "待付款", paid: "已付款", fulfilled: "已履約",
  refunded: "已退款", processing: "處理中", succeeded: "付款成功", failed: "付款失敗",
  awaiting_review: "等待人工審核", applied: "已建立行程",
  hotel: "飯店", flight: "航班", transfer: "接送", activity: "活動",
  dining: "餐飲", other: "其他",
  scheduled: "待處理", acknowledged: "已處理", dismissed: "已略過",
  task_due: "任務期限", payment_follow_up: "付款追蹤", trip_countdown: "出發確認",
  retrying: "等待重試", dead_letter: "需人工介入",
  operational_reminder_scan: "營運提醒掃描",
  sent: "Mock 已寄送",
  active: "啟用中", inactive: "已停用",
  admin: "Admin", advisor: "Advisor", finance: "Finance",
};

const communicationSourceLabels = {
  ai_followup: "AI Follow-up",
  manual_edit: "手動修改",
  template: "套用範本",
  migration_backfill: "既有內容匯入",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDate(value, includeTime = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return escapeHtml(value);
  return new Intl.DateTimeFormat("zh-TW", includeTime
    ? { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }
    : { year: "numeric", month: "short", day: "numeric" }
  ).format(date);
}

function formatMoney(value, currency = "TWD") {
  if (value === null || value === undefined) return "未設定";
  return new Intl.NumberFormat("zh-TW", {
    style: "currency", currency, maximumFractionDigits: 0,
  }).format(Number(value));
}

function showToast(message, error = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", error);
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 2800);
}

function setSyncing(syncing) {
  const indicator = $("#sync-state");
  indicator.textContent = syncing ? "◌ 同步中" : "● 已同步";
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  if (state.token) headers.Authorization = `Bearer ${state.token}`;

  const response = await fetch(path, { ...options, headers });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/auth/login") logout();
    const detail = Array.isArray(data?.detail)
      ? data.detail.map((item) => item.msg).join("；")
      : data?.detail || data?.message || `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return data;
}

async function downloadPdf(path, filename) {
  const headers = state.token ? { Authorization: `Bearer ${state.token}` } : {};
  const response = await fetch(path, { headers });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || `下載失敗 (${response.status})`);
  }
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

async function login(email, password) {
  const data = await api("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  state.token = data.access_token;
  localStorage.setItem("voyageops_token", state.token);
  await bootApp();
}

function logout() {
  state.token = null;
  state.user = null;
  localStorage.removeItem("voyageops_token");
  $("#app-view").classList.add("hidden");
  $("#login-view").classList.remove("hidden");
}

async function bootApp() {
  try {
    state.user = await api("/api/users/me");
    $("#login-view").classList.add("hidden");
    $("#app-view").classList.remove("hidden");
    $("#user-name").textContent = state.user.name;
    $("#user-role").textContent = state.user.role;
    $("#user-initial").textContent = state.user.name.slice(0, 1).toUpperCase();
    $$('.nav-item[data-admin-only]').forEach((element) => element.classList.toggle("hidden", state.user.role !== "admin"));
    await loadData();
  } catch (error) {
    logout();
    $("#login-error").textContent = error.message;
  }
}

async function loadData() {
  setSyncing(true);
  try {
    [state.members, state.requests, state.tasks, state.reminders, state.communicationDrafts, state.communicationTemplates, state.jobs, state.workerStatus, state.trips, state.quotes, state.orders, state.aiProviderStatus] = await Promise.all([
      api("/api/members?limit=100"),
      api("/api/travel-requests?limit=100"),
      api("/api/tasks?limit=100"),
      api("/api/reminders?limit=100"),
      api("/api/communication-drafts?limit=100"),
      api("/api/communication-templates"),
      api("/api/operations/jobs?limit=20"),
      api("/api/operations/worker/status"),
      api("/api/trips"),
      api("/api/quotes"),
      api("/api/orders"),
      api("/api/ai/providers/status"),
    ]);
    const communicationVersionLists = await Promise.all(
      state.communicationDrafts.map((draft) => api(`/api/communication-drafts/${draft.id}/versions`))
    );
    state.communicationVersions = Object.fromEntries(
      state.communicationDrafts.map((draft, index) => [draft.id, communicationVersionLists[index]])
    );
    const paymentLists = await Promise.all(
      state.orders.map((order) => api(`/api/orders/${order.id}/payments`))
    );
    state.paymentsByOrder = Object.fromEntries(
      state.orders.map((order, index) => [order.id, paymentLists[index]])
    );
    const aiPlanLists = await Promise.all(
      state.requests.map((request) => api(`/api/travel-requests/${request.id}/ai-plans`))
    );
    state.aiPlans = aiPlanLists.flat().sort((a, b) => b.id - a.id);
    if (state.user.role === "admin") {
      [state.staffUsers, state.auditPage, state.auditFacets] = await Promise.all([
        api("/api/staff-users"),
        api(buildAuditPath(state.auditPage.offset || 0)),
        api("/api/audit-logs/facets"),
      ]);
    } else {
      state.staffUsers = [];
      state.auditPage = { items: [], total: 0, limit: 50, offset: 0 };
      state.auditFacets = { entity_types: [], actions: [], actors: [] };
    }
    if (!state.selectedTripId && state.trips.length) state.selectedTripId = state.trips[0].id;
    if (state.selectedTripId && state.trips.some((trip) => trip.id === state.selectedTripId)) {
      state.selectedTrip = await api(`/api/trips/${state.selectedTripId}`);
    } else {
      state.selectedTripId = null;
      state.selectedTrip = null;
    }
    renderAll();
  } finally {
    setSyncing(false);
  }
}

function buildAuditPath(offset = 0) {
  const parameters = new URLSearchParams({ limit: "50", offset: String(offset) });
  Object.entries(state.auditFilters).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) parameters.set(key, value);
  });
  return `/api/audit-logs?${parameters}`;
}

async function loadAuditLogs(offset = 0) {
  setSyncing(true);
  try {
    state.auditPage = await api(buildAuditPath(offset));
    renderAuditLogs();
  } finally {
    setSyncing(false);
  }
}

function renderAll() {
  renderStats();
  renderOverview();
  renderMembers();
  renderPipeline();
  renderTasks();
  renderReminders();
  renderJobs();
  renderTripStudio();
  renderOrders();
  renderAIPlans();
  renderOperationsAgent();
  renderStaff();
  renderAuditLogs();
  populateAuditFilters();
  populateFormOptions();
}

function renderStats() {
  const activeRequests = state.requests.filter((item) => !["completed", "cancelled"].includes(item.status));
  const activeTasks = state.tasks.filter((item) => !["completed", "cancelled"].includes(item.status));
  const urgentTasks = activeTasks.filter((item) => ["high", "urgent"].includes(item.priority));
  $("#stat-members").textContent = state.members.filter((item) => item.status === "active").length;
  $("#stat-requests").textContent = activeRequests.length;
  $("#stat-tasks").textContent = activeTasks.length;
  $("#stat-urgent").textContent = urgentTasks.length;
}

function renderOperationsAgent() {
  const container = $("#operations-agent-result");
  const run = state.latestAgentRun;
  if (!run) {
    container.innerHTML = '<div class="agent-empty"><span>✧</span><h3>等待你的問題</h3><p>Agent 的答案、使用工具與執行路徑會顯示在這裡。</p></div>';
    return;
  }
  container.innerHTML = `
    <div class="agent-result-heading"><div><p class="eyebrow">EVIDENCE-BACKED RESPONSE</p><h2>營運建議</h2></div><div class="agent-run-id"><strong>Run #${run.run_id}</strong><small>${escapeHtml(run.provider)} · ${run.node_trace.length} 個步驟${run.fallback_used ? " · fallback" : ""}</small></div></div>
    <div class="agent-answer">${escapeHtml(run.answer).replaceAll("\n", "<br>")}</div>
    <div class="agent-tools"><strong>使用的唯讀工具</strong><div>${run.tools_used.map((tool) => `<span><b>${escapeHtml(tool.label)}</b><small>${tool.result_count} 筆結果</small></span>`).join("")}</div></div>
    <div class="agent-guardrail"><strong>✓ Human-in-the-loop</strong><p>${escapeHtml(run.guardrails.note)}</p></div>
    <details class="agent-trace"><summary>查看 LangGraph 執行路徑</summary><ol>${run.node_trace.map((node) => `<li>${escapeHtml(node)}</li>`).join("")}</ol></details>`;
}

function memberName(memberId) {
  return state.members.find((member) => member.id === memberId)?.name || `會員 #${memberId}`;
}

function renderOverview() {
  const recent = [...state.requests].slice(0, 5);
  $("#recent-requests").innerHTML = recent.length ? recent.map((item) => `
    <div class="request-row">
      <div><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(memberName(item.member_id))}</small></div>
      <span>${escapeHtml(item.destination)}</span>
      <span>${formatMoney(item.budget_amount, item.budget_currency)}</span>
      <span class="status-badge ${escapeHtml(item.status)}">${escapeHtml(labels[item.status] || item.status)}</span>
    </div>`).join("") : '<div class="empty-state">尚無旅遊需求</div>';

  const priority = state.tasks
    .filter((item) => !["completed", "cancelled"].includes(item.status))
    .sort((a, b) => ({ urgent: 0, high: 1, normal: 2, low: 3 }[a.priority] - ({ urgent: 0, high: 1, normal: 2, low: 3 }[b.priority])))
    .slice(0, 5);
  $("#priority-tasks").innerHTML = priority.length ? priority.map((task) => `
    <div class="task-row">
      <span class="priority-dot ${escapeHtml(task.priority)}"></span>
      <div><strong>${escapeHtml(task.title)}</strong><small>${task.due_at ? `到期 ${formatDate(task.due_at, true)}` : "未設定期限"}</small></div>
      <span class="priority-badge">${escapeHtml(labels[task.priority] || task.priority)}</span>
    </div>`).join("") : '<div class="empty-state">尚無待辦任務</div>';
}

function renderMembers() {
  const keyword = $("#member-search").value.trim().toLowerCase();
  const members = state.members.filter((member) =>
    [member.name, member.email, member.phone].some((value) => String(value || "").toLowerCase().includes(keyword))
  );
  $("#member-table").innerHTML = members.map((member) => `
    <tr>
      <td><div class="member-cell"><span class="avatar">${escapeHtml(member.name.slice(0, 1).toUpperCase())}</span><div><strong>${escapeHtml(member.name)}</strong><br><small>#${member.id}</small></div></div></td>
      <td><span class="tier-badge ${escapeHtml(member.tier)}">${escapeHtml(labels[member.tier] || member.tier)}</span></td>
      <td>${escapeHtml(member.email || "—")}<br><small>${escapeHtml(member.phone || "")}</small></td>
      <td>${escapeHtml(member.source || "—")}</td>
      <td>${member.owner_id ? `#${member.owner_id}` : "未指派"}</td>
      <td>${formatDate(member.updated_at)}</td>
    </tr>`).join("");
  $("#member-empty").classList.toggle("hidden", members.length > 0);
}

function requestStatusOptions(item) {
  const options = [item.status, ...(requestTransitions[item.status] || [])];
  return options.map((status) => `<option value="${status}" ${status === item.status ? "selected" : ""}>${escapeHtml(labels[status] || status)}</option>`).join("");
}

function renderPipeline() {
  $("#pipeline-board").innerHTML = requestStatuses.map((status) => {
    const items = state.requests.filter((item) => item.status === status);
    return `<section class="pipeline-column">
      <div class="pipeline-heading"><strong>${escapeHtml(labels[status] || status)}</strong><span>${items.length}</span></div>
      <div class="pipeline-cards">${items.map((item) => `
        <article class="request-card">
          <h3>${escapeHtml(item.title)}</h3>
          <p>${escapeHtml(memberName(item.member_id))} · ${escapeHtml(item.destination)}</p>
          <div class="card-meta"><span>${item.party_size} 位旅客</span><span>${formatMoney(item.budget_amount, item.budget_currency)}</span></div>
          <select data-request-status="${item.id}" aria-label="更新 ${escapeHtml(item.title)} 狀態">${requestStatusOptions(item)}</select>
        </article>`).join("")}</div>
    </section>`;
  }).join("");
}

function taskStatusOptions(task) {
  const options = [task.status, ...(taskTransitions[task.status] || [])];
  return options.map((status) => `<option value="${status}" ${status === task.status ? "selected" : ""}>${escapeHtml(labels[status] || status)}</option>`).join("");
}

function renderTasks() {
  let tasks = state.tasks;
  if (state.taskFilter === "active") tasks = tasks.filter((item) => !["completed", "cancelled"].includes(item.status));
  if (state.taskFilter === "completed") tasks = tasks.filter((item) => item.status === "completed");
  $("#task-board").innerHTML = tasks.length ? tasks.map((task) => `
    <article class="task-card">
      <span class="priority-dot ${escapeHtml(task.priority)}"></span>
      <div><h3>${escapeHtml(task.title)}</h3><p>${escapeHtml(task.description || "沒有補充說明")}</p></div>
      <div><span class="priority-badge">${escapeHtml(labels[task.priority] || task.priority)}</span><p>${task.due_at ? formatDate(task.due_at, true) : "未設定期限"}</p></div>
      <select data-task-status="${task.id}" aria-label="更新 ${escapeHtml(task.title)} 狀態">${taskStatusOptions(task)}</select>
    </article>`).join("") : '<div class="panel empty-state">目前沒有符合條件的任務。</div>';
}

function renderReminders() {
  const active = state.reminders.filter((item) => item.status === "scheduled");
  $("#reminder-summary").innerHTML = `
    <div><span class="provider-dot ${active.length ? "live" : "local"}"></span><div><strong>${active.length} 筆待處理提醒</strong><small>規則掃描 · Human-in-the-loop</small></div></div>
    <p>相同來源與期限只會建立一次；處理結果會留下審核人員與時間。</p>`;
  $("#reminder-board").innerHTML = state.reminders.length ? state.reminders.map((item) => {
    const payload = item.payload || {};
    const draft = item.ai_draft;
    const communication = state.communicationDrafts.find((candidate) => candidate.reminder_id === item.id);
    const canEditCommunication = communication && communication.status !== "sent" && ["admin", "advisor"].includes(state.user.role);
    const canApproveCommunication = communication && communication.status === "draft" && state.user.role === "admin" && state.user.id !== communication.last_edited_by;
    const approvalHint = communication?.status === "draft"
      ? (state.user.id === communication.last_edited_by
        ? "等待另一位 Admin 核准（建立者／最後編輯者不可自行核准）"
        : state.user.role !== "admin" ? "等待 Admin 核准" : "可由目前 Admin 獨立核准")
      : "";
    const communicationVersions = communication ? (state.communicationVersions[communication.id] || []) : [];
    const templateOptions = state.communicationTemplates.map((template) => `<option value="${template.id}">${escapeHtml(template.name)} · v${template.version}</option>`).join("");
    const templateControls = canEditCommunication && templateOptions ? `<div class="communication-template-row">
      <select data-template-select="${communication.id}" aria-label="選擇通訊範本"><option value="">選擇範本</option>${templateOptions}</select>
      <button class="button ghost compact" type="button" data-apply-template="${communication.id}">套用範本</button>
    </div>` : "";
    const versionHistory = communicationVersions.length ? `<details class="communication-history">
      <summary>版本歷史（${communicationVersions.length}）</summary>
      <ol>${communicationVersions.map((version) => `<li><strong>v${version.version} · ${escapeHtml(communicationSourceLabels[version.source] || version.source)}</strong><small>${escapeHtml(version.edited_by_name)} · ${formatDate(version.created_at, true)}${version.source_template_name ? ` · ${escapeHtml(version.source_template_name)}` : ""}</small><span>${escapeHtml(version.subject)}</span></li>`).join("")}</ol>
    </details>` : "";
    const communicationPanel = communication ? `<form class="communication-editor" data-communication-form="${communication.id}">
      <div class="communication-heading"><div><strong>Mock Email 草稿</strong><small>${escapeHtml(communication.recipient_label)} · v${communication.version}</small></div><span class="status-badge ${escapeHtml(communication.status)}">${escapeHtml(labels[communication.status] || communication.status)}</span></div>
      ${templateControls}
      <label>主旨<input name="subject" value="${escapeHtml(communication.subject)}" maxlength="160" required ${canEditCommunication ? "" : "readonly"} /></label>
      <label>內容<textarea name="body" rows="5" maxlength="5000" required ${canEditCommunication ? "" : "readonly"}>${escapeHtml(communication.body)}</textarea></label>
      <small>建立：${escapeHtml(communication.created_by_name)} · 最後編輯：${escapeHtml(communication.last_edited_by_name)}${communication.approved_by_name ? ` · 核准：${escapeHtml(communication.approved_by_name)}` : ""}${communication.sent_by_name ? ` · 寄送：${escapeHtml(communication.sent_by_name)}` : ""}</small>
      <small>${escapeHtml(approvalHint || "Mock Provider 不會連外，也不會使用真實 Email 地址。")}</small>
      ${versionHistory}
      <footer>${canEditCommunication ? `<button class="button ghost compact" type="submit">儲存修改</button>` : ""}${canApproveCommunication ? `<button class="button primary compact" type="button" data-approve-communication="${communication.id}">核准 Mock 寄送</button>` : ""}${communication.status === "approved" && state.user.role === "admin" ? `<button class="button primary compact" type="button" data-send-communication="${communication.id}">執行 Mock Send</button>` : ""}</footer>
    </form>` : (item.ai_draft_status === "approved" ? `<button class="button ghost compact" type="button" data-create-communication="${item.id}">建立可編輯 Mock Email 草稿</button>` : "");
    const draftPanel = draft ? `<details class="ai-followup" open>
      <summary><span>✦ AI Follow-up Copilot</span><span class="status-badge ${escapeHtml(item.ai_draft_status)}">${escapeHtml(labels[item.ai_draft_status] || item.ai_draft_status)}</span></summary>
      <div class="ai-followup-body">
        ${draft.provider_warning ? `<div class="guardrail-note">⚠ ${escapeHtml(draft.provider_warning)}</div>` : ""}
        <p><strong>內部摘要</strong>${escapeHtml(draft.internal_summary)}</p>
        <div><strong>建議步驟</strong><ol>${(draft.recommended_steps || []).map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol></div>
        <div class="message-draft"><small>聯絡草稿 · 尚未寄送</small><strong>${escapeHtml(draft.message_subject)}</strong><p>${escapeHtml(draft.message_body)}</p></div>
        ${item.ai_draft_status === "awaiting_review" ? `<footer><button class="button primary compact" data-review-followup="${item.id}" data-decision="approve">核准供顧問使用</button><button class="button ghost compact" data-review-followup="${item.id}" data-decision="reject">退回草稿</button></footer>` : `<small>此狀態只記錄人工判斷，不會觸發寄送。</small>`}
        ${communicationPanel}
      </div>
    </details>` : (item.status === "scheduled" ? `<button class="button ghost compact ai-draft-button" data-generate-followup="${item.id}">✦ 產生 AI 跟進草稿</button>` : "");
    return `<article class="panel reminder-card ${escapeHtml(payload.severity || "normal")}">
      <div class="reminder-icon">${item.reminder_type === "payment_follow_up" ? "$" : item.reminder_type === "trip_countdown" ? "✈" : "!"}</div>
      <div class="reminder-copy"><p class="eyebrow">${escapeHtml(labels[item.reminder_type] || item.reminder_type)} · ${escapeHtml(payload.severity || "normal")}</p><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(payload.reason || "需要人工確認")}</p><small>建議：${escapeHtml(payload.recommended_action || "檢查最新狀態")} · ${formatDate(item.scheduled_at, true)}</small></div>
      <span class="status-badge ${escapeHtml(item.status)}">${escapeHtml(labels[item.status] || item.status)}</span>
      <div class="reminder-actions">${item.status === "scheduled" ? `<button class="button primary compact" data-reminder-status="${item.id}" data-target-status="acknowledged">已處理</button><button class="button ghost compact" data-reminder-status="${item.id}" data-target-status="dismissed">略過</button>` : `<small>${item.reviewed_at ? formatDate(item.reviewed_at, true) : "已完成審核"}</small>`}</div>
      ${draftPanel}
    </article>`;
  }).join("") : '<div class="panel empty-state">尚無提醒。按「掃描營運風險」檢查目前資料。</div>';
}

function renderJobs() {
  const status = state.workerStatus || {};
  $("#worker-status").innerHTML = `<span class="provider-dot ${status.redis_ready ? "live" : "local"}"></span><strong>${status.redis_ready ? "Redis Ready" : "Redis Offline"}</strong><small>重試 ${status.retrying || 0} · Dead Letter ${status.dead_letter || 0}</small>`;
  $("#job-board").innerHTML = state.jobs.length ? state.jobs.map((job) => `
    <div class="job-row">
      <div><strong>${escapeHtml(labels[job.event_type] || job.event_type)}</strong><small>#${job.id} · ${formatDate(job.created_at, true)}</small></div>
      <span>${job.attempts} 次嘗試</span>
      <span class="status-badge ${escapeHtml(job.status)}">${escapeHtml(labels[job.status] || job.status)}</span>
      ${job.status === "dead_letter" && state.user.role === "admin" ? `<button class="button ghost compact" data-retry-job="${job.id}">重新排程</button>` : `<small>${job.last_error ? escapeHtml(job.last_error) : "—"}</small>`}
    </div>`).join("") : '<div class="panel empty-state">Worker 啟動後會在這裡顯示排程紀錄。</div>';
}

function populateFormOptions() {
  const memberOptions = state.members.map((member) => `<option value="${member.id}">${escapeHtml(member.name)}</option>`).join("");
  $("#request-member").innerHTML = memberOptions || '<option value="">請先建立會員</option>';
  $("#task-member").innerHTML = `<option value="">不指定</option>${memberOptions}`;
  $("#task-request").innerHTML = `<option value="">不指定</option>${state.requests.map((item) => `<option value="${item.id}">${escapeHtml(item.title)}</option>`).join("")}`;
  $("#trip-request").innerHTML = state.requests.map((item) => `<option value="${item.id}">${escapeHtml(item.title)}</option>`).join("") || '<option value="">請先建立需求</option>';
  $("#ai-plan-request").innerHTML = state.requests.map((item) => `<option value="${item.id}">${escapeHtml(item.title)}</option>`).join("") || '<option value="">請先建立需求</option>';
}

function populateAuditFilters() {
  if (state.user?.role !== "admin") return;
  const selected = state.auditFilters;
  $("#audit-entity-type").innerHTML = `<option value="">全部</option>${state.auditFacets.entity_types.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("")}`;
  $("#audit-action").innerHTML = `<option value="">全部</option>${state.auditFacets.actions.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("")}`;
  $("#audit-actor").innerHTML = `<option value="">全部</option>${state.auditFacets.actors.map((actor) => `<option value="${actor.id}">${escapeHtml(actor.name)}</option>`).join("")}`;
  $("#audit-entity-type").value = selected.entity_type || "";
  $("#audit-action").value = selected.action || "";
  $("#audit-actor").value = selected.actor_id || "";
}

function renderAuditData(label, value) {
  if (!value) return "";
  return `<div><strong>${label}</strong><pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre></div>`;
}

function renderAuditLogs() {
  if (state.user?.role !== "admin") return;
  const page = state.auditPage;
  $("#audit-total").textContent = `${page.total} 筆`;
  $("#audit-log-table").innerHTML = page.items.map((item) => `<tr>
    <td>${formatDate(item.created_at, true)}</td>
    <td><strong>${escapeHtml(item.actor_name || "System")}</strong><br><small>${item.actor_id ? `#${item.actor_id}` : "背景程序"}</small></td>
    <td><span class="audit-entity">${escapeHtml(item.entity_type)}</span><br><small>#${escapeHtml(item.entity_id)}</small></td>
    <td><span class="audit-action">${escapeHtml(item.action)}</span></td>
    <td><details class="audit-detail"><summary>檢視變更</summary><div class="audit-json-grid">${renderAuditData("Before", item.before_data)}${renderAuditData("After", item.after_data) || '<div class="muted">沒有內容快照</div>'}</div>${item.correlation_id ? `<small>Correlation ID：${escapeHtml(item.correlation_id)}</small>` : ""}</details></td>
  </tr>`).join("");
  $("#audit-empty").classList.toggle("hidden", page.items.length > 0);
  const currentPage = Math.floor(page.offset / page.limit) + 1;
  const pageCount = Math.max(1, Math.ceil(page.total / page.limit));
  $("#audit-page-info").textContent = `第 ${currentPage} / ${pageCount} 頁`;
  $("#audit-prev").disabled = page.offset === 0;
  $("#audit-next").disabled = page.offset + page.limit >= page.total;
}

function renderStaff() {
  if (state.user?.role !== "admin") return;
  $("#staff-table").innerHTML = state.staffUsers.map((staff) => {
    const isSelf = staff.id === state.user.id;
    const roleOptions = ["advisor", "finance", "admin"].map((role) =>
      `<option value="${role}" ${staff.role === role ? "selected" : ""}>${labels[role]}</option>`
    ).join("");
    return `<tr>
      <td><strong>${escapeHtml(staff.name)}</strong><br><small>${escapeHtml(staff.email)} · #${staff.id}</small></td>
      <td><select class="staff-role-select" data-staff-role="${staff.id}" ${isSelf ? "disabled" : ""}>${roleOptions}</select></td>
      <td><span class="status-badge ${staff.is_active ? "active" : "inactive"}">${staff.is_active ? labels.active : labels.inactive}</span></td>
      <td>${formatDate(staff.created_at)}</td>
      <td>${isSelf
        ? '<span class="self-account">目前帳號</span>'
        : `<button class="button ghost compact" data-staff-active="${staff.id}" data-next-active="${staff.is_active ? "false" : "true"}">${staff.is_active ? "停用帳號" : "重新啟用"}</button>`}
      </td>
    </tr>`;
  }).join("");
  $("#staff-empty").classList.toggle("hidden", state.staffUsers.length > 0);
}

function showSection(section) {
  $$(".workspace-section").forEach((element) => element.classList.add("hidden"));
  $(`#section-${section}`).classList.remove("hidden");
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.section === section));
  $("#page-title").textContent = ({ overview: "營運總覽", members: "會員管理", requests: "需求 Pipeline", "operations-agent": "AI Operations Copilot", "ai-planning": "AI 行程規劃", itineraries: "行程與報價", orders: "訂單與付款", reminders: "營運提醒", tasks: "內部任務", staff: "員工權限", audit: "Audit Log" })[section];
}

function tripStatusOptions(trip) {
  return [trip.status, ...(tripTransitions[trip.status] || [])]
    .map((value) => `<option value="${value}" ${value === trip.status ? "selected" : ""}>${escapeHtml(labels[value] || value)}</option>`)
    .join("");
}

function allowedQuoteTransitions(quote) {
  const candidates = quoteTransitions[quote.status] || [];
  if (state.user.role === "admin") return candidates;
  if (state.user.role === "finance") return candidates.filter((item) => ["approved", "rejected"].includes(item));
  return candidates.filter((item) => !["approved", "rejected"].includes(item));
}

function quoteStatusOptions(quote) {
  return [quote.status, ...allowedQuoteTransitions(quote)]
    .map((value) => `<option value="${value}" ${value === quote.status ? "selected" : ""}>${escapeHtml(labels[value] || value)}</option>`)
    .join("");
}

function renderTripStudio() {
  $("#trip-list").innerHTML = state.trips.length ? state.trips.map((trip) => `
    <button class="trip-list-card ${trip.id === state.selectedTripId ? "active" : ""}" data-select-trip="${trip.id}">
      <strong>${escapeHtml(trip.name)}</strong>
      <small>${escapeHtml(labels[trip.status] || trip.status)} · v${trip.version}</small>
    </button>`).join("") : '<div class="empty-state">尚無行程草稿</div>';

  const trip = state.selectedTrip;
  if (!trip) {
    $("#trip-detail").innerHTML = '<div class="empty-state">選擇一筆行程開始編輯。</div>';
    return;
  }
  const quotes = state.quotes.filter((quote) => quote.trip_id === trip.id);
  const request = state.requests.find((item) => item.id === trip.request_id);
  const itemIcons = { hotel: "▣", flight: "✈", transfer: "↔", activity: "◇", dining: "◉", other: "＋" };
  $("#trip-detail").innerHTML = `
    <div class="trip-detail-header">
      <div><p class="eyebrow">ITINERARY V${trip.version}</p><h2>${escapeHtml(trip.name)}</h2><p>${escapeHtml(request?.title || `需求 #${trip.request_id}`)} · ${formatDate(trip.start_date)} — ${formatDate(trip.end_date)}</p></div>
      <div class="trip-actions"><select data-trip-status="${trip.id}">${tripStatusOptions(trip)}</select><button class="button ghost" data-open-dialog="item-dialog">＋ 項目</button><button class="button primary" data-open-dialog="quote-dialog">建立報價</button></div>
    </div>
    <div class="studio-block">
      <div class="studio-block-heading"><h3>行程項目</h3><span class="muted">${trip.items.length} 項</span></div>
      <div class="itinerary-items">${trip.items.length ? trip.items.map((item) => `
        <div class="itinerary-item">
          <span class="item-type-icon">${itemIcons[item.item_type] || "＋"}</span>
          <div><div class="item-title-row"><strong>${escapeHtml(item.title)}</strong><button class="text-button" data-edit-item="${item.id}">編輯</button></div><small>${escapeHtml(labels[item.item_type] || item.item_type)} · ${escapeHtml(item.supplier_name || item.location || "未指定供應商")}</small></div>
          <div class="item-quantity">數量 ${item.quantity}</div>
          <div class="item-price">${formatMoney(item.unit_price ? Number(item.unit_price) * item.quantity : null)}</div>
        </div>`).join("") : '<div class="empty-state">加入飯店、交通或活動後即可建立報價。</div>'}</div>
    </div>
    <div class="studio-block">
      <div class="studio-block-heading"><h3>報價版本</h3><span class="muted">每一版都是不可變快照</span></div>
      <div class="quote-list">${quotes.length ? quotes.map((quote) => `
        <div class="quote-card">
          <div><strong>${escapeHtml(quote.quote_number)}</strong><small>Version ${quote.version}${quote.parent_quote_id ? ` · 延續 #${quote.parent_quote_id}` : ""}</small></div>
          <span class="status-badge ${escapeHtml(quote.status)}">${escapeHtml(labels[quote.status] || quote.status)}</span>
          <div class="quote-total">${formatMoney(quote.total, quote.currency)}</div>
          <div class="quote-action">
            ${quote.status === "approved" ? `<button class="button ghost compact" data-download-quote="${quote.id}" data-quote-number="${escapeHtml(quote.quote_number)}">下載 PDF</button>` : ""}
            ${quote.status === "approved" && !state.orders.some((order) => order.quote_id === quote.id)
              ? `<button class="button primary compact" data-create-order="${quote.id}">建立訂單</button>`
              : `<select data-quote-status="${quote.id}">${quoteStatusOptions(quote)}</select>`}
          </div>
        </div>`).join("") : '<div class="empty-state">尚未建立報價版本。</div>'}</div>
    </div>`;
}

function renderOrders() {
  const board = $("#order-board");
  if (!state.orders.length) {
    board.innerHTML = '<div class="panel empty-state">核准報價後，可在「行程與報價」建立第一筆訂單。</div>';
    return;
  }
  board.innerHTML = state.orders.map((order) => {
    const payments = state.paymentsByOrder[order.id] || [];
    const latest = payments[0];
    const canPay = order.status === "pending_payment" && (!latest || latest.status === "failed");
    return `<article class="panel order-card">
      <header class="order-heading">
        <div><p class="eyebrow">ORDER #${order.id}</p><h2>${escapeHtml(order.order_number)}</h2><small>${escapeHtml(memberName(order.member_id))} · 報價 #${order.quote_id}</small></div>
        <div class="order-total"><span class="status-badge ${escapeHtml(order.status)}">${escapeHtml(labels[order.status] || order.status)}</span><strong>${formatMoney(order.total, order.currency)}</strong></div>
      </header>
      <div class="payment-timeline">${payments.length ? payments.map((payment) => `
        <div class="payment-row">
          <div><strong>付款嘗試 #${payment.attempt_number}</strong><small>${escapeHtml(payment.provider)} · ${escapeHtml(payment.provider_transaction_id || "等待交易編號")}</small></div>
          <span class="status-badge ${escapeHtml(payment.status)}">${escapeHtml(labels[payment.status] || payment.status)}</span>
          <span>${formatMoney(payment.amount, payment.currency)}</span>
          <div class="payment-actions">${payment.status === "processing" && payment.provider === "mockpay" && state.user.role === "admin" ? `
            <button class="button primary compact" data-simulate-payment="${payment.id}" data-result="succeeded">模擬成功</button>
            <button class="button ghost compact" data-simulate-payment="${payment.id}" data-result="failed">模擬失敗</button>` : ""}</div>
        </div>`).join("") : '<div class="empty-state compact-empty">尚未發起付款。</div>'}</div>
      ${canPay ? `<footer class="order-footer"><button class="button primary" data-create-payment="${order.id}" data-attempt="${payments.length + 1}">發起 MockPay 付款</button></footer>` : ""}
    </article>`;
  }).join("");
}

function renderAIPlans() {
  const board = $("#ai-plan-board");
  const provider = state.aiProviderStatus;
  const dialogNotice = $("#ai-plan-provider-notice");
  if (dialogNotice && provider) {
    dialogNotice.textContent = provider.active_provider === "gemini"
      ? `將使用 ${provider.active_model} 產生草稿；不會查詢即時價格或庫存。`
      : "本機 local-planner 不會呼叫外部模型，也不會查詢即時價格或庫存。";
  }
  $("#ai-provider-status").innerHTML = provider ? `
    <div><span class="provider-dot ${provider.active_provider === "gemini" ? "live" : "local"}"></span><div><strong>${provider.active_provider === "gemini" ? "Gemini API" : "Local Planner"}</strong><small>${escapeHtml(provider.active_model)}${provider.fallback_model ? ` → ${escapeHtml(provider.fallback_model)}` : ""}</small></div></div>
    <p>${provider.active_provider === "gemini"
      ? "已啟用外部模型；只傳送畫面列出的必要規劃欄位。"
      : provider.gemini_configured
        ? "Gemini key 已設定；將 AI_PLANNING_PROVIDER 切換為 gemini 後即可啟用。"
        : "目前為離線測試模式；設定免費 Gemini API key 後即可切換真實模型。"}</p>` : "";
  if (!state.aiPlans.length) {
    board.innerHTML = '<div class="panel empty-state">選擇一筆旅遊需求，產生第一份待人工審核的行程草稿。</div>';
    return;
  }
  board.innerHTML = state.aiPlans.map((run) => {
    const output = run.output_data || {};
    const request = state.requests.find((item) => item.id === run.request_id);
    const items = output.itinerary_items || [];
    return `<article class="panel ai-plan-card">
      <header class="ai-plan-heading">
        <div><p class="eyebrow">${escapeHtml(run.workflow_name)} · ${escapeHtml(run.model_name)}</p><h2>${escapeHtml(output.draft_name || `AI 草稿 #${run.id}`)}</h2><small>${escapeHtml(request?.title || `需求 #${run.request_id}`)} · ${formatDate(run.completed_at, true)}</small></div>
        <span class="status-badge ${escapeHtml(run.status)}">${escapeHtml(labels[run.status] || run.status)}</span>
      </header>
      <div class="ai-summary"><strong>需求摘要</strong><p>${escapeHtml(output.summary || "尚無摘要")}</p></div>
      <div class="ai-meta-grid">
        <div><strong>缺漏資訊</strong><p>${output.missing_fields?.length ? output.missing_fields.map(escapeHtml).join("、") : "資料欄位完整"}</p></div>
        <div><strong>工作流節點</strong><p>${(output.node_trace || []).map(escapeHtml).join(" → ")}</p></div>
      </div>
      <div class="ai-draft-items">${items.map((item) => `
        <div><span>Day ${item.day}</span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.rationale)}</small></div>`).join("")}</div>
      <div class="guardrail-note">⚠ ${(output.guardrails?.warnings || []).map(escapeHtml).join(" ")}</div>
      ${run.status === "awaiting_review" ? `<footer class="ai-review-actions"><button class="button primary" data-review-ai="${run.id}" data-decision="approve">核准並建立行程</button><button class="button ghost" data-review-ai="${run.id}" data-decision="reject">退回草稿</button></footer>` : run.applied_trip_id ? `<footer class="ai-review-actions"><button class="text-button" data-open-applied-trip="${run.applied_trip_id}">查看行程 #${run.applied_trip_id} →</button></footer>` : ""}
    </article>`;
  }).join("");
}

function formError(form, message = "") {
  form.querySelector(".form-error").textContent = message;
}

function commaList(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#login-error").textContent = "";
  try {
    await login($("#login-email").value.trim(), $("#login-password").value);
  } catch (error) {
    $("#login-error").textContent = error.message;
  }
});

$("#logout-button").addEventListener("click", logout);
$("#member-search").addEventListener("input", renderMembers);

$$('[data-dialog]').forEach((button) => button.addEventListener("click", () => {
  const dialog = document.getElementById(button.dataset.dialog);
  formError(dialog.querySelector("form"));
  dialog.showModal();
}));

$$('.close-dialog').forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
$$('.nav-item').forEach((button) => button.addEventListener("click", () => showSection(button.dataset.section)));
$$('.section-link').forEach((button) => button.addEventListener("click", () => showSection(button.dataset.target)));

$("#audit-filter-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget));
  state.auditFilters = Object.fromEntries(
    Object.entries(values).filter(([, value]) => value !== "")
  );
  try {
    await loadAuditLogs(0);
    showSection("audit");
  } catch (error) { showToast(error.message, true); }
});

$("#audit-reset").addEventListener("click", async () => {
  $("#audit-filter-form").reset();
  state.auditFilters = {};
  try {
    await loadAuditLogs(0);
    showSection("audit");
  } catch (error) { showToast(error.message, true); }
});

$("#audit-prev").addEventListener("click", async () => {
  try {
    await loadAuditLogs(Math.max(0, state.auditPage.offset - state.auditPage.limit));
  } catch (error) { showToast(error.message, true); }
});

$("#audit-next").addEventListener("click", async () => {
  try {
    await loadAuditLogs(state.auditPage.offset + state.auditPage.limit);
  } catch (error) { showToast(error.message, true); }
});

$("#member-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  try {
    await api("/api/members", { method: "POST", body: JSON.stringify({
      name: values.name, email: values.email || null, phone: values.phone || null,
      locale: "zh-TW", tier: values.tier, source: values.source || null,
      notes: values.notes || null, travel_styles: commaList(values.travel_styles),
      dietary_restrictions: [], room_preferences: [], accessibility_needs: [],
    }) });
    form.reset(); form.closest("dialog").close(); await loadData(); showToast("會員已建立");
  } catch (error) { formError(form, error.message); }
});

$$('[data-agent-prompt]').forEach((button) => button.addEventListener("click", () => {
  $("#operations-agent-question").value = button.dataset.agentPrompt;
  $("#operations-agent-question").focus();
}));

$("#operations-agent-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  button.textContent = "分析營運資料中…";
  try {
    state.latestAgentRun = await api("/api/operations-agent/runs", {
      method: "POST",
      body: JSON.stringify({ question: $("#operations-agent-question").value.trim() }),
    });
    renderOperationsAgent();
    showToast("Agent 已完成唯讀分析");
  } catch (error) { showToast(error.message, true); }
  finally {
    button.disabled = false;
    button.textContent = "✧ 執行 Agent";
  }
});

$("#staff-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  try {
    await api("/api/staff-users", {
      method: "POST",
      body: JSON.stringify({
        name: values.name,
        email: values.email,
        role: values.role,
        password: values.password,
      }),
    });
    form.reset();
    form.closest("dialog").close();
    await loadData();
    showSection("staff");
    showToast("員工帳號已建立");
  } catch (error) { formError(form, error.message); }
});

$("#staff-table").addEventListener("change", async (event) => {
  const select = event.target.closest("[data-staff-role]");
  if (!select) return;
  select.disabled = true;
  try {
    await api(`/api/staff-users/${select.dataset.staffRole}`, {
      method: "PATCH",
      body: JSON.stringify({ role: select.value }),
    });
    await loadData();
    showSection("staff");
    showToast("員工角色已更新");
  } catch (error) {
    await loadData();
    showSection("staff");
    showToast(error.message, true);
  }
});

$("#staff-table").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-staff-active]");
  if (!button) return;
  button.disabled = true;
  try {
    await api(`/api/staff-users/${button.dataset.staffActive}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: button.dataset.nextActive === "true" }),
    });
    await loadData();
    showSection("staff");
    showToast(button.dataset.nextActive === "true" ? "員工帳號已啟用" : "員工帳號已停用");
  } catch (error) {
    await loadData();
    showSection("staff");
    showToast(error.message, true);
  }
});

$("#request-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  try {
    await api("/api/travel-requests", { method: "POST", body: JSON.stringify({
      member_id: Number(values.member_id), title: values.title,
      destination: values.destination, start_date: values.start_date || null,
      end_date: values.end_date || null, party_size: Number(values.party_size),
      budget_currency: "TWD", budget_amount: values.budget_amount ? Number(values.budget_amount) : null,
      requirements: values.requirements ? { notes: values.requirements } : {},
    }) });
    form.reset(); form.closest("dialog").close(); await loadData(); showSection("requests"); showToast("旅遊需求已建立");
  } catch (error) { formError(form, error.message); }
});

$("#task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  try {
    await api("/api/tasks", { method: "POST", body: JSON.stringify({
      title: values.title, description: values.description || null,
      member_id: values.member_id ? Number(values.member_id) : null,
      request_id: values.request_id ? Number(values.request_id) : null,
      assignee_id: state.user.id, priority: values.priority,
      due_at: values.due_at || null,
    }) });
    form.reset(); form.closest("dialog").close(); await loadData(); showSection("tasks"); showToast("任務已建立");
  } catch (error) { formError(form, error.message); }
});

$("#trip-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  try {
    const trip = await api(`/api/travel-requests/${values.request_id}/trips`, {
      method: "POST",
      body: JSON.stringify({
        name: values.name,
        start_date: values.start_date || null,
        end_date: values.end_date || null,
      }),
    });
    state.selectedTripId = trip.id;
    form.reset(); form.closest("dialog").close(); await loadData(); showSection("itineraries"); showToast("行程草稿已建立");
  } catch (error) { formError(form, error.message); }
});

$("#item-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  if (!state.selectedTripId) return formError(form, "請先選擇行程");
  try {
    const payload = {
      item_type: values.item_type,
      title: values.title,
      supplier_name: values.supplier_name || null,
      location: values.location || null,
      unit_price: Number(values.unit_price),
      quantity: Number(values.quantity),
      sort_order: Number(values.sort_order),
    };
    const editing = Boolean(values.item_id);
    if (editing) {
      await api(`/api/trip-items/${values.item_id}`, {
        method: "PATCH", body: JSON.stringify(payload),
      });
    } else {
      await api(`/api/trips/${state.selectedTripId}/items`, {
        method: "POST",
        body: JSON.stringify({ ...payload, source_payload: { source: "admin_dashboard" } }),
      });
    }
    form.reset(); form.closest("dialog").close(); await loadData();
    showToast(editing ? "行程項目已更新" : "行程項目已加入");
  } catch (error) { formError(form, error.message); }
});

$("#quote-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  if (!state.selectedTripId) return formError(form, "請先選擇行程");
  try {
    await api(`/api/trips/${state.selectedTripId}/quotes`, {
      method: "POST",
      body: JSON.stringify({
        tax_rate: Number(values.tax_rate || 0) / 100,
        expires_at: values.expires_at || null,
        notes: values.notes || null,
      }),
    });
    form.reset(); form.closest("dialog").close(); await loadData(); showToast("新版報價快照已建立");
  } catch (error) { formError(form, error.message); }
});

$("#ai-plan-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  const submit = form.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    await api(`/api/travel-requests/${values.request_id}/ai-plans`, {
      method: "POST",
      headers: { "Idempotency-Key": `ai-plan-${values.request_id}-${crypto.randomUUID()}` },
      body: JSON.stringify({ planning_notes: values.planning_notes || null }),
    });
    form.reset(); form.closest("dialog").close(); await loadData(); showSection("ai-planning"); showToast("AI 草稿已產生，等待人工審核");
  } catch (error) { formError(form, error.message); }
  finally { submit.disabled = false; }
});

$("#ai-plan-board").addEventListener("click", async (event) => {
  const reviewButton = event.target.closest("[data-review-ai]");
  const tripButton = event.target.closest("[data-open-applied-trip]");
  if (tripButton) {
    state.selectedTripId = Number(tripButton.dataset.openAppliedTrip);
    await loadData(); showSection("itineraries");
    return;
  }
  if (!reviewButton) return;
  reviewButton.disabled = true;
  try {
    const result = await api(`/api/ai-plans/${reviewButton.dataset.reviewAi}/review`, {
      method: "POST",
      body: JSON.stringify({ decision: reviewButton.dataset.decision, notes: null }),
    });
    if (result.trip_id) state.selectedTripId = result.trip_id;
    await loadData(); showSection("ai-planning");
    showToast(result.trip_id ? "草稿已核准並建立可編輯行程" : "AI 草稿已退回");
  } catch (error) { reviewButton.disabled = false; showToast(error.message, true); }
});

$("#pipeline-board").addEventListener("change", async (event) => {
  const select = event.target.closest("[data-request-status]");
  if (!select) return;
  try {
    await api(`/api/travel-requests/${select.dataset.requestStatus}`, {
      method: "PATCH", body: JSON.stringify({ status: select.value }),
    });
    await loadData(); showToast("需求狀態已更新");
  } catch (error) { await loadData(); showToast(error.message, true); }
});

$("#task-board").addEventListener("change", async (event) => {
  const select = event.target.closest("[data-task-status]");
  if (!select) return;
  try {
    await api(`/api/tasks/${select.dataset.taskStatus}`, {
      method: "PATCH", body: JSON.stringify({ status: select.value }),
    });
    await loadData(); showToast("任務狀態已更新");
  } catch (error) { await loadData(); showToast(error.message, true); }
});

$("#scan-reminders-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const result = await api("/api/reminders/scan", { method: "POST" });
    await loadData();
    showSection("reminders");
    showToast(`新增 ${result.created_count} 筆提醒；${result.existing_count} 筆已存在`);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#reminder-board").addEventListener("click", async (event) => {
  const createCommunication = event.target.closest("[data-create-communication]");
  const applyTemplate = event.target.closest("[data-apply-template]");
  const approveCommunication = event.target.closest("[data-approve-communication]");
  const sendCommunication = event.target.closest("[data-send-communication]");
  if (applyTemplate) {
    const draftId = applyTemplate.dataset.applyTemplate;
    const select = document.querySelector(`[data-template-select="${draftId}"]`);
    if (!select?.value) return showToast("請先選擇通訊範本", true);
    applyTemplate.disabled = true;
    try {
      await api(`/api/communication-drafts/${draftId}/templates/${select.value}`, { method: "POST" });
      await loadData(); showSection("reminders"); showToast("範本已套用並建立新版本；核准狀態已重設");
    } catch (error) { applyTemplate.disabled = false; showToast(error.message, true); }
    return;
  }
  if (createCommunication) {
    createCommunication.disabled = true;
    try {
      await api(`/api/reminders/${createCommunication.dataset.createCommunication}/communication-draft`, { method: "POST" });
      await loadData(); showSection("reminders"); showToast("可編輯 Mock Email 草稿已建立");
    } catch (error) { createCommunication.disabled = false; showToast(error.message, true); }
    return;
  }
  if (approveCommunication) {
    approveCommunication.disabled = true;
    try {
      await api(`/api/communication-drafts/${approveCommunication.dataset.approveCommunication}/approve`, { method: "POST" });
      await loadData(); showSection("reminders"); showToast("通訊草稿已核准；尚未執行 Mock Send");
    } catch (error) { approveCommunication.disabled = false; showToast(error.message, true); }
    return;
  }
  if (sendCommunication) {
    sendCommunication.disabled = true;
    try {
      await api(`/api/communication-drafts/${sendCommunication.dataset.sendCommunication}/send`, {
        method: "POST",
        headers: { "Idempotency-Key": `mock-send-${sendCommunication.dataset.sendCommunication}` },
      });
      await loadData(); showSection("reminders"); showToast("Mock Send 完成；未連線至外部 Email 服務");
    } catch (error) { sendCommunication.disabled = false; showToast(error.message, true); }
    return;
  }
  const generateButton = event.target.closest("[data-generate-followup]");
  const reviewButton = event.target.closest("[data-review-followup]");
  if (generateButton) {
    generateButton.disabled = true;
    try {
      await api(`/api/reminders/${generateButton.dataset.generateFollowup}/ai-draft`, {
        method: "POST",
        headers: { "Idempotency-Key": `followup-${generateButton.dataset.generateFollowup}-${crypto.randomUUID()}` },
      });
      await loadData(); showSection("reminders"); showToast("AI 跟進草稿已產生，等待人工審核");
    } catch (error) { generateButton.disabled = false; showToast(error.message, true); }
    return;
  }
  if (reviewButton) {
    reviewButton.disabled = true;
    try {
      await api(`/api/reminders/${reviewButton.dataset.reviewFollowup}/ai-draft/review`, {
        method: "POST",
        body: JSON.stringify({ decision: reviewButton.dataset.decision, notes: null }),
      });
      await loadData(); showSection("reminders");
      showToast(reviewButton.dataset.decision === "approve" ? "草稿已核准供顧問使用；尚未寄送" : "AI 草稿已退回");
    } catch (error) { reviewButton.disabled = false; showToast(error.message, true); }
    return;
  }
  const button = event.target.closest("[data-reminder-status]");
  if (!button) return;
  button.disabled = true;
  try {
    await api(`/api/reminders/${button.dataset.reminderStatus}`, {
      method: "PATCH",
      body: JSON.stringify({ status: button.dataset.targetStatus }),
    });
    await loadData();
    showSection("reminders");
    showToast(button.dataset.targetStatus === "acknowledged" ? "提醒已標記為處理完成" : "提醒已略過");
  } catch (error) {
    button.disabled = false;
    showToast(error.message, true);
  }
});

$("#reminder-board").addEventListener("submit", async (event) => {
  const form = event.target.closest("[data-communication-form]");
  if (!form) return;
  event.preventDefault();
  const submit = form.querySelector('button[type="submit"]');
  submit.disabled = true;
  const values = Object.fromEntries(new FormData(form));
  try {
    await api(`/api/communication-drafts/${form.dataset.communicationForm}`, {
      method: "PATCH",
      body: JSON.stringify({ subject: values.subject, body: values.body }),
    });
    await loadData(); showSection("reminders"); showToast("修改已儲存；如曾核准，核准狀態已重設");
  } catch (error) { submit.disabled = false; showToast(error.message, true); }
});

$("#job-board").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-retry-job]");
  if (!button) return;
  button.disabled = true;
  try {
    await api(`/api/operations/jobs/${button.dataset.retryJob}/retry`, { method: "POST" });
    await loadData(); showSection("reminders"); showToast("Dead Letter 工作已重新排程");
  } catch (error) { button.disabled = false; showToast(error.message, true); }
});

$("#trip-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-select-trip]");
  if (!button) return;
  state.selectedTripId = Number(button.dataset.selectTrip);
  state.selectedTrip = await api(`/api/trips/${state.selectedTripId}`);
  renderTripStudio();
});

$("#trip-detail").addEventListener("click", async (event) => {
  const downloadButton = event.target.closest("[data-download-quote]");
  if (downloadButton) {
    downloadButton.disabled = true;
    try {
      await downloadPdf(
        `/api/quotes/${downloadButton.dataset.downloadQuote}/documents/proposal.pdf`,
        `voyageops-${downloadButton.dataset.quoteNumber}.pdf`,
      );
      showToast("報價 PDF 已下載");
    } catch (error) {
      showToast(error.message, true);
    } finally {
      downloadButton.disabled = false;
    }
    return;
  }
  const editItemButton = event.target.closest("[data-edit-item]");
  if (editItemButton) {
    const item = state.selectedTrip?.items.find(
      (candidate) => candidate.id === Number(editItemButton.dataset.editItem)
    );
    if (!item) return;
    const form = $("#item-form");
    form.reset();
    form.elements.item_id.value = item.id;
    form.elements.item_type.value = item.item_type;
    form.elements.sort_order.value = item.sort_order;
    form.elements.title.value = item.title;
    form.elements.supplier_name.value = item.supplier_name || "";
    form.elements.location.value = item.location || "";
    form.elements.unit_price.value = item.unit_price ?? "";
    form.elements.quantity.value = item.quantity;
    $("#item-dialog-title").textContent = "編輯行程項目";
    $("#item-submit-button").textContent = "儲存變更";
    formError(form);
    form.closest("dialog").showModal();
    return;
  }
  const createOrderButton = event.target.closest("[data-create-order]");
  if (createOrderButton) {
    createOrderButton.disabled = true;
    try {
      await api(`/api/quotes/${createOrderButton.dataset.createOrder}/orders`, {
        method: "POST",
        headers: { "Idempotency-Key": `order-quote-${createOrderButton.dataset.createOrder}` },
      });
      await loadData(); showSection("orders"); showToast("訂單已建立");
    } catch (error) { createOrderButton.disabled = false; showToast(error.message, true); }
    return;
  }
  const button = event.target.closest("[data-open-dialog]");
  if (!button) return;
  const dialog = document.getElementById(button.dataset.openDialog);
  if (dialog.id === "item-dialog") {
    const form = dialog.querySelector("form");
    form.reset();
    form.elements.item_id.value = "";
    $("#item-dialog-title").textContent = "加入行程項目";
    $("#item-submit-button").textContent = "加入行程";
  }
  formError(dialog.querySelector("form"));
  dialog.showModal();
});

$("#order-board").addEventListener("click", async (event) => {
  const paymentButton = event.target.closest("[data-create-payment]");
  const simulationButton = event.target.closest("[data-simulate-payment]");
  if (!paymentButton && !simulationButton) return;
  const button = paymentButton || simulationButton;
  button.disabled = true;
  try {
    if (paymentButton) {
      await api(`/api/orders/${paymentButton.dataset.createPayment}/payments`, {
        method: "POST",
        headers: { "Idempotency-Key": `payment-order-${paymentButton.dataset.createPayment}-attempt-${paymentButton.dataset.attempt}` },
        body: JSON.stringify({ provider: "mockpay" }),
      });
      showToast("付款請求已建立，等待 provider 回傳結果");
    } else {
      const succeeded = simulationButton.dataset.result === "succeeded";
      await api(`/api/payments/${simulationButton.dataset.simulatePayment}/simulate`, {
        method: "POST",
        body: JSON.stringify({
          status: simulationButton.dataset.result,
          failure_code: succeeded ? null : "MOCK_DECLINED",
          failure_message: succeeded ? null : "本機模擬付款失敗",
        }),
      });
      showToast(succeeded ? "付款已確認，訂單更新為已付款" : "付款失敗，可安全重試");
    }
    await loadData(); showSection("orders");
  } catch (error) { button.disabled = false; showToast(error.message, true); }
});

$("#trip-detail").addEventListener("change", async (event) => {
  const tripSelect = event.target.closest("[data-trip-status]");
  const quoteSelect = event.target.closest("[data-quote-status]");
  try {
    if (tripSelect) {
      await api(`/api/trips/${tripSelect.dataset.tripStatus}`, {
        method: "PATCH", body: JSON.stringify({ status: tripSelect.value }),
      });
      await loadData(); showToast("行程狀態已更新");
    }
    if (quoteSelect) {
      await api(`/api/quotes/${quoteSelect.dataset.quoteStatus}`, {
        method: "PATCH", body: JSON.stringify({ status: quoteSelect.value }),
      });
      await loadData(); showToast("報價狀態已更新");
    }
  } catch (error) {
    await loadData(); showToast(error.message, true);
  }
});

$$('[data-task-filter]').forEach((button) => button.addEventListener("click", () => {
  state.taskFilter = button.dataset.taskFilter;
  $$('[data-task-filter]').forEach((item) => item.classList.toggle("active", item === button));
  renderTasks();
}));

$("#today-label").textContent = new Intl.DateTimeFormat("zh-TW", { weekday: "long", month: "long", day: "numeric" }).format(new Date());

if (state.token) bootApp();
