const $ = (selector) => document.querySelector(selector);
const money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });
const num = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
let dashboardData = null;

function escapeHtml(value) {
  return String(value ?? "—").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
}
function formatMoney(value) { return value === null || value === undefined ? "—" : money.format(value); }
function formatPct(value) { return value === null || value === undefined ? "—" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`; }
function titleCase(value) { return String(value || "—").replaceAll("_", " ").replace(/\b\w/g, (m) => m.toUpperCase()); }
function formatDate(value, options = { day: "2-digit", month: "short", year: "numeric" }) { if (!value) return "—"; return new Intl.DateTimeFormat("en-IN", options).format(new Date(value)); }
function conditionLabel(condition) { return `${formatDate(condition.check_in, { day: "2-digit", month: "short" })} → ${formatDate(condition.check_out, { day: "2-digit", month: "short" })} · ${condition.guests} guest${condition.guests > 1 ? "s" : ""} · ${condition.rooms} room${condition.rooms > 1 ? "s" : ""}`; }

async function request(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

function setStatus(element, status) {
  element.textContent = titleCase(status);
  element.className = `status ${status === "sold_out" ? "sold_out" : status === "limited" ? "limited" : ""}`;
}
function renderMetrics(data) {
  const metrics = data.metrics;
  $("#primaryRate").textContent = formatMoney(metrics.primary_rate);
  $("#marketAverage").textContent = formatMoney(metrics.competitor_average_rate);
  const position = metrics.primary_rate_position_pct;
  $("#ratePosition").textContent = position === null ? "No rate position yet" : `${formatPct(position)} to market average`;
  $("#availableCount").textContent = `${metrics.available_competitors} / ${metrics.competitors_covered}`;
  $("#soldOutCount").textContent = metrics.sold_out_competitors;
  $("#estimatedNights").textContent = metrics.estimated_room_nights;
  $("#estimatedRevenue").textContent = formatMoney(metrics.estimated_gross_booking_value);
  $("#competitorCoverage").textContent = metrics.competitors_covered;
  $("#pressureMetric").textContent = metrics.visible_inventory_pressure_pct === null ? "—" : `${(metrics.visible_inventory_pressure_pct * 100).toFixed(0)}%`;
  $("#pressureNote").textContent = metrics.occupancy_note;
}
function renderPrimary(primary) {
  if (!primary) return;
  $("#primary-title").textContent = primary.name;
  setStatus($("#primaryStatus"), primary.availability_status);
  $("#primaryObservation").textContent = formatDate(primary.observed_at, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  $("#primaryUnits").textContent = primary.available_units ?? "Not observed";
  $("#primaryEstimatedUnits").textContent = primary.estimated_units_sold || "No reduction recorded";
  $("#primaryAction").textContent = primary.action;
}
function renderRateChart(data) {
  const values = [data.primary, ...data.competitors].filter((item) => item && item.current_rate !== null);
  const focus = values.slice(0, 11);
  const max = Math.max(...focus.map((item) => item.current_rate), 1);
  $("#rateChart").innerHTML = focus.map((item) => `
    <div class="rate-row">
      <span class="rate-label" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</span>
      <div class="rate-track"><div class="rate-fill ${item.role === "primary" ? "primary" : ""}" style="width:${Math.max(3, (item.current_rate / max) * 100)}%"></div></div>
      <span class="rate-value">${formatMoney(item.current_rate)}</span>
    </div>`).join("") || `<p class="empty">No comparable rates are available for this condition.</p>`;
}
function renderTrend(trend) {
  const target = $("#trendChart");
  if (!trend?.length) { target.innerHTML = `<p class="empty">Add repeated snapshots to see the trend.</p>`; return; }
  const width = 570, height = 230, pad = { left: 52, right: 16, top: 20, bottom: 36 };
  const values = trend.flatMap((item) => [item.primary_rate, item.competitor_average]).filter((x) => x !== null && x !== undefined);
  if (!values.length) { target.innerHTML = `<p class="empty">No rate data to plot.</p>`; return; }
  const minimum = Math.min(...values) * .93, maximum = Math.max(...values) * 1.06, span = Math.max(1, maximum - minimum);
  const x = (index) => pad.left + index * ((width - pad.left - pad.right) / Math.max(1, trend.length - 1));
  const y = (value) => pad.top + (maximum - value) * ((height - pad.top - pad.bottom) / span);
  const path = (key) => trend.filter((point) => point[key] !== null).map((point, index) => `${index ? "L" : "M"}${x(index)},${y(point[key])}`).join(" ");
  const grid = [0, .5, 1].map((part) => { const yy = pad.top + part * (height - pad.top - pad.bottom); const val = maximum - part * span; return `<line class="chart-gridline" x1="${pad.left}" x2="${width - pad.right}" y1="${yy}" y2="${yy}"/><text class="chart-label" x="0" y="${yy + 4}">${compact.format(val)}</text>`; }).join("");
  const labels = trend.map((point, index) => `<text class="chart-label" text-anchor="middle" x="${x(index)}" y="${height - 10}">${formatDate(point.observed_at, { day: "2-digit", month: "short" })}</text>`).join("");
  const dots = (key, className) => trend.map((point, index) => point[key] === null ? "" : `<circle class="${className}" cx="${x(index)}" cy="${y(point[key])}" r="3.5"/>`).join("");
  target.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Price trend"><g>${grid}</g><path class="line-primary" d="${path("primary_rate")}"/><path class="line-market" d="${path("competitor_average")}"/>${dots("primary_rate", "point-primary")}${dots("competitor_average", "point-market")}${labels}</svg>`;
}
function renderMiniBars(targetId, rows, labeler) {
  const target = $(targetId);
  const max = Math.max(...rows.map((item) => item.average_rate || 0), 1);
  target.innerHTML = rows.map((item) => `<div class="mini-row"><span>${escapeHtml(labeler(item))}</span><div class="mini-track"><div class="mini-fill" style="width:${(item.average_rate / max) * 100}%"></div></div><span class="mini-value">${formatMoney(item.average_rate)}</span></div>`).join("") || `<p class="empty">No observations yet.</p>`;
}
function renderCompetitorTable(competitors) {
  $("#competitorTable").innerHTML = competitors.map((item) => {
    const moveClass = item.rate_change > 0 ? "rate-up" : item.rate_change < 0 ? "rate-down" : "";
    const move = item.rate_change === null ? "—" : `${formatPct(item.rate_change_pct)} <small>(${formatMoney(item.rate_change)})</small>`;
    const flagClass = item.priority === 3 ? "p1" : item.priority === 2 ? "p2" : "p3";
    return `<tr>
      <td><span class="property-name">${escapeHtml(item.name)}</span><span class="property-segment">${escapeHtml(item.segment || "Comparable")}</span></td>
      <td>${escapeHtml(item.market)}</td><td>${formatMoney(item.current_rate)}</td>
      <td class="${moveClass}">${move}</td><td><span class="availability ${item.availability_status}">${escapeHtml(titleCase(item.availability_status))}</span></td>
      <td>${item.available_units ?? "—"}</td><td>${item.estimated_units_sold || "—"}</td>
      <td><span class="flag ${flagClass}">${escapeHtml(item.action)}</span></td>
    </tr>`;
  }).join("") || `<tr><td colspan="8" class="empty">No competitors match this condition.</td></tr>`;
}
function renderChanges(changes) {
  $("#changesList").innerHTML = changes.map((change) => {
    const critical = ["became_sold_out", "availability_decreased", "price_decreased"].includes(change.event_type);
    const values = change.old_value === null && change.new_value === null ? "" : ` · ${escapeHtml(change.old_value ?? "—")} → ${escapeHtml(change.new_value ?? "—")}`;
    return `<div class="change-item ${critical ? "critical" : ""}"><i class="event-dot"></i><div><strong>${escapeHtml(change.property_name)} — ${escapeHtml(titleCase(change.event_type))}</strong><p>${escapeHtml(titleCase(change.field_name))}${values}${change.estimated_units_sold ? ` · ${change.estimated_units_sold} estimated unit signal` : ""}</p></div><time>${formatDate(change.observed_at, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</time></div>`;
  }).join("") || `<p class="empty">A prior comparison is required before the ledger populates.</p>`;
}
function renderDashboard(data) {
  dashboardData = data;
  const condition = data.condition;
  $("#conditionMeta").textContent = `${condition.stay_nights ?? ""} night${condition.stay_nights === 1 ? "" : "s"} · ${condition.meal_preference} · ${condition.cancellation_preference}`;
  $("#demoNotice").classList.toggle("hidden", !data.metrics.is_demo_dataset);
  renderMetrics(data); renderPrimary(data.primary); renderRateChart(data); renderTrend(data.trend);
  renderMiniBars("#guestMix", data.guest_mix, (item) => `${item.guests} guest${item.guests > 1 ? "s" : ""}`);
  renderMiniBars("#weekendMix", data.weekday_vs_weekend, (item) => item.period);
  renderCompetitorTable(data.competitors); renderChanges(data.top_changes);
  $("#methodologySales").textContent = data.methodology.estimated_sales;
  $("#methodologyRevenue").textContent = data.methodology.estimated_revenue;
  $("#systemProperties").textContent = data.metrics.properties_covered ?? "—";
  $("#systemObservations").textContent = num.format(data.metrics.total_observations ?? 0);
  $("#systemCheckpoints").textContent = data.metrics.observation_checkpoints ?? "—";
  $("#systemRuns").textContent = data.metrics.collection_runs ?? "—";
  const latestRun = data.metrics.latest_run;
  $("#systemSource").textContent = latestRun
    ? `Source: ${titleCase(latestRun.source_type)} · ${titleCase(latestRun.status)}`
    : "Source: No collection run";
  const exportLink = $("#exportObservations");
  if (exportLink) exportLink.href = `/api/export/observations.csv?condition_id=${encodeURIComponent(condition.condition_id)}`;
  renderRoomTypes(data.room_types || []);
} 
function renderRoomTypes(items) {
  const target = $("#roomTypes");
  if (!target) return;
  target.innerHTML = items.length ? items.slice(0, 8).map(item => `
    <div class="room-type">
      <div><strong>${escapeHtml(item.room_type)}</strong><span>${num.format(item.observations)} observations</span></div>
      <b>${formatMoney(item.average_rate)}</b>
    </div>`).join("") : `<p class="empty">No room-type observations for this condition.</p>`;
}
async function loadDashboard(conditionId) { const data = await request(`/api/dashboard${conditionId ? `?condition_id=${encodeURIComponent(conditionId)}` : ""}`); renderDashboard(data); }
async function boot() {
  try {
    const health = await request("/api/health"); $("#dbHealth").textContent = `Database online · ${health.database}`;
    const { conditions } = await request("/api/conditions");
    const select = $("#conditionSelect");
    select.innerHTML = conditions.map((condition) => `<option value="${condition.condition_id}">${escapeHtml(conditionLabel(condition))}</option>`).join("");
    if (!conditions.length) return;
    select.addEventListener("change", () => loadDashboard(select.value).catch(showError));
    await loadDashboard(conditions[0].condition_id);
  } catch (error) { showError(error); }
}
function showError(error) { console.error(error); document.querySelector("main").insertAdjacentHTML("afterbegin", `<section class="notice"><strong>Dashboard unavailable</strong><span>Start the application with <code>python app.py --seed-demo</code> and refresh this page.</span></section>`); }
boot();
