// App — state, routing, event delegation, init
import { loadPlugins, setSearchQuery, togglePlugin } from './dashboard.js';
import { loadLogs, startLogRefresh, stopLogRefresh } from './logs.js';
import { showDetail, showConfigEditor, closeDetail } from './modal.js';

// ---- toast (shared) ----
let _toastTimer = null;
export function toast(msg, type = 'ok') {
  let el = document.getElementById('toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast';
    el.className = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = 'toast ' + type + ' show';
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 2500);
}

// ---- routing ----
function switchTab(page) {
  document.querySelectorAll('.page').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav button').forEach(el => el.classList.remove('active'));
  document.getElementById('page' + page.charAt(0).toUpperCase() + page.slice(1)).classList.add('active');
  document.querySelector(`.nav button[data-page="${page}"]`).classList.add('active');

  if (page === 'logs') {
    loadLogs();
    startLogRefresh();
  } else {
    stopLogRefresh();
  }
}

// ---- event delegation ----
document.addEventListener('click', e => {
  const actionBtn = e.target.closest('[data-action]');
  if (actionBtn) {
    const { action, plugin } = actionBtn.dataset;
    if (action === 'detail') showDetail(plugin);
    else if (action === 'config') showConfigEditor(plugin);
    return;
  }
  if (e.target.closest('#modalClose') || e.target.closest('.modal-overlay') === e.target) closeDetail();
});

document.addEventListener('change', e => {
  const cb = e.target.closest('.toggle input[type=checkbox]');
  if (cb && cb.dataset.plugin) {
    togglePlugin(cb.dataset.plugin, cb.checked);
    return;
  }
  if (e.target.id === 'autoRefresh') startLogRefresh();
});

document.getElementById('searchInput').addEventListener('input', e => {
  setSearchQuery(e.target.value);
});

document.querySelectorAll('.nav button').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.page));
});

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail(); });

// ---- init ----
loadPlugins();
if (document.getElementById('autoRefresh').checked) startLogRefresh();
