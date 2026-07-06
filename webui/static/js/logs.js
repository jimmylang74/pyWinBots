// Logs — load, render, auto-refresh
import { api } from './api.js';

let _timer = null;

export function stopLogRefresh() {
  if (_timer) { clearInterval(_timer); _timer = null; }
}

export function startLogRefresh() {
  stopLogRefresh();
  if (document.getElementById('autoRefresh').checked) {
    _timer = setInterval(loadLogs, 3000);
  }
}

export async function loadLogs() {
  try {
    const data = await api('/api/logs?lines=200');
    const lines = data.logs || [];
    const box = document.getElementById('logBox');
    if (lines.length === 0) {
      box.innerHTML = '<div class="empty">暂无日志</div>';
      return;
    }
    box.innerHTML = lines
      .map(line => {
        const clean = line.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        let badge = '';
        if (/\[ERROR\]/i.test(line)) badge = '<span class="log-badge ERROR">ERROR</span>';
        else if (/\[WARNING\]/i.test(line)) badge = '<span class="log-badge WARNING">WARN</span>';
        else if (/\[INFO\]/i.test(line)) badge = '<span class="log-badge INFO">INFO</span>';
        else if (/\[DEBUG\]/i.test(line)) badge = '<span class="log-badge DEBUG">DEBUG</span>';
        return `<div class="line">${badge} ${clean}</div>`;
      })
      .join('');
    box.scrollTop = box.scrollHeight;
  } catch (e) {
    document.getElementById('logBox').innerHTML =
      `<div class="empty">加载日志失败: ${e.message}</div>`;
  }
}
