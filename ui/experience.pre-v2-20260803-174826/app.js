
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function relativeTime(iso) {
  const d = new Date(iso);
  const sec = Math.round((Date.now() - d.getTime()) / 1000);
  if (Math.abs(sec) < 60) return "moments ago";
  if (Math.abs(sec) < 3600) return `${Math.round(Math.abs(sec)/60)} minutes ago`;
  if (Math.abs(sec) < 86400) return `${Math.round(Math.abs(sec)/3600)} hours ago`;
  return `${Math.round(Math.abs(sec)/86400)} days ago`;
}

function buildHistoryOrbit(history) {
  const orbit = $(".history-orbit");
  orbit.innerHTML = "";
  history.slice(-7).forEach((item, index) => {
    const dot = document.createElement("span");
    const angle = -112 + (index * 16);
    const radius = 46;
    dot.style.left = `${50 + Math.cos(angle * Math.PI / 180) * radius}%`;
    dot.style.top = `${50 + Math.sin(angle * Math.PI / 180) * radius}%`;
    dot.style.background = item.level === "high" ? "var(--accent)" : item.level === "moderate" ? "var(--amber)" : "var(--danger)";
    orbit.appendChild(dot);
  });
}

function renderStory(items) {
  const list = $("#story-list");
  list.innerHTML = items.map(item => `
    <li>
      <strong>${item.label}</strong>
      <time>${item.time}</time>
    </li>`).join("");
}

function renderCoverage(items) {
  $("#coverage-list").innerHTML = items.map(item => {
    const pct = Math.min(100, (item.current / item.target) * 100);
    return `<div class="coverage-row">
      <div><strong>${item.label}</strong><small>${item.detail}</small></div>
      <div class="coverage-track" aria-label="${item.current} of ${item.target}">
        <div class="coverage-fill" style="width:${pct}%"></div>
      </div>
      <div class="coverage-value">${item.current} / ${item.target}</div>
    </div>`;
  }).join("");
}

function drawLineChart(svg, data, key, suffix) {
  const W = 900, H = 220, p = {l:28,r:16,t:18,b:34};
  const vals = data.map(d => d[key]);
  const min = Math.min(...vals), max = Math.max(...vals);
  const spread = Math.max(1, max - min);
  const x = i => p.l + (i * (W-p.l-p.r)/(data.length-1));
  const y = v => p.t + ((max-v)/spread)*(H-p.t-p.b);
  const pts = data.map((d,i) => [x(i),y(d[key])]);
  const path = pts.map((pt,i) => `${i?"L":"M"}${pt[0].toFixed(1)},${pt[1].toFixed(1)}`).join(" ");
  const area = `${path} L${pts.at(-1)[0]},${H-p.b} L${pts[0][0]},${H-p.b} Z`;
  svg.innerHTML = `
    <line class="grid" x1="${p.l}" y1="${H-p.b}" x2="${W-p.r}" y2="${H-p.b}"/>
    <line class="grid" x1="${p.l}" y1="${p.t + (H-p.t-p.b)/2}" x2="${W-p.r}" y2="${p.t + (H-p.t-p.b)/2}"/>
    <path class="area" d="${area}"/>
    <path class="line" d="${path}"/>
    ${pts.map((pt,i)=>`<circle class="point" cx="${pt[0]}" cy="${pt[1]}" r="${i===pts.length-1?6:4}">
      <title>${data[i].date}: ${data[i][key]}${suffix}</title></circle>`).join("")}
    ${data.map((d,i)=>`<text x="${x(i)}" y="${H-8}" text-anchor="middle">${d.date}</text>`).join("")}
  `;
}

function filterReference(value) {
  const q = value.trim().toLowerCase();
  $$("#reference-results article").forEach(article => {
    article.hidden = q && !article.textContent.toLowerCase().includes(q);
  });
}

async function start() {
  const data = await fetch("/data/experience.json", {cache:"no-store"}).then(r => r.json());
  document.documentElement.dataset.season = data.site.season;
  $("#confidence-message").textContent = data.confidence.message;
  $("#confidence-label").textContent = data.confidence.label;
  $("#last-verified").textContent = relativeTime(data.confidence.last_verified_at);
  buildHistoryOrbit(data.confidence.history);
  renderStory(data.story);
  renderCoverage(data.coverage);
  $("#latest-size").textContent = `${data.history.at(-1).size} MB`;
  $("#latest-duration").textContent = `${data.history.at(-1).duration} seconds`;
  drawLineChart($("#size-chart"), data.history, "size", " MB");
  drawLineChart($("#duration-chart"), data.history, "duration", " seconds");

  setTimeout(() => $("#startup").classList.add("complete"), 1280);
}

$("#site-button").addEventListener("click", () => {
  const expanded = $("#site-button").getAttribute("aria-expanded") === "true";
  $("#site-button").setAttribute("aria-expanded", String(!expanded));
  $("#site-sheet").hidden = expanded;
});
document.addEventListener("click", event => {
  if (!event.target.closest("#site-button") && !event.target.closest("#site-sheet")) {
    $("#site-button").setAttribute("aria-expanded","false");
    $("#site-sheet").hidden = true;
  }
});
$("#confidence-details-button").addEventListener("click", () => {
  const panel = $("#confidence-details");
  panel.hidden = !panel.hidden;
  $("#confidence-details-button").textContent = panel.hidden ? "View verification chain" : "Hide verification chain";
});
$("#reference-search").addEventListener("input", e => filterReference(e.target.value));

start().catch(error => {
  console.error(error);
  $("#startup").classList.add("complete");
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/service-worker.js").catch(()=>{}));
}
