'use strict';

const $ = (sel) => document.querySelector(sel);
const CAMERAS = ['front', 'left_repeater', 'right_repeater', 'back', 'left_pillar', 'right_pillar'];
const CAMERA_LABELS = {
  front: t("Przód"), left_repeater: t("Lewy bok"), right_repeater: t("Prawy bok"), back: t("Tył"),
  left_pillar: t("Lewy słupek"), right_pillar: t("Prawy słupek"), side: t("Bok (kamera nieustalona)"),
};
const GEARS = ['P', 'D', 'R', 'N'];
const AUTOPILOT = ['', 'FSD', 'Autosteer', t("Tempomat")];
const CLIP_SECONDS = 60;
const SESSION_GAP = 5 * 60;   // seconds between clips that start a new recording in the lists

const app = {
  step: 'drive',
  drive: null,
  clips: [],          // scan results
  range: null,        // [startUtc, endUtc] or null for all
  pollTimer: null,
  jobHandlers: {},
};

// ---------- helpers ----------

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  };
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = t("Nie udało się ukończyć operacji (kod {0}).", [res.status]);
    try { const detail = (await res.json()).detail; if (typeof detail === 'string') msg = detail; } catch (e) { /* not JSON */ }
    throw new Error(msg);
  }
  return res.json();
}

function toast(msg, ms = 4000) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.add('hidden'), ms);
}

const cameraCount = n => window.LANG === 'en' ? `${n} ${n === 1 ? 'camera' : 'cameras'}` : `${n} ${n === 1 ? 'kamera' : n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14) ? 'kamery' : 'kamer'}`;
const clipCount = n => window.LANG === 'en' ? `${n} ${n === 1 ? 'clip' : 'clips'}` : `${n} ${n === 1 ? 'klip' : n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14) ? 'klipy' : 'klipów'}`;
const fmtSize = b => {
  const [value, unit] = b >= 1e9 ? [b / 1e9, 'GB'] : b >= 1e6 ? [b / 1e6, 'MB'] : b >= 1e3 ? [b / 1e3, 'KB'] : [b, 'B'];
  return value.toLocaleString(locale(), { maximumFractionDigits: 1 }) + ' ' + unit;
};
const fmtDate = (t) => new Date(t * 1000).toLocaleDateString(locale(), { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' });
const fmtTime = (t) => new Date(t * 1000).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const fmtDateTime = (t) => fmtDate(t) + ' ' + fmtTime(t);

function toLocalInput(t) {
  const d = new Date(t * 1000);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
const fromLocalInput = (s) => s ? new Date(s).getTime() / 1000 : null;

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const c of children) if (c != null) e.append(c);
  return e;
}

/** Split time-sorted items into groups separated by more than gap seconds. */
function sessions(items, timeOf, gap = SESSION_GAP) {
  const out = [];
  for (const it of items) {
    const t = timeOf(it);
    const last = out[out.length - 1];
    if (last && t - last.end <= gap) { last.items.push(it); last.end = t; }
    else out.push({ start: t, end: t, items: [it] });
  }
  return out;
}

// ---------- navigation ----------

function show(step) {
  if (step !== 'viewer' && typeof viewer !== 'undefined' && viewer.playing) viewer.pause();
  const changed = app.step !== step;
  app.step = step;
  document.querySelectorAll('.screen').forEach((s) => s.classList.toggle('active', s.id === 'screen-' + step));
  document.querySelectorAll('#steps button').forEach((b) => b.classList.toggle('active', b.dataset.step === step));
  if (step === 'drive') refreshDrives();
  if (step === 'select') renderSelect();
  if (step === 'copy') renderCopy();
  if (step === 'viewer') viewer.load();
  if (changed) document.getElementById('screen-' + step).scrollTop = 0;
  if (location.hash !== '#' + step) history.replaceState(null, '', '#' + step);
}

document.querySelectorAll('#steps button').forEach((b) => b.addEventListener('click', () => show(b.dataset.step)));

// ---------- job polling ----------

function renderProgress(container, job, extra) {
  if (!job) return;
  const key = JSON.stringify([window.LANG, job.phase, job.done, job.total, job.status, job.error, !!extra]);
  if (container.dataset.progressKey === key) return;
  container.dataset.progressKey = key;
  container.innerHTML = '';
  const pct = job.total ? Math.min(100, 100 * job.done / job.total) : (job.status === 'done' ? 100 : 0);
  const bar = el('div', { class: 'bar' + (job.total <= 1 && job.done === 0 && job.status === 'running' ? ' indeterminate' : ''), role: 'progressbar', 'aria-label': job.phase, 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': Math.round(pct) }, el('div'));
  bar.firstChild.style.width = pct + '%';
  container.append(el('div', { class: 'phase' }, job.phase + (job.total > 1 && job.status === 'running' ? ` — ${pct.toFixed(0)}%` : '')), bar);
  if (job.status === 'running') {
    container.append(el('button', { onclick: () => api('/api/cancel', {}) }, t("Anuluj")));
  } else if (job.status === 'error' || job.status === 'auth') {
    container.append(el('div', { class: 'error' }, job.error));
    if (job.error_details && job.error_details !== job.error) container.append(el('details', {}, el('summary', {}, t("Szczegóły błędu")), el('p', { class: 'muted small' }, job.error_details)));
  } else if (job.status === 'cancelled') {
    container.append(el('div', { class: 'error' }, t("Operacja anulowana.")));
  }
  if (extra) container.append(extra);
}

async function poll() {
  let st;
  try { st = await api('/api/state'); } catch (e) { return; }
  app.state = st;
  const job = st.job;
  if (job) {
    const handler = app.jobHandlers[job.kind];
    if (handler) handler(job);
    if (job.status !== 'running' && app.watching === job.kind) {
      app.watching = null;
      const done = app.jobHandlers[job.kind + ':done'];
      if (done) done(job);
    }
  }
  const busy = job?.status === 'running';
  ['#open-folder-btn', '#copy-btn', '#signin-btn', '#decrypt-btn', '#pick-image-btn', '#release-usb-btn'].forEach(id => $(id).disabled = busy);
  $('#release-usb-btn').classList.toggle('hidden', !st.authorized_device);
  $('#signin-btn').disabled = busy || !((st.library?.counts?.encrypted || 0) + (st.library?.counts?.key_error || 0));
  $('#decrypt-btn').disabled = busy || !st.library;
  $('#copy-btn').disabled = busy || !st.scanned;
  markDoneSteps(st);
}

function markDoneSteps(st) {
  const done = {
    drive: !!st.drive, scan: st.scanned, select: st.scanned && !!st.out_dir, copy: !!st.library,
    signin: st.signed_in, decrypt: st.library && (st.library.counts.ok || 0) > 0,
  };
  document.querySelectorAll('#steps button').forEach((b) => b.classList.toggle('done', !!done[b.dataset.step]));
}

const JOB_SCREENS = { authorize: 'scan', scan: 'scan', export: 'copy', signin: 'signin', decrypt: 'decrypt', repair: 'decrypt' };

async function startJob(kind, path, body) {
  try {
    await api(path, body);
    app.watching = kind;
    poll();
  } catch (e) {
    // Another step is still running: show it (with its Cancel button) instead of failing quietly.
    const st = await api('/api/state').catch(() => null);
    const running = st && st.job && st.job.status === 'running' ? st.job : null;
    if (running && JOB_SCREENS[running.kind]) {
      app.watching = running.kind;
      show(JOB_SCREENS[running.kind]);
      toast(t("Trwa operacja: „{0}”. Poczekaj lub ją anuluj.", [running.phase]), 8000);
    } else {
      toast(e.message, 8000);
    }
    throw e;
  }
}

setInterval(poll, 500);

// ---------- 1. drive ----------

async function refreshDrives() {
  if (app.step !== 'drive' || app.refreshingDrives) return;
  app.refreshingDrives = true;
  try {
    const drives = await api('/api/drives');
    app.drives = drives;
    const teslaDrives = drives.filter(d => d.teslacam);
    if (!app.drive && teslaDrives.length === 1) app.drive = teslaDrives[0].drive;
    if (app.drive && !drives.some(d => d.drive === app.drive)) app.drive = null;
    const selected = drives.find(d => d.drive === app.drive);
    $('#scan-btn').disabled = !(selected?.supported) || app.state?.job?.status === 'running';
    const key = JSON.stringify([drives, app.drive]);
    if (app.driveCardsKey === key) return;
    app.driveCardsKey = key;
    const list = $('#drive-list'); list.innerHTML = '';
    for (const d of drives) {
      list.append(el('button', { class: 'card' + (d.drive === app.drive ? ' selected' : ''),
        'aria-pressed': d.drive === app.drive ? 'true' : 'false',
        onclick: () => { app.drive = d.drive; refreshDrives(); } },
        el('div', { class: 'big' }, d.label || t("Nośnik USB")),
        el('div', { class: 'muted' }, `${d.fs} · ${fmtSize(d.size)}`),
        el('div', { class: 'badge ' + (d.teslacam ? 'ready' : '') }, d.image ? t("Obraz partycji") : d.teslacam ? t("Wykryto TeslaCam") : t("Brak folderu TeslaCam")),
        el('div', { class: 'device-path' }, d.drive),
        d.supported ? null : el('div', { class: 'warn' }, t("Wymagana partycja exFAT lub FAT32"))));
    }
    $('#drive-empty').textContent = drives.length ? '' : t("Nie wykryto USB. Podłącz pendrive lub otwórz obraz partycji.");
  } catch (e) {
    $('#drive-empty').textContent = t("Nie udało się odczytać listy źródeł. ") + e.message;
  } finally { app.refreshingDrives = false; }
}
setInterval(refreshDrives, 3000);
$('#refresh-drives-btn').addEventListener('click', () => { app.driveCardsKey = null; refreshDrives(); });
$('#pick-image-btn').addEventListener('click', async () => {
  const result = await api('/api/pick-image', {});
  if (result.path) { app.drive = result.path; app.driveCardsKey = null; await refreshDrives(); }
});
$('#release-usb-btn').addEventListener('click', async () => {
  await api('/api/release-usb', {}); app.clips = []; app.range = null;
  await poll(); await refreshDrives(); toast(t("Zakończono odczyt. Nośnik można bezpiecznie odłączyć po zamontowaniu."));
});
$('#scan-btn').addEventListener('click', async () => {
  if (!app.drive) return;
  app.pendingDrive = app.drive;
  app.range = null; app.dateFilter = ''; $('#timeline-zoom').value = '1';
  show('scan');
  if (app.state?.platform === 'darwin' && app.drive.startsWith('/dev/') && app.state.authorized_device !== app.drive) {
    await startJob('authorize', '/api/authorize-usb', { drive: app.drive });
  } else await startJob('scan', '/api/scan', { drive: app.drive });
});
app.jobHandlers.authorize = job => renderProgress($('#scan-progress'), job);
app.jobHandlers['authorize:done'] = async job => {
  if (job.status === 'done') await startJob('scan', '/api/scan', { drive: job.result.drive });
};

// ---------- 2. scan ----------

app.jobHandlers.scan = (job) => {
  let extra = null;
  if (job.status === 'error' && /denied|permission|access|dostęp/i.test(job.error_details || job.error || '')) {
    extra = app.state?.platform === 'win32'
      ? el('button', { onclick: () => api('/api/elevate', {}) }, t("Uruchom jako administrator"))
      : el('p', { class: 'muted' }, t("Sprawdź pełny dostęp do dysku w Ustawieniach systemowych → Prywatność i ochrona. Dla skryptu włącz Terminal, a dla aplikacji zgodę dla procesu uruchamiającego odczyt."));
  }
  renderProgress($('#scan-progress'), job, extra);
};
app.jobHandlers['scan:done'] = async (job) => {
  if (job.status !== 'done') return;
  app.clips = await api('/api/clips');
  app.range = null; app.dateFilter = '';
  show('select');
};

function qualityBadge(quality) {
  return el('span', { class: 'badge ' + (quality?.code || 'unverified'), title: quality?.note || '' }, quality?.label || t("Do weryfikacji"));
}
function visibleTimedClips() {
  return app.clips.filter(c => c.start_utc != null && (!app.dateFilter || toLocalInput(c.start_utc).slice(0, 10) === app.dateFilter));
}
$('#timeline-zoom').addEventListener('input', drawTimeline);
$('#reset-range-btn').addEventListener('click', () => { app.dateFilter = ''; renderSelect(); setRange(null); });
$('#timeline-day').addEventListener('change', ev => {
  app.dateFilter = ev.target.value;
  const visible = visibleTimedClips();
  app.range = app.dateFilter && visible.length ? [visible[0].start_utc, visible[visible.length - 1].start_utc + CLIP_SECONDS] : null;
  renderSelect(); setRange(app.range);
});

// ---------- 3. select ----------

function selectedClips() {
  if (!app.range) return app.clips;
  const [a, b] = app.range;
  return app.clips.filter((c) => c.start_utc != null && c.start_utc <= b && c.start_utc + CLIP_SECONDS >= a);
}

function updateSelectionInfo() {
  const sel = selectedClips();
  const size = sel.reduce((s, c) => s + c.size, 0);
  const deleted = sel.filter((c) => c.source !== 'live').length;
  $('#selection-info').textContent = t("Wybrano: {0} · {1} po usunięciu · {2}", [clipCount(sel.length), deleted, fmtSize(size)]) + (app.range ? ` · ${fmtTime(app.range[0])}–${fmtTime(app.range[1])}` : '');
  $('#to-copy-btn').disabled = !sel.length;
  document.querySelectorAll('.session').forEach((row) => {
    const s = app.sessionList[row.dataset.i];
    row.classList.toggle('selected', !!app.range && s.start <= app.range[1] && s.end + CLIP_SECONDS >= app.range[0]);
  });
  drawTimeline();
}

function setRange(range) {
  app.range = range;
  document.querySelector(`input[name=range][value=${range ? 'range' : 'all'}]`).checked = true;
  if (range) {
    $('#range-from').value = toLocalInput(range[0]);
    $('#range-to').value = toLocalInput(range[1]);
  }
  updateSelectionInfo();
}

function renderSelect() {
  const clips = app.clips;
  if (!clips.length) {
    $('#select-summary').textContent = app.state?.scanned ? t("Nie odnaleziono nagrań. Wybierz inne źródło lub sprawdź, czy dane nie zostały nadpisane.") : t("Najpierw przeskanuj źródło nagrań.");
    $('#session-list').innerHTML = ''; $('#scan-stats').innerHTML = ''; app.sessionList = [];
    updateSelectionInfo(); return;
  }
  const timed = clips.filter((c) => c.start_utc != null);
  const live = clips.filter((c) => c.source === 'live').length;
  $('#select-summary').textContent =
    t("Odnaleziono {0}: {1} na nośniku i {2} w danych po usunięciu", [clipCount(clips.length), live, clips.length - live]) +
    (timed.length ? t(". Zakres: {0} — {1}.", [fmtDateTime(timed[0].start_utc), fmtDateTime(timed[timed.length - 1].start_utc)]) : '.');

  const days = [...new Set(timed.map(c => toLocalInput(c.start_utc).slice(0, 10)))];
  const daySelect = $('#timeline-day'); daySelect.innerHTML = '';
  daySelect.append(el('option', { value: '' }, t("Wszystkie dni")));
  days.forEach(day => daySelect.append(el('option', { value: day }, day)));
  daySelect.value = app.dateFilter || '';
  const partial = clips.filter(c => c.quality?.code === 'partial').length;
  const stats = $('#scan-stats'); stats.innerHTML = '';
  [[live, t("na nośniku")], [clips.length - live, t("w danych po usunięciu")], [partial, t("z wykrytymi brakami")], [clips.length - timed.length, t("z nieustalonym czasem")]].forEach(([n, label]) => stats.append(el('div', {}, el('b', {}, String(n)), label)));
  app.sessionList = sessions(visibleTimedClips(), (c) => c.start_utc);
  const list = $('#session-list');
  list.innerHTML = '';
  app.sessionList.slice().reverse().forEach((s) => {
    const i = app.sessionList.indexOf(s);
    const minutes = new Set(s.items.map((c) => Math.round(c.start_utc / 60))).size;
    const del = s.items.filter((c) => c.source !== 'live').length;
    const mix = el('div', { class: 'mix' }, el('div', { class: 'l' }), el('div', { class: 'd' }));
    mix.children[0].style.width = (100 * (s.items.length - del) / s.items.length) + '%';
    mix.children[1].style.width = (100 * del / s.items.length) + '%';
    const row = el('div', { role: 'button', tabindex: 0, class: 'session', 'data-i': i, onclick: (ev) => {
      if (ev.shiftKey && app.range) setRange([Math.min(app.range[0], s.start), Math.max(app.range[1], s.end + CLIP_SECONDS)]);
      else setRange([s.start, s.end + CLIP_SECONDS]);
    } },
    el('div', { class: 'when' }, fmtDate(s.start) + ' ' + fmtTime(s.start).slice(0, 5)),
    el('div', {}, `${minutes} min · ${clipCount(s.items.length)}` + (del ? t(" · {0} po usunięciu", [del]) : ''),
      el('div', { class: 'badges' }, qualityBadge(s.items.some(c => c.quality?.code === 'partial') ? { code: 'partial', label: t("Wykryto częściowe pliki"), note: t("Niektóre klipy mają wykryte braki.") } : { code: 'unverified', label: t("Odtwarzalność do weryfikacji"), note: t("Pliki zostaną sprawdzone po skopiowaniu.") }))), mix,
    el('div', { class: 'muted' }, fmtSize(s.items.reduce((a, c) => a + c.size, 0))));
    list.append(row);
  });
  const untimed = clips.length - timed.length;
  if (untimed) list.append(el('p', { class: 'muted' }, t("Klipy z nieustalonym czasem: {0}. Aby je odzyskać, wybierz „Wszystkie nagrania”.", [untimed])));
  updateSelectionInfo();
}

// Timeline: a bar per time bucket; drag to choose a range.
function drawTimeline() {
  const canvas = $('#timeline');
  const timed = visibleTimedClips();
  const w = Math.max(1, $('#timeline-scroll').clientWidth) * Number($('#timeline-zoom').value), h = 170;
  canvas.style.width = w + 'px';
  canvas.width = w * devicePixelRatio; canvas.height = h * devicePixelRatio;
  const ctx = canvas.getContext('2d');
  ctx.scale(devicePixelRatio, devicePixelRatio);
  ctx.clearRect(0, 0, w, h);
  app.timelineMap = [];
  if (!timed.length) return;
  // Compress long gaps: lay out recordings side by side, separated by small gaps.
  const segs = sessions(timed, (c) => c.start_utc, 3600);
  const gapPx = Math.min(18, w / Math.max(1, 3 * segs.length));
  const total = segs.reduce((a, s) => a + (s.end - s.start + CLIP_SECONDS), 0);
  const scale = (w - gapPx * (segs.length - 1)) / total;
  let x = 0;
  app.timelineMap = [];
  const css = getComputedStyle(document.documentElement);
  for (const s of segs) {
    const width = (s.end - s.start + CLIP_SECONDS) * scale;
    app.timelineMap.push({ x0: x, x1: x + width, t0: s.start, t1: s.end + CLIP_SECONDS });
    const buckets = Math.max(1, Math.floor(width / 3));
    const counts = Array.from({ length: buckets }, () => [0, 0]);
    for (const c of s.items) {
      const b = Math.min(buckets - 1, Math.floor((c.start_utc - s.start) / (s.end - s.start + CLIP_SECONDS) * buckets));
      counts[b][c.source === 'live' ? 0 : 1]++;
    }
    const max = 12;
    counts.forEach(([l, d], i) => {
      const bx = x + i * width / buckets, bw = Math.max(1, width / buckets - 0.5);
      const lh = Math.min(1, l / max) * (h - 20), dh = Math.min(1, d / max) * (h - 20);
      ctx.fillStyle = css.getPropertyValue('--live'); ctx.fillRect(bx, h - 16 - lh, bw, lh);
      ctx.fillStyle = css.getPropertyValue('--deleted'); ctx.fillRect(bx, h - 16 - lh - dh, bw, dh);
    });
    if (width > 80) {
      ctx.fillStyle = css.getPropertyValue('--muted'); ctx.font = '11px system-ui';
      ctx.fillText(fmtTime(s.start).slice(0, 5), x + 2, h - 3);
      if (width > 170) ctx.fillText(fmtTime(s.end + CLIP_SECONDS).slice(0, 5), x + width - 38, h - 3);
    }
    x += width + gapPx;
  }
  if (app.range) {
    const [a, b] = [timeToX(app.range[0]), timeToX(app.range[1])];
    ctx.fillStyle = 'rgba(62,142,247,.18)'; ctx.fillRect(a, 0, Math.max(2, b - a), h - 16);
    ctx.strokeStyle = css.getPropertyValue('--accent'); ctx.strokeRect(a, 0.5, Math.max(2, b - a), h - 17);
  }
}

function timeToX(t) {
  const m = app.timelineMap || [];
  for (const s of m) if (t <= s.t1) return t < s.t0 ? s.x0 : s.x0 + (t - s.t0) / (s.t1 - s.t0) * (s.x1 - s.x0);
  return m.length ? m[m.length - 1].x1 : 0;
}
function xToTime(x) {
  const m = app.timelineMap || [];
  for (const s of m) if (x <= s.x1) return x < s.x0 ? s.t0 : s.t0 + (x - s.x0) / (s.x1 - s.x0) * (s.t1 - s.t0);
  return m.length ? m[m.length - 1].t1 : 0;
}

(() => {
  const canvas = $('#timeline');
  let dragStart = null;
  const xOf = (ev) => ev.clientX - canvas.getBoundingClientRect().left;
  canvas.addEventListener('mousedown', (ev) => { if (app.timelineMap?.length) dragStart = xOf(ev); });
  canvas.addEventListener('mousemove', ev => { if (app.timelineMap?.length) $('#timeline-hint').textContent = fmtDateTime(xToTime(xOf(ev))) + t(" · przeciągnij, aby wybrać zakres"); });
  window.addEventListener('mousemove', (ev) => {
    if (dragStart == null) return;
    const current = Math.max(0, Math.min(canvas.clientWidth, xOf(ev)));
    const [a, b] = [dragStart, current].sort((p, q) => p - q);
    if (b - a > 3) setRange([xToTime(a), xToTime(b)]);
  });
  window.addEventListener('mouseup', () => { dragStart = null; });
  window.addEventListener('resize', () => { if (app.step === 'select') drawTimeline(); });
})();

document.querySelectorAll('input[name=range]').forEach((r) => r.addEventListener('change', () => {
  if (r.checked && r.value === 'all') setRange(null);
  if (r.checked && r.value === 'range') {
    const a = fromLocalInput($('#range-from').value), b = fromLocalInput($('#range-to').value);
    if (a && b) setRange([a, b]);
  }
}));
['#range-from', '#range-to'].forEach((id) => $(id).addEventListener('change', () => {
  const a = fromLocalInput($('#range-from').value), b = fromLocalInput($('#range-to').value);
  if (a && b) setRange([Math.min(a, b), Math.max(a, b)]);
}));

$('#to-copy-btn').addEventListener('click', () => {
  if (!selectedClips().length) return toast(t("Brak nagrań w wybranym zakresie."));
  show('copy');
});

// ---------- 4. copy ----------

function renderCopy() {
  const sel = selectedClips();
  $('#copy-summary').textContent = app.clips.length
    ? t("Skopiujemy {0} ({1}). Wybierz pusty folder na innym dysku. Przy odszyfrowaniu i naprawie mogą powstać dodatkowe kopie — zapewnij co najmniej dwa razy więcej miejsca.", [clipCount(sel.length), fmtSize(sel.reduce((s, c) => s + c.size, 0))])
    : t("Najpierw przeskanuj nośnik i wybierz nagrania.");
  if (!$('#out-dir').value && app.state && app.state.last_out_dir) $('#out-dir').value = app.state.last_out_dir;
}

$('#pick-out-btn').addEventListener('click', async () => {
  const r = await api('/api/pick-folder', { initial: $('#out-dir').value || null });
  if (r.path) $('#out-dir').value = r.path;
});

$('#copy-btn').addEventListener('click', async () => {
  const out = $('#out-dir').value.trim();
  if (!out) return toast(t("Najpierw wybierz folder docelowy."));
  const body = { out_dir: out, start_utc: app.range ? app.range[0] : null, end_utc: app.range ? app.range[1] : null };
  await startJob('export', '/api/export', body);
});
app.jobHandlers.export = (job) => renderProgress($('#copy-progress'), job);
app.jobHandlers['export:done'] = (job) => {
  if (job.status !== 'done') return;
  toast(t("Skopiowano {0}.", [clipCount(job.result.copied)]));
  const counts = app.state?.library?.counts || {};
  show((counts.encrypted || counts.key_error) && !app.state?.signed_in ? 'signin' : 'decrypt');
};

// ---------- 5. sign in ----------

$('#signin-btn').addEventListener('click', () => startJob('signin', '/api/signin', {}));
app.jobHandlers.signin = (job) => renderProgress($('#signin-progress'), job);
app.jobHandlers['signin:done'] = (job) => {
  if (job.status === 'done') { toast(t("Zalogowano do Tesli.")); show('decrypt'); }
};
$('#token-btn').addEventListener('click', async () => {
  try {
    await api('/api/token', { token: $('#token-input').value });
    $('#token-input').value = '';
    toast(t("Token zapisano w pamięci na czas tej sesji."));
    show('decrypt');
  } catch (e) { toast(e.message); }
});

// ---------- 6. decrypt ----------

$('#decrypt-btn').addEventListener('click', () => {
  $('#decrypt-result').innerHTML = '';
  startJob('decrypt', '/api/decrypt', { keep_encrypted: $('#keep-encrypted').checked });
});
app.jobHandlers.decrypt = (job) => renderProgress($('#decrypt-progress'), job);
app.jobHandlers['decrypt:done'] = async (job) => {
  if (job.status === 'auth') {
    toast(t("Zaloguj się do Tesli ponownie. Odszyfrowywanie wznowimy od miejsca przerwania."), 8000);
    show('signin');
    return;
  }
  const st = await api('/api/state');
  const counts = (st.library && st.library.counts) || {};
  const box = $('#decrypt-result');
  box.innerHTML = '';
  const grid = el('div', { class: 'result-grid' });
  const labels = { ok: t("gotowe do odtwarzania"), unplayable: t("nieodtwarzalne (folder „unplayable”)"), key_error: t("bez klucza z Tesli"), encrypted: t("nadal zaszyfrowane") };
  for (const [k, label] of Object.entries(labels)) if (counts[k]) grid.append(el('div', {}, el('b', {}, String(counts[k])), label));
  box.append(grid,
    el('div', { class: 'actions' },
      el('button', { class: 'primary', onclick: () => { viewer.loaded = false; show('viewer'); } }, t("Oglądaj nagrania")),
      counts.unplayable ? el('button', { onclick: startRepair }, t("Spróbuj naprawić uszkodzone pliki")) : null,
      el('button', { onclick: () => api('/api/open-folder', {}) }, t("Otwórz folder"))));
};

function startRepair() {
  show('decrypt');
  $('#decrypt-result').innerHTML = '';
  startJob('repair', '/api/repair', {});
}
app.jobHandlers.repair = (job) => renderProgress($('#decrypt-progress'), job);
app.jobHandlers['repair:done'] = (job) => {
  viewer.loaded = false;
  if (job.status === 'done') toast(t("Naprawa zakończona."));
  app.jobHandlers['decrypt:done'](job);
};

// ---------- open an existing folder ----------

$('#open-folder-btn').addEventListener('click', async () => {
  const r = await api('/api/pick-folder', {});
  if (!r.path) return;
  try {
    await api('/api/open-library', { folder: r.path });
    viewer.loaded = false;
    show('viewer');
  } catch (e) { toast(e.message); }
});

// ---------- 7. viewer ----------

const viewer = {
  loaded: false,
  minutes: [],      // [{t, clips: {camera: clip}, title, comment}]
  index: -1,
  focus: null,      // camera shown large, or null for the grid
  rate: 1,
  playing: false,
  telemetry: null,
  telemetryFile: null,
  marked: new Set(),

  async load() {
    if (this.loaded) return;
    let lib;
    try { lib = await api('/api/library'); } catch (e) {
      $('#clip-list').replaceChildren(el('div', { class: 'other' }, t("Nie otwarto jeszcze nagrań. Ukończ odzyskiwanie lub wybierz „Otwórz bibliotekę…”.")));
      return;
    }
    this.loaded = true;
    // One entry per recording minute; all six cameras share the same mvhd time.
    const byTime = new Map();
    for (const c of lib.clips) {
      const key = Math.round(c.recorded_utc);
      if (!byTime.has(key)) byTime.set(key, { t: c.recorded_utc, clips: {}, title: c.title, comment: c.comment });
      const m = byTime.get(key);
      let cam = c.camera || 'side';
      if (m.clips[cam]) cam = cam + '_' + c.id;   // unexpected duplicate: keep, but not in a tile
      m.clips[cam] = c;
      if (!m.title && c.title) { m.title = c.title; m.comment = c.comment; }
    }
    this.marked.clear(); this.lastMarked = null; this.index = -1; this.telemetry = null;
    this.minutes = [...byTime.values()].sort((a, b) => a.t - b.t);
    this.renderList(lib);
    this.buildTiles();
    if (this.minutes.length) this.open(0, false);
    else { $('#viewer-info').textContent = t("Brak nagrań gotowych do odtwarzania. Przejdź do przygotowania lub naprawy plików."); this.pause(); }
  },

  renderList(lib) {
    const list = $('#clip-list');
    list.innerHTML = '';
    let day = null;
    for (const s of sessions(this.minutes, (m) => m.t, SESSION_GAP)) {
      const d = fmtDate(s.start);
      if (d !== day) { day = d; list.append(el('div', { class: 'day' }, d)); }
      list.append(el('div', { class: 'group' }, `${fmtTime(s.start).slice(0, 5)} – ${fmtTime(s.end + CLIP_SECONDS).slice(0, 5)} · ${s.items.length} min`));
      for (const m of s.items) {
        const i = this.minutes.indexOf(m);
        const n = Object.keys(m.clips).length;
        const row = el('div', { role: 'button', 'aria-pressed': String(this.marked.has(i)), tabindex: 0, class: 'minute', 'data-i': i, title: [m.title, m.comment].filter(Boolean).join(', '),
          onclick: (ev) => ev.metaKey || ev.ctrlKey || ev.shiftKey ? this.mark(i, ev.shiftKey) : this.open(i, this.playing) },
        el('span', {}, el('span', { class: 't' }, fmtTime(m.t)), qualityBadge(Object.values(m.clips).find(c => ['partial', 'repaired'].includes(c.quality?.code))?.quality || Object.values(m.clips)[0]?.quality)),
        el('span', { class: 'loc' }, m.comment || m.title || ''),
        el('span', { class: 'n' }, n < 6 ? `${n}/6` : ''));
        list.append(row);
      }
    }
    if (lib.other.length) {
      list.append(el('div', { class: 'other' }, t("{0} klipów czeka na przygotowanie lub pozostaje nieodtwarzalnych. ", [lib.other.length]),
        el('button', { class: 'small', onclick: startRepair }, t("Spróbuj je naprawić"))));
    }
    list.append(el('div', { class: 'other' }, t("⌘ / Ctrl + klik zaznacza minuty; Shift + klik zaznacza zakres. Następnie wybierz „Zapisz wybór…”.")));
  },

  mark(i, range) {
    if (range && this.lastMarked != null) {
      const [a, b] = [Math.min(i, this.lastMarked), Math.max(i, this.lastMarked)];
      for (let k = a; k <= b; k++) this.marked.add(k);
    } else if (this.marked.has(i)) this.marked.delete(i);
    else this.marked.add(i);
    this.lastMarked = i;
    document.querySelectorAll('.clip-list .minute').forEach(r => { r.classList.toggle('marked', this.marked.has(+r.dataset.i)); r.setAttribute('aria-pressed', String(this.marked.has(+r.dataset.i))); });
  },

  buildTiles() {
    const box = $('#videos');
    box.innerHTML = '';
    this.tiles = {};
    for (const cam of CAMERAS) {
      const video = el('video', { muted: '', playsinline: '', preload: 'auto' });
      video.muted = true;
      const tile = el('div', { class: 'tile', 'data-cam': cam, onclick: () => this.setFocus(this.focus === cam ? null : cam) },
        video, el('div', { class: 'missing hidden' }, t("Brak nagrania")), el('div', { class: 'label' }, CAMERA_LABELS[cam]), el('div', { class: 'quality' }));
      box.append(tile);
      this.tiles[cam] = { tile, video };
      video.sync = { lastSeek: 0, lastTime: -1, stuckSince: 0, reloads: 0 };
      video.addEventListener('ended', () => { if (video === this.master()) this.next(); });
      video.addEventListener('error', () => this.recover(video));
    }
    this.applyLayout();
  },

  applyLayout() {
    const box = $('#videos');
    box.classList.toggle('grid', !this.focus);
    box.classList.toggle('focus', !!this.focus);
    let t = 1;
    for (const cam of CAMERAS) {
      const { tile } = this.tiles[cam];
      tile.style.gridArea = this.focus ? (cam === this.focus ? 'main' : 't' + t++) : cam;
    }
  },

  setFocus(cam) {
    if (!this.tiles) return;
    this.focus = cam;
    this.applyLayout();
  },

  // The video that drives the clock: the large one, else front, else any tile that has a clip
  // (a minute may only have clips of unknown camera, shown in spare tiles).
  master() {
    if (!this.tiles) return null;
    const loaded = CAMERAS.filter((c) => this.tiles[c].video.dataset.src && !this.tiles[c].video.sync.dead);
    if (this.focus && loaded.includes(this.focus)) return this.tiles[this.focus].video;
    // The longest clip, so a shorter (e.g. repaired) camera doesn't end the minute early.
    let best = null;
    for (const c of loaded) {
      const v = this.tiles[c].video;
      if (!best || (v.duration || 0) > (best.duration || 0) + 0.5) best = v;
    }
    return best;
  },

  renderInfo(m) {
    const info = $('#viewer-info'); info.innerHTML = '';
    info.append(el('span', {}, fmtDateTime(m.t) + ' · ' + cameraCount(Object.keys(m.clips).length) + ' · ' + [m.title, m.comment].filter(Boolean).join(', ')));
    info.append(qualityBadge(Object.values(m.clips).find(c => ['partial', 'repaired'].includes(c.quality?.code))?.quality || Object.values(m.clips)[0]?.quality));
  },

  async refreshLanguage() {
    if (!this.loaded) return;
    const lib = await api('/api/library');
    const qualities = new Map(lib.clips.map(c => [String(c.id), c.quality]));
    for (const minute of this.minutes) for (const clip of Object.values(minute.clips)) clip.quality = qualities.get(String(clip.id)) || clip.quality;
    this.renderList(lib);
    document.querySelectorAll('.clip-list .minute').forEach(row => {
      row.classList.toggle('current', Number(row.dataset.i) === this.index);
      row.classList.toggle('marked', this.marked.has(Number(row.dataset.i)));
      row.setAttribute('aria-pressed', String(this.marked.has(Number(row.dataset.i))));
    });
    for (const cam of CAMERAS) {
      const { tile, video } = this.tiles[cam];
      tile.querySelector('.label').textContent = CAMERA_LABELS[tile.dataset.labelKey || cam];
      tile.querySelector('.missing').textContent = video.sync.dead ? t('Nie można odtworzyć tego klipu') : t('Brak nagrania');
      const box = tile.querySelector('.quality'); box.innerHTML = '';
      if (video.dataset.clipId) box.append(qualityBadge(qualities.get(video.dataset.clipId)));
    }
    const minute = this.minutes[this.index];
    if (minute) this.renderInfo(minute);
    else $('#viewer-info').textContent = t('Brak nagrań gotowych do odtwarzania. Przejdź do przygotowania lub naprawy plików.');
  },

  open(i, autoplay) {
    if (i < 0 || i >= this.minutes.length) return;
    this.index = i;
    const m = this.minutes[i];
    this.renderInfo(m);
    // Clips of unknown camera ("side") fill empty side tiles so nothing is hidden.
    const extra = Object.keys(m.clips).filter((k) => !CAMERAS.includes(k)).map((k) => m.clips[k]);
    for (const cam of CAMERAS) {
      const { tile, video } = this.tiles[cam];
      let clip = m.clips[cam];
      let labelKey = cam;
      if (!clip && cam !== 'front' && extra.length) { clip = extra.shift(); labelKey = 'side'; }
      tile.dataset.labelKey = labelKey; video.dataset.clipId = clip?.id || '';
      const label = CAMERA_LABELS[labelKey];
      tile.querySelector('.label').textContent = label;
      const badge = tile.querySelector('.quality'); badge.innerHTML = '';
      if (clip) badge.append(qualityBadge(clip.quality));
      tile.querySelector('.missing').textContent = t("Brak nagrania");
      tile.querySelector('.missing').classList.toggle('hidden', !!clip);
      const src = clip ? '/media/' + clip.file.split('/').map(encodeURIComponent).join('/') : '';
      if (video.dataset.src !== src) {
        video.dataset.src = src;
        video.sync = { lastSeek: 0, lastTime: -1, stuckSince: 0, reloads: 0 };
        if (src) video.src = src; else video.removeAttribute('src');
        video.load();
      }
      video.playbackRate = this.rate;
    }
    document.querySelectorAll('.clip-list .minute').forEach((r) => {
      const cur = +r.dataset.i === i;
      r.classList.toggle('current', cur);
      if (cur) r.scrollIntoView({ block: 'nearest' });
    });
    this.loadTelemetry(m);
    if (autoplay) this.play(); else this.pause();
  },

  next() { if (this.index + 1 < this.minutes.length) this.open(this.index + 1, true); else this.pause(); },
  prev() { this.open(Math.max(0, this.index - 1), this.playing); },

  videos() { return this.tiles ? CAMERAS.map((c) => this.tiles[c].video).filter((v) => v.dataset.src) : []; },

  play() {
    this.playing = true;
    $('#play-btn').textContent = '⏸';
    for (const v of this.videos()) if (!v.sync.dead) v.play().catch(() => {});
  },

  // A video that errored or stopped advancing: reload it at the current time (twice at most,
  // then mark the tile as unplayable so the other cameras carry on).
  recover(video) {
    const s = video.sync;
    const tile = video.parentElement;
    if (!video.dataset.src) return;
    if (s.reloads >= 2) {
      s.dead = true;
      tile.querySelector('.missing').textContent = t("Nie można odtworzyć tego klipu");
      tile.querySelector('.missing').classList.remove('hidden');
      return;
    }
    s.reloads++;
    s.stuckSince = 0;
    const master = this.master();
    const t = master && master !== video ? master.currentTime : video.currentTime;
    video.load();
    video.addEventListener('loadedmetadata', () => {
      video.currentTime = Math.min(t, video.duration || t);
      video.playbackRate = this.rate;
      if (this.playing) video.play().catch(() => {});
    }, { once: true });
  },
  pause() {
    this.playing = false;
    $('#play-btn').textContent = '▶';
    for (const v of this.videos()) v.pause();
  },
  seek(t) {
    for (const v of this.videos()) {
      v.currentTime = Math.min(t, (v.duration || t));
      v.sync.lastSeek = performance.now();
      v.sync.stuckSince = 0;
    }
  },

  // Keep one camera on the master's time. Small drift is corrected by nudging the playback rate;
  // only large drift seeks, at most once every 1.5 s, and never while the video is still seeking
  // (seeking every frame is what left a camera frozen).
  syncVideo(v, master, t, now) {
    const s = v.sync;
    if (s.dead || v.readyState < 1) return;
    const dur = v.duration || 0;
    if (t >= dur - 0.05) { v.playbackRate = this.rate; return; }   // this camera's clip is shorter
    if (this.playing && v.paused && !v.ended && !v.seeking) v.play().catch(() => {});
    if (v.seeking || v.readyState < 2) return;
    const drift = v.currentTime - t;
    if (!this.playing) {
      if (Math.abs(drift) > 0.05) { v.currentTime = t; s.lastSeek = now; }
      return;
    }
    if (Math.abs(drift) > 1 && now - s.lastSeek > 1500) {
      v.currentTime = t + 0.1 * this.rate;
      s.lastSeek = now;
      v.playbackRate = this.rate;
    } else if (Math.abs(drift) > 0.04) {
      v.playbackRate = this.rate * (drift > 0 ? 0.9 : 1.1);
    } else {
      v.playbackRate = this.rate;
    }
    this.watchdog(v, now);
  },

  // A playing video whose time hasn't moved for 2.5 s is stuck (decoder hiccup): reload it.
  watchdog(v, now) {
    const s = v.sync;
    if (!this.playing || v.paused || v.ended || v.seeking) { s.stuckSince = 0; s.lastTime = v.currentTime; return; }
    if (v.currentTime !== s.lastTime) { s.lastTime = v.currentTime; s.stuckSince = 0; return; }
    if (!s.stuckSince) s.stuckSince = now;
    else if (now - s.stuckSince > 2500) this.recover(v);
  },

  // Keep the other cameras on the master's time and update the clock / overlay.
  tick() {
    // Schedule first, so an error in one frame can't stop the clock for good.
    requestAnimationFrame(() => this.tick());
    const master = this.master();
    const m = this.minutes[this.index];
    if (master && m) {
      const t = master.currentTime;
      const now = performance.now();
      for (const v of this.videos()) {
        if (v === master) this.watchdog(v, now);
        else this.syncVideo(v, master, t, now);
      }
      const seek = $('#seek');
      if (master.duration) seek.max = master.duration;
      if (!this.seeking) seek.value = t;
      $('#clock').textContent = new Date((m.t + t) * 1000).toLocaleDateString(locale()) + ' ' + fmtTime(m.t + t);
      this.drawTelemetry(t);
    }
  },

  async loadTelemetry(m) {
    const clip = m.clips.front || Object.values(m.clips)[0];
    this.telemetry = null;
    this.telemetryFile = clip && clip.file;
    if (!clip || !$('#tm-toggle').checked) return;
    try {
      const data = await api('/api/telemetry?file=' + encodeURIComponent(clip.file));
      if (this.telemetryFile === clip.file) this.telemetry = data;
    } catch (e) { /* no telemetry for this clip */ }
  },

  drawTelemetry(t) {
    const box = $('#telemetry');
    const d = this.telemetry;
    const on = $('#tm-toggle').checked && d && d.t.length;
    box.classList.toggle('hidden', !on);
    if (!on) return;
    // Last frame at or before t.
    let lo = 0, hi = d.t.length - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (d.t[mid] <= t) lo = mid; else hi = mid - 1; }
    const v = (k) => d[k] ? d[k][lo] : null;
    if (v('speed') == null) { box.classList.add('hidden'); return; }
    $('#tm-speed').textContent = Math.round(v('speed') * 3.6);
    $('#tm-gear').textContent = GEARS[v('gear')] || '?';
    $('#tm-bl').classList.toggle('on', !!v('blinker_left'));
    $('#tm-br').classList.toggle('on', !!v('blinker_right'));
    $('#tm-wheel').style.transform = `rotate(${v('steering')}deg)`;
    $('#tm-steer').textContent = Math.round(v('steering')) + '°';
    $('#tm-acc').style.width = Math.max(0, Math.min(100, v('accelerator'))) + '%';
    $('#tm-brake').classList.toggle('on', !!v('brake'));
    $('#tm-ap').textContent = AUTOPILOT[v('autopilot')] || '';
    const lat = v('lat'), lon = v('lon');
    $('#tm-gps').textContent = lat ? `${lat.toFixed(5)}, ${lon.toFixed(5)} · ${Math.round(v('heading'))}°` : '';
  },
};

$('#play-btn').addEventListener('click', () => viewer.playing ? viewer.pause() : viewer.play());
$('#next-btn').addEventListener('click', () => viewer.next());
$('#prev-btn').addEventListener('click', () => viewer.prev());
$('#seek').addEventListener('input', (e) => { viewer.seeking = true; viewer.seek(+e.target.value); });
$('#seek').addEventListener('change', () => { viewer.seeking = false; });
$('#speed').addEventListener('change', (e) => { viewer.rate = +e.target.value; viewer.videos().forEach((v) => { v.playbackRate = viewer.rate; }); });
$('#layout-btn').addEventListener('click', () => viewer.setFocus(viewer.focus ? null : 'front'));
$('#tm-toggle').addEventListener('change', () => { const m = viewer.minutes[viewer.index]; if (m) viewer.loadTelemetry(m); });
$('#save-btn').addEventListener('click', async () => {
  const idx = viewer.marked.size ? [...viewer.marked].sort((a, b) => a - b) : [viewer.index];
  const files = idx.flatMap((i) => Object.values(viewer.minutes[i] ? viewer.minutes[i].clips : {}).map((c) => c.file));
  if (!files.length) return;
  const r = await api('/api/pick-folder', {});
  if (!r.path) return;
  await startJob('save', '/api/save', { files, dest: r.path });
  toast(t("Zapisuję {0} · zaznaczone minuty: {1}…", [clipCount(files.length), idx.length]));
});
app.jobHandlers['save:done'] = (job) => toast(job.status === 'done' ? t("Zapisano {0} w {1}", [clipCount(job.result.saved), job.result.dest]) : (job.error || t("Nie udało się zapisać nagrań.")));

document.addEventListener('keydown', (e) => {
  if (e.target.matches('.session, .minute') && ['Enter', 'Space'].includes(e.code)) {
    e.preventDefault(); e.target.dispatchEvent(new MouseEvent('click', { bubbles: true, shiftKey: e.shiftKey, metaKey: e.metaKey, ctrlKey: e.ctrlKey })); return;
  }
  if (app.step !== 'viewer' || e.target.matches('input, select, textarea')) return;
  if (e.code === 'Space') { e.preventDefault(); viewer.playing ? viewer.pause() : viewer.play(); }
  if (e.code === 'ArrowRight' && viewer.master()) viewer.seek(viewer.master().currentTime + 5);
  if (e.code === 'ArrowLeft' && viewer.master()) viewer.seek(Math.max(0, viewer.master().currentTime - 5));
  if (e.code === 'PageDown' || e.code === 'ArrowDown') { e.preventDefault(); viewer.next(); }
  if (e.code === 'PageUp' || e.code === 'ArrowUp') { e.preventDefault(); viewer.prev(); }
  const n = parseInt(e.key, 10);
  if (n >= 1 && n <= 6) viewer.setFocus(CAMERAS[n - 1]);
  if (e.key === '0' || e.key === 'Escape') viewer.setFocus(null);
});

requestAnimationFrame(() => viewer.tick());

// ---------- start ----------

(async () => {
  await window.i18nReady;
  await poll();
  const st = app.state || {};
  window.LANG = st.language || 'pl';
  updateLanguageLabels();
  applyStaticLanguage();
  if (st.scanned) app.clips = await api('/api/clips');
  const step = location.hash.slice(1);
  if (step && document.getElementById('screen-' + step)) show(step);
  else show(st.library ? 'viewer' : 'drive');
})();

window.addEventListener('hashchange', () => {
  const step = location.hash.slice(1);
  if (step !== app.step && document.getElementById('screen-' + step)) show(step);
});

// Catch async action failures once so a failed picker or cancelled permission never leaves a silent UI.
window.addEventListener('unhandledrejection', event => { event.preventDefault(); toast(event.reason?.message || t("Nie udało się ukończyć operacji."), 8000); });

function updateLanguageLabels() {
  const keys = { front: 'Przód', back: 'Tył', left_repeater: 'Lewy bok', right_repeater: 'Prawy bok', left_pillar: 'Lewy słupek', right_pillar: 'Prawy słupek', side: 'Bok (kamera nieustalona)' };
  for (const [camera, key] of Object.entries(keys)) CAMERA_LABELS[camera] = t(key);
  AUTOPILOT[3] = t('Tempomat');
}
document.querySelectorAll('[data-language]').forEach(button => button.addEventListener('click', async event => {
  if (event.currentTarget.dataset.language === window.LANG) return;
  document.querySelectorAll('[data-language]').forEach(button => { button.disabled = true; });
  try {
    const result = await api('/api/language', { language: event.currentTarget.dataset.language });
    window.LANG = result.language;
    updateLanguageLabels(); applyStaticLanguage();
    await poll();
    if (app.state.scanned) app.clips = await api('/api/clips');
    app.driveCardsKey = null;
    if (app.step === 'drive') await refreshDrives();
    if (app.step === 'select') renderSelect();
    renderCopy();
    if (viewer.loaded) await viewer.refreshLanguage();
    $('#timeline-hint').textContent = t('Przesuń kursor, aby zobaczyć czas. Przeciągnij, aby zaznaczyć zakres.');
  } catch (error) {
    toast(error.message, 8000);
  } finally {
    document.querySelectorAll('[data-language]').forEach(button => { button.disabled = false; });
  }
}));
