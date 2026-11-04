/**
 * API client for the RAG backend.
 * Base path: /api/v1 (served on the same origin by the backend; CORS allows
 * http://localhost:7000 where this SPA is served).
 */

// Backend runs on port 8000; frontend is served on port 7000.
// CORS allows http://localhost:7000 / http://127.0.0.1:7000.
const API_BASE = 'http://localhost:8000/api/v1';

let authToken = null;

// Load any persisted token on startup.
try {
  authToken = localStorage.getItem('rag_token') || null;
} catch (e) {
  authToken = null;
}

export function setToken(token) {
  authToken = token;
  try {
    if (token) localStorage.setItem('rag_token', token);
    else localStorage.removeItem('rag_token');
  } catch (e) {
    // localStorage unavailable; ignore.
  }
}

export function getToken() {
  return authToken;
}

export function clearToken() {
  authToken = null;
  try { localStorage.removeItem('rag_token'); } catch (e) {}
}

async function request(path, { method = 'GET', body, headers = {}, auth = true, formData = false } = {}) {
  const h = { ...headers };
  // Only set a default Content-Type if the caller did not specify one.
  if (!formData && body && !h['Content-Type']) {
    if (typeof body === 'string') {
      h['Content-Type'] = 'application/json';
    } else if (!(body instanceof FormData)) {
      h['Content-Type'] = 'application/json';
      body = JSON.stringify(body);
    }
  }
  if (auth && authToken) {
    h['Authorization'] = `Bearer ${authToken}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: h,
    ...(body ? { body } : {}),
  });

  // 204 No Content -> nothing to parse.
  if (res.status === 204) return { ok: true, status: res.status, data: null };

  const contentType = res.headers.get('content-type') || '';
  let data;
  if (contentType.includes('application/json')) {
    data = await res.json();
  } else {
    data = await res.text();
  }

  if (!res.ok) {
    const err = new Error(data && data.detail ? data.detail : `Request failed (${res.status})`);
    err.status = res.status;
    err.data = data;
    throw err;
  }

  return { ok: true, status: res.status, data };
}

/* ---------- Auth ---------- */
export async function login(username, password) {
  const body = `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`;
  const { data } = await request('/auth/login', {
    method: 'POST',
    body,
    auth: false,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return data; // Token { access_token, token_type }
}

export async function register({ username, name, password, password_repeat }) {
  const { data } = await request('/auth/register', { method: 'POST', body: JSON.stringify({ username, name, password, password_repeat }), auth: false });
  return data;
}

export async function me() {
  const { data } = await request('/auth/me');
  return data; // CurrentUserInfoResponse { username, name, created_at }
}

/* ---------- Projects ---------- */
export async function listProjects() {
  const { data } = await request('/projects');
  return data; // ProjectResponse[]
}

export async function getProject(id) {
  const { data } = await request(`/projects/${id}`);
  return data;
}

export async function createProject({ name, description }) {
  const { data } = await request('/projects', { method: 'POST', body: JSON.stringify({ name, description }) });
  return data;
}

export async function updateProject(id, { name, description }) {
  const body = {};
  if (name !== undefined) body.name = name;
  if (description !== undefined) body.description = description;
  const { data } = await request(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
  return data;
}

export async function deleteProject(id) {
  await request(`/projects/${id}`, { method: 'DELETE' });
}

/* ---------- Documents ---------- */
export async function uploadDocument(projectId, file) {
  const form = new FormData();
  form.append('pdf_document', file);
  const { data } = await request(`/projects/${projectId}/documents`, { method: 'POST', body: form, formData: true });
  return data; // DocumentResponse { document_id, status }
}

export async function listDocuments(projectId) {
  const { data } = await request(`/projects/${projectId}/documents`);
  return data; // DocumentResponse[] { document_id, filename, status }
}

export async function deleteDocument(projectId, documentId) {
  await request(`/projects/${projectId}/documents/${documentId}`, { method: 'DELETE' });
}

/* ---------- Chat ---------- */
export async function createChatSession(projectId) {
  const { data } = await request('/chat/creating', { method: 'POST', body: JSON.stringify({ project_id: projectId }) });
  return data; // { chat_session_id: UUID }
}

export async function getChatHistory(chatId) {
  const { data } = await request(`/chat/${encodeURIComponent(chatId)}`);
  return data; // [{ role, content }]
}

/**
 * Stream chat response via Server-Sent Events.
 * Yields { type, content } events from the backend.
 */
export async function* sendMessageStream(chatId, message) {
  const res = await fetch(`${API_BASE}/chat/${encodeURIComponent(chatId)}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(authToken ? { 'Authorization': `Bearer ${authToken}` } : {}),
    },
    body: JSON.stringify({ message }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Stream failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || ''; // keep incomplete last line

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data: ')) continue;

        try {
          const event = JSON.parse(trimmed.slice(6));
          yield event;
        } catch (e) {
          // skip malformed SSE data lines
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
