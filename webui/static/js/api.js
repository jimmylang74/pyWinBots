// API helper — thin wrapper around fetch + JSON
export async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText}${body ? ': ' + body.slice(0, 120) : ''}`);
  }
  return res.json();
}
