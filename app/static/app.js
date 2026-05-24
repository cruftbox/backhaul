/* ── Activity log refresh ──────────────────────────────────────────────── */

async function refreshActivity() {
  try {
    const res = await fetch('/api/activity');
    const entries = await res.json();
    const list = document.getElementById('activity-list');
    if (!list) return;

    if (entries.length === 0) {
      list.innerHTML = '<p class="empty-state">No activity yet.</p>';
      return;
    }

    list.innerHTML = entries.map(e => {
      const time = e.timestamp.slice(0, 16).replace('T', ' ');
      return `<div class="activity-entry log-${e.log_type}">
        <span class="activity-time">${time}</span>
        <span class="activity-msg">${escHtml(e.message)}</span>
      </div>`;
    }).join('');

    const ts = document.getElementById('activity-updated');
    if (ts) ts.textContent = 'updated ' + new Date().toLocaleTimeString();
  } catch (e) {
    console.error('refreshActivity failed:', e);
  }
}

/* ── Toast notifications ────────────────────────────────────────────────── */

function showToast(msg, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.style.cssText = [
      'position:fixed', 'bottom:1.5rem', 'right:1.5rem',
      'display:flex', 'flex-direction:column', 'gap:0.5rem', 'z-index:9999'
    ].join(';');
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  const colors = { info: '#4f9cf9', error: '#ef4444', success: '#22c55e' };
  toast.style.cssText = [
    `background:${colors[type] || colors.info}`,
    'color:white', 'padding:0.6rem 1rem', 'border-radius:6px',
    'font-size:0.85rem', 'max-width:320px', 'box-shadow:0 4px 12px rgba(0,0,0,0.4)',
    'transition:opacity 0.3s'
  ].join(';');
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

/* ── Test notification ──────────────────────────────────────────────────── */

async function testNotification(btn) {
  const orig = btn.textContent;
  btn.textContent = 'Sending…';
  btn.disabled = true;
  try {
    const res = await fetch('/api/test-notification', { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      showToast('Test SMS sent — check your phone', 'success');
    } else {
      showToast('Failed: ' + (data.error || 'unknown error'), 'error');
    }
  } catch (e) {
    showToast('Failed to send test', 'error');
  } finally {
    btn.textContent = orig;
    btn.disabled = false;
  }
}

/* ── Helpers ────────────────────────────────────────────────────────────── */

function escHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
