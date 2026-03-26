var scheduleGrid = document.getElementById('schedule-grid');
var emptyState = document.getElementById('empty-state');
var meta = document.getElementById('meta');

loadSchedules();

async function loadSchedules() {
  try {
    var manifest = await fetchManifest();
    var primaryEntry = manifest.current_week && manifest.current_week.alias ? manifest.current_week : manifest.next_week && manifest.next_week.alias ? manifest.next_week : null;
    var cards = [
      buildCard(manifest.current_week, primaryEntry && manifest.current_week && manifest.current_week.label === primaryEntry.label),
      buildCard(manifest.next_week, primaryEntry && manifest.next_week && manifest.next_week.label === primaryEntry.label),
      buildTvCard(primaryEntry)
    ].filter(Boolean);

    if (!cards.length) {
      showEmpty();
      return;
    }

    scheduleGrid.innerHTML = cards.join('');
    emptyState.hidden = true;
    meta.textContent = 'Auto-generated every 4 hours. `schedule.png` points at this week on Monday-Friday and next week on Saturday-Sunday. `scheduletv.png` is the in-store portrait layout.';
  } catch (err) {
    console.error(err);
    meta.textContent = 'Could not load generated schedule assets.';
    showEmpty();
  }
}

function fetchManifest() {
  return fetch('generated/manifest.json', { cache: 'no-store' }).then(function (response) {
    if (!response.ok) {
      throw new Error('HTTP ' + response.status + ' loading manifest');
    }
    return response.json();
  });
}

function buildCard(entry, isPrimary) {
  if (!entry || !entry.filename) return '';

  var imagePath = 'generated/' + entry.filename;
  var aliasLink = entry.alias ? '<a class="btn btn-secondary" href="generated/' + entry.alias + '" download>Download Generic</a>' : '';

  return (
    '<article class="schedule-card' + (isPrimary ? ' primary' : '') + '">' +
      '<div class="schedule-card-header">' +
        '<div>' +
          '<h3>' + escapeHtml(entry.label) + '</h3>' +
          '<p class="schedule-range">' + formatRange(entry.start, entry.end) + '</p>' +
        '</div>' +
        (isPrimary ? '<div class="schedule-badge">Primary share image</div>' : '') +
      '</div>' +
      '<a class="schedule-preview" href="' + imagePath + '" target="_blank" rel="noreferrer">' +
        '<img src="' + imagePath + '" alt="' + escapeHtml(entry.label) + ' schedule">' +
      '</a>' +
      '<div class="schedule-actions">' +
        '<a class="btn btn-primary" href="' + imagePath + '" download>Download Image</a>' +
        aliasLink +
      '</div>' +
    '</article>'
  );
}

function buildTvCard(primaryEntry) {
  if (!primaryEntry) return '';

  var imagePath = 'generated/scheduletv.png';

  return (
    '<article class="schedule-card tv">' +
      '<div class="schedule-card-header">' +
        '<div>' +
          '<h3>In-Store TV</h3>' +
          '<p class="schedule-range">' + formatRange(primaryEntry.start, primaryEntry.end) + '</p>' +
        '</div>' +
        '<div class="schedule-badge">Large-type layout</div>' +
      '</div>' +
      '<a class="schedule-preview" href="' + imagePath + '" target="_blank" rel="noreferrer">' +
        '<img src="' + imagePath + '" alt="In-store TV schedule">' +
      '</a>' +
      '<div class="schedule-actions">' +
        '<a class="btn btn-primary" href="' + imagePath + '" download>Download TV Image</a>' +
      '</div>' +
    '</article>'
  );
}

function showEmpty() {
  scheduleGrid.innerHTML = '';
  emptyState.hidden = false;
}

function formatRange(startIso, endIso) {
  var start = new Date(startIso + 'T00:00:00');
  var end = new Date(endIso + 'T00:00:00');
  var startLabel = start.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  var endLabel = end.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  return startLabel + ' – ' + endLabel;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
