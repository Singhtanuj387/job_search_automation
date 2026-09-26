import React, { useState, useEffect } from 'react';
import { Clock, Play, Check, AlertCircle, X, Shield } from 'lucide-react';
import { getAutomateConfig, saveAutomateConfig, runAutomateNow } from '../api';

export default function AutomateModal({ isOpen, onClose }) {
  if (!isOpen) return null;

  const [enabled, setEnabled] = useState(false);
  const [scheduleTime, setScheduleTime] = useState("08:00");
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getAutomateConfig().then((cfg) => {
      setEnabled(Boolean(cfg.enabled));
      setScheduleTime(cfg.schedule_time || "08:00");
    }).catch(console.error);
  }, [isOpen]);

  const handleSave = async () => {
    setError("");
    setMsg("");
    try {
      await saveAutomateConfig(enabled, scheduleTime, "chat");
      setMsg("Nightly automate schedule updated successfully.");
    } catch (e) {
      setError("Failed to update automate schedule.");
    }
  };

  const handleRunNow = async () => {
    setRunning(true);
    setError("");
    setMsg("");
    try {
      const res = await runAutomateNow();
      setMsg(`Execution completed! Found ${res.results_count} jobs. Check the chat feed for your morning briefing.`);
    } catch (e) {
      setError("Execution failed: " + e.message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <div className="modal-header">
          <div className="modal-title">
            <div className="page-header-icon-wrap" style={{ width: "36px", height: "36px", borderRadius: "10px" }}>
              <Clock size={18} className="text-terracotta" />
            </div>
            <span>Automated Nightly Search</span>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close dialog">
            <X size={16} />
          </button>
        </div>

        {error && (
          <div className="modal-banner error">
            <AlertCircle size={16} style={{ marginTop: "1px", flexShrink: 0 }} />
            <div>{error}</div>
          </div>
        )}

        {msg && (
          <div className="modal-banner success">
            <Check size={16} style={{ marginTop: "1px", flexShrink: 0 }} />
            <div>{msg}</div>
          </div>
        )}

        {/* Toggle Switch Card */}
        <label className="modal-switch-card">
          <div>
            <div className="switch-label-title">Enable Nightly Autonomous Scan</div>
            <div className="switch-label-desc">
              Runs while you sleep, scrapes fresh jobs, and compiles an executive morning briefing ready in Career Copilot.
            </div>
          </div>
          <div className="toggle-switch-wrapper">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            <span className="toggle-switch-slider" />
          </div>
        </label>

        <div className="form-group" style={{ marginBottom: "1.25rem" }}>
          <label className="form-label">Morning Delivery Target Time</label>
          <input
            type="time"
            className="form-input"
            value={scheduleTime}
            onChange={(e) => setScheduleTime(e.target.value)}
            style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, maxWidth: "200px" }}
          />
        </div>

        <div className="trust-card-text" style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1.75rem" }}>
          <Shield size={14} className="text-terracotta" />
          <span>Respects per-domain rate limits, jitter protection, and robots.txt Crawl-delay.</span>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
          <button className="btn-secondary" onClick={handleRunNow} disabled={running}>
            <Play size={14} />
            <span>{running ? "Running Scan..." : "Trigger Run Now"}</span>
          </button>
          <div style={{ display: "flex", gap: "0.75rem" }}>
            <button className="btn-secondary" onClick={onClose}>Cancel</button>
            <button className="btn-primary" onClick={handleSave}>
              <Check size={14} />
              <span>Save Schedule</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
