// api.js
//
// バックエンド(scenario.py / Flask想定)への最小限のHTTPクライアント。
// 外部npmパッケージへの依存を避けるため、Node標準のhttp/httpsだけで実装している
// (拡張機能をvsceでパッケージする際、npm installなしでも動くようにするため)。

const http = require('http');
const https = require('https');
const { URL } = require('url');

function request(method, url, body) {
  return new Promise((resolve, reject) => {
    let u;
    try {
      u = new URL(url);
    } catch (e) {
      reject(new Error(`不正なURLです: ${url}`));
      return;
    }
    const lib = u.protocol === 'https:' ? https : http;
    const payload = body !== undefined ? JSON.stringify(body) : null;
    const headers = { 'Content-Type': 'application/json' };
    if (payload) headers['Content-Length'] = Buffer.byteLength(payload);

    const req = lib.request(
      {
        hostname: u.hostname,
        port: u.port || (u.protocol === 'https:' ? 443 : 80),
        path: `${u.pathname}${u.search}`,
        method,
        headers,
      },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          const text = Buffer.concat(chunks).toString('utf8');
          if (res.statusCode >= 200 && res.statusCode < 300) {
            if (!text) { resolve(null); return; }
            try {
              resolve(JSON.parse(text));
            } catch (e) {
              resolve(text);
            }
          } else {
            reject(new Error(`HTTP ${res.statusCode}: ${text || res.statusMessage} (${method} ${url})`));
          }
        });
      }
    );
    req.on('error', (err) => reject(new Error(`通信に失敗しました: ${err.message} (${method} ${url})`)));
    if (payload) req.write(payload);
    req.end();
  });
}

class ScenarioApi {
  constructor(baseUrl) {
    this.baseUrl = (baseUrl || '').replace(/\/+$/, '');
  }

  url(path) {
    return `${this.baseUrl}${path}`;
  }

  // イベント一覧([{id, subEvents: [{subId, ...}], ...}, ...])
  async listEvents() {
    return request('GET', this.url('/api/scenario-event'));
  }

  // Role一覧([{name, ...}, ...])
  async listRoles() {
    return request('GET', this.url('/api/scenario-role'));
  }

  // 1つのRoleのフォームスキーマ({fields: [...]})
  async getRoleFormSchema(roleName) {
    return request('GET', this.url(`/api/role-form-schema/${encodeURIComponent(roleName)}`));
  }

  // 指定Subのノードツリー({nodes, edges})
  async getSubTransition(eventId, subId) {
    return request('GET', this.url(`/api/scenario-event/${encodeURIComponent(eventId)}/sub/${encodeURIComponent(subId)}/transition`));
  }

  // 指定Subのノードツリーを保存
  async saveSubTransition(eventId, subId, tree) {
    return request('POST', this.url(`/api/scenario-event/${encodeURIComponent(eventId)}/sub/${encodeURIComponent(subId)}/transition`), tree);
  }
}

module.exports = { ScenarioApi };
