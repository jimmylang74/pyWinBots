// App - state, routing, event delegation, init
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
    else if (action === 'location') openLocationModal(plugin);
    return;
  }
  if (e.target.closest('#locationModalClose') || (e.target.closest('.modal-overlay') === e.target && e.target.id === 'locationModal')) {
    closeLocationModal();
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

let _locWs = null;
let _locPlugin = '';

function openLocationModal(pluginName) {
  _locPlugin = pluginName;
  const modal = document.getElementById('locationModal');
  document.getElementById('locPluginName').value = pluginName;
  document.getElementById('locName').value = '';
  document.getElementById('locX').value = '';
  document.getElementById('locY').value = '';
  document.getElementById('locStatus').textContent = '';
  document.getElementById('btnStartLoc').disabled = false;
  document.getElementById('btnStopLoc').disabled = true;
  
  modal.classList.add('open');
  
  document.getElementById('btnStartLoc').onclick = startLocRecording;
  document.getElementById('btnStopLoc').onclick = stopLocRecording;
}

function closeLocationModal() {
  document.getElementById('locationModal').classList.remove('open');
  if (_locWs) {
    _locWs.close();
    _locWs = null;
  }
}

function startLocRecording() {
  const locName = document.getElementById('locName').value.trim();
  if (!locName) {
    toast('Please enter a location name', 'err');
    return;
  }

  document.getElementById('btnStartLoc').disabled = true;
  document.getElementById('btnStopLoc').disabled = false;
  document.getElementById('locStatus').textContent = 'Connecting...';

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  _locWs = new WebSocket(`${protocol}//${window.location.host}/ws/location_record`);

  _locWs.onopen = () => {
    _locWs.send(JSON.stringify({
      plugin_name: _locPlugin,
      location_name: locName
    }));
  };

  _locWs.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'status') {
      document.getElementById('locStatus').textContent = `Status: ${data.status}`;
    } else if (data.type === 'result') {
      document.getElementById('locX').value = data.x;
      document.getElementById('locY').value = data.y;
      document.getElementById('locStatus').textContent = `Saved! X: ${data.x}, Y: ${data.y}`;
      toast('Location recorded successfully!');
      setTimeout(closeLocationModal, 1000);
    } else if (data.type === 'error') {
      document.getElementById('locStatus').textContent = `Error: ${data.message}`;
      document.getElementById('btnStartLoc').disabled = false;
      document.getElementById('btnStopLoc').disabled = true;
    }
  };

  _locWs.onclose = () => {
    document.getElementById('btnStartLoc').disabled = false;
    document.getElementById('btnStopLoc').disabled = true;
  };
}

function stopLocRecording() {
  if (_locWs) {
    _locWs.close();
    _locWs = null;
    document.getElementById('btnStartLoc').disabled = false;
    document.getElementById('btnStopLoc').disabled = true;
    document.getElementById('locStatus').textContent = 'Recording stopped.';
  }
}

document.addEventListener('keydown', e => { 
  if (e.key === 'Escape') {
    if (document.getElementById('locationModal').classList.contains('open')) {
      closeLocationModal();
    } else {
      closeDetail();
    }
  }
});

// ---- init ----
loadPlugins();
if (document.getElementById('autoRefresh').checked) startLogRefresh();
