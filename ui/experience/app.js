const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];

const defaultResources = {
  site: '/api/v1/site.json',
  confidence: '/api/v1/confidence.json',
  story: '/api/v1/story.json',
  history: '/api/v1/history.json',
  coverage: '/api/v1/coverage.json',
  system: '/api/v1/system.json'
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function requestJson(url) {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

function titleCase(value = '') {
  return value
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, letter => letter.toUpperCase())
    .replace('Onedrive', 'OneDrive');
}

function formatDate(value, options = {}) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unavailable';
  return new Intl.DateTimeFormat(undefined, options).format(date);
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) return 'Unavailable';
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

function confidenceStatus(level) {
  return {
    high: 'All Systems Normal',
    moderate: 'Attention Recommended',
    low: 'Recovery At Risk',
    unknown: 'Status Unavailable'
  }[level] || 'Status Unavailable';
}

function renderProduct(index, system) {
  const tagline = index?.product?.tagline || system?.tagline;
  if (!tagline) return;
  $('#startup-tagline').textContent = tagline;
  $('#product-tagline').textContent = tagline;
}

function renderSite(site) {
  $('#site-id').textContent = site?.site_id || '—';
  document.body.dataset.season = site?.season || 'summer';
}

function renderConfidence(confidence) {
  const level = confidence?.level || 'unknown';
  const status = confidenceStatus(level);
  document.body.dataset.confidence = level;
  $('#confidence-label').textContent = titleCase(level);
  $('#confidence-message').textContent = confidence?.message || 'Confidence data unavailable.';
  $('#system-health').textContent = status;
  $('#offsite-status').textContent = !confidence
    ? 'Synchronization data unavailable'
    : confidence.checks?.onedrive_synchronized
      ? 'OneDrive synchronized'
      : 'Synchronization not verified';
  $('#restore-status').textContent = confidence?.last_verified_at
    ? `${titleCase(level)} · verified ${formatDate(confidence.last_verified_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}`
    : 'Verification unavailable';
  $$('[data-system-status]').forEach(node => { node.textContent = status; });

  const checks = $('#checks');
  checks.replaceChildren();
  if (!confidence) {
    checks.append(element('div', 'check', 'Confidence checks unavailable'));
    return;
  }

  if (confidence.last_verified_at) {
    const row = element('div', 'check');
    row.append(
      element('span', '', 'Last verified'),
      element('strong', '', formatDate(confidence.last_verified_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }))
    );
    checks.append(row);
  }

  Object.entries(confidence.checks || {}).forEach(([name, passed]) => {
    const row = element('div', 'check');
    row.append(element('span', '', titleCase(name)), element('strong', '', passed ? 'Verified' : 'Not verified'));
    checks.append(row);
  });
}

function renderStory(story, history) {
  if (!story) {
    $('#story-text').textContent = 'Backup story unavailable.';
    return;
  }

  const completed = (story.steps || []).filter(step => step.status === 'complete').length;
  const total = story.steps?.length || 0;
  const run = history?.runs?.find(item => item.backup_id === story.backup_id);
  const completedAt = formatDate(story.completed_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  const details = [`Backup completed ${completedAt}.`, `${completed} of ${total} steps completed.`];
  if (run) details.push(`Archive ${formatBytes(run.archive_size_bytes)} in ${formatDuration(run.duration_seconds)}; container downtime ${formatDuration(run.container_downtime_seconds)}.`);
  $('#story-text').textContent = details.join(' ');
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return 'size unavailable';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit > 1 ? 1 : 0)} ${units[unit]}`;
}

function renderHistory(history) {
  const runs = history?.runs || [];
  const archives = $('#archive-list');
  archives.replaceChildren();

  if (!runs.length) {
    archives.append(element('div', 'archive unavailable', 'History unavailable'));
    $('#archive-summary').textContent = 'Archive history unavailable.';
    $('#backup-status').textContent = 'Backup history unavailable';
    return;
  }

  runs.slice(0, 7).forEach(run => {
    const date = new Date(run.completed_at);
    const card = element('div', `archive level-${run.level || 'unknown'}`);
    card.title = `${titleCase(run.level || 'unknown')} confidence · ${formatBytes(run.archive_size_bytes)}`;
    card.append(
      element('strong', '', Number.isNaN(date.getTime()) ? '—' : String(date.getDate())),
      element('span', '', Number.isNaN(date.getTime()) ? 'Unknown' : formatDate(date, { month: 'short' }))
    );
    archives.append(card);
  });

  const latest = runs[0];
  $('#archive-summary').textContent = `${runs.length} ${runs.length === 1 ? 'archive' : 'archives'} in history · latest ${formatDate(latest.completed_at, { month: 'short', day: 'numeric' })}`;
  $('#backup-status').textContent = `${titleCase(latest.level)} · ${formatDuration(latest.duration_seconds)} · ${formatBytes(latest.archive_size_bytes)}`;
}

function renderCoverage(coverage) {
  const tiers = coverage?.tiers || [];
  if (!tiers.length) {
    $('#coverage-status').textContent = 'Coverage unavailable';
    return;
  }
  const current = tiers.reduce((sum, tier) => sum + tier.current, 0);
  const target = tiers.reduce((sum, tier) => sum + tier.target, 0);
  const complete = tiers.filter(tier => tier.state === 'complete').length;
  $('#coverage-status').textContent = `${current} of ${target} restore points · ${complete} of ${tiers.length} tiers complete`;
}

function addSystemCheck(system) {
  if (!system) return;
  const checks = $('#checks');
  const row = element('div', 'check');
  row.append(
    element('span', '', 'Data generated'),
    element('strong', '', formatDate(system.generated_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }))
  );
  checks.append(row);
}

function renderReferences(resources, data) {
  const results = $('#results');
  results.replaceChildren();
  Object.entries(resources).forEach(([name, url]) => {
    const article = element('article');
    article.append(
      element('strong', '', titleCase(name)),
      element('span', '', `${data[name] ? 'Available' : 'Unavailable'} · ${url}`)
    );
    results.append(article);
  });
}

async function loadExperience() {
  let index;
  try {
    index = await requestJson('/api/v1/index.json');
  } catch (error) {
    console.warn(error);
  }

  const resources = { ...defaultResources, ...(index?.resources || {}) };
  const entries = Object.entries(resources);
  const results = await Promise.allSettled(entries.map(([, url]) => requestJson(url)));
  const data = {};
  results.forEach((result, position) => {
    const name = entries[position][0];
    if (result.status === 'fulfilled') data[name] = result.value;
    else console.warn(result.reason);
  });

  renderProduct(index, data.system);
  renderSite(data.site);
  renderConfidence(data.confidence);
  renderHistory(data.history);
  renderStory(data.story, data.history);
  renderCoverage(data.coverage);
  addSystemCheck(data.system);
  renderReferences(resources, data);
}

loadExperience();

$('#search').addEventListener('input', event => {
  const query = event.target.value.trim().toLowerCase();
  $$('#results article').forEach(article => {
    article.hidden = Boolean(query) && !article.textContent.toLowerCase().includes(query);
  });
});

const navLinks = $$('nav a[href^="#"]');
const sections = $$('main section[id], #archives');
const sectionObserver = new IntersectionObserver(entries => {
  const visible = entries
    .filter(entry => entry.isIntersecting)
    .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
  if (!visible) return;

  navLinks.forEach(link => {
    const active = link.hash === `#${visible.target.id}`;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
}, { rootMargin: '-20% 0px -60%', threshold: [0, .25, .5] });
sections.forEach(section => sectionObserver.observe(section));

const startupBegan = performance.now();
window.addEventListener('load', () => {
  const minimumDisplay = 1900;
  const remaining = Math.max(0, minimumDisplay - (performance.now() - startupBegan));
  setTimeout(() => $('#startup').classList.add('done'), remaining);
}, { once: true });
