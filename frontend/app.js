/**
 * RAG Assistant frontend application.
 * Vanilla JS SPA. Talks to /api/v1. Auth via Bearer token in localStorage.
 */

import {
  setToken, getToken, clearToken,
  login, register, me,
  listProjects, createProject, updateProject, deleteProject,
  uploadDocument, deleteDocument,
  createChatSession, getChatHistory, sendMessageStream,
} from './api.js';

/* ---------- DOM elements ---------- */
const viewAuth = document.getElementById('view-auth');
const viewApp = document.getElementById('view-app');

const authForm = document.getElementById('auth-form');
const authMode = document.getElementById('auth-mode');
const authHeader = document.getElementById('auth-header');
const authSubmit = document.getElementById('auth-submit');
const authToggleText = document.getElementById('auth-toggle-text');
const authToggle = document.getElementById('auth-toggle');
const nameField = document.getElementById('name-field');
const passwordRepeatField = document.getElementById('password-repeat-field');

const logoutBtn = document.getElementById('logout-btn');
const userGreeting = document.getElementById('user-greeting');

/* Dashboard */
const newProjectBtn = document.getElementById('new-project-btn');
const projectsGrid = document.getElementById('projects-grid');
const dashboardEmpty = document.getElementById('dashboard-empty');
const backToProjects = document.getElementById('back-to-projects');
const pageDashboard = document.getElementById('page-dashboard');
const pageProject = document.getElementById('page-project');

/* New project modal */
const modalBackdrop = document.getElementById('modal-backdrop');
const modalNewProject = document.getElementById('modal-new-project');
const newProjectForm = document.getElementById('new-project-form');
const closeNewProject = document.getElementById('close-new-project');
const cancelNewProject = document.getElementById('cancel-new-project');

/* Project detail */
const projectTitle = document.getElementById('project-title');
const projectSubtitle = document.getElementById('project-subtitle');
const tabBtns = document.querySelectorAll('.tab-btn');
const tabDocuments = document.getElementById('tab-documents');
const tabChat = document.getElementById('tab-chat');

/* Documents */
const uploadZone = document.getElementById('upload-zone');
const fileInput = document.getElementById('file-input');
const pickFileBtn = document.getElementById('pick-file-btn');
const uploadProgress = document.getElementById('upload-progress');
const progressFill = document.querySelector('.progress-fill');
const progressText = document.querySelector('.progress-text');
const documentsList = document.getElementById('documents-list');
const documentsEmpty = document.getElementById('documents-empty');
const docCount = document.getElementById('doc-count');

/* Chat */
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatSend = document.getElementById('chat-send');
const chatMessages = document.getElementById('chat-messages');
const chatTyping = document.getElementById('chat-typing');

/* Sidebar */
const sidebar = document.getElementById('sidebar');
const navToggle = document.querySelector('.nav-toggle');
const navClose = document.querySelector('.nav-close');

/* ---------- State ---------- */
let currentProjectId = null;
let currentChatSessionId = null;
let activeTab = 'documents';
let projectDocuments = new Map(); // projectId -> Document[]

/* ---------- Helpers ---------- */
function toast({ message, type = 'info', duration = 4000 } = {}) {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type === 'error' ? 'error' : type === 'success' ? 'success' : ''}`;
  el.innerHTML = `<b>${escapeHtml(message || '')}</b>`;
  container.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transform = 'translateX(120px)';
    setTimeout(() => el.remove(), 250);
  }, duration);
  return el;
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function showView(view) {
  viewAuth.style.display = 'none';
  viewApp.style.display = 'none';
  view.style.display = view === viewApp ? 'flex' : 'block';
  // app-shell needs flex to fill height; auth uses its own layout.
  if (view === viewApp) viewApp.style.display = 'flex';
}

function setLoading(btn, loading, label) {
  if (!btn) return;
  if (loading) {
    btn.disabled = true;
    btn.dataset.original = btn.innerHTML;
    btn.innerHTML = `<span>⏳</span> ${label || 'Working…'}`;
  } else {
    btn.disabled = false;
    btn.innerHTML = btn.dataset.original || label || btn.innerHTML;
  }
}

/* ---------- Auth flow ---------- */
async function initAuth() {
  const token = getToken();
  if (token) {
    try {
      const user = await me();
      userGreeting.textContent = `Hello, ${escapeHtml(user.name || user.username)}`;
      showView(viewApp);
      loadProjects();
    } catch (err) {
      // token invalid or expired
      clearToken();
      showView(viewAuth);
    }
  } else {
    showView(viewAuth);
  }
}

authToggle.addEventListener('click', () => {
  const isLogin = authMode.value === 'login';
  authMode.value = isLogin ? 'register' : 'login';

  const h = authHeader;
  if (isLogin) {
    h.querySelector('h2').textContent = 'Create account';
    h.querySelector('p').textContent = 'Join to start managing your projects';
    nameField.style.display = 'block';
    passwordRepeatField.style.display = 'block';
    authSubmit.textContent = 'Create account';
    authToggleText.textContent = 'Already have an account?';
    authToggle.textContent = 'Sign in';
  } else {
    h.querySelector('h2').textContent = 'Welcome back';
    h.querySelector('p').textContent = 'Sign in to access your projects and documents';
    nameField.style.display = 'none';
    passwordRepeatField.style.display = 'none';
    authSubmit.textContent = 'Sign in';
    authToggleText.textContent = "Don't have an account?";
    authToggle.textContent = 'Create account';
  }
});

authForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const formData = new FormData(authForm);
  const username = formData.get('username').trim();
  const password = formData.get('password');
  const name = formData.get('name');

  setLoading(authSubmit, true, authMode.value === 'login' ? 'Signing in…' : 'Creating account…');

  try {
    if (authMode.value === 'login') {
      const token = await login(username, password);
      if (!token || !token.access_token) {
        throw new Error('Login failed: no access token received');
      }
      setToken(token.access_token);
      const user = await me();
      userGreeting.textContent = `Hello, ${escapeHtml(user.name || user.username)}`;
      toast({ message: 'Signed in successfully', type: 'success' });
      showView(viewApp);
      loadProjects();
    } else {
      await register({
        username,
        name: name.trim(),
        password,
        password_repeat: formData.get('password_repeat'),
      });
      toast({ message: 'Account created. Please sign in.', type: 'success' });
      authToggle.click();
    }
  } catch (err) {
    console.error('Auth error:', err);
    toast({ message: err.message || 'Something went wrong', type: 'error' });
  } finally {
    setLoading(authSubmit, false);
  }
});

logoutBtn.addEventListener('click', () => {
  clearToken();
  currentProjectId = null;
  currentChatSessionId = null;
  activeTab = 'documents';
  projectDocuments.clear();
  chatMessages.innerHTML = '';
  documentsList.innerHTML = '';
  projectsGrid.innerHTML = '';
  showView(viewAuth);
  toast({ message: 'Signed out', type: 'success' });
});

/* ---------- Projects ---------- */
async function loadProjects() {
  try {
    const projects = await listProjects();
    renderProjects(projects);
  } catch (err) {
    toast({ message: 'Failed to load projects', type: 'error' });
  }
}

function renderProjects(projects) {
  projectsGrid.innerHTML = '';
  if (!projects || projects.length === 0) {
    dashboardEmpty.style.display = 'flex';
    return;
  }
  dashboardEmpty.style.display = 'none';

  for (const p of projects) {
    const card = document.createElement('div');
    card.className = 'project-card';
    card.tabIndex = 0;
    card.role = 'button';
    card.ariaLabel = `Open project ${escapeHtml(p.name)}`;
    const created = p.created_at ? new Date(p.created_at).toLocaleDateString() : '';
    card.innerHTML = `
      <div class="card-meta"><span>📁</span><span>${escapeHtml(created)}</span></div>
      <h3>${escapeHtml(p.name)}</h3>
      <p>${escapeHtml(p.description || 'No description')}</p>
      <div class="project-actions">
        <button class="btn btn-sm btn-outline edit-project" data-id="${p.id}">Edit</button>
        <button class="btn btn-sm btn-outline delete-project" data-id="${p.id}">Delete</button>
      </div>
    `;
    card.addEventListener('click', (e) => {
      if (e.target.classList.contains('edit-project') || e.target.closest('.edit-project')) {
        e.stopPropagation();
        openEditProject(p);
        return;
      }
      if (e.target.classList.contains('delete-project') || e.target.closest('.delete-project')) {
        e.stopPropagation();
        deleteProjectConfirmed(p);
        return;
      }
      openProject(p.id, p.name, p.description);
    });
    projectsGrid.appendChild(card);
  }
}

async function openEditProject(p) {
  const name = prompt('Project name', p.name);
  if (name === null || name.trim() === '') return;
  const description = prompt('Description', p.description || '');
  if (description === null) return;

  try {
    await updateProject(p.id, { name: name.trim(), description: description === '' ? '' : description.trim() });
    toast({ message: 'Project updated', type: 'success' });
    loadProjects();
  } catch (err) {
    toast({ message: err.message || 'Failed to update project', type: 'error' });
  }
}

async function deleteProjectConfirmed(p) {
  if (!confirm(`Delete project "${escapeHtml(p.name)}"? This will also delete all its documents.`)) return;

  try {
    await deleteProject(p.id);
    toast({ message: 'Project deleted', type: 'success' });
    if (currentProjectId === p.id) {
      currentProjectId = null;
      currentChatSessionId = null;
      pageProject.style.display = 'none';
      pageDashboard.style.display = 'block';
      chatMessages.innerHTML = '';
      documentsList.innerHTML = '';
    }
    loadProjects();
  } catch (err) {
    toast({ message: err.message || 'Failed to delete project', type: 'error' });
  }
}

function openModal(el) {
  el.style.display = 'block';
  modalBackdrop.style.display = 'block';
}

function closeModal(el) {
  el.style.display = 'none';
  modalBackdrop.style.display = 'none';
}

/* New project modal */
newProjectBtn.addEventListener('click', () => {
  newProjectForm.reset();
  openModal(modalNewProject);
});

closeNewProject.addEventListener('click', () => closeModal(modalNewProject));
cancelNewProject.addEventListener('click', () => closeModal(modalNewProject));
modalBackdrop.addEventListener('click', () => {
  closeModal(modalNewProject);
});

newProjectForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(newProjectForm);
  const name = fd.get('name').trim();
  const description = fd.get('description').trim();

  const btn = newProjectForm.querySelector('button[type="submit"]');
  setLoading(btn, true, 'Creating…');
  try {
    await createProject({ name, description });
    closeModal(modalNewProject);
    toast({ message: 'Project created', type: 'success' });
    loadProjects();
  } catch (err) {
    toast({ message: err.message || 'Failed to create project', type: 'error' });
  } finally {
    setLoading(btn, false);
  }
});

/* ---------- Project detail ---------- */
backToProjects.addEventListener('click', () => {
  currentProjectId = null;
  currentChatSessionId = null;
  projectDocuments.clear();
  pageProject.style.display = 'none';
  pageDashboard.style.display = 'block';
  chatMessages.innerHTML = '';
  documentsList.innerHTML = '';
});

async function openProject(id, name, description) {
  currentProjectId = id;
  projectTitle.textContent = escapeHtml(name);
  projectSubtitle.textContent = escapeHtml(description || 'No description');

  pageDashboard.style.display = 'none';
  pageProject.style.display = 'block';
  setTab('documents');

  await loadDocuments();
  // Don't auto-create a chat session; create on first message instead.
}

async function setTab(tab) {
  activeTab = tab;
  tabBtns.forEach(b => {
    b.classList.toggle('tab-active', b.dataset.tab === tab);
  });
  tabDocuments.style.display = tab === 'documents' ? 'block' : 'none';
  tabChat.style.display = tab === 'chat' ? 'block' : 'none';
  if (tab === 'documents') {
    documentsList.innerHTML = '';
    await loadDocuments();
  } else if (tab === 'chat') {
    if (!currentChatSessionId) {
      try {
        const res = await createChatSession(currentProjectId);
        currentChatSessionId = res.chat_session_id;
      } catch (err) {
        toast({ message: 'Failed to start chat session', type: 'error' });
      }
    }
    await loadChatHistory();
  }
}

tabBtns.forEach(b => {
  b.addEventListener('click', () => setTab(b.dataset.tab));
});

/* ---------- Documents ---------- */
async function loadDocuments() {
  if (!currentProjectId) return;
  try {
    const docs = projectDocuments.get(currentProjectId) || [];
    renderDocuments(docs);
  } catch (err) {
    toast({ message: 'Failed to load documents', type: 'error' });
  }
}

function renderDocuments(docs) {
  documentsList.innerHTML = '';
  docCount.textContent = `${docs.length} document${docs.length !== 1 ? 's' : ''}`;

  if (!docs || docs.length === 0) {
    documentsEmpty.style.display = 'flex';
    return;
  }
  documentsEmpty.style.display = 'none';

  for (const doc of docs) {
    const row = document.createElement('div');
    row.className = 'document-row';
    const statusClass = (doc.status || 'pending').toLowerCase();
    row.innerHTML = `
      <div class="document-info">
        <span class="doc-icon">📄</span>
        <div>
          <div class="doc-title">${escapeHtml(doc.filename || 'Untitled')}</div>
          <div class="doc-meta">${doc.id} • ${escapeHtml(doc.status || 'pending')}</div>
        </div>
      </div>
      <span class="document-status ${statusClass}">${escapeHtml(doc.status || 'pending')}</span>
      <div class="document-actions">
        <button class="btn-icon" title="Delete document" data-id="${doc.id}">🗑️</button>
      </div>
    `;
    row.querySelector('[data-id]').addEventListener('click', (e) => {
      e.stopPropagation();
      deleteDocumentConfirmed(currentProjectId, doc.id);
    });
    documentsList.appendChild(row);
  }
}

async function deleteDocumentConfirmed(projectId, documentId) {
  if (!confirm('Delete this document?')) return;

  try {
    await deleteDocument(projectId, documentId);
    toast({ message: 'Document deleted', type: 'success' });
    const docs = projectDocuments.get(projectId) || [];
    const updated = docs.filter(d => d.id !== documentId);
    projectDocuments.set(projectId, updated);
    renderDocuments(updated);
  } catch (err) {
    toast({ message: err.message || 'Failed to delete document', type: 'error' });
  }
}

/* Upload drag & drop */
uploadZone.addEventListener('click', () => fileInput.click());
pickFileBtn.addEventListener('click', (e) => { e.stopPropagation(); fileInput.click(); });

['dragenter', 'dragover'].forEach(evt => {
  uploadZone.addEventListener(evt, (e) => {
    e.preventDefault();
    uploadZone.style.borderColor = 'var(--color-brand)';
    uploadZone.style.background = 'var(--color-brand-light)';
  });
});
['dragleave', 'drop'].forEach(evt => {
  uploadZone.addEventListener(evt, (e) => {
    e.preventDefault();
    uploadZone.style.borderColor = 'var(--color-border)';
    uploadZone.style.background = 'var(--color-surface)';
  });
});

uploadZone.addEventListener('drop', (e) => {
  const files = e.dataTransfer.files;
  if (files.length) handleFileSelection(files[0]);
});

fileInput.addEventListener('change', (e) => {
  if (e.target.files.length) handleFileSelection(e.target.files[0]);
});

async function handleFileSelection(file) {
  if (!currentProjectId) {
    toast({ message: 'No project selected', type: 'error' });
    return;
  }
  if (file.type !== 'application/pdf') {
    toast({ message: 'Only PDF files are allowed', type: 'error' });
    return;
  }

  uploadProgress.style.display = 'block';
  progressFill.style.width = '0%';
  progressText.textContent = 'Uploading…';

  let progressInterval = null;
  try {
    // Simulate progress since fetch doesn't expose upload progress easily without the XHR/ReadableStream path.
    progressInterval = setInterval(() => {
      const w = parseFloat(progressFill.style.width || '0');
      if (w < 80) progressFill.style.width = (w + 10) + '%';
    }, 100);

    const res = await uploadDocument(currentProjectId, file);
    clearInterval(progressInterval);
    progressFill.style.width = '100%';
    progressText.textContent = 'Upload complete';

    setTimeout(() => {
      uploadProgress.style.display = 'none';
      progressFill.style.width = '0%';
      fileInput.value = '';
      toast({ message: 'Document uploaded', type: 'success' });

      // Track the uploaded document locally (no list-documents endpoint exists).
      const doc = {
        id: res.document_id,
        filename: file.name,
        status: res.status || 'pending',
      };
      const docs = projectDocuments.get(currentProjectId) || [];
      docs.push(doc);
      projectDocuments.set(currentProjectId, docs);

      loadDocuments();
    }, 400);
  } catch (err) {
    clearInterval(progressInterval);
    uploadProgress.style.display = 'none';
    toast({ message: err.message || 'Upload failed', type: 'error' });
  }
}

/* ---------- Chat ---------- */
function addMessage(role, text) {
  const div = document.createElement('div');
  div.className = `msg msg-${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.textContent = text;
  div.appendChild(bubble);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

async function loadChatHistory() {
  if (!currentChatSessionId) return;
  try {
    const history = await getChatHistory(currentChatSessionId);
    chatMessages.innerHTML = '';
    for (const m of history) {
      addMessage(m.role, m.content);
    }
  } catch (err) {
    toast({ message: 'Failed to load chat history', type: 'error' });
  }
}

chatForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  if (!currentProjectId) {
    toast({ message: 'No project selected', type: 'error' });
    return;
  }

  chatInput.value = '';
  chatSend.disabled = true;

  // Add user message
  addMessage('user', text);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  // Create assistant message bubble (starts empty, fills as tokens stream in)
  const assistantDiv = addMessage('assistant', '');
  const bubble = assistantDiv.querySelector('.msg-bubble');

  chatTyping.style.display = 'block';
  chatMessages.scrollTop = chatMessages.scrollHeight;

  let fullAnswer = '';
  let statusEl = null;

  try {
    if (!currentChatSessionId) {
      const res = await createChatSession(currentProjectId);
      currentChatSessionId = res.chat_session_id;
    }

    for await (const event of sendMessageStream(currentChatSessionId, text)) {
      if (event.type === 'token') {
        chatTyping.style.display = 'none';
        fullAnswer += event.content || '';
        bubble.textContent = fullAnswer;
        chatMessages.scrollTop = chatMessages.scrollHeight;
      } else if (event.type === 'status') {
        chatTyping.style.display = 'none';
        if (!statusEl) {
          statusEl = document.createElement('div');
          statusEl.className = 'chat-status';
          statusEl.textContent = `● ${event.content}`;
          assistantDiv.appendChild(statusEl);
        } else {
          statusEl.textContent = `● ${event.content}`;
        }
      } else if (event.type === 'error') {
        chatTyping.style.display = 'none';
        toast({ message: event.content || 'Stream error', type: 'error' });
        if (!fullAnswer) bubble.textContent = 'Error: ' + (event.content || 'Something went wrong');
        break;
      } else if (event.type === 'done') {
        chatTyping.style.display = 'none';
        if (statusEl) statusEl.remove();
      }
    }
  } catch (err) {
    chatTyping.style.display = 'none';
    toast({ message: err.message || 'Failed to send message', type: 'error' });
    if (!fullAnswer) bubble.textContent = 'Error: ' + (err.message || 'Failed to send message');
  } finally {
    chatTyping.style.display = 'none';
    chatSend.disabled = false;
    chatInput.focus();
  }
});

/* ---------- Sidebar toggle (mobile) ---------- */
navToggle.addEventListener('click', () => sidebar.classList.toggle('open'));
navClose.addEventListener('click', () => sidebar.classList.remove('open'));

/* ---------- Boot ---------- */
(function boot() {
  try {
    initAuth();
  } catch (err) {
    console.error('Boot failed', err);
    // Ensure auth view is visible so the user is not left with a white page.
    try {
      viewAuth.style.display = 'block';
      viewApp.style.display = 'none';
    } catch (e) {}
    toast({ message: 'Application failed to load. Refresh the page.', type: 'error' });
  }
})();
