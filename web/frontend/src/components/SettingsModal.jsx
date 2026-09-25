import React, { useState, useEffect } from 'react';
import {
  Key,
  ShieldCheck,
  Trash2,
  RefreshCw,
  X,
  Check,
  AlertCircle,
  Sparkles,
  Cpu,
  Eye,
  EyeOff,
  Lock,
  CheckCircle2,
  Globe,
  Edit2,
  ExternalLink,
  Sun,
  Moon,
} from 'lucide-react';
import {
  getSecret,
  saveSecret,
  deleteSecret,
  testGemini,
  getApplyCredentials,
  saveApplyCredentials,
  deleteApplyCredentials,
  clearApplyCookies,
  getIndeedCredentials,
  saveIndeedCredentials,
  deleteIndeedCredentials,
  clearIndeedCookies,
  getSeekCredentials,
  saveSeekCredentials,
  deleteSeekCredentials,
  clearSeekCookies,
} from '../api';

export default function SettingsModal({ isOpen, onClose, initialTab = "ai", theme = "light", onToggleTheme = null }) {
  if (!isOpen) return null;

  const [activeMainTab, setActiveMainTab] = useState(initialTab || "ai");

  useEffect(() => {
    if (initialTab) {
      setActiveMainTab(initialTab);
    }
  }, [initialTab, isOpen]);

  // AI & LLM Provider configuration state
  const [provider, setProvider] = useState("gemini");
  const [apiKey, setApiKey] = useState("");
  const [geminiModelId, setGeminiModelId] = useState("gemma-4-31b-it");
  const [testResult, setTestResult] = useState(null);
  const [testingModel, setTestingModel] = useState(false);
  const [modelName, setModelName] = useState("");
  const [customModel, setCustomModel] = useState("");
  const [awsRegion, setAwsRegion] = useState("us-east-1");
  const [secretInfo, setSecretInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  // Platform Credentials state - LinkedIn
  const [linkedinInfo, setLinkedinInfo] = useState(null);
  const [liEmail, setLiEmail] = useState("");
  const [liPassword, setLiPassword] = useState("");
  const [showLiPassword, setShowLiPassword] = useState(false);
  const [isEditingLi, setIsEditingLi] = useState(false);
  const [liLoading, setLiLoading] = useState(false);
  const [liError, setLiError] = useState("");
  const [liSuccess, setLiSuccess] = useState("");

  // Platform Credentials state - Indeed
  const [indeedInfo, setIndeedInfo] = useState(null);
  const [indEmail, setIndEmail] = useState("");
  const [indPassword, setIndPassword] = useState("");
  const [showIndPassword, setShowIndPassword] = useState(false);
  const [isEditingInd, setIsEditingInd] = useState(false);
  const [indLoading, setIndLoading] = useState(false);
  const [indError, setIndError] = useState("");
  const [indSuccess, setIndSuccess] = useState("");

  // Platform Credentials state - SEEK
  const [seekInfo, setSeekInfo] = useState(null);
  const [seekEmail, setSeekEmail] = useState("");
  const [seekPassword, setSeekPassword] = useState("");
  const [showSeekPassword, setShowSeekPassword] = useState(false);
  const [isEditingSeek, setIsEditingSeek] = useState(false);
  const [seekLoading, setSeekLoading] = useState(false);
  const [seekError, setSeekError] = useState("");
  const [seekSuccess, setSeekSuccess] = useState("");

  const loadSecret = async () => {
    try {
      const data = await getSecret();
      setSecretInfo(data);
      if (data.has_key && data.provider) {
        setProvider(data.provider);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const loadPlatformCredentials = async () => {
    try {
      const data = await getApplyCredentials();
      setLinkedinInfo(data);
      if (data?.has_credentials && data?.email) {
        setLiEmail(data.email);
      }
    } catch (e) {
      console.error("Failed to load platform credentials:", e);
    }
  };

  const loadIndeedCredentials = async () => {
    try {
      const data = await getIndeedCredentials();
      setIndeedInfo(data);
      if (data?.has_credentials && data?.email) {
        setIndEmail(data.email);
      }
    } catch (e) {
      console.error("Failed to load Indeed credentials:", e);
    }
  };

  const loadSeekCredentials = async () => {
    try {
      const data = await getSeekCredentials();
      setSeekInfo(data);
      if (data?.has_credentials && data?.email) {
        setSeekEmail(data.email);
      }
    } catch (e) {
      console.error("Failed to load SEEK credentials:", e);
    }
  };

  useEffect(() => {
    loadSecret();
    loadPlatformCredentials();
    loadIndeedCredentials();
    loadSeekCredentials();
  }, [isOpen]);

  const handleTestGemini = async () => {
    setTestingModel(true);
    setError("");
    setTestResult(null);
    try {
      const data = await testGemini(apiKey.trim() || undefined, geminiModelId.trim() || "gemma-4-31b-it");
      setTestResult(data);
    } catch (err) {
      setError(err.message || "Failed to test Gemini API");
    } finally {
      setTestingModel(false);
    }
  };

  const handleSave = async () => {
    setLoading(true);
    setError("");
    setSuccessMsg("");

    try {
      if (!apiKey.trim()) {
        setError("Please enter an API key to validate and store.");
        setLoading(false);
        return;
      }

      let extraConfig = {};
      if (provider === "gemini") {
        extraConfig = {
          model_id: geminiModelId.trim() || "gemma-4-31b-it",
        };
      }

      const res = await saveSecret(provider, apiKey.trim(), extraConfig);
      setSuccessMsg(res.message || "Key validated and encrypted at rest.");
      setApiKey("");
      await loadSecret();
    } catch (err) {
      setError(err.message || "Failed to save API key.");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAI = async () => {
    if (!window.confirm("Are you sure you want to disconnect and delete stored AI credentials?")) return;
    setError("");
    setSuccessMsg("");
    setLoading(true);
    try {
      await deleteSecret();
      setSuccessMsg("AI credentials deleted.");
      await loadSecret();
    } catch (err) {
      setError(err.message || "Failed to delete API key.");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveLinkedIn = async (e) => {
    if (e) e.preventDefault();
    setLiError("");
    setLiSuccess("");
    setLiLoading(true);

    try {
      if (!liEmail?.trim() || !liPassword?.trim()) {
        throw new Error("Email and password are required.");
      }
      await saveApplyCredentials(liEmail.trim(), liPassword.trim());
      setLiSuccess("LinkedIn credentials encrypted and saved successfully.");
      setLiPassword("");
      setIsEditingLi(false);
      await loadPlatformCredentials();
    } catch (err) {
      setLiError(err.message || "Failed to save LinkedIn credentials.");
    } finally {
      setLiLoading(false);
    }
  };

  const handleDeleteLinkedIn = async () => {
    if (!window.confirm("Are you sure you want to remove stored LinkedIn credentials?")) return;
    setLiLoading(true);
    setLiError("");
    setLiSuccess("");
    try {
      await deleteApplyCredentials();
      setLiSuccess("LinkedIn credentials removed.");
      setIsEditingLi(false);
      await loadPlatformCredentials();
    } catch (err) {
      setLiError(err.message || "Failed to delete credentials.");
    } finally {
      setLiLoading(false);
    }
  };

  const handleClearCookies = async () => {
    setLiLoading(true);
    setLiError("");
    setLiSuccess("");
    try {
      await clearApplyCookies();
      setLiSuccess("Cached LinkedIn session cookies cleared.");
      await loadPlatformCredentials();
    } catch (err) {
      setLiError(err.message || "Failed to clear cookies.");
    } finally {
      setLiLoading(false);
    }
  };

  const handleSaveIndeed = async (e) => {
    e?.preventDefault?.();
    setIndError("");
    setIndSuccess("");
    setIndLoading(true);

    try {
      if (!indEmail?.trim()) {
        throw new Error("Indeed Gmail / Email is required.");
      }
      await saveIndeedCredentials(indEmail.trim(), indPassword?.trim() || "");
      setIndSuccess("Indeed email saved. Passwordless 'Sign in with a code' active.");
      setIndPassword("");
      setIsEditingInd(false);
      await loadIndeedCredentials();
    } catch (err) {
      setIndError(err.message || "Failed to save Indeed credentials.");
    } finally {
      setIndLoading(false);
    }
  };

  const handleDeleteIndeed = async () => {
    if (!window.confirm("Are you sure you want to remove stored Indeed credentials?")) return;
    setIndLoading(true);
    setIndError("");
    setIndSuccess("");
    try {
      await deleteIndeedCredentials();
      setIndSuccess("Indeed credentials removed.");
      setIsEditingInd(false);
      await loadIndeedCredentials();
    } catch (err) {
      setIndError(err.message || "Failed to delete Indeed credentials.");
    } finally {
      setIndLoading(false);
    }
  };

  const handleClearIndeedCookies = async () => {
    setIndLoading(true);
    setIndError("");
    setIndSuccess("");
    try {
      await clearIndeedCookies();
      setIndSuccess("Cached Indeed session cookies cleared.");
      await loadIndeedCredentials();
    } catch (err) {
      setIndError(err.message || "Failed to clear cookies.");
    } finally {
      setIndLoading(false);
    }
  };

  const handleSaveSeek = async (e) => {
    e?.preventDefault();
    setSeekError("");
    setSeekSuccess("");
    setSeekLoading(true);

    try {
      if (!seekEmail?.trim()) {
        throw new Error("SEEK Email is required.");
      }
      await saveSeekCredentials(seekEmail.trim(), seekPassword?.trim() || "");
      setSeekSuccess("SEEK email saved. Passwordless 'Email me a sign in code' active.");
      setSeekPassword("");
      setIsEditingSeek(false);
      await loadSeekCredentials();
    } catch (err) {
      setSeekError(err.message || "Failed to save SEEK credentials.");
    } finally {
      setSeekLoading(false);
    }
  };

  const handleDeleteSeek = async () => {
    if (!window.confirm("Are you sure you want to remove stored SEEK credentials?")) return;
    setSeekLoading(true);
    setSeekError("");
    setSeekSuccess("");
    try {
      await deleteSeekCredentials();
      setSeekSuccess("SEEK credentials removed.");
      setIsEditingSeek(false);
      await loadSeekCredentials();
    } catch (err) {
      setSeekError(err.message || "Failed to delete SEEK credentials.");
    } finally {
      setSeekLoading(false);
    }
  };

  const handleClearSeekCookies = async () => {
    setSeekLoading(true);
    setSeekError("");
    setSeekSuccess("");
    try {
      await clearSeekCookies();
      setSeekSuccess("Cached SEEK session cookies cleared.");
      await loadSeekCredentials();
    } catch (err) {
      setSeekError(err.message || "Failed to clear cookies.");
    } finally {
      setSeekLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-card" style={{ maxWidth: "600px" }}>
        {/* Header */}
        <div className="modal-header">
          <div className="modal-title" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Key size={20} color="var(--accent-gold)" /> Settings & Credentials
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            {onToggleTheme && (
              <button
                type="button"
                className="btn-theme-toggle"
                onClick={onToggleTheme}
                title={theme === 'dark' ? "Switch to Warm Light Theme" : "Switch to Dark Theme"}
                aria-label="Toggle light/dark theme"
                style={{ width: "30px", height: "30px" }}
              >
                {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
              </button>
            )}
            <button className="close-btn" onClick={onClose}><X size={18} /></button>
          </div>
        </div>

        {/* Top-Level Tabs Navigation */}
        <div style={{
          display: "flex",
          gap: "0.5rem",
          borderBottom: "1px solid var(--border-subtle)",
          paddingBottom: "0.75rem",
          marginBottom: "1.25rem",
        }}>
          <button
            type="button"
            onClick={() => { setActiveMainTab("ai"); setError(""); setSuccessMsg(""); }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.45rem",
              padding: "0.45rem 0.9rem",
              borderRadius: "6px",
              fontSize: "0.85rem",
              cursor: "pointer",
              border: activeMainTab === "ai" ? "1px solid var(--accent-gold)" : "1px solid transparent",
              background: activeMainTab === "ai" ? "var(--accent-bg)" : "transparent",
              color: activeMainTab === "ai" ? "var(--accent-gold)" : "var(--text-muted)",
              fontWeight: activeMainTab === "ai" ? 600 : 400,
              transition: "all 0.2s ease",
            }}
          >
            <Key size={15} />
            <span>AI & LLM Providers</span>
          </button>

          <button
            type="button"
            onClick={() => { setActiveMainTab("platforms"); setLiError(""); setLiSuccess(""); }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.45rem",
              padding: "0.45rem 0.9rem",
              borderRadius: "6px",
              fontSize: "0.85rem",
              cursor: "pointer",
              border: activeMainTab === "platforms" ? "1px solid var(--accent-gold)" : "1px solid transparent",
              background: activeMainTab === "platforms" ? "var(--accent-bg)" : "transparent",
              color: activeMainTab === "platforms" ? "var(--accent-gold)" : "var(--text-muted)",
              fontWeight: activeMainTab === "platforms" ? 600 : 400,
              transition: "all 0.2s ease",
            }}
          >
            <ShieldCheck size={15} />
            <span>Platform Credentials</span>
            {(linkedinInfo?.has_credentials || indeedInfo?.has_credentials || seekInfo?.has_credentials) && (
              <span style={{
                background: "var(--badge-emerald-bg)",
                color: "var(--badge-emerald-text)",
                borderRadius: "10px",
                padding: "0.1rem 0.45rem",
                fontSize: "0.7rem",
                fontWeight: 700,
              }}>
                {(linkedinInfo?.has_credentials ? 1 : 0) + (indeedInfo?.has_credentials ? 1 : 0) + (seekInfo?.has_credentials ? 1 : 0)} Connected
              </span>
            )}
          </button>
        </div>

        {/* ────────────── TAB 1: AI & LLM PROVIDERS ────────────── */}
        {activeMainTab === "ai" && (
          <div>
            {error && (
              <div style={{ background: "rgba(239, 68, 68, 0.12)", border: "1px solid rgba(239, 68, 68, 0.3)", color: "#f87171", padding: "0.65rem 0.85rem", borderRadius: "8px", fontSize: "0.85rem", marginBottom: "1rem", display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
                <AlertCircle size={16} style={{ marginTop: "2px", flexShrink: 0 }} />
                <div>{error}</div>
              </div>
            )}

            {successMsg && (
              <div style={{ background: "var(--badge-emerald-bg)", border: "1px solid var(--badge-emerald-border)", color: "var(--badge-emerald-text)", padding: "0.65rem 0.85rem", borderRadius: "8px", fontSize: "0.85rem", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Check size={16} /> {successMsg}
              </div>
            )}

            {/* Existing Active Key Banner */}
            {secretInfo?.has_key && (
              <div style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", padding: "0.85rem", marginBottom: "1.25rem" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.4rem" }}>
                  <span style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "var(--text-muted)", fontWeight: 600 }}>Active Encrypted Key</span>
                  <span style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.75rem", color: "var(--badge-emerald-text)", fontWeight: 600 }}>
                    <ShieldCheck size={14} /> Validated at rest
                  </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div>
                    <span style={{ fontWeight: 600, fontSize: "0.9rem", marginRight: "0.6rem" }}>{secretInfo.provider?.toUpperCase()}</span>
                    <code style={{ fontFamily: "JetBrains Mono, monospace", fontSize: "0.85rem", color: "var(--accent-gold)" }}>{secretInfo.masked_key}</code>
                  </div>
                  <button className="btn-secondary" onClick={handleDeleteAI} title="Delete stored key" style={{ padding: "0.3rem 0.6rem" }}>
                    <Trash2 size={14} color="#b91c1c" />
                  </button>
                </div>
              </div>
            )}

            <div className="form-group">
              <label className="form-label">LLM Provider</label>
              <select className="form-select" value={provider} onChange={(e) => setProvider(e.target.value)}>
                <option value="gemini">Google Gemini &amp; Gemma (gemma-4-31b-it / Gemini)</option>
                <option value="openai">OpenAI (GPT-4o / GPT-4o-mini)</option>
                <option value="anthropic">Anthropic Claude (Claude 3.5 Sonnet / Haiku)</option>
              </select>
            </div>

            {provider === "gemini" ? (
              <div>
                <div className="form-group" style={{ marginBottom: "0.85rem" }}>
                  <label className="form-label" style={{ fontSize: "0.82rem" }}>
                    {secretInfo?.has_key && secretInfo?.provider === "gemini" ? "Rotate Google Gemini API Key" : "Google Gemini API Key"}
                  </label>
                  <input
                    type="password"
                    className="form-input"
                    placeholder="AIzaSy..."
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  />
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem", display: "block" }}>
                    Get your API key from <a href="https://aistudio.google.com" target="_blank" rel="noreferrer" style={{ color: "var(--accent-gold)", textDecoration: "underline" }}>Google AI Studio</a>.
                  </span>
                </div>

                <div className="form-group" style={{ marginBottom: "0.85rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.3rem" }}>
                    <label className="form-label" style={{ fontSize: "0.82rem", margin: 0 }}>Model ID</label>
                    <div style={{ display: "flex", gap: "0.35rem" }}>
                      {["gemma-4-31b-it", "gemini-2.5-flash", "gemini-1.5-flash"].map((m) => (
                        <button
                          key={m}
                          type="button"
                          onClick={() => setGeminiModelId(m)}
                          style={{
                            fontSize: "0.7rem",
                            padding: "0.15rem 0.45rem",
                            borderRadius: "4px",
                            border: geminiModelId === m ? "1px solid var(--accent-gold)" : "1px solid var(--border-subtle)",
                            background: geminiModelId === m ? "var(--bg-tertiary)" : "transparent",
                            color: geminiModelId === m ? "var(--accent-gold)" : "var(--text-muted)",
                            cursor: "pointer",
                          }}
                        >
                          {m}
                        </button>
                      ))}
                    </div>
                  </div>
                  <input
                    className="form-input"
                    value={geminiModelId}
                    onChange={(e) => setGeminiModelId(e.target.value)}
                    placeholder="e.g. gemma-4-31b-it"
                  />
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem", display: "block" }}>
                    Powered by official <code>google-genai</code> Client: <code>client.interactions.create(model="{geminiModelId}", input=...)</code>
                  </span>
                </div>

                {/* Test button & Output */}
                <div style={{ marginBottom: "1rem" }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={handleTestGemini}
                    disabled={testingModel || (!apiKey && !secretInfo?.has_key)}
                    style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem", display: "flex", alignItems: "center", gap: "0.4rem" }}
                  >
                    <Sparkles size={14} color="var(--accent-gold)" />
                    {testingModel ? "Testing Model via google-genai..." : "Test Model & API Key Live"}
                  </button>

                  {testResult && (
                    <div style={{ marginTop: "0.75rem", background: "var(--bg-tertiary)", border: "1px solid var(--border-subtle)", borderRadius: "8px", padding: "0.75rem", fontSize: "0.8rem" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem", color: "var(--badge-emerald-text)", fontWeight: 600 }}>
                        <span>✓ Response Received ({testResult.latency_seconds}s)</span>
                        <code style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{testResult.model}</code>
                      </div>
                      <div style={{ color: "var(--text-main)", whiteSpace: "pre-wrap", lineHeight: 1.4 }}>
                        {testResult.output_text}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="form-group">
                <label className="form-label">
                  {secretInfo?.has_key ? "Rotate API Key" : "Enter API Key"}
                </label>
                <input
                  type="password"
                  className="form-input"
                  placeholder={
                    provider === "anthropic" ? "sk-ant-api03-..." :
                    "sk-..."
                  }
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem", display: "block" }}>
                  Keys are validated with a test probe before saving and encrypted at rest using Fernet.
                </span>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1.5rem" }}>
              <button className="btn-secondary" onClick={onClose}>Close</button>
              <button className="btn-primary" onClick={handleSave} disabled={loading}>
                {loading ? "Testing & Saving..." : (secretInfo?.has_key ? "Rotate & Validate" : "Validate & Save Key")}
              </button>
            </div>
          </div>
        )}

        {/* ────────────── TAB 2: PLATFORM CREDENTIALS ────────────── */}
        {activeMainTab === "platforms" && (
          <div>
            {/* Vault reassurance notice */}
            <div style={{
              background: "var(--accent-bg)",
              border: "1px solid var(--border-focus)",
              borderRadius: "8px",
              padding: "0.85rem 1rem",
              marginBottom: "1.25rem",
              display: "flex",
              alignItems: "flex-start",
              gap: "0.75rem",
            }}>
              <ShieldCheck size={20} color="var(--accent-gold)" style={{ flexShrink: 0, marginTop: "2px" }} />
              <div>
                <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--accent-gold)" }}>
                  Local Platform Credentials Vault
                </div>
                <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: "0.2rem", lineHeight: 1.45 }}>
                  Store platform login details here locally with <strong>AES-256 encryption</strong>. The auto-apply agent reads credentials directly from this vault during <code>/job-skill apply linkedin</code> — you never need to type passwords in chat.
                </div>
              </div>
            </div>

            {/* Platform Messages */}
            {liError && (
              <div style={{ background: "rgba(239, 68, 68, 0.12)", border: "1px solid rgba(239, 68, 68, 0.3)", color: "#f87171", padding: "0.65rem 0.85rem", borderRadius: "8px", fontSize: "0.85rem", marginBottom: "1rem", display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
                <AlertCircle size={16} style={{ marginTop: "2px", flexShrink: 0 }} />
                <div>{liError}</div>
              </div>
            )}

            {liSuccess && (
              <div style={{ background: "var(--badge-emerald-bg)", border: "1px solid var(--badge-emerald-border)", color: "var(--badge-emerald-text)", padding: "0.65rem 0.85rem", borderRadius: "8px", fontSize: "0.85rem", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Check size={16} /> {liSuccess}
              </div>
            )}

            {/* LinkedIn Account Card */}
            <div style={{
              background: "var(--bg-tertiary)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "10px",
              padding: "1rem",
              marginBottom: "1rem",
            }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.85rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                  <div style={{
                    width: "32px",
                    height: "32px",
                    borderRadius: "6px",
                    background: "#0a66c2",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="white"><path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.46 10.9v8.37H9.2V10.9H6.46M7.83 6.45a1.6 1.6 0 0 0-1.6 1.6 1.6 1.6 0 0 0 1.6 1.6 1.6 1.6 0 0 0 1.6-1.6 1.6 1.6 0 0 0-1.6-1.6Z"/></svg>
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.95rem", color: "var(--text-primary)" }}>LinkedIn</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Easy Apply Auto-Application Agent</div>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  {linkedinInfo?.has_credentials ? (
                    <span style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.3rem",
                      background: "var(--badge-emerald-bg)",
                      color: "var(--badge-emerald-text)",
                      border: "1px solid var(--badge-emerald-border)",
                      borderRadius: "20px",
                      padding: "0.2rem 0.65rem",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                    }}>
                      <CheckCircle2 size={12} /> Connected & Encrypted
                    </span>
                  ) : (
                    <span style={{
                      background: "var(--bg-secondary)",
                      color: "var(--text-muted)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "20px",
                      padding: "0.2rem 0.65rem",
                      fontSize: "0.75rem",
                    }}>
                      Not Configured
                    </span>
                  )}
                </div>
              </div>

              {linkedinInfo?.has_credentials && !isEditingLi ? (
                <div>
                  <div style={{
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "6px",
                    padding: "0.75rem 0.85rem",
                    marginBottom: "0.85rem",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Active Account</span>
                      <span style={{ fontSize: "0.75rem", color: "var(--accent-gold)", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                        <Lock size={12} /> AES-256 Vault
                      </span>
                    </div>
                    <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text-main)", fontFamily: "JetBrains Mono, monospace" }}>
                      {linkedinInfo.email || linkedinInfo.masked_email}
                    </div>
                    {linkedinInfo.saved_at && (
                      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                        Saved: {new Date(linkedinInfo.saved_at).toLocaleDateString()} at {new Date(linkedinInfo.saved_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    )}
                    <div style={{ marginTop: "0.5rem", paddingTop: "0.5rem", borderTop: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div style={{ fontSize: "0.75rem", color: linkedinInfo.has_cookies ? "#34d399" : "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                        <ShieldCheck size={14} />
                        <span>{linkedinInfo.has_cookies ? "Browser session cached (instant login active)" : "No cached session (agent will log in with password)"}</span>
                      </div>
                      {linkedinInfo.has_cookies && (
                        <button
                          type="button"
                          onClick={handleClearCookies}
                          disabled={liLoading}
                          style={{
                            background: "transparent",
                            border: "none",
                            color: "var(--accent-gold)",
                            fontSize: "0.72rem",
                            cursor: "pointer",
                            textDecoration: "underline",
                          }}
                          title="Clear cached browser cookies to force fresh login"
                        >
                          Clear session
                        </button>
                      )}
                    </div>
                  </div>

                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.6rem" }}>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => { setIsEditingLi(true); setLiPassword(""); }}
                      style={{ fontSize: "0.8rem", padding: "0.35rem 0.75rem", display: "flex", alignItems: "center", gap: "0.35rem" }}
                    >
                      <Edit2 size={13} /> Change Credentials
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={handleDeleteLinkedIn}
                      disabled={liLoading}
                      style={{ fontSize: "0.8rem", padding: "0.35rem 0.75rem", color: "#f87171", borderColor: "rgba(239, 68, 68, 0.3)", display: "flex", alignItems: "center", gap: "0.35rem" }}
                    >
                      <Trash2 size={13} /> Disconnect
                    </button>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleSaveLinkedIn}>
                  <div className="form-group" style={{ marginBottom: "0.75rem" }}>
                    <label className="form-label" style={{ fontSize: "0.8rem" }}>LinkedIn Email or Phone</label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="e.g. your.email@example.com"
                      value={liEmail}
                      onChange={(e) => setLiEmail(e.target.value)}
                      disabled={liLoading}
                      required
                    />
                  </div>

                  <div className="form-group" style={{ marginBottom: "0.85rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.25rem" }}>
                      <label className="form-label" style={{ fontSize: "0.8rem", marginBottom: 0 }}>LinkedIn Password</label>
                      <button
                        type="button"
                        onClick={() => setShowLiPassword(!showLiPassword)}
                        style={{
                          background: "transparent",
                          border: "none",
                          color: "var(--text-muted)",
                          fontSize: "0.75rem",
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.25rem",
                        }}
                      >
                        {showLiPassword ? <EyeOff size={13} /> : <Eye size={13} />}
                        <span>{showLiPassword ? "Hide" : "Show"}</span>
                      </button>
                    </div>
                    <div style={{ position: "relative" }}>
                      <input
                        type={showLiPassword ? "text" : "password"}
                        className="form-input"
                        placeholder="Enter LinkedIn password"
                        value={liPassword}
                        onChange={(e) => setLiPassword(e.target.value)}
                        disabled={liLoading}
                        required
                      />
                    </div>
                    <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.25rem", display: "block" }}>
                      🔒 Encrypted at rest using AES-256 in local SQLite vault. Never shared with LLMs.
                    </span>
                  </div>

                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.6rem" }}>
                    {isEditingLi && (
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => setIsEditingLi(false)}
                        disabled={liLoading}
                        style={{ fontSize: "0.8rem", padding: "0.4rem 0.85rem" }}
                      >
                        Cancel
                      </button>
                    )}
                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={liLoading || !liEmail.trim() || !liPassword.trim()}
                      style={{ fontSize: "0.8rem", padding: "0.4rem 0.95rem" }}
                    >
                      {liLoading ? "Encrypting & Saving..." : (linkedinInfo?.has_credentials ? "Update Credentials" : "Save & Connect LinkedIn")}
                    </button>
                  </div>
                </form>
              )}
            </div>

            {/* ────────────── INDEED PLATFORM CARD ────────────── */}
            <div style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "10px",
              padding: "1.2rem",
              marginTop: "1rem",
            }}>
              {/* Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <div style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "8px",
                    background: "#2164f4",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
                      <path d="M12.5 3a2.5 2.5 0 0 0-2.5 2.5v13a2.5 2.5 0 0 0 5 0v-13A2.5 2.5 0 0 0 12.5 3zM6 8a2 2 0 0 0-2 2v8a2 2 0 0 0 4 0v-8a2 2 0 0 0-2-2zm12 3a2 2 0 0 0-2 2v5a2 2 0 0 0 4 0v-5a2 2 0 0 0-2-2z"/>
                    </svg>
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.95rem", color: "var(--text-primary)" }}>Indeed</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Indeed Apply / Easily Apply Auto-Application Agent</div>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  {indeedInfo?.has_credentials ? (
                    <span style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.3rem",
                      background: "var(--badge-emerald-bg)",
                      color: "var(--badge-emerald-text)",
                      border: "1px solid var(--badge-emerald-border)",
                      borderRadius: "20px",
                      padding: "0.2rem 0.65rem",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                    }}>
                      <CheckCircle2 size={12} /> Connected & Encrypted
                    </span>
                  ) : (
                    <span style={{
                      background: "var(--bg-secondary)",
                      color: "var(--text-muted)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "20px",
                      padding: "0.2rem 0.65rem",
                      fontSize: "0.75rem",
                    }}>
                      Not Configured
                    </span>
                  )}
                </div>
              </div>

              {indeedInfo?.has_credentials && !isEditingInd ? (
                <div>
                  <div style={{
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "6px",
                    padding: "0.75rem 0.85rem",
                    marginBottom: "0.85rem",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Active Account</span>
                      <span style={{ fontSize: "0.75rem", color: "var(--accent-gold)", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                        <Lock size={12} /> AES-256 Vault
                      </span>
                    </div>
                    <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text-main)", fontFamily: "JetBrains Mono, monospace" }}>
                      {indeedInfo.email || indeedInfo.masked_email}
                    </div>
                    {indeedInfo.saved_at && (
                      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                        Saved: {new Date(indeedInfo.saved_at).toLocaleDateString()} at {new Date(indeedInfo.saved_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    )}
                    <div style={{ marginTop: "0.5rem", paddingTop: "0.5rem", borderTop: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div style={{ fontSize: "0.75rem", color: indeedInfo.has_cookies ? "#34d399" : "var(--accent-gold)", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                        <ShieldCheck size={14} />
                        <span>{indeedInfo.has_cookies ? "Browser session cached (instant login active)" : "Passwordless active (agent will request OTP code in chat)"}</span>
                      </div>
                      {indeedInfo.has_cookies && (
                        <button
                          type="button"
                          onClick={handleClearIndeedCookies}
                          disabled={indLoading}
                          style={{
                            background: "transparent",
                            border: "none",
                            color: "var(--accent-gold)",
                            fontSize: "0.72rem",
                            cursor: "pointer",
                            textDecoration: "underline",
                          }}
                          title="Clear cached browser cookies to force fresh login"
                        >
                          Clear session
                        </button>
                      )}
                    </div>
                  </div>

                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.6rem" }}>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => { setIsEditingInd(true); setIndPassword(""); }}
                      style={{ fontSize: "0.8rem", padding: "0.35rem 0.75rem", display: "flex", alignItems: "center", gap: "0.35rem" }}
                    >
                      <Edit2 size={13} /> Change Gmail
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={handleDeleteIndeed}
                      disabled={indLoading}
                      style={{ fontSize: "0.8rem", padding: "0.35rem 0.75rem", color: "#f87171", borderColor: "rgba(239, 68, 68, 0.3)", display: "flex", alignItems: "center", gap: "0.35rem" }}
                    >
                      <Trash2 size={13} /> Disconnect
                    </button>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleSaveIndeed}>
                  {indError && (
                    <div style={{ background: "rgba(239, 68, 68, 0.12)", border: "1px solid rgba(239, 68, 68, 0.3)", color: "#f87171", padding: "0.5rem 0.75rem", borderRadius: "6px", fontSize: "0.8rem", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <AlertCircle size={14} />
                      <div>{indError}</div>
                    </div>
                  )}

                  {indSuccess && (
                    <div style={{ background: "var(--badge-emerald-bg)", border: "1px solid var(--badge-emerald-border)", color: "var(--badge-emerald-text)", padding: "0.5rem 0.75rem", borderRadius: "6px", fontSize: "0.8rem", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <Check size={14} /> {indSuccess}
                    </div>
                  )}

                  <div style={{ marginBottom: "0.85rem" }}>
                    <label style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: "0.35rem" }}>
                      Indeed Gmail / Email Address
                    </label>
                    <input
                      type="email"
                      className="input-field"
                      placeholder="e.g. singhtanuj387@gmail.com"
                      value={indEmail}
                      onChange={(e) => setIndEmail(e.target.value)}
                      required
                      disabled={indLoading}
                      style={{ width: "100%", fontSize: "0.85rem", padding: "0.5rem 0.75rem" }}
                    />
                  </div>

                  <div style={{
                    background: "rgba(33, 100, 244, 0.08)",
                    border: "1px solid rgba(33, 100, 244, 0.25)",
                    borderRadius: "6px",
                    padding: "0.65rem 0.85rem",
                    fontSize: "0.76rem",
                    color: "var(--text-main)",
                    marginBottom: "0.85rem",
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "0.55rem",
                    lineHeight: "1.4",
                  }}>
                    <ShieldCheck size={16} color="#2164f4" style={{ flexShrink: 0, marginTop: "2px" }} />
                    <div>
                      <strong style={{ color: "#2164f4" }}>Passwordless 'Sign in with a code':</strong> Indeed does not require a password for Google-linked accounts. When you run <code>/job-skill apply indeed</code>, Indeed sends a 6-digit code to this email, and the agent will prompt you in chat to enter it.
                    </div>
                  </div>

                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                    {isEditingInd && (
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => setIsEditingInd(false)}
                        disabled={indLoading}
                        style={{ fontSize: "0.8rem", padding: "0.4rem 0.85rem" }}
                      >
                        Cancel
                      </button>
                    )}
                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={indLoading || !indEmail?.trim()}
                      style={{ fontSize: "0.8rem", padding: "0.4rem 0.95rem" }}
                    >
                      {indLoading ? "Saving..." : (indeedInfo?.has_credentials ? "Update Indeed Email" : "Save Indeed Gmail")}
                    </button>
                  </div>
                </form>
              )}
            </div>

            {/* ────────────── SEEK PLATFORM CARD ────────────── */}
            <div style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "10px",
              padding: "1.2rem",
              marginTop: "1rem",
            }}>
              {/* Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <div style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "8px",
                    background: "#e60278",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 800,
                    color: "#ffffff",
                    fontSize: "0.85rem",
                    letterSpacing: "0.5px",
                  }}>
                    SEK
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.95rem", color: "var(--text-primary)" }}>SEEK</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>SEEK Quick Apply Auto-Application Agent</div>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  {seekInfo?.has_credentials ? (
                    <span style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.3rem",
                      background: "var(--badge-emerald-bg)",
                      color: "var(--badge-emerald-text)",
                      border: "1px solid var(--badge-emerald-border)",
                      borderRadius: "20px",
                      padding: "0.2rem 0.65rem",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                    }}>
                      <CheckCircle2 size={12} /> Connected & Encrypted
                    </span>
                  ) : (
                    <span style={{
                      background: "var(--bg-secondary)",
                      color: "var(--text-muted)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "20px",
                      padding: "0.2rem 0.65rem",
                      fontSize: "0.75rem",
                    }}>
                      Not Configured
                    </span>
                  )}
                </div>
              </div>

              {seekInfo?.has_credentials && !isEditingSeek ? (
                <div>
                  <div style={{
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "6px",
                    padding: "0.75rem 0.85rem",
                    marginBottom: "0.85rem",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Active Account</span>
                      <span style={{ fontSize: "0.75rem", color: "var(--accent-gold)", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                        <Lock size={12} /> AES-256 Vault
                      </span>
                    </div>
                    <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text-main)", fontFamily: "JetBrains Mono, monospace" }}>
                      {seekInfo.email || seekInfo.masked_email}
                    </div>
                    {seekInfo.saved_at && (
                      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                        Saved: {new Date(seekInfo.saved_at).toLocaleDateString()} at {new Date(seekInfo.saved_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    )}
                    <div style={{ marginTop: "0.5rem", paddingTop: "0.5rem", borderTop: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div style={{ fontSize: "0.75rem", color: seekInfo.has_cookies ? "#34d399" : "var(--accent-gold)", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                        <ShieldCheck size={14} />
                        <span>{seekInfo.has_cookies ? "Browser session cached (instant login active)" : "Passwordless active (agent will request 6-digit OTP code in chat)"}</span>
                      </div>
                      {seekInfo.has_cookies && (
                        <button
                          type="button"
                          onClick={handleClearSeekCookies}
                          disabled={seekLoading}
                          style={{
                            background: "transparent",
                            border: "none",
                            color: "var(--accent-gold)",
                            fontSize: "0.72rem",
                            cursor: "pointer",
                            textDecoration: "underline",
                          }}
                          title="Clear cached browser cookies to force fresh login"
                        >
                          Clear session
                        </button>
                      )}
                    </div>
                  </div>

                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.6rem" }}>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => { setIsEditingSeek(true); setSeekPassword(""); }}
                      style={{ fontSize: "0.8rem", padding: "0.35rem 0.75rem", display: "flex", alignItems: "center", gap: "0.35rem" }}
                    >
                      <Edit2 size={13} /> Change Email
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={handleDeleteSeek}
                      disabled={seekLoading}
                      style={{ fontSize: "0.8rem", padding: "0.35rem 0.75rem", color: "#f87171", borderColor: "rgba(239, 68, 68, 0.3)", display: "flex", alignItems: "center", gap: "0.35rem" }}
                    >
                      <Trash2 size={13} /> Disconnect
                    </button>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleSaveSeek}>
                  {seekError && (
                    <div style={{ background: "rgba(239, 68, 68, 0.12)", border: "1px solid rgba(239, 68, 68, 0.3)", color: "#f87171", padding: "0.5rem 0.75rem", borderRadius: "6px", fontSize: "0.8rem", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <AlertCircle size={14} />
                      <div>{seekError}</div>
                    </div>
                  )}

                  {seekSuccess && (
                    <div style={{ background: "var(--badge-emerald-bg)", border: "1px solid var(--badge-emerald-border)", color: "var(--badge-emerald-text)", padding: "0.5rem 0.75rem", borderRadius: "6px", fontSize: "0.8rem", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <Check size={14} /> {seekSuccess}
                    </div>
                  )}

                  <div style={{ marginBottom: "0.85rem" }}>
                    <label style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: "0.35rem" }}>
                      SEEK Login Email Address
                    </label>
                    <input
                      type="email"
                      className="input-field"
                      placeholder="e.g. your.email@example.com"
                      value={seekEmail}
                      onChange={(e) => setSeekEmail(e.target.value)}
                      required
                      disabled={seekLoading}
                      style={{ width: "100%", fontSize: "0.85rem", padding: "0.5rem 0.75rem" }}
                    />
                  </div>

                  <div style={{
                    background: "rgba(230, 2, 120, 0.08)",
                    border: "1px solid rgba(230, 2, 120, 0.25)",
                    borderRadius: "6px",
                    padding: "0.65rem 0.85rem",
                    fontSize: "0.76rem",
                    color: "var(--text-main)",
                    marginBottom: "0.85rem",
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "0.55rem",
                    lineHeight: "1.4",
                  }}>
                    <ShieldCheck size={16} color="#e60278" style={{ flexShrink: 0, marginTop: "2px" }} />
                    <div>
                      <strong style={{ color: "#e60278" }}>Quick Apply &amp; Passwordless Auth:</strong> SEEK sends a 6-digit sign-in code to your email. The agent will prompt you in chat to enter it once. The agent applies <em>only</em> to on-platform Quick Apply listings, safely skipping external redirects.
                    </div>
                  </div>

                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                    {isEditingSeek && (
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => setIsEditingSeek(false)}
                        disabled={seekLoading}
                        style={{ fontSize: "0.8rem", padding: "0.4rem 0.85rem" }}
                      >
                        Cancel
                      </button>
                    )}
                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={seekLoading || !seekEmail?.trim()}
                      style={{ fontSize: "0.8rem", padding: "0.4rem 0.95rem" }}
                    >
                      {seekLoading ? "Saving..." : (seekInfo?.has_credentials ? "Update SEEK Email" : "Save SEEK Email")}
                    </button>
                  </div>
                </form>
              )}
            </div>

            {/* Other Platforms Preview */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "0.75rem",
              marginTop: "1rem",
            }}>
              <div style={{
                background: "rgba(255, 255, 255, 0.02)",
                border: "1px dashed var(--border-subtle)",
                borderRadius: "8px",
                padding: "0.85rem",
                opacity: 0.75,
              }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.3rem" }}>
                  <span style={{ fontWeight: 600, fontSize: "0.85rem", color: "var(--text-main)" }}>Naukri India</span>
                  <span style={{ fontSize: "0.68rem", background: "rgba(255,255,255,0.06)", padding: "0.15rem 0.45rem", borderRadius: "10px", color: "var(--text-muted)" }}>Coming Soon</span>
                </div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Automated 1-click FastForward apply</div>
              </div>

              <div style={{
                background: "rgba(255, 255, 255, 0.02)",
                border: "1px dashed var(--border-subtle)",
                borderRadius: "8px",
                padding: "0.85rem",
                opacity: 0.75,
              }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.3rem" }}>
                  <span style={{ fontWeight: 600, fontSize: "0.85rem", color: "var(--text-main)" }}>Glassdoor</span>
                  <span style={{ fontSize: "0.68rem", background: "rgba(255,255,255,0.06)", padding: "0.15rem 0.45rem", borderRadius: "10px", color: "var(--text-muted)" }}>Coming Soon</span>
                </div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Glassdoor Easy Apply integration</div>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "1.25rem" }}>
              <button className="btn-secondary" onClick={onClose}>Close</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
