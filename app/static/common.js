const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl = u => /^https?:\/\//i.test(u || '') ? esc(u) : '';
const when = iso => iso ? new Date(iso).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}) : '—';
const badge = (s, label) => `<span class="badge ${esc(s)}">${esc(label || String(s).replace(/_/g, ' '))}</span>`;

let state = { accounts: [], editing: null, credFor: null, post: null };

function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.style.display = 'block';
  clearTimeout(toast.timer); toast.timer = setTimeout(() => t.style.display = 'none', 3500);
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
    try { await onReady(data); } catch (e) { toast(e.message || 'Could not load this page'); }
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

