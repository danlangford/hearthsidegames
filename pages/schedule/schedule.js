/**
 * Weekly Schedule Generator for Hearthside Games
 * Fetches Leagues + Spotlight Google Calendars (iCal),
 * parses events for the coming week, renders a 1080×1920 canvas.
 */

var W = 1080;
var H = 1920;

var CALENDARS = {
  leagues: {
    id: 'da80818db985c7def75a3f684726983ff5361d88ebe99a1800a16230d7348b0f@group.calendar.google.com',
    type: 'league'
  },
  spotlight: {
    id: 'c5990df85ec2c327d239e1ad43a117f68cb3cd715aca633e833de1c0f80b6e3a@group.calendar.google.com',
    type: 'spotlight'
  }
};

var DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
var DAY_ABBR = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
var MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];
var MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

var generateBtn = document.getElementById('generate-btn');
var downloadBtn = document.getElementById('download-btn');
var copyBtn = document.getElementById('copy-btn');
var canvas = document.getElementById('story-canvas');
var ctx = canvas.getContext('2d');
var previewSection = document.getElementById('preview-section');
var emptyState = document.getElementById('empty-state');
var statusMsg = document.getElementById('status-msg');
var eventSummary = document.getElementById('event-summary');

// Preload logo
var hearthsideLogo = null;
var logoImg = new Image();
logoImg.onload = function () { hearthsideLogo = logoImg; };
logoImg.src = '../flame-deck-compat.svg';

// Preload font
var hearthFont = new FontFace('HearthLexendExaVF', "url('../HearthLexendExaVF.ttf')");
hearthFont.load().then(function (font) {
  document.fonts.add(font);
}).catch(function (err) { console.warn('Font load failed:', err); });

// ──── WEEK CALCULATION ────

function getComingWeek() {
  // Returns { start: Monday 00:00, end: Sunday 23:59:59 } of the coming week
  var now = new Date();
  var day = now.getDay(); // 0=Sun
  // Days until next Monday
  var daysToMon = (8 - day) % 7;
  if (daysToMon === 0) daysToMon = 7;
  // If it's Sunday, the "coming week" starts tomorrow (Monday)
  // If called on Sunday, daysToMon would be 1 which is correct
  var mon = new Date(now);
  mon.setDate(now.getDate() + daysToMon);
  mon.setHours(0, 0, 0, 0);

  var sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);
  sun.setHours(23, 59, 59, 999);

  return { start: mon, end: sun };
}

// ──── ICAL PARSING ────

function fetchCalendar(calId) {
  var url = 'https://calendar.google.com/calendar/ical/' +
    encodeURIComponent(calId) + '/public/basic.ics';
  // Use CORS proxy
  return fetch('https://api.allorigins.win/raw?url=' + encodeURIComponent(url))
    .then(function (r) { return r.text(); });
}

function parseICS(text) {
  var events = [];
  var lines = unfoldLines(text.split(/\r?\n/));
  var current = null;

  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    if (line === 'BEGIN:VEVENT') {
      current = {};
    } else if (line === 'END:VEVENT') {
      if (current) events.push(current);
      current = null;
    } else if (current) {
      var sep = line.indexOf(':');
      if (sep === -1) continue;
      var key = line.substring(0, sep);
      var val = line.substring(sep + 1);
      // Strip params from key for storage but keep full key for parsing
      var baseKey = key.split(';')[0];

      if (baseKey === 'SUMMARY') {
        current.summary = val;
      } else if (baseKey === 'DTSTART') {
        current.dtstart = val;
        current.dtstartKey = key;
      } else if (baseKey === 'DTEND') {
        current.dtend = val;
        current.dtendKey = key;
      } else if (baseKey === 'RRULE') {
        current.rrule = val;
      } else if (baseKey === 'DESCRIPTION') {
        current.description = val;
      } else if (baseKey === 'STATUS') {
        current.status = val;
      }
    }
  }
  return events;
}

function unfoldLines(lines) {
  var result = [];
  for (var i = 0; i < lines.length; i++) {
    if (lines[i].length > 0 && (lines[i][0] === ' ' || lines[i][0] === '\t')) {
      if (result.length > 0) {
        result[result.length - 1] += lines[i].substring(1);
      }
    } else {
      result.push(lines[i]);
    }
  }
  return result;
}

function parseICSDate(val, key) {
  // VALUE=DATE (all-day)
  if (key && key.indexOf('VALUE=DATE') !== -1) {
    // YYYYMMDD
    var y = parseInt(val.substring(0, 4));
    var m = parseInt(val.substring(4, 6)) - 1;
    var d = parseInt(val.substring(6, 8));
    return { date: new Date(y, m, d), allDay: true };
  }

  // TZID=America/Denver:20260107T190000
  if (key && key.indexOf('TZID=') !== -1) {
    // Local time (treat as Denver = Mountain)
    var y2 = parseInt(val.substring(0, 4));
    var m2 = parseInt(val.substring(4, 6)) - 1;
    var d2 = parseInt(val.substring(6, 8));
    var h2 = parseInt(val.substring(9, 11));
    var mi2 = parseInt(val.substring(11, 13));
    var s2 = parseInt(val.substring(13, 15));
    // Create as Mountain Time — we'll use a rough approach
    // since the store is in Mountain time and we just need day/time
    return { date: new Date(y2, m2, d2, h2, mi2, s2 || 0), allDay: false, local: true };
  }

  // UTC: 20260111T020000Z
  if (val.endsWith('Z')) {
    var y3 = parseInt(val.substring(0, 4));
    var m3 = parseInt(val.substring(4, 6)) - 1;
    var d3 = parseInt(val.substring(6, 8));
    var h3 = parseInt(val.substring(9, 11));
    var mi3 = parseInt(val.substring(11, 13));
    var s3 = parseInt(val.substring(13, 15));
    var utc = new Date(Date.UTC(y3, m3, d3, h3, mi3, s3 || 0));
    // Convert UTC to Mountain Time (roughly -7 MDT / -6 MST)
    // Use offset for Mountain Daylight or Standard
    var mountain = new Date(utc.getTime() - 7 * 60 * 60 * 1000);
    // Check if MST (Nov first Sun to Mar second Sun) — rough check
    var moNum = mountain.getMonth();
    if (moNum >= 10 || moNum <= 2) {
      mountain = new Date(utc.getTime() - 7 * 60 * 60 * 1000); // MST = -7
    } else {
      mountain = new Date(utc.getTime() - 6 * 60 * 60 * 1000); // MDT = -6
    }
    return { date: mountain, allDay: false, local: true };
  }

  // Plain datetime
  var y4 = parseInt(val.substring(0, 4));
  var m4 = parseInt(val.substring(4, 6)) - 1;
  var d4 = parseInt(val.substring(6, 8));
  var h4 = val.length >= 13 ? parseInt(val.substring(9, 11)) : 0;
  var mi4 = val.length >= 13 ? parseInt(val.substring(11, 13)) : 0;
  return { date: new Date(y4, m4, d4, h4, mi4, 0), allDay: val.length <= 8 };
}

// ──── RRULE EXPANSION ────

function parseRRule(rruleStr) {
  var parts = {};
  rruleStr.split(';').forEach(function (p) {
    var kv = p.split('=');
    parts[kv[0]] = kv[1];
  });
  return parts;
}

function expandEvent(event, weekStart, weekEnd) {
  // Returns array of { summary, date, allDay, type } within the week
  if (event.status === 'CANCELLED') return [];

  var parsed = parseICSDate(event.dtstart, event.dtstartKey);
  var startDate = parsed.date;
  var allDay = parsed.allDay;

  var endParsed = event.dtend ? parseICSDate(event.dtend, event.dtendKey) : null;

  if (!event.rrule) {
    // One-off event — check if it falls in the target week
    if (startDate >= weekStart && startDate <= weekEnd) {
      return [{ summary: event.summary, date: startDate, allDay: allDay }];
    }
    return [];
  }

  // Recurring event
  var rule = parseRRule(event.rrule);

  // Handle UNTIL
  if (rule.UNTIL) {
    var untilParsed = parseICSDate(rule.UNTIL, '');
    if (untilParsed.date < weekStart) return [];
  }

  // Handle COUNT (approximate — check if we'd still be within count)
  // We'll just check if the interval would reach our target week

  if (rule.FREQ === 'WEEKLY') {
    var interval = parseInt(rule.INTERVAL || '1');
    var byDay = rule.BYDAY ? rule.BYDAY.split(',') : null;

    var dayMap = { SU: 0, MO: 1, TU: 2, WE: 3, TH: 4, FR: 5, SA: 6 };
    var results = [];

    if (byDay) {
      byDay.forEach(function (d) {
        var targetDow = dayMap[d];
        if (targetDow === undefined) return;

        // Find the occurrence of this day-of-week in the target week
        // weekStart is Monday (dow=1)
        var daysFromMon = (targetDow - 1 + 7) % 7; // 0=Mon, 6=Sun
        var occDate = new Date(weekStart);
        occDate.setDate(weekStart.getDate() + daysFromMon);
        occDate.setHours(startDate.getHours(), startDate.getMinutes(), 0, 0);

        // Check if this occurrence is valid (after original start, before UNTIL)
        if (occDate < startDate) return;
        if (rule.UNTIL) {
          var untilD = parseICSDate(rule.UNTIL, '').date;
          if (occDate > untilD) return;
        }

        // Check interval: weeks since start must be divisible by interval
        if (interval > 1) {
          var weeksDiff = Math.round((occDate - startDate) / (7 * 24 * 60 * 60 * 1000));
          if (weeksDiff % interval !== 0) return;
        }

        // Handle COUNT
        if (rule.COUNT) {
          var count = parseInt(rule.COUNT);
          var weeksSinceStart = Math.round((occDate - startDate) / (7 * 24 * 60 * 60 * 1000));
          var occNum = Math.floor(weeksSinceStart / interval) + 1;
          if (occNum > count) return;
        }

        if (occDate >= weekStart && occDate <= weekEnd) {
          results.push({ summary: event.summary, date: occDate, allDay: allDay });
        }
      });
    } else {
      // No BYDAY — recurs on same day of week as start
      var targetDow = startDate.getDay();
      var daysFromMon = (targetDow - 1 + 7) % 7;
      var occDate = new Date(weekStart);
      occDate.setDate(weekStart.getDate() + daysFromMon);
      occDate.setHours(startDate.getHours(), startDate.getMinutes(), 0, 0);

      if (occDate >= startDate && occDate >= weekStart && occDate <= weekEnd) {
        if (interval > 1) {
          var weeksDiff = Math.round((occDate - startDate) / (7 * 24 * 60 * 60 * 1000));
          if (weeksDiff % interval === 0) {
            results.push({ summary: event.summary, date: occDate, allDay: allDay });
          }
        } else {
          results.push({ summary: event.summary, date: occDate, allDay: allDay });
        }
      }
    }

    return results;
  }

  // DAILY, MONTHLY etc — just check single occurrence for now
  if (startDate >= weekStart && startDate <= weekEnd) {
    return [{ summary: event.summary, date: startDate, allDay: allDay }];
  }

  return [];
}

// ──── MAIN GENERATE ────

generateBtn.addEventListener('click', generate);

async function generate() {
  generateBtn.classList.add('loading');
  generateBtn.disabled = true;

  try {
    showStatus('Fetching calendars...');

    var [leaguesText, spotlightText] = await Promise.all([
      fetchCalendar(CALENDARS.leagues.id),
      fetchCalendar(CALENDARS.spotlight.id)
    ]);

    var leagueEvents = parseICS(leaguesText);
    var spotlightEvents = parseICS(spotlightText);

    var week = getComingWeek();

    // Expand all events into the target week
    var allEvents = [];

    leagueEvents.forEach(function (ev) {
      expandEvent(ev, week.start, week.end).forEach(function (occ) {
        occ.type = 'league';
        allEvents.push(occ);
      });
    });

    spotlightEvents.forEach(function (ev) {
      expandEvent(ev, week.start, week.end).forEach(function (occ) {
        occ.type = 'spotlight';
        allEvents.push(occ);
      });
    });

    // De-duplicate by summary + day
    var seen = {};
    allEvents = allEvents.filter(function (ev) {
      var key = ev.summary + '|' + ev.date.toDateString();
      if (seen[key]) return false;
      seen[key] = true;
      return true;
    });

    // Sort by date, then time
    allEvents.sort(function (a, b) { return a.date - b.date; });

    // Group by day (0=Monday .. 6=Sunday)
    var byDay = [[], [], [], [], [], [], []]; // Mon-Sun
    allEvents.forEach(function (ev) {
      var dayIdx = (ev.date.getDay() - 1 + 7) % 7; // Convert Sun=0 to Mon=0
      byDay[dayIdx].push(ev);
    });

    showStatus('Rendering ' + allEvents.length + ' events...');

    render(byDay, week);

    previewSection.style.display = 'block';
    emptyState.style.display = 'none';

    // Show summary
    var summaryHTML = '<strong>' + allEvents.length + ' events</strong> for ' +
      formatDateShort(week.start) + ' – ' + formatDateShort(week.end);
    eventSummary.innerHTML = summaryHTML;

    showStatus('Schedule generated!');
  } catch (err) {
    showStatus('Error fetching calendars: ' + err.message);
    console.error(err);
  } finally {
    generateBtn.classList.remove('loading');
    generateBtn.disabled = false;
  }
}

// ──── FORMAT HELPERS ────

function formatDateShort(d) {
  return MONTH_ABBR[d.getMonth()] + ' ' + d.getDate();
}

function formatDateRange(start, end) {
  if (start.getMonth() === end.getMonth()) {
    return MONTH_NAMES[start.getMonth()] + ' ' + start.getDate() + ' – ' + end.getDate();
  }
  return MONTH_ABBR[start.getMonth()] + ' ' + start.getDate() + ' – ' +
    MONTH_ABBR[end.getMonth()] + ' ' + end.getDate();
}

function formatTime(d) {
  var h = d.getHours();
  var m = d.getMinutes();
  var ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12;
  if (h === 0) h = 12;
  if (m === 0) return h + ' ' + ampm;
  return h + ':' + (m < 10 ? '0' : '') + m + ' ' + ampm;
}

function getOrdinal(n) {
  var s = 'th';
  if (n < 11 || n > 13) {
    if (n % 10 === 1) s = 'st';
    else if (n % 10 === 2) s = 'nd';
    else if (n % 10 === 3) s = 'rd';
  }
  return n + s;
}

// ──── CANVAS RENDERING ────

function measureContentHeight(byDay) {
  // Calculate total height needed without drawing
  var titleY = 200;
  var rangeY = titleY + 68;
  var legendY = rangeY + 48;
  var dayStartY = legendY + 45;
  var currentY = dayStartY;

  var eventLineH = 42;
  var rowMinH = 120;

  for (var i = 0; i < 7; i++) {
    var events = byDay[i];
    var eventsH = Math.max(1, events.length) * eventLineH;
    var rowH = Math.max(rowMinH, eventsH + 30);
    currentY += rowH;
  }

  // Add space for bottom branding
  currentY += 30 + 70; // gap + branding height
  // Add bottom padding
  currentY += 40;

  return currentY;
}

function render(byDay, week) {
  // Resize canvas to fit content
  var contentH = measureContentHeight(byDay);
  H = contentH;
  canvas.height = H;

  drawBackground();
  drawLogo();

  var titleY = 200;
  drawTitle(titleY);

  // Date range
  var rangeY = titleY + 68;
  ctx.save();
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.font = '300 30px HearthLexendExaVF, Inter, sans-serif';
  ctx.fillStyle = '#4D4740';
  ctx.fillText(formatDateRange(week.start, week.end) + ', ' + week.start.getFullYear(), W / 2, rangeY);
  ctx.restore();

  // Legend
  var legendY = rangeY + 48;
  ctx.save();
  ctx.textBaseline = 'top';
  ctx.font = '400 20px HearthLexendExaVF, Inter, sans-serif';
  // League dot + label
  var legendLeft = W / 2 - 130;
  ctx.fillStyle = '#BF5700';
  ctx.beginPath();
  ctx.arc(legendLeft, legendY + 10, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#4D4740';
  ctx.textAlign = 'left';
  ctx.fillText('Weekly', legendLeft + 14, legendY);
  // Spotlight dot + label
  var spotLeft = W / 2 + 30;
  ctx.fillStyle = '#4A5D68';
  ctx.beginPath();
  ctx.arc(spotLeft, legendY + 10, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#4D4740';
  ctx.fillText('Special', spotLeft + 14, legendY);
  ctx.restore();

  // Days
  var dayStartY = legendY + 45;
  var dayNames = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];
  var currentY = dayStartY;

  for (var i = 0; i < 7; i++) {
    var dayDate = new Date(week.start);
    dayDate.setDate(week.start.getDate() + i);
    var events = byDay[i];

    currentY = drawDay(dayNames[i], dayDate, events, currentY, i);
  }

  // Bottom branding
  drawBottomBranding(currentY + 30);
  drawParticles();
}

function drawBackground() {
  // Match hearthside.games: --bg: #F4F0EC, --surface: #FAEBD7
  var bg = ctx.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, '#F4F0EC');
  bg.addColorStop(0.3, '#F2EDE8');
  bg.addColorStop(0.7, '#EFE9E2');
  bg.addColorStop(1, '#EBE4DC');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  // Subtle warm glow at top
  var glow = ctx.createRadialGradient(W / 2, H * 0.15, 50, W / 2, H * 0.15, 500);
  glow.addColorStop(0, 'rgba(191, 87, 0, 0.04)');
  glow.addColorStop(1, 'transparent');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, W, H);
}

function drawLogo() {
  if (!hearthsideLogo) return;
  var sz = 70;
  var lx = (W - sz) / 2;
  var ly = 55;

  var off = document.createElement('canvas');
  off.width = sz;
  off.height = sz;
  var oc = off.getContext('2d');
  oc.drawImage(hearthsideLogo, 0, 0, sz, sz);
  oc.globalCompositeOperation = 'source-in';
  oc.fillStyle = '#BF5700';
  oc.fillRect(0, 0, sz, sz);

  ctx.save();
  ctx.shadowColor = 'rgba(191, 87, 0, 0.2)';
  ctx.shadowBlur = 20;
  ctx.drawImage(off, lx, ly, sz, sz);
  ctx.restore();

  ctx.save();
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.font = '300 20px HearthLexendExaVF, Inter, sans-serif';
  ctx.fillStyle = 'rgba(77, 71, 64, 0.55)';
  ctx.fillText('HEARTHSIDE GAMES', W / 2, ly + sz + 12);
  ctx.restore();
}

function drawTitle(y) {
  var cx = W / 2;
  ctx.save();
  ctx.textAlign = 'center';

  var lw = 260;
  var lg = ctx.createLinearGradient(cx - lw, y - 12, cx + lw, y - 12);
  lg.addColorStop(0, 'transparent');
  lg.addColorStop(0.3, 'rgba(191, 87, 0, 0.2)');
  lg.addColorStop(0.5, 'rgba(191, 87, 0, 0.35)');
  lg.addColorStop(0.7, 'rgba(191, 87, 0, 0.2)');
  lg.addColorStop(1, 'transparent');
  ctx.strokeStyle = lg;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(cx - lw, y - 12);
  ctx.lineTo(cx + lw, y - 12);
  ctx.stroke();

  ctx.fillStyle = '#BF5700';
  ctx.font = '18px serif';
  ctx.textBaseline = 'bottom';
  ctx.fillText('\u2726', cx, y - 16);

  ctx.textBaseline = 'top';
  ctx.font = '600 48px Cinzel, serif';
  ctx.fillStyle = '#BF5700';
  ctx.fillText('THIS WEEK', cx, y);

  ctx.strokeStyle = lg;
  ctx.beginPath();
  ctx.moveTo(cx - lw, y + 60);
  ctx.lineTo(cx + lw, y + 60);
  ctx.stroke();

  ctx.restore();
}

// ──── DAY ROW ────

function drawDay(dayName, dayDate, events, y, dayIdx) {
  var leftPad = 65;
  var rightPad = 65;
  var contentLeft = 220;
  var rowMinH = 120;

  // Calculate row height based on event count
  var eventLineH = 42;
  var eventsH = Math.max(1, events.length) * eventLineH;
  var rowH = Math.max(rowMinH, eventsH + 30);

  // Subtle separator line
  if (dayIdx > 0) {
    ctx.save();
    var sepGrad = ctx.createLinearGradient(leftPad, y, W - rightPad, y);
    sepGrad.addColorStop(0, 'transparent');
    sepGrad.addColorStop(0.2, 'rgba(74, 93, 104, 0.18)');
    sepGrad.addColorStop(0.8, 'rgba(74, 93, 104, 0.18)');
    sepGrad.addColorStop(1, 'transparent');
    ctx.strokeStyle = sepGrad;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(leftPad, y);
    ctx.lineTo(W - rightPad, y);
    ctx.stroke();
    ctx.restore();
  }

  var centerY = y + rowH / 2;

  // Day name
  ctx.save();
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.font = '600 32px HearthLexendExaVF, Inter, sans-serif';
  ctx.fillStyle = '#BF5700';
  ctx.fillText(dayName, leftPad, y + 16);
  ctx.restore();

  // Date number
  ctx.save();
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.font = '300 20px HearthLexendExaVF, Inter, sans-serif';
  ctx.fillStyle = 'rgba(77, 71, 64, 0.5)';
  ctx.fillText(MONTH_ABBR[dayDate.getMonth()] + ' ' + dayDate.getDate(), leftPad, y + 50);
  ctx.restore();

  // Events
  if (events.length === 0) {
    ctx.save();
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.font = '300 24px HearthLexendExaVF, Inter, sans-serif';
    ctx.fillStyle = 'rgba(77, 71, 64, 0.25)';
    ctx.fillText('No events', contentLeft, y + 18 + 14);
    ctx.restore();
  } else {
    for (var j = 0; j < events.length; j++) {
      var ev = events[j];
      var ey = y + 18 + j * eventLineH;

      // Color vars based on type
      var isSpotlight = ev.type === 'spotlight';
      var dotColor = isSpotlight ? '#4A5D68' : '#BF5700';
      var nameColor = isSpotlight ? '#4A5D68' : '#1B1B1B';
      var timeColor = isSpotlight ? 'rgba(74, 93, 104, 0.6)' : 'rgba(77, 71, 64, 0.55)';

      // Colored dot indicator
      ctx.save();
      ctx.fillStyle = dotColor;
      ctx.beginPath();
      ctx.arc(contentLeft - 18, ey + 14, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      // Time
      ctx.save();
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.font = '400 22px HearthLexendExaVF, Inter, sans-serif';
      ctx.fillStyle = timeColor;
      if (ev.allDay) {
        ctx.fillText('ALL DAY', contentLeft, ey + 2);
      } else {
        ctx.fillText(formatTime(ev.date), contentLeft, ey + 2);
      }
      ctx.restore();

      // Event name
      ctx.save();
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.font = '400 24px HearthLexendExaVF, Inter, sans-serif';
      ctx.fillStyle = nameColor;

      // Truncate if needed
      var maxTextW = W - 420 - rightPad;
      var evName = ev.summary;
      while (ctx.measureText(evName).width > maxTextW && evName.length > 3) {
        evName = evName.substring(0, evName.length - 2) + '…';
      }
      ctx.fillText(evName, 420, ey + 2);
      ctx.restore();
    }
  }

  return y + rowH;
}

// ──── BOTTOM BRANDING ────

function drawBottomBranding(y) {
  var cx = W / 2;
  ctx.save();
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';

  ctx.font = '300 22px HearthLexendExaVF, Inter, sans-serif';
  ctx.fillStyle = 'rgba(77, 71, 64, 0.6)';
  ctx.fillText('hearthside.games', cx, y);

  ctx.font = '300 20px HearthLexendExaVF, Inter, sans-serif';
  ctx.fillStyle = 'rgba(77, 71, 64, 0.4)';
  ctx.fillText('6802 S Redwood Rd \u00B7 West Jordan, UT', cx, y + 32);

  ctx.restore();
}

function drawParticles() {
  ctx.save();
  var pts = [
    { x: 100, y: 280, s: 2.5, a: 0.22 },
    { x: 970, y: 350, s: 2, a: 0.18 },
    { x: 80, y: 1650, s: 2, a: 0.18 },
    { x: 990, y: 1550, s: 2, a: 0.16 },
    { x: 180, y: 1800, s: 1.5, a: 0.13 },
    { x: 900, y: 240, s: 1.5, a: 0.13 },
    { x: 540, y: 180, s: 2, a: 0.16 },
    { x: 500, y: 1860, s: 1.5, a: 0.13 }
  ];
  for (var i = 0; i < pts.length; i++) {
    var p = pts[i];
    var g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.s * 8);
    g.addColorStop(0, 'rgba(191, 87, 0, ' + (p.a * 0.35) + ')');
    g.addColorStop(1, 'transparent');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.s * 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = 'rgba(191, 87, 0, ' + (p.a * 0.5) + ')';
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.s, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

// ──── UTILITY ────

function showStatus(text) {
  statusMsg.textContent = text;
  statusMsg.classList.add('visible');
  clearTimeout(showStatus.t);
  showStatus.t = setTimeout(function () {
    statusMsg.classList.remove('visible');
  }, 4000);
}

downloadBtn.addEventListener('click', function () {
  var week = getComingWeek();
  var a = document.createElement('a');
  a.download = 'hearthside-week-' + formatDateShort(week.start).replace(' ', '') + '.png';
  a.href = canvas.toDataURL('image/png');
  a.click();
  showStatus('Downloaded!');
});

copyBtn.addEventListener('click', async function () {
  try {
    var blob = await new Promise(function (r) { canvas.toBlob(r, 'image/png'); });
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
    showStatus('Copied to clipboard!');
  } catch (e) {
    showStatus('Could not copy. Try downloading instead.');
  }
});
