const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl = u => /^https?:\/\//i.test(u || '') ? esc(u) : '';
const when = iso => iso ? new Date(iso).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}) : '—';
const badge = (s, label) => `<span class="badge ${esc(s)}">${esc(label || String(s).replace(/_/g, ' '))}</span>`;

let state = { accounts: [], editing: null, credFor: null, post: null };

const ICONS = {
  success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m8 12.5 3 3 5-6"/></svg>',
  error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M12 11v5"/></svg>',
};

// toast(message, type) - type is 'info' (default), 'success' or 'error'. Several can be on screen at once,
// each dismisses itself after a few seconds (longer for errors) or on click.
function toast(msg, type = 'info') {
  const stack = $('toastStack');
  if (!stack) return; // page has no toast container
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.innerHTML = `${ICONS[type] || ICONS.info}<span>${esc(msg)}</span>`;
  const remove = () => { el.classList.add('out'); setTimeout(() => el.remove(), 200); };
  el.onclick = remove;
  stack.appendChild(el);
  setTimeout(remove, type === 'error' ? 6000 : 3500);
}

async function api(path, method = 'GET', body) {
  const r = await fetch('/api' + path, { method, headers: body ? {'Content-Type': 'application/json'} : {},
                                         body: body ? JSON.stringify(body) : undefined });
  if (r.status === 401 && path !== '/login') { showLogin(); throw new Error('Login required'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`);
  return data;
}

function showLogin() { $('app').classList.add('hidden'); $('login').classList.remove('hidden'); }
function showApp() { $('login').classList.add('hidden'); $('app').classList.remove('hidden'); }

function renderHeader(data) {
  const m = data.master;
  $('masterBadge').className = 'badge ' + (m.online ? 'online' : 'offline');
  $('masterBadge').textContent = m.online ? '● Master agent online' : '● Master agent offline';
  const sum = k => data.accounts.reduce((n, a) => n + (a.counts[k] || 0), 0);
  $('pendingCount').textContent = sum('draft');
  $('pendingCount').classList.toggle('hidden', !sum('draft'));
}

// Every page calls this once on load: it checks the session, reveals #app (or #login on 401),
// and keeps the header (master status, pending count) current. `onReady(data)` runs after the
// first successful load, for the page's own content - do page setup there, not before boot().
async function boot(onReady) {
  let data;
  try { data = await api('/overview'); }
  catch (e) { return; } // api() already called showLogin() on 401; any other error leaves the page blank rather than guessing
  state.accounts = data.accounts;
  showApp();
  renderHeader(data);
  if (onReady) {
    try { await onReady(data); } catch (e) { toast(e.message || 'Could not load this page', 'error'); }
  }
  setInterval(() => api('/overview').then(d => { state.accounts = d.accounts; renderHeader(d); }).catch(() => {}), 10000);
}

$('loginForm').onsubmit = async e => {
  e.preventDefault(); $('loginErr').textContent = '';
  try { await api('/login', 'POST', { password: $('password').value }); $('password').value = ''; location.reload(); }
  catch (err) { $('loginErr').textContent = err.message; }
};
$('logout').onclick = async () => { await api('/logout', 'POST'); showLogin(); };

document.querySelectorAll('[data-close]').forEach(b => b.onclick = () => b.closest('dialog').close());

// ---- shared AI model picker: a <select> + a paired "type it manually" <input>, used in Settings for the
// global model and in the account dialog for a per-account override. ----

async function loadModelOptions(selectId, customId, savedValue, { blankOption, provider, baseUrl, force } = {}) {
  const sel = $(selectId), custom = customId ? $(customId) : null;
  sel.innerHTML = '<option value="">Loading models…</option>';
  sel.disabled = true;
  try {
    const q = new URLSearchParams();
    if (provider !== undefined) q.set('provider', provider);
    if (baseUrl !== undefined) q.set('base_url', baseUrl);
    if (force) q.set('force', '1');
    const r = await api('/settings/models' + (q.toString() ? '?' + q.toString() : ''));
    sel.innerHTML = '';
    if (blankOption) {
      const b = document.createElement('option');
      b.value = ''; b.textContent = blankOption;
      sel.appendChild(b);
    }
    for (const m of r.models) {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.id + (m.billing ? ' — ' + m.billing : '') + (m.disabled ? ' (unavailable - last call failed)' : '');
      opt.disabled = !!m.disabled;
      sel.appendChild(opt);
    }
    const other = document.createElement('option');
    other.value = '__custom__';
    other.textContent = 'Other (type model id manually)…';
    sel.appendChild(other);

    if (savedValue && [...sel.options].some(o => o.value === savedValue)) {
      sel.value = savedValue;
      if (custom) custom.classList.add('hidden');
    } else if (savedValue) {
      sel.value = '__custom__';
      if (custom) { custom.value = savedValue; custom.classList.remove('hidden'); }
    } else if (blankOption) {
      sel.value = '';
    } else if (r.models.length) {
      sel.value = r.models[0].id;
    }
    return r;
  } catch (err) {
    sel.innerHTML = '<option value="">Could not load models</option>';
    return { models: [], error: err.message };
  } finally {
    sel.disabled = false;
  }
}

function modelSelectValue(selectId, customId) {
  const sel = $(selectId);
  return sel.value === '__custom__' ? $(customId).value.trim() : sel.value;
}

function wireModelCustomToggle(selectId, customId) {
  $(selectId).onchange = () => {
    const custom = $(selectId).value === '__custom__';
    $(customId).classList.toggle('hidden', !custom);
    if (custom) $(customId).focus();
  };
}

// Mobile menu toggle
const menuToggle = document.querySelector('.menu-toggle');
const sidebar = document.querySelector('aside');
if (menuToggle && sidebar) {
  menuToggle.onclick = () => sidebar.classList.toggle('open');
  // Close sidebar when clicking outside on mobile
  document.addEventListener('click', (e) => {
    if (window.innerWidth <= 768 && sidebar.classList.contains('open') && !sidebar.contains(e.target) && !menuToggle.contains(e.target)) {
      sidebar.classList.remove('open');
    }
  });
}

// Sidebar collapse toggle
const sidebarToggle = document.querySelector('.sidebar-toggle');
if (sidebarToggle && sidebar) {
  sidebarToggle.onclick = () => {
    sidebar.classList.toggle('collapsed');
    sidebarToggle.textContent = sidebar.classList.contains('collapsed') ? '▶' : '◀';
  };
}

