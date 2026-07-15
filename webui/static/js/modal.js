// Modal — plugin detail + config editor
import { api } from './api.js';
import { toast } from './app.js';
import { loadPlugins } from './dashboard.js';

export function closeDetail() {
  document.getElementById('detailModal').classList.remove('open');
}

export async function showDetail(name) {
  const titleEl = document.getElementById('modalTitle');
  const bodyEl = document.getElementById('modalBody');
  titleEl.textContent = name;
  bodyEl.innerHTML = '<div class="spinner" style="margin:40px auto"></div>';
  document.getElementById('detailModal').classList.add('open');
  try {
    const info = await api(`/api/plugins/${name}`);
    const manifest = info.manifest || {};
    bodyEl.innerHTML = `
      <table>
        <tr><td>名称</td><td>${esc(info.display_name || info.name)}</td></tr>
        <tr><td>标识</td><td>${esc(info.name)}</td></tr>
        <tr><td>版本</td><td>${esc(manifest.version || '-')}</td></tr>
        <tr><td>状态</td><td>${info.enabled ? '已启用' : '已禁用'}</td></tr>
        <tr><td>已初始化</td><td>${info.initialized ? '是' : '否'}</td></tr>
        <tr><td>能力</td><td>${(info.capabilities || []).join(', ') || '-'}</td></tr>
        <tr><td>应用路径</td><td style="font-family:var(--font);font-size:12px;word-break:break-all">${esc(manifest.app_path || '-')}</td></tr>
      </table>
      <hr style="border-color:var(--border);margin:16px 0">
      <pre>${esc(JSON.stringify(info, null, 2))}</pre>`;
  } catch (e) {
    bodyEl.innerHTML = `<p style="color:var(--red)">加载失败: ${e.message}</p>`;
  }
}

export async function showConfigEditor(name) {
  const titleEl = document.getElementById('modalTitle');
  const bodyEl = document.getElementById('modalBody');
  titleEl.textContent = `配置: ${name}`;
  bodyEl.innerHTML = '<div class="spinner" style="margin:40px auto"></div>';
  document.getElementById('detailModal').classList.add('open');
  try {
    const data = await api(`/api/plugins/${name}/config`);
    const json = JSON.stringify(data, null, 2);
    bodyEl.innerHTML = `
      <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px">
        编辑 <code>manifest.json</code> — 修改后点击保存，页面将自动刷新。
      </p>
      <textarea id="configEditor"
        style="width:100%;min-height:360px;background:#0a0c12;border:1px solid var(--border);
               border-radius:var(--radius);color:var(--text);font-family:var(--font);
               font-size:12px;padding:12px;resize:vertical;white-space:pre;tab-size:2"
        spellcheck="false">${esc(json)}</textarea>
      <div style="display:flex;gap:8px;margin-top:12px">
        <button id="saveConfigBtn"
          style="background:var(--primary);border:none;color:#fff;padding:8px 20px;
                 border-radius:var(--radius);cursor:pointer;font-size:14px">保存</button>
        <button id="cancelConfigBtn"
          style="background:var(--surface2);border:none;color:var(--text);padding:8px 20px;
                 border-radius:var(--radius);cursor:pointer;font-size:14px">取消</button>
      </div>`;
    document.getElementById('saveConfigBtn').addEventListener('click', () => saveConfig(name));
    document.getElementById('cancelConfigBtn').addEventListener('click', closeDetail);
  } catch (e) {
    bodyEl.innerHTML = `<p style="color:var(--red)">加载配置失败: ${e.message}</p>`;
  }
}

async function saveConfig(name) {
  const btn = document.getElementById('saveConfigBtn');
  btn.disabled = true;
  btn.textContent = '保存中...';
  try {
    const raw = document.getElementById('configEditor').value;
    JSON.parse(raw); // validate
    await api(`/api/plugins/${name}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: raw,
    });
    toast('配置已保存');
    closeDetail();
    await loadPlugins();
  } catch (e) {
    toast(`保存失败: ${e.message}`, 'err');
    btn.disabled = false;
    btn.textContent = '保存';
  }
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
