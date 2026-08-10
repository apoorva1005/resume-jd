/* HTTP client for the FastAPI backend.
 *
 * nginx proxies /api to the backend container, so the browser only ever talks
 * to its own origin -- no CORS preflight, and no hardcoded backend hostname.
 *
 * Every call returns { ok, data } so callers never touch status codes. */

const API = (() => {
  const BASE = '/api';

  function token() {
    return localStorage.getItem('token');
  }

  function setToken(value) {
    if (value) localStorage.setItem('token', value);
    else localStorage.removeItem('token');
  }

  function readError(payload, status) {
    const detail = payload && payload.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
    }
    return `Request failed (${status})`;
  }

  async function request(path, { method = 'GET', body, auth = true } = {}) {
    const headers = {};
    if (auth && token()) headers.Authorization = `Bearer ${token()}`;
    // Let the browser set Content-Type for FormData -- it has to add the
    // multipart boundary, and setting it by hand breaks the upload.
    if (body && !(body instanceof FormData) && !(body instanceof URLSearchParams)) {
      headers['Content-Type'] = 'application/json';
    }

    let response;
    try {
      response = await fetch(BASE + path, {
        method,
        headers,
        body: body instanceof FormData || body instanceof URLSearchParams
          ? body
          : body
            ? JSON.stringify(body)
            : undefined,
      });
    } catch (err) {
      return { ok: false, data: `Could not reach the API: ${err.message}` };
    }

    // 401 means the token expired or was tampered with; drop it so the UI
    // falls back to the login screen instead of looping on failed calls.
    if (response.status === 401 && auth) {
      setToken(null);
      return { ok: false, data: 'Session expired. Please log in again.' };
    }

    let payload = null;
    try {
      payload = await response.json();
    } catch {
      /* 204 and empty bodies are fine. */
    }

    if (!response.ok) return { ok: false, data: readError(payload, response.status) };
    return { ok: true, data: payload };
  }

  return {
    token,
    setToken,
    isLoggedIn: () => Boolean(token()),

    signup: (email, password) =>
      request('/auth/signup', { method: 'POST', body: { email, password }, auth: false }),

    // The OAuth2 password flow wants form-encoded data with a "username" field.
    login: (email, password) =>
      request('/auth/login', {
        method: 'POST',
        auth: false,
        body: new URLSearchParams({ username: email, password }),
      }),

    me: () => request('/auth/me'),

    uploadResume: (file) => {
      const form = new FormData();
      form.append('file', file);
      return request('/resumes', { method: 'POST', body: form });
    },

    uploadJdFile: (file) => {
      const form = new FormData();
      form.append('file', file);
      return request('/jds', { method: 'POST', body: form });
    },

    uploadJdText: (text) => {
      const form = new FormData();
      form.append('text', text);
      return request('/jds', { method: 'POST', body: form });
    },

    listResumes: () => request('/resumes'),
    listJds: () => request('/jds'),

    createMatch: (resumeId, jdId) =>
      request('/matches', {
        method: 'POST',
        body: { resume_id: resumeId, jd_id: jdId },
      }),

    listMatches: () => request('/matches'),

    submitFeedback: (matchId, rating, corrected, comment) =>
      request('/feedback', {
        method: 'POST',
        body: {
          match_id: matchId,
          user_rating: rating,
          corrected_score: corrected,
          comment: comment || '',
        },
      }),
  };
})();
