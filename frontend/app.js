const $ = (id) => document.getElementById(id);

let toastTimer;
function toast(message, kind = '') {
  const el = $('toast');
  el.textContent = message;
  el.className = `toast ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), 4000);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text == null ? '' : String(text);
  return div.innerHTML;
}

function percent(value) {
  return `${Math.round((value || 0) * 100)}%`;
}

function scoreClass(score) {
  if (score >= 0.7) return 'score-good';
  return score >= 0.45 ? 'score-mid' : 'score-bad';
}

function shortDate(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString();
}

async function withBusy(button, label, action) {
  const original = button.textContent;
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span>${label}`;
  try {
    await action();
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function renderMarkdown(text) {
  const safe = escapeHtml(text);
  const lines = safe.split('\n');
  const html = [];
  let inList = false;

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      if (inList) { html.push('</ul>'); inList = false; }
      continue;
    }
    const bolded = line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    if (line.startsWith('- ') || line.startsWith('* ')) {
      if (!inList) { html.push('<ul>'); inList = true; }
      html.push(`<li>${bolded.slice(2)}</li>`);
    } else {
      if (inList) { html.push('</ul>'); inList = false; }
      html.push(`<p>${bolded}</p>`);
    }
  }
  if (inList) html.push('</ul>');
  return html.join('');
}

function showApp(email) {
  $('auth-view').classList.add('hidden');
  $('app-view').classList.remove('hidden');
  $('user-email').textContent = email || '';
  loadDocuments();
}

function showAuth() {
  $('app-view').classList.add('hidden');
  $('auth-view').classList.remove('hidden');
}

function switchTab(name) {
  document.querySelectorAll('[data-tab]').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.tab === name);
  });
  ['upload', 'match', 'history'].forEach((tab) => {
    $(`tab-${tab}`).classList.toggle('hidden', tab !== name);
  });
  if (name === 'match') loadDocuments();
  if (name === 'history') loadHistory();
}

document.querySelectorAll('[data-auth-tab]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.authTab;
    document.querySelectorAll('[data-auth-tab]').forEach((b) => {
      b.classList.toggle('active', b === btn);
    });
    $('login-form').classList.toggle('hidden', target !== 'login');
    $('signup-form').classList.toggle('hidden', target !== 'signup');
  });
});

$('login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const email = $('login-email').value.trim();
  const { ok, data } = await API.login(email, $('login-password').value);
  if (!ok) return toast(data, 'error');
  API.setToken(data.access_token);
  showApp(email);
});

$('signup-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const email = $('signup-email').value.trim();
  const { ok, data } = await API.signup(email, $('signup-password').value);
  if (!ok) return toast(data, 'error');
  API.setToken(data.access_token);
  showApp(email);
});

$('logout-btn').addEventListener('click', () => {
  API.setToken(null);
  showAuth();
});

document.querySelectorAll('[data-tab]').forEach((btn) => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

$('upload-resume-btn').addEventListener('click', (event) => {
  const file = $('resume-file').files[0];
  if (!file) return toast('Choose a resume file first.', 'error');

  withBusy(event.target, 'Parsing...', async () => {
    const { ok, data } = await API.uploadResume(file);
    if (!ok) return toast(data, 'error');
    toast('Resume saved.', 'success');
    $('resume-file').value = '';
    loadDocuments();
  });
});

$('upload-jd-btn').addEventListener('click', (event) => {
  const file = $('jd-file').files[0];
  const text = $('jd-text').value.trim();
  if (!file && !text) return toast('Paste some text or choose a file.', 'error');

  withBusy(event.target, 'Saving...', async () => {
    const { ok, data } = file
      ? await API.uploadJdFile(file)
      : await API.uploadJdText(text);
    if (!ok) return toast(data, 'error');
    toast('Job description saved.', 'success');
    $('jd-text').value = '';
    $('jd-file').value = '';
    loadDocuments();
  });
});

function fillSelect(select, items) {
  if (!items.length) {
    select.innerHTML = '<option value="">Nothing uploaded yet</option>';
    return;
  }
  select.innerHTML = items
    .map((doc) => {
      const label = `${shortDate(doc.created_at)} - ${doc.preview.slice(0, 60)}...`;
      return `<option value="${escapeHtml(doc.id)}">${escapeHtml(label)}</option>`;
    })
    .join('');
}

async function loadDocuments() {
  const [resumes, jds] = await Promise.all([API.listResumes(), API.listJds()]);
  if (resumes.ok) fillSelect($('resume-select'), resumes.data);
  if (jds.ok) fillSelect($('jd-select'), jds.data);
}

$('run-match-btn').addEventListener('click', (event) => {
  const resumeId = $('resume-select').value;
  const jdId = $('jd-select').value;
  if (!resumeId || !jdId) return toast('Upload a resume and a JD first.', 'error');

  withBusy(event.target, 'Scoring...', async () => {
    const { ok, data } = await API.createMatch(resumeId, jdId);
    if (!ok) return toast(data, 'error');
    renderMatch(data);
  });
});

function renderMatch(match) {
  const features = match.features || {};
  const panel = $('match-result');

  panel.innerHTML = `
    <div class="card">
      <div class="score-big ${scoreClass(match.final_score)}">
        ${percent(match.final_score)}
      </div>
      <p class="muted">Overall match score</p>

      <div class="metrics">
        <div class="metric">
          <div class="label">Embedding similarity</div>
          <div class="value">${percent(match.cosine_score)}</div>
        </div>
        <div class="metric">
          <div class="label">Cross-encoder</div>
          <div class="value">${percent(match.cross_encoder_score)}</div>
        </div>
        <div class="metric">
          <div class="label">Keyword overlap</div>
          <div class="value">${percent(features.keyword_overlap)}</div>
        </div>
        <div class="metric">
          <div class="label">Years match</div>
          <div class="value">${percent(features.years_match)}</div>
        </div>
        <div class="metric">
          <div class="label">Education match</div>
          <div class="value">${percent(features.education_match)}</div>
        </div>
      </div>

      <details>
        <summary>Raw feature values</summary>
        <pre>${escapeHtml(JSON.stringify(features, null, 2))}</pre>
      </details>

      <div class="explanation">${renderMarkdown(match.explanation_text)}</div>
    </div>
  `;
  panel.classList.remove('hidden');
}

async function loadHistory() {
  const list = $('history-list');
  const { ok, data } = await API.listMatches();

  if (!ok) {
    list.innerHTML = `<p class="muted">${escapeHtml(data)}</p>`;
    return;
  }
  if (!data.length) {
    list.innerHTML = '<p class="muted">No matches yet.</p>';
    return;
  }

  list.innerHTML = data
    .map(
      (match) => `
      <div class="history-item">
        <details>
          <summary>
            <span class="${scoreClass(match.final_score)}">
              ${percent(match.final_score)}
            </span>
            &nbsp;&mdash;&nbsp;
            <span class="muted small">${shortDate(match.created_at)}</span>
          </summary>
          <div class="explanation">${renderMarkdown(match.explanation_text)}</div>
        </details>
      </div>`,
    )
    .join('');
}

(async function start() {
  if (!API.isLoggedIn()) return showAuth();
  const { ok, data } = await API.me();
  if (ok) showApp(data.email);
  else showAuth();
})();
