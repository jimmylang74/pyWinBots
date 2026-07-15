// Dashboard — stats, plugin grid, search, toggle
import { api } from './api.js';
import { showDetail, showConfigEditor } from './modal.js';
import { toast } from './app.js';

let _plugins = [];
let _searchQuery = '';

export function getPlugins() { return _plugins; }
export function setPlugins(p) { _plugins = p; }

export function renderStats() {
  const total = _plugins.length;
  const enabled = _plugins.filter(p => p.enabled).length;
  const caps = _plugins.reduce((s, p) => s + (p.capabilities || []).length, 0);
  document.getElementById('statsRow').innerHTML = `
    <div class="stat-card"><div class="value">${total}</div><div class="label">插件总数</div></div>
    <div class="stat-card"><div class="value">${enabled}</div><div class="label">已启用</div></div>
    <div class="stat-card"><div class="value">${caps}</div><div class="label">总能力数</div></div>`;
}

export function renderPlugins() {
  const q = _searchQuery.toLowerCase();
  const filtered = q
    ? _plugins.filter(p =>
        p.name.toLowerCase().includes(q) ||
        (p.display_name || '').toLowerCase().includes(q) ||
        (p.capabilities || []).some(c => c.toLowerCase().includes(q))
      )
    : _plugins;

  const grid = document.getElementById('pluginGrid');
  if (filtered.length === 0) {
    grid.innerHTML = `<p style="color:var(--text-dim);text-align:center;padding:60px 0;">${
      q ? '无匹配插件' : '未加载任何插件。请在 apptools/ 下放置插件。'
    }</p>`;
    return;
  }

  grid.innerHTML = filtered
    .map(p => {
      const dotCls = p.enabled ? 'on' : 'off';
      const statusText = p.enabled ? 'Online' : 'Offline';
      const capsHtml = (p.capabilities || [])
        .map(c => `<span>${escapeHtml(c)}</span>`)
        .join('');
      return `<div class="plugin-card" data-name="${p.name}">
        <div class="info">
          <div class="name">
            ${escapeHtml(p.display_name || p.name)}
            <span class="dot ${dotCls}"></span>
          </div>
          <div class="desc">${escapeHtml(p.name)} ${p.enabled ? '' : '(已禁用)'}</div>
          <div class="caps">${capsHtml}</div>
          <div class="toggle-wrap">
            <label class="toggle">
              <input type="checkbox" ${p.enabled ? 'checked' : ''} data-plugin="${p.name}">
              <span class="slider"></span>
            </label>
            <span class="toggle-label" id="togLabel-${p.name}">${p.enabled ? '已启用' : '已禁用'}</span>
            <button class="detail-btn" data-action="detail" data-plugin="${p.name}">Detail</button>
            <button class="detail-btn config-btn" data-action="config" data-plugin="${p.name}">⚙ Config</button>
            <button class="detail-btn location-btn" data-action="location" data-plugin="${p.name}">Location Record</button>
          </div>
        </div>
        <div class="status"><span class="dot ${dotCls}"></span> ${statusText}</div>
      </div>`;
    })
    .join('');
}

export function setSearchQuery(q) {
  _searchQuery = q;
  renderPlugins();
}

export async function togglePlugin(name, enabled) {
  const form = new FormData();
  form.append('enabled', String(enabled));
  try {
    await api(`/api/plugins/${name}/toggle`, { method: 'POST', body: form });
    toast(enabled ? `${name} 已启用` : `${name} 已禁用`);
    await loadPlugins();
  } catch (e) {
    toast(`操作失败: ${e.message}`, 'err');
  }
}

export async function loadPlugins() {
  try {
    const data = await api('/api/plugins');
    _plugins = data.plugins || [];
    renderStats();
    renderPlugins();
  } catch (e) {
    document.getElementById('pluginGrid').innerHTML =
      `<p style="color:var(--red);text-align:center;padding:60px 0;">加载失败: ${e.message}</p>`;
  }
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
