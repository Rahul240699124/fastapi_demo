/*
 * static/js/api.js - the website's tiny client for OUR OWN JSON API.
 *
 * WHY JAVASCRIPT?
 *   The backend authenticates with JWT bearer tokens (see routers/auth.py). A browser
 *   doesn't send such a token by itself, so the pages use JavaScript to:
 *     1. log in   -> POST /api/auth/token  -> keep the returned token
 *     2. call the API with the header  "Authorization: Bearer <token>"
 *   The HTML pages are just another API client, exactly like Swagger or a mobile app.
 *
 * WHERE IS THE TOKEN KEPT?
 *   In localStorage (survives page reloads and browser restarts). It's simple, but any
 *   JavaScript running on the page can read it, so an XSS bug could steal it.
 *   That's why we never insert user text with innerHTML without escaping it
 *   (see escapeHtml). Bigger apps often use an httpOnly cookie instead.
 *
 * Everything useful is exported on `window.App`, e.g.  App.api("/api/users/me")
 */

(function () {
  "use strict";

  const TOKEN_KEY = "access_token";

  // ------------------------------------------------------------------ token storage
  // localStorage can throw (private mode, blocked storage), so every access is guarded.
  const auth = {
    getToken() {
      try {
        return localStorage.getItem(TOKEN_KEY);
      } catch {
        return null;
      }
    },
    setToken(token) {
      try {
        localStorage.setItem(TOKEN_KEY, token);
      } catch {
        /* storage blocked: the user just won't stay logged in */
      }
    },
    clearToken() {
      try {
        localStorage.removeItem(TOKEN_KEY);
      } catch {
        /* nothing to clear */
      }
      cachedUser = undefined;
    },
    // JWTs are stateless: "logging out" simply means forgetting the token.
    logout() {
      this.clearToken();
      window.location.href = "/";
    },
  };

  // ------------------------------------------------------------------ errors
  class ApiError extends Error {
    constructor(status, message) {
      super(message);
      this.status = status; // HTTP status code, e.g. 401, 403, 422
    }
  }

  // FastAPI errors look like {"detail": "text"} or, for 422 validation errors,
  // {"detail": [{"loc": ["body", "title"], "msg": "String should have..."}, ...]}.
  function errorMessage(data, status) {
    if (!data || data.detail === undefined) return `Request failed (HTTP ${status})`;
    if (typeof data.detail === "string") return data.detail;
    return data.detail
      .map((e) => `${e.loc[e.loc.length - 1]}: ${e.msg}`) // "title: String should have..."
      .join(" · ");
  }

  // ------------------------------------------------------------------ fetch wrapper
  /**
   * Call the API and return the parsed JSON (or null for 204 No Content).
   *   App.api("/api/posts")                                     GET
   *   App.api("/api/posts", { method: "POST", json: {...} })    JSON body
   *   App.api("/api/auth/token", { method: "POST", form: {...} })  form body (login)
   *   App.api("/api/users/me/picture", { method: "PUT", body: formData })  file upload
   * Throws ApiError when the response status is not 2xx.
   */
  async function api(path, { method = "GET", json, form, body, auth: sendToken = true } = {}) {
    const headers = {};
    let payload = body;

    if (json !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(json);
    } else if (form !== undefined) {
      // URLSearchParams = "application/x-www-form-urlencoded", what the OAuth2 login expects.
      payload = new URLSearchParams(form);
    }
    // For FormData (file uploads) we set NO Content-Type: the browser adds
    // "multipart/form-data; boundary=..." itself, and the boundary must match.

    const token = auth.getToken();
    if (sendToken && token) headers["Authorization"] = `Bearer ${token}`;

    const response = await fetch(path, { method, headers, body: payload });
    if (response.status === 204) return null;

    const data = await response.json().catch(() => null);
    if (!response.ok) {
      // 401 with a token = the token expired or the account is gone -> forget it.
      if (response.status === 401 && sendToken && token) auth.clearToken();
      throw new ApiError(response.status, errorMessage(data, response.status));
    }
    return data;
  }

  // ------------------------------------------------------------------ current user
  // undefined = not fetched yet, null = not logged in, object = the user.
  let cachedUser;

  async function getCurrentUser({ refresh = false } = {}) {
    if (!auth.getToken()) return null;
    if (cachedUser === undefined || refresh) {
      try {
        cachedUser = await api("/api/users/me");
      } catch {
        cachedUser = null;
      }
    }
    return cachedUser;
  }

  /** Send visitors who aren't logged in to /login, then bring them back here. */
  function requireLogin() {
    if (auth.getToken()) return true;
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/login?next=${next}`;
    return false;
  }

  /** Only allow redirects to OUR site ("/account"), never to "https://evil.com"
   *  or "//evil.com" - otherwise ?next= could be abused for phishing ("open redirect"). */
  function safeNext(fallback = "/") {
    const next = new URLSearchParams(window.location.search).get("next");
    return next && next.startsWith("/") && !next.startsWith("//") ? next : fallback;
  }

  // ------------------------------------------------------------------ small UI helpers
  // Turn user-provided text into safe HTML text: "<b>" becomes "&lt;b&gt;".
  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text ?? "";
    return div.innerHTML;
  }

  /** Show a Bootstrap alert inside `container` (type: success, danger, info, warning). */
  function showAlert(container, message, type = "danger") {
    if (!container) return;
    container.innerHTML = `<div class="alert alert-${type} border-0 shadow-sm small mb-3" role="alert">${escapeHtml(message)}</div>`;
  }

  /** Disable a button while a request runs, so it can't be clicked twice. */
  function setBusy(button, busy, busyText = "Please wait…") {
    if (!button) return;
    if (busy) {
      button.dataset.originalText = button.textContent;
      button.textContent = busyText;
      button.disabled = true;
    } else {
      button.textContent = button.dataset.originalText || button.textContent;
      button.disabled = false;
    }
  }

  // ------------------------------------------------------------------ navbar
  // The server renders the same HTML for everyone; the login-dependent part of the
  // navbar (#auth-nav in layout.html) is filled in here.
  async function renderNav() {
    const nav = document.getElementById("auth-nav");
    if (!nav) return;

    const user = await getCurrentUser();
    if (!user) {
      nav.innerHTML = `
        <a class="btn btn-outline-light btn-sm" href="/login">Log in</a>
        <a class="btn btn-primary btn-sm" href="/register">Sign up</a>`;
      return;
    }

    nav.innerHTML = `
      <a class="btn btn-primary btn-sm" href="/posts/new">&#9998; New Post</a>
      <div class="dropdown">
        <button class="btn btn-sm btn-outline-light dropdown-toggle d-flex align-items-center gap-2"
                type="button" data-bs-toggle="dropdown" aria-expanded="false">
          <img src="${escapeHtml(user.image_path)}" alt="" class="avatar" width="24" height="24"
               onerror="this.onerror=null; this.src='/static/profile_pics/default.png';">
          <span>${escapeHtml(user.username)}</span>
        </button>
        <ul class="dropdown-menu dropdown-menu-end shadow-sm">
          <li><a class="dropdown-item" href="/account">My Account</a></li>
          <li><a class="dropdown-item" href="/users/${user.id}/posts">My Posts</a></li>
          <li><hr class="dropdown-divider"></li>
          <li><button class="dropdown-item text-danger" type="button" id="logout-btn">Log out</button></li>
        </ul>
      </div>`;
    document.getElementById("logout-btn").addEventListener("click", () => auth.logout());
  }

  document.addEventListener("DOMContentLoaded", renderNav);

  // Expose the helpers for the page scripts.
  window.App = {
    api,
    auth,
    ApiError,
    getCurrentUser,
    requireLogin,
    safeNext,
    escapeHtml,
    showAlert,
    setBusy,
    renderNav,
  };
})();
