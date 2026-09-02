const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];

const defaultResources = {
  site: '/api/v1/site.json',
  confidence: '/api/v1/confidence.json',
  story: '/api/v1/story.json',
  history: '/api/v1/history.json',
  coverage: '/api/v1/coverage.json',
  system: '/api/v1/system.json',
  inventory: '/api/v1/inventory.json',
  infrastructure: '/api/v1/infrastructure.json'
};

const resourceDescriptions = {
  site: 'Identity, edition, protection start, and active visual season for this Harbr site.',
  confidence: 'Current Restore Confidence, verification time, evidence checks, and recent confidence history.',
  story: 'The ordered events recorded for the newest backup and verification run.',
  history: 'Recent archive metrics and the point-in-time evidence captured for each run.',
  coverage: 'Current local, daily, weekly, and monthly protection against configured retention targets.',
  system: 'Read-only product version, generation time, and next scheduled protection run.',
  inventory: 'Curated host recovery prerequisites merged with safe detected versions, service states, and Harbr-scoped identities.',
  infrastructure: 'Current sanitized operational health, maintenance, hosts, workloads, and freshness across Harbr sites.'
};

const appState = {
  data: {},
  index: null,
  resources: defaultResources,
  documentation: [],
  documentationUpdatedAt: null,
  selectedBackupId: null,
  referenceItems: new Map()
};

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
let archiveTransitionTimer;
let archiveTransitionFinishTimer;
let infrastructurePollTimer;

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

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return 'Unavailable';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit > 1 ? 1 : 0)} ${units[unit]}`;
}

function infrastructureFreshness(data, pollFailed = false) {
  const generated = new Date(data?.generated_at).getTime();
  const maxAge = Number(data?.stale_after_seconds) * 1000;
  const stale = pollFailed || !Number.isFinite(generated) || !Number.isFinite(maxAge) || Date.now() - generated > maxAge;
  return { stale, status: stale ? 'unknown' : (data?.status || 'unknown') };
}

function infrastructureStatusLabel(status) {
  return { healthy: 'Healthy', warning: 'Attention recommended', failure: 'Failure', unknown: 'Cannot verify' }[status] || 'Cannot verify';
}

function formatUptime(seconds) {
  if (!Number.isFinite(seconds)) return 'Unavailable';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return days ? `${days}d ${hours}h` : `${hours}h`;
}

function statusLine(label, value, status = 'unknown') {
  const row = element('div', 'infrastructure-fact');
  row.dataset.status = status;
  row.append(element('span', '', label), element('strong', '', value));
  return row;
}

function renderService(service) {
  const row = element('div', 'service-row');
  row.dataset.status = service.runtime_status || 'unknown';
  const identity = element('div');
  identity.append(element('strong', '', service.name || service.service_id), element('small', '', [service.container_name, service.image].filter(Boolean).join(' · ')));
  const states = element('div', 'service-states');
  states.append(element('span', 'status-chip', `Runtime ${infrastructureStatusLabel(service.runtime_status)}`));
  const update = element('span', 'update-chip', service.update_status === 'update_available' ? 'Update available' : service.update_status === 'current' ? 'Image current' : 'Update unknown');
  update.dataset.status = service.update_status === 'update_available' ? 'warning' : service.update_status === 'current' ? 'healthy' : 'unknown';
  states.append(update);
  row.append(identity, states);
  return row;
}

function renderProject(project) {
  const card = element('article', 'project-card');
  card.dataset.status = project.status || 'unknown';
  const heading = element('header');
  heading.append(element('h5', '', project.name || project.project_id), element('span', 'status-chip', infrastructureStatusLabel(project.status)));
  card.append(heading);
  (project.services || []).forEach(service => card.append(renderService(service)));
  if (!(project.services || []).length) card.append(element('p', 'data-unavailable', 'No services reported.'));
  return card;
}

function renderHost(host, stale = false) {
  const card = element('article', 'host-card');
  card.dataset.status = stale ? 'unknown' : (host.status || 'unknown');
  const heading = element('header', 'host-heading');
  const title = element('div');
  title.append(element('p', 'eyebrow', titleCase(host.role || 'host')), element('h4', '', host.name || host.host_id));
  heading.append(title, element('span', 'status-chip', stale ? 'Last known · current state unverified' : infrastructureStatusLabel(host.status)));
  card.append(heading);
  const facts = element('div', 'host-facts');
  facts.append(
    statusLine('Operating system', host.os?.pretty_name || [host.os?.name, host.os?.version].filter(Boolean).join(' ') || host.platform || 'Unavailable', host.os ? 'healthy' : 'unknown'),
    statusLine('Uptime', formatUptime(host.uptime_seconds), Number.isFinite(host.uptime_seconds) ? 'healthy' : 'unknown'),
    statusLine('Reboot', host.reboot_required === true ? 'Required' : host.reboot_required === false ? 'Not required' : 'Unknown', host.reboot_required === true ? 'warning' : host.reboot_required === false ? 'healthy' : 'unknown'),
    statusLine('Package updates', host.package_updates ? `${host.package_updates.available} available · ${host.package_updates.security} security` : 'Unavailable', host.package_updates?.status || 'unknown'),
    statusLine('System services', host.systemd ? `${host.systemd.failed_units} failed` : 'Unavailable', host.systemd?.status || 'unknown')
  );
  if (host.docker) facts.append(statusLine('Docker', `${infrastructureStatusLabel(host.docker.daemon_status)}${host.docker.server_version ? ` · ${host.docker.server_version}` : ''}${host.docker.compose_version ? ` · Compose ${host.docker.compose_version}` : ''}`, host.docker.daemon_status));
  card.append(facts);
  if ((host.filesystems || []).length) {
    const filesystems = element('div', 'filesystem-grid');
    host.filesystems.forEach(fs => filesystems.append(statusLine(fs.label, Number.isFinite(fs.used_percent) ? `${fs.used_percent}% used` : 'Usage unavailable', fs.status)));
    card.append(element('h5', 'workload-heading', 'Storage'), filesystems);
  }
  const projects = host.docker?.projects || [];
  if (projects.length) {
    const grid = element('div', 'project-grid');
    projects.forEach(project => grid.append(renderProject(project)));
    card.append(element('h5', 'workload-heading', 'Applications & containers'), grid);
  }
  const vms = host.virtualization?.virtual_machines || [];
  if (vms.length) {
    const grid = element('div', 'vm-grid');
    vms.forEach(vm => { const vmCard = element('article', 'vm-card'); vmCard.dataset.status = vm.status || 'unknown'; vmCard.append(element('strong', '', vm.name || vm.vm_id), element('span', 'status-chip', infrastructureStatusLabel(vm.status))); (vm.services || []).forEach(service => vmCard.append(renderService(service))); (vm.docker?.projects || []).forEach(project => vmCard.append(renderProject(project))); grid.append(vmCard); });
    card.append(element('h5', 'workload-heading', 'Virtual machines'), grid);
  }
  return card;
}

function renderInfrastructure(data, pollFailed = false) {
  const summaryRoot = $('#infrastructure-summary');
  const sitesRoot = $('#infrastructure-sites');
  summaryRoot.replaceChildren(); sitesRoot.replaceChildren();
  const freshness = infrastructureFreshness(data, pollFailed);
  const freshnessNode = $('#infrastructure-freshness');
  freshnessNode.dataset.status = freshness.status;
  freshnessNode.textContent = freshness.stale ? 'Status cannot be verified · data is stale or unavailable' : `Current · checked ${formatDate(data.generated_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}`;
  const summary = data?.summary || {};
  [
    ['Host Health', summary.hosts ? infrastructureStatusLabel(freshness.status) : 'No hosts reported', freshness.status],
    ['Service Health', `${summary.healthy_services || 0} of ${summary.services || 0} operational`, freshness.stale ? 'unknown' : summary.failed_services ? 'failure' : summary.warning_services ? 'warning' : summary.services ? 'healthy' : 'unknown'],
    ['Updates', `${(summary.image_updates || 0) + (summary.package_updates || 0)} waiting`, freshness.stale ? 'unknown' : (summary.image_updates || summary.package_updates) ? 'warning' : 'healthy'],
    ['Reboot', summary.reboots_required ? `${summary.reboots_required} required` : 'Not required', freshness.stale ? 'unknown' : summary.reboots_required ? 'warning' : 'healthy']
  ].forEach(([label, value, status]) => summaryRoot.append(statusLine(label, value, status)));
  (data?.sites || []).forEach(site => {
    const section = element('section', 'site-card'); section.dataset.status = freshness.stale ? 'unknown' : (site.status || 'unknown');
    const heading = element('header', 'site-heading'); const title = element('div'); title.append(element('p', 'eyebrow', site.site_id), element('h3', '', site.name));
    heading.append(title, element('span', 'status-chip', freshness.stale ? 'Cannot verify current state' : infrastructureStatusLabel(site.status))); section.append(heading);
    const hosts = element('div', 'host-list'); (site.hosts || []).forEach(host => hosts.append(renderHost(host, freshness.stale))); section.append(hosts); sitesRoot.append(section);
  });
  if (!(data?.sites || []).length) sitesRoot.append(element('p', 'infrastructure-empty', 'Infrastructure has not been published yet. Existing Harbr recovery data remains available.'));
}

async function pollInfrastructure() {
  try {
    const data = await requestJson(appState.resources.infrastructure || defaultResources.infrastructure);
    appState.data.infrastructure = data;
    renderInfrastructure(data);
    renderReferences();
  } catch (error) {
    console.warn(error);
    renderInfrastructure(appState.data.infrastructure, true);
  }
}

function startInfrastructurePolling() {
  if (infrastructurePollTimer) return;
  infrastructurePollTimer = window.setInterval(() => { if (!document.hidden) pollInfrastructure(); }, 60000);
}

function confidenceStatus(level) {
  return {
    high: 'All Systems Normal',
    moderate: 'Attention Recommended',
    low: 'Recovery At Risk',
    unknown: 'Status Unavailable'
  }[level] || 'Status Unavailable';
}

function semanticConfidenceStatus(level) {
  return {
    high: 'healthy',
    moderate: 'warning',
    low: 'failure',
    unknown: 'unknown'
  }[level] || 'unknown';
}

function setGlanceStatus(iconId, status) {
  const icon = $(`#${iconId}`);
  const card = icon?.closest('article');
  if (card) card.dataset.status = status;
}

function appendCheck(label, value) {
  const row = element('div', 'check');
  row.append(element('span', '', label), element('strong', '', value));
  $('#checks').append(row);
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
  $('#confidence-label').textContent = confidence ? titleCase(level) : 'Unknown';
  $('#confidence-message').textContent = confidence?.message || 'Confidence data unavailable for this archive.';
  $('#system-health').textContent = status;
  setGlanceStatus('system-health-icon', semanticConfidenceStatus(level));
  $('#offsite-status').textContent = !confidence?.checks
    ? 'Synchronization data unavailable'
    : confidence.checks.onedrive_synchronized
      ? 'OneDrive synchronized'
      : 'Synchronization not verified';
  setGlanceStatus(
    'offsite-status-icon',
    !confidence?.checks ? 'unknown' : confidence.checks.onedrive_synchronized ? 'healthy' : 'failure'
  );
  $('#restore-status').textContent = confidence?.last_verified_at
    ? `${titleCase(level)} · verified ${formatDate(confidence.last_verified_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}`
    : 'Verification unavailable';
  setGlanceStatus(
    'restore-status-icon',
    confidence?.last_verified_at ? semanticConfidenceStatus(level) : 'unknown'
  );
  $$('[data-system-status]').forEach(node => { node.textContent = status; });

  const checks = $('#checks');
  checks.replaceChildren();
  if (!confidence) {
    appendCheck('Verification checks', 'Unavailable');
    return;
  }

  appendCheck(
    'Last verified',
    confidence.last_verified_at
      ? formatDate(confidence.last_verified_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
      : 'Unavailable'
  );

  if (!confidence.checks) {
    appendCheck('Historical checks', 'Unavailable');
    return;
  }

  Object.entries(confidence.checks).forEach(([name, passed]) => {
    appendCheck(titleCase(name), passed ? 'Verified' : 'Not verified');
  });
}

function renderRunMetrics(run) {
  if (!run) {
    $('#backup-status').textContent = 'Backup history unavailable';
    setGlanceStatus('backup-status-icon', 'unknown');
    appendCheck('Archive metrics', 'Unavailable');
    return;
  }
  $('#backup-status').textContent = `${titleCase(run.level || 'unknown')} · ${formatDuration(run.duration_seconds)} · ${formatBytes(run.archive_size_bytes)}`;
  setGlanceStatus('backup-status-icon', semanticConfidenceStatus(run.level || 'unknown'));
  appendCheck('Archive size', formatBytes(run.archive_size_bytes));
  appendCheck('Backup duration', formatDuration(run.duration_seconds));
  appendCheck('Container downtime', formatDuration(run.container_downtime_seconds));
}

function renderStory(story, run) {
  if (!story) {
    $('#story-text').textContent = 'Backup story unavailable for this archive.';
    return;
  }
  const steps = story.steps || [];
  const completed = steps.filter(step => step.status === 'complete').length;
  const completedAt = formatDate(story.completed_at, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  const details = [`Backup completed ${completedAt}.`, `${completed} of ${steps.length} steps completed.`];
  if (run) {
    details.push(`Archive ${formatBytes(run.archive_size_bytes)} in ${formatDuration(run.duration_seconds)}; container downtime ${formatDuration(run.container_downtime_seconds)}.`);
  }
  $('#story-text').textContent = details.join(' ');
}

function renderCoverage(coverage) {
  const tiers = coverage?.tiers || [];
  if (!tiers.length) {
    $('#coverage-status').textContent = 'Historical coverage unavailable';
    setGlanceStatus('coverage-status-icon', 'unknown');
    return;
  }
  const current = tiers.reduce((sum, tier) => sum + tier.current, 0);
  const target = tiers.reduce((sum, tier) => sum + tier.target, 0);
  const complete = tiers.filter(tier => tier.state === 'complete').length;
  $('#coverage-status').textContent = `${current} of ${target} restore points · ${complete} of ${tiers.length} tiers complete`;
  const states = tiers.map(tier => tier.state || 'unknown');
  const coverageStatus = states.includes('failed')
    ? 'failure'
    : states.every(state => state === 'complete')
      ? 'healthy'
      : states.some(state => state === 'warning' || state === 'building')
        ? 'warning'
        : 'unknown';
  setGlanceStatus('coverage-status-icon', coverageStatus);
}

function addGenerationCheck(value, historical = false) {
  if (!value) return;
  appendCheck(
    historical ? 'Snapshot generated' : 'Data generated',
    formatDate(value, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
  );
}

function renderCurrentView() {
  const { confidence, story, history, coverage, system } = appState.data;
  const latest = history?.runs?.[0] || null;
  appState.selectedBackupId = latest?.backup_id || null;
  renderConfidence(confidence || null);
  renderRunMetrics(latest);
  renderStory(story || null, latest);
  renderCoverage(coverage || null);
  addGenerationCheck(system?.generated_at, false);
  $('#historical-notice').hidden = true;
  updateArchiveSelection();
}

function renderHistoricalView(run) {
  const snapshot = run.snapshot || {};
  const story = snapshot.story
    ? { backup_id: run.backup_id, ...snapshot.story }
    : null;
  appState.selectedBackupId = run.backup_id;
  renderConfidence(snapshot.confidence || null);
  renderRunMetrics(run);
  renderStory(story, run);
  renderCoverage(snapshot.coverage || null);
  addGenerationCheck(snapshot.generated_at, true);
  const notice = $('#historical-notice');
  notice.textContent = `Viewing archive from ${formatDate(run.completed_at, { month: 'long', day: 'numeric', year: 'numeric' })}`;
  notice.hidden = false;
  updateArchiveSelection();
}

function selectArchive(backupId) {
  const runs = appState.data.history?.runs || [];
  const position = runs.findIndex(run => run.backup_id === backupId);
  if (position < 0 || backupId === appState.selectedBackupId) return;
  transitionArchiveView(() => {
    if (position === 0) renderCurrentView();
    else renderHistoricalView(runs[position]);
  });
}

function transitionArchiveView(render) {
  if (reducedMotion.matches) {
    render();
    return;
  }

  const content = [$('.status-pill'), $('.ring-stage'), $('.story-card'), $('.verified-card'), $('.summary-panel')]
    .filter(Boolean);
  const main = $('main');
  clearTimeout(archiveTransitionTimer);
  clearTimeout(archiveTransitionFinishTimer);
  content.forEach(node => node.classList.add('archive-view-content', 'archive-view-fading'));
  main?.setAttribute('aria-busy', 'true');

  archiveTransitionTimer = setTimeout(() => {
    render();
    requestAnimationFrame(() => {
      content.forEach(node => node.classList.remove('archive-view-fading'));
      archiveTransitionFinishTimer = setTimeout(() => main?.removeAttribute('aria-busy'), 200);
    });
  }, 200);
}

function updateArchiveSelection() {
  $$('.archive[data-backup-id]').forEach(button => {
    const selected = button.dataset.backupId === appState.selectedBackupId;
    button.classList.toggle('selected', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
}

function renderArchiveList(history) {
  const runs = history?.runs || [];
  const archives = $('#archive-list');
  archives.replaceChildren();
  if (!runs.length) {
    archives.append(element('div', 'archive unavailable', 'History unavailable'));
    $('#archive-summary').textContent = 'Archive history unavailable.';
    return;
  }

  runs.slice(0, 7).forEach((run, position) => {
    const date = new Date(run.completed_at);
    const button = element('button', `archive level-${run.level || 'unknown'}`);
    button.type = 'button';
    button.dataset.backupId = run.backup_id;
    button.setAttribute('aria-pressed', String(position === 0));
    button.setAttribute('aria-label', `View archive from ${formatDate(run.completed_at, { month: 'long', day: 'numeric', year: 'numeric' })}`);
    button.title = `${titleCase(run.level || 'unknown')} confidence · ${formatBytes(run.archive_size_bytes)}`;
    button.append(
      element('strong', '', Number.isNaN(date.getTime()) ? '—' : String(date.getDate())),
      element('span', '', Number.isNaN(date.getTime()) ? 'Unknown' : formatDate(date, { month: 'short' }))
    );
    archives.append(button);
  });

  const latest = runs[0];
  $('#archive-summary').textContent = `${runs.length} ${runs.length === 1 ? 'archive' : 'archives'} in history · latest ${formatDate(latest.completed_at, { month: 'short', day: 'numeric' })}`;
}

function resourceTimestamp(name, data) {
  if (!data) return null;
  if (name === 'confidence') return data.last_verified_at;
  if (name === 'story') return data.completed_at;
  if (name === 'history') return data.runs?.[0]?.completed_at;
  if (name === 'system') return data.generated_at;
  if (name === 'inventory') return data.generated_at;
  if (name === 'site') return data.first_protected_at;
  return null;
}

function renderStructuredValue(value) {
  if (value === null || value === undefined) return element('span', 'data-unavailable', 'Unavailable');
  if (Array.isArray(value)) {
    const list = element('ol', 'data-list');
    value.forEach(item => {
      const entry = element('li');
      entry.append(renderStructuredValue(item));
      list.append(entry);
    });
    return list;
  }
  if (typeof value === 'object') {
    const list = element('dl', 'data-grid');
    Object.entries(value).forEach(([key, child]) => {
      list.append(element('dt', '', titleCase(key)));
      const description = element('dd');
      description.append(renderStructuredValue(child));
      list.append(description);
    });
    return list;
  }
  if (typeof value === 'boolean') return element('span', '', value ? 'Yes' : 'No');
  return element('span', '', String(value));
}

function openReference(item) {
  const dialog = $('#reference-detail');
  const title = $('#reference-detail-title');
  const summary = $('#reference-detail-summary');
  const timestamp = $('#reference-detail-timestamp');
  const raw = $('#reference-raw');
  const eyebrow = dialog.querySelector('.eyebrow');
  const isDocumentation = item.kind === 'documentation';
  const placeholder = isDocumentation ? item.data.sections[0] : null;
  const isPlaceholder = isDocumentation && item.data.sections.length === 1 && placeholder?.heading === 'Recovery Center';

  title.textContent = isPlaceholder ? placeholder.heading : item.title;
  summary.textContent = isPlaceholder ? placeholder.paragraphs[0] : item.summary;
  timestamp.textContent = item.timestamp
    ? `Generated or verified ${formatDate(item.timestamp, { month: 'long', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })}`
    : 'Generated or verified timestamp unavailable';
  timestamp.hidden = isDocumentation;
  raw.hidden = isDocumentation;
  eyebrow.hidden = isDocumentation;
  const content = $('#reference-detail-content');
  content.replaceChildren();

  if (isPlaceholder) {
    placeholder.paragraphs.slice(1).forEach(paragraph => content.append(element('p', '', paragraph)));
  } else if (isDocumentation) {
    item.data.sections.forEach(section => {
      const sectionNode = element('section', 'documentation-section');
      sectionNode.append(element('h3', '', section.heading));
      section.paragraphs.forEach(paragraph => sectionNode.append(element('p', '', paragraph)));
      content.append(sectionNode);
    });
  } else if (item.data) {
    content.append(renderStructuredValue(item.data));
  } else {
    content.append(element('p', 'data-unavailable', 'This resource is currently unavailable.'));
  }

  $('#reference-raw-json').textContent = JSON.stringify(item.data, null, 2) || 'Unavailable';
  raw.open = false;
  if (typeof dialog.showModal === 'function') dialog.showModal();
  else dialog.setAttribute('open', '');
}

function closeReference() {
  const dialog = $('#reference-detail');
  if (typeof dialog.close === 'function') dialog.close();
  else dialog.removeAttribute('open');
}

function createReferenceButton(item) {
  appState.referenceItems.set(item.id, item);
  const button = element('button', 'reference-entry');
  button.type = 'button';
  button.dataset.referenceId = item.id;
  button.setAttribute('aria-label', `Open ${item.title}`);
  button.append(
    element('strong', '', item.title),
    element('span', '', item.summary)
  );
  return button;
}

function renderReferences() {
  const results = $('#results');
  results.replaceChildren();
  appState.referenceItems.clear();

  const documentationGroup = element('section', 'reference-group');
  documentationGroup.append(element('h3', '', 'Recovery Center'));
  if (appState.documentation.length) {
    appState.documentation.forEach(entry => {
      documentationGroup.append(createReferenceButton({
        id: `doc:${entry.id}`,
        kind: 'documentation',
        title: entry.title,
        summary: entry.summary,
        timestamp: appState.documentationUpdatedAt,
        data: entry
      }));
    });
  } else {
    documentationGroup.append(element('p', 'data-unavailable', 'Recovery procedures are being added to this release.'));
  }
  results.append(documentationGroup);

  const resourceGroup = element('section', 'reference-group');
  resourceGroup.append(element('h3', '', 'Live API Resources'));
  Object.entries(appState.resources).forEach(([name, url]) => {
    const data = appState.data[name] || null;
    resourceGroup.append(createReferenceButton({
      id: `api:${name}`,
      kind: 'api',
      title: titleCase(name),
      summary: data ? resourceDescriptions[name] || `Live Harbr ${titleCase(name)} resource.` : `${titleCase(name)} is currently unavailable.`,
      timestamp: resourceTimestamp(name, data),
      data,
      url
    }));
  });
  results.append(resourceGroup);
}

async function loadExperience() {
  try {
    appState.index = await requestJson('/api/v1/index.json');
  } catch (error) {
    console.warn(error);
  }

  appState.resources = { ...defaultResources, ...(appState.index?.resources || {}) };
  const entries = Object.entries(appState.resources);
  const requests = entries.map(([, url]) => requestJson(url));
  requests.push(requestJson('/data/reference.json'));
  const results = await Promise.allSettled(requests);

  entries.forEach(([name], position) => {
    const result = results[position];
    if (result.status === 'fulfilled') appState.data[name] = result.value;
    else console.warn(result.reason);
  });

  const documentationResult = results[results.length - 1];
  if (documentationResult.status === 'fulfilled') {
    const recoveryOrder = documentationResult.value.display_order || [];
    appState.documentation = [...(documentationResult.value.entries || [])].sort((left, right) => {
      const leftPosition = recoveryOrder.indexOf(left.id);
      const rightPosition = recoveryOrder.indexOf(right.id);
      if (leftPosition === -1 && rightPosition === -1) return 0;
      if (leftPosition === -1) return 1;
      if (rightPosition === -1) return -1;
      return leftPosition - rightPosition;
    });
    appState.documentationUpdatedAt = documentationResult.value.updated_at || null;
  } else {
    console.warn(documentationResult.reason);
  }

  renderProduct(appState.index, appState.data.system);
  renderSite(appState.data.site);
  renderArchiveList(appState.data.history);
  renderCurrentView();
  renderInfrastructure(appState.data.infrastructure);
  renderReferences();
  startInfrastructurePolling();
}

loadExperience();
document.addEventListener('visibilitychange', () => { if (!document.hidden) pollInfrastructure(); });

$('#archive-list').addEventListener('click', event => {
  const button = event.target.closest('.archive[data-backup-id]');
  if (button) selectArchive(button.dataset.backupId);
});

$('#results').addEventListener('click', event => {
  const button = event.target.closest('.reference-entry[data-reference-id]');
  if (button) openReference(appState.referenceItems.get(button.dataset.referenceId));
});

$('#search').addEventListener('input', event => {
  const query = event.target.value.trim().toLowerCase();
  $$('.reference-entry').forEach(button => {
    button.hidden = Boolean(query) && !button.textContent.toLowerCase().includes(query);
  });
});

$('#reference-detail-close').addEventListener('click', closeReference);
$('#reference-detail').addEventListener('click', event => {
  if (event.target === $('#reference-detail')) closeReference();
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
}, { rootMargin: '-20% 0px -60%', threshold: [0, 0.25, 0.5] });
sections.forEach(section => sectionObserver.observe(section));

const startupBegan = performance.now();
window.addEventListener('load', () => {
  const elapsed = performance.now() - startupBegan;
  const endingStart = Math.max(0, 2400 - elapsed);
  setTimeout(() => $('#startup').classList.add('icon-away'), endingStart);
  setTimeout(() => $('#startup').classList.add('wordmark-away'), endingStart + 400);
  setTimeout(() => $('#startup').classList.add('done'), endingStart + 1500);
}, { once: true });
