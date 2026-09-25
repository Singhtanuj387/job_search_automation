/**
 * API client for the Job Search Automation backend.
 */
const API_BASE = window.location.port === "5173" ? "http://127.0.0.1:8000/api" : "/api";

export function getSessionId() {
  let sid = localStorage.getItem("job_search_session_id");
  if (!sid) {
    sid = "sess_" + (typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID().replace(/-/g, "") : Math.random().toString(36).substring(2) + Date.now().toString(36));
    localStorage.setItem("job_search_session_id", sid);
  }
  return sid;
}

export function resetSessionId() {
  localStorage.removeItem("job_search_session_id");
  return getSessionId();
}

function sessionFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!headers.has("X-Session-ID")) {
    headers.set("X-Session-ID", getSessionId());
  }
  return fetch(url, {
    ...options,
    headers,
  });
}


export async function getProfile() {
  const res = await sessionFetch(`${API_BASE}/profile`);
  return res.json();
}

export async function updateProfile(data) {
  const res = await sessionFetch(`${API_BASE}/profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function uploadResume(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await sessionFetch(`${API_BASE}/profile/upload-resume`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to upload resume");
  }
  return res.json();
}

export function getResumeDownloadUrl() {
  return `${API_BASE}/profile/resume/download?session_id=${encodeURIComponent(getSessionId())}`;
}

export async function deleteProfileResume() {
  const res = await sessionFetch(`${API_BASE}/profile/resume`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to delete resume" }));
    throw new Error(err.detail || "Failed to delete resume");
  }
  return res.json();
}

export async function getSecret() {
  const res = await sessionFetch(`${API_BASE}/settings/secret`);
  return res.json();
}

export async function saveSecret(provider, apiKey, extraConfig = {}) {
  const res = await sessionFetch(`${API_BASE}/settings/secret`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, api_key: apiKey, extra_config: extraConfig }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Validation failed");
  }
  return res.json();
}

export async function deleteSecret() {
  const res = await sessionFetch(`${API_BASE}/settings/secret`, {
    method: "DELETE",
  });
  return res.json();
}

export async function listSessions() {
  const res = await sessionFetch(`${API_BASE}/chat/sessions`);
  return res.json();
}

export async function createSession(title) {
  const res = await sessionFetch(`${API_BASE}/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  return res.json();
}

export async function deleteSession(sessionId) {
  const res = await sessionFetch(`${API_BASE}/chat/sessions/${sessionId}`, {
    method: "DELETE",
  });
  return res.json();
}

export async function getSessionMessages(sessionId) {
  const res = await sessionFetch(`${API_BASE}/chat/sessions/${sessionId}/messages`);
  return res.json();
}

export async function sendMessage(sessionId, content) {
  const res = await sessionFetch(`${API_BASE}/chat/sessions/${sessionId}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to send message");
  }
  return res.json();
}

export async function sendMessageStream(sessionId, content, onProgressEvent) {
  const res = await sessionFetch(`${API_BASE}/chat/sessions/${sessionId}/message/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to stream message" }));
    throw new Error(err.detail || "Failed to stream message");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalMessage = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const trimmed = part.trim();
      if (!trimmed.startsWith("data:")) continue;
      const dataStr = trimmed.slice(5).trim();
      if (dataStr === "[DONE]") continue;

      try {
        const evt = JSON.parse(dataStr);
        if (evt.type === "complete") {
          finalMessage = evt.message;
        }
        if (onProgressEvent) {
          onProgressEvent(evt);
        }
      } catch (e) {
        console.error("Error parsing stream chunk:", e);
      }
    }
  }

  return finalMessage;
}

export async function getTracker() {
  const res = await sessionFetch(`${API_BASE}/tracker`);
  return res.json();
}

export async function addToTracker(entry) {
  const res = await sessionFetch(`${API_BASE}/tracker`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
  return res.json();
}

export async function updateTrackerStatus(id, status, notes = null) {
  const res = await sessionFetch(`${API_BASE}/tracker/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, notes }),
  });
  return res.json();
}

export async function getAutoImprovement() {
  const res = await sessionFetch(`${API_BASE}/tracker/auto-improve`);
  return res.json();
}

export async function getGmailPrivacyQuery() {
  const res = await sessionFetch(`${API_BASE}/tracker/gmail-query-preview`);
  return res.json();
}

export async function getAutomateConfig() {
  const res = await sessionFetch(`${API_BASE}/automate/config`);
  return res.json();
}

export async function saveAutomateConfig(enabled, scheduleTime, reportDelivery = "chat") {
  const res = await sessionFetch(`${API_BASE}/automate/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      enabled,
      schedule_time: scheduleTime,
      report_delivery: reportDelivery,
    }),
  });
  return res.json();
}

export async function runAutomateNow() {
  const res = await sessionFetch(`${API_BASE}/automate/run-now`, {
    method: "POST",
  });
  return res.json();
}

export async function getOpportunities(params = {}) {
  const query = new URLSearchParams(params).toString();
  const res = await sessionFetch(`${API_BASE}/opportunities${query ? '?' + query : ''}`);
  return res.json();
}

export async function getOpportunitiesStats() {
  const res = await sessionFetch(`${API_BASE}/opportunities/stats`);
  return res.json();
}

export async function saveOpportunityToTracker(oppId) {
  const res = await sessionFetch(`${API_BASE}/opportunities/${oppId}/save-to-tracker`, {
    method: "POST",
  });
  return res.json();
}

export async function clearAllOpportunities(clearFoundTracker = true) {
  const res = await sessionFetch(`${API_BASE}/opportunities?clear_found_tracker=${clearFoundTracker}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to clear opportunities" }));
    throw new Error(err.detail || "Failed to clear opportunities");
  }
  return res.json();
}


// ── LinkedIn Auto-Apply API ──

export async function getLinkedInCredentials() {
  const res = await sessionFetch(`${API_BASE}/apply/credentials`);
  return res.json();
}

export async function saveLinkedInCredentials(email, password) {
  const res = await sessionFetch(`${API_BASE}/apply/credentials`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to save credentials" }));
    throw new Error(err.detail || "Failed to save credentials");
  }
  return res.json();
}

export async function deleteLinkedInCredentials() {
  const res = await sessionFetch(`${API_BASE}/apply/credentials`, {
    method: "DELETE",
  });
  return res.json();
}

export async function clearLinkedInCookies() {
  const res = await sessionFetch(`${API_BASE}/apply/credentials/cookies`, {
    method: "DELETE",
  });
  return res.json();
}

export async function getIndeedCredentials() {
  const res = await sessionFetch(`${API_BASE}/apply/indeed/credentials`);
  return res.json();
}

export async function saveIndeedCredentials(email, password = "") {
  const res = await sessionFetch(`${API_BASE}/apply/indeed/credentials`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: password || "" }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to save Indeed credentials" }));
    throw new Error(err.detail || "Failed to save Indeed credentials");
  }
  return res.json();
}

export async function deleteIndeedCredentials() {
  const res = await sessionFetch(`${API_BASE}/apply/indeed/credentials`, {
    method: "DELETE",
  });
  return res.json();
}

export async function clearIndeedCookies() {
  const res = await sessionFetch(`${API_BASE}/apply/indeed/credentials/cookies`, {
    method: "DELETE",
  });
  return res.json();
}

export async function startIndeedApply(maxApplies = 25, onProgressEvent) {
  const res = await sessionFetch(`${API_BASE}/apply/indeed/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_applies: maxApplies, platform: "indeed" }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to start Indeed apply session" }));
    throw new Error(err.detail || "Failed to start Indeed apply session");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const trimmed = part.trim();
      if (!trimmed.startsWith("data:")) continue;
      const dataStr = trimmed.slice(5).trim();
      if (dataStr === "[DONE]") continue;

      try {
        const evt = JSON.parse(dataStr);
        if (evt.type === "apply_complete") {
          finalResult = evt;
        }
        if (onProgressEvent) {
          onProgressEvent(evt);
        }
      } catch (e) {
        console.error("Error parsing Indeed apply stream chunk:", e);
      }
    }
  }

  return finalResult;
}

export async function getSeekCredentials() {
  const res = await sessionFetch(`${API_BASE}/apply/seek/credentials`);
  return res.json();
}

export async function saveSeekCredentials(email, password = "") {
  const res = await sessionFetch(`${API_BASE}/apply/seek/credentials`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: password || "" }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to save SEEK credentials" }));
    throw new Error(err.detail || "Failed to save SEEK credentials");
  }
  return res.json();
}

export async function deleteSeekCredentials() {
  const res = await sessionFetch(`${API_BASE}/apply/seek/credentials`, {
    method: "DELETE",
  });
  return res.json();
}

export async function clearSeekCookies() {
  const res = await sessionFetch(`${API_BASE}/apply/seek/credentials/cookies`, {
    method: "DELETE",
  });
  return res.json();
}

export async function startSeekApply(maxApplies = 25, onProgressEvent) {
  const res = await sessionFetch(`${API_BASE}/apply/seek/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_applies: maxApplies, platform: "seek" }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to start SEEK apply session" }));
    throw new Error(err.detail || "Failed to start SEEK apply session");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const trimmed = part.trim();
      if (!trimmed.startsWith("data:")) continue;
      const dataStr = trimmed.slice(5).trim();
      if (dataStr === "[DONE]") continue;

      try {
        const evt = JSON.parse(dataStr);
        if (evt.type === "apply_complete") {
          finalResult = evt;
        }
        if (onProgressEvent) {
          onProgressEvent(evt);
        }
      } catch (e) {
        console.error("Error parsing SEEK apply stream chunk:", e);
      }
    }
  }

  return finalResult;
}

export async function startLinkedInApply(maxApplies = 25, onProgressEvent) {
  const res = await sessionFetch(`${API_BASE}/apply/linkedin/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_applies: maxApplies, platform: "linkedin" }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to start apply session" }));
    throw new Error(err.detail || "Failed to start apply session");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const trimmed = part.trim();
      if (!trimmed.startsWith("data:")) continue;
      const dataStr = trimmed.slice(5).trim();
      if (dataStr === "[DONE]") continue;

      try {
        const evt = JSON.parse(dataStr);
        if (evt.type === "apply_complete") {
          finalResult = evt;
        }
        if (onProgressEvent) {
          onProgressEvent(evt);
        }
      } catch (e) {
        console.error("Error parsing apply stream chunk:", e);
      }
    }
  }

  return finalResult;
}

export async function respondToApplyQuestion(sessionId, answer) {
  const res = await sessionFetch(`${API_BASE}/apply/linkedin/respond/${sessionId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer }),
  });
  return res.json();
}

export async function stopApplySession(sessionId) {
  const res = await sessionFetch(`${API_BASE}/apply/linkedin/stop/${sessionId}`, {
    method: "POST",
  });
  return res.json();
}

export async function getActiveApplySession() {
  try {
    const res = await sessionFetch(`${API_BASE}/apply/active`);
    if (!res.ok) return { active: false };
    return await res.json();
  } catch (e) {
    return { active: false };
  }
}

export async function reconnectApplySession(sessionId, onProgressEvent) {
  const res = await sessionFetch(`${API_BASE}/apply/sessions/${sessionId}/stream`);
  if (!res.ok) return null;

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const trimmed = part.trim();
      if (!trimmed.startsWith("data:")) continue;
      const dataStr = trimmed.slice(5).trim();
      if (dataStr === "[DONE]") continue;

      try {
        const evt = JSON.parse(dataStr);
        if (evt.type === "apply_complete") {
          finalResult = evt;
        }
        if (onProgressEvent) {
          onProgressEvent(evt);
        }
      } catch (e) {
        console.error("Error parsing reconnected apply stream:", e);
      }
    }
  }

  return finalResult;
}

export async function getApplyStatus(sessionId) {
  const res = await sessionFetch(`${API_BASE}/apply/sessions/${sessionId}`);
  return res.json();
}

export async function listApplySessions() {
  const res = await sessionFetch(`${API_BASE}/apply/sessions`);
  return res.json();
}

export async function getApplyCredentials() {
  const res = await sessionFetch(`${API_BASE}/apply/credentials`);
  return res.json();
}

export async function saveApplyCredentials(email, password) {
  const res = await sessionFetch(`${API_BASE}/apply/credentials`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to save credentials" }));
    throw new Error(err.detail || "Failed to save credentials");
  }
  return res.json();
}

export async function deleteApplyCredentials() {
  const res = await sessionFetch(`${API_BASE}/apply/credentials`, {
    method: "DELETE",
  });
  return res.json();
}

export async function clearApplyCookies() {
  const res = await sessionFetch(`${API_BASE}/apply/credentials/cookies`, {
    method: "DELETE",
  });
  return res.json();
}

export async function testGemini(apiKey, modelId = "gemma-4-31b-it") {
  const res = await sessionFetch(`${API_BASE}/settings/test-gemini`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_key: apiKey || undefined,
      model_id: modelId,
      input_text: "Explain how AI works in a few words",
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Test probe failed" }));
    throw new Error(err.detail || "Gemini test probe failed");
  }
  return res.json();
}
