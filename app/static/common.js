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

async function updateHeader() {
  try {
    const data = await api('/overview');
    state.accounts = data.accounts;
    const m = data.master;
    $('masterBadge').className = 'badge ' + (m.online ? 'online' : 'offline');
    $('masterBadge').textContent = m.online ? '● Master agent online' : '● Master agent offline';
    const sum = k => data.accounts.reduce((n, a) => n + (a.counts[k] || 0), 0);
    $('pendingCount').textContent = sum('draft');
    $('pendingCount').classList.toggle('hidden', !sum('draft'));
  } catch (e) {
    // Ignore errors on non-dashboard pages
  }
}

$('loginForm').onsubmit = async e => {
  e.preventDefault(); $('loginErr').textContent = '';
  try { await api('/login', 'POST', { password: $('password').value }); $('password').value = ''; showApp(); updateHeader(); }
  catch (err) { $('loginErr').textContent = err.message; }
};
$('logout').onclick = async () => { await api('/logout', 'POST'); showLogin(); };

document.querySelectorAll('[data-close]').forEach(b => b.onclick = () => b.closest('dialog').close());

// Update header info on all pages
document.addEventListener('DOMContentLoaded', function() {
  if (!$('app').classList.contains('hidden')) {
    updateHeader();
    setInterval(updateHeader, 10000);
  }
});

