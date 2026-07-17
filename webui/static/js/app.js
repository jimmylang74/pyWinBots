// App - state, routing, event delegation, init
import { loadPlugins, setSearchQuery, togglePlugin } from './dashboard.js';
import { loadLogs, startLogRefresh, stopLogRefresh } from './logs.js';
import { showDetail, showConfigEditor, closeDetail } from './modal.js';
import { api } from './api.js';

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
  if (e.target.closest('#btnCloseLoc')) {
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

  if (e.target.id === 'locNameSelect') {
    const newInput = document.getElementById('locNameNew');
    if (e.target.value === '__new__') {
      newInput.style.display = 'block';
      newInput.focus();
    } else {
      newInput.style.display = 'none';
      newInput.value = '';
    }
  }
});

document.getElementById('searchInput').addEventListener('input', e => {
  setSearchQuery(e.target.value);
});

document.querySelectorAll('.nav button').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.page));
});

// ---- Location Record ----
let _locPlugin = '';

async function openLocationModal(pluginName) {
  _locPlugin = pluginName;
  const modal = document.getElementById('locationModal');
  document.getElementById('locPluginName').value = pluginName;
  document.getElementById('locX').value = '';
  document.getElementById('locY').value = '';
  document.getElementById('locWindow').value = '';
  document.getElementById('locStatus').textContent = '';
  document.getElementById('locNameNew').value = '';
  document.getElementById('locNameNew').style.display = 'none';

  const btnStart = document.getElementById('btnStartLoc');
  const btnClose = document.getElementById('btnCloseLoc');
  btnStart.style.display = '';
  btnStart.disabled = false;
  btnStart.textContent = 'Start Record';
  btnClose.style.display = 'none';

  const select = document.getElementById('locNameSelect');
  select.innerHTML = '<option value="" disabled selected>加载中...</option>';

  modal.classList.add('open');

  try {
    const data = await api(`/api/plugins/${pluginName}/locations`);
    const locations = data.locations || {};
    const names = Object.keys(locations);

    select.innerHTML = '';
    if (names.length > 0) {
      names.forEach(n => {
        const opt = document.createElement('option');
        opt.value = n;
        opt.textContent = `${n}  [${locations[n][0]}, ${locations[n][1]}]`;
        select.appendChild(opt);
      });
    }
    const newOpt = document.createElement('option');
    newOpt.value = '__new__';
    newOpt.textContent = '+ 新建...';
    select.appendChild(newOpt);

    if (names.length > 0) {
      select.value = names[0];
    } else {
      select.value = '__new__';
      document.getElementById('locNameNew').style.display = 'block';
      document.getElementById('locNameNew').focus();
    }
  } catch (e) {
    select.innerHTML = '<option value="__new__" selected>+ 新建...</option>';
    document.getElementById('locNameNew').style.display = 'block';
  }
}

function closeLocationModal() {
  document.getElementById('locationModal').classList.remove('open');
}

function _getSelectedName() {
  const select = document.getElementById('locNameSelect');
  if (select.value === '__new__') {
    return document.getElementById('locNameNew').value.trim();
  }
  return select.value;
}

async function startLocRecording() {
  const locName = _getSelectedName();
  if (!locName) {
    toast('请输入或选择一个 Location 名称', 'err');
    return;
  }

  const btnStart = document.getElementById('btnStartLoc');
  const btnClose = document.getElementById('btnCloseLoc');
  btnStart.disabled = true;
  btnStart.textContent = 'Recording...';
  document.getElementById('locStatus').textContent = '等待鼠标点击...';

  try {
    const data = await api(`/api/plugins/${_locPlugin}/record`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ location_name: locName }),
    });

    document.getElementById('locX').value = data.x;
    document.getElementById('locY').value = data.y;
    document.getElementById('locWindow').value =
      data.title ? `${data.title}  (0x${data.handle})` : '';
    document.getElementById('locStatus').textContent =
      `已记录: (${data.x}, ${data.y})`;

    btnStart.style.display = 'none';
    btnClose.style.display = '';
    btnClose.focus();
    toast(`Location "${locName}" 已保存`);
  } catch (e) {
    document.getElementById('locStatus').textContent = `错误: ${e.message}`;
    btnStart.disabled = false;
    btnStart.textContent = 'Start Record';
    toast('录制失败', 'err');
  }
}

document.getElementById('btnStartLoc').onclick = startLocRecording;

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
