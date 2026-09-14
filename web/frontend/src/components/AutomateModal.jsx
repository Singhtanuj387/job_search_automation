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
          <div className="modal-title" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Clock size={20} color="var(--accent-gold)" /> Automated Nightly Search
          </div>
          <button className="close-btn" onClick={onClose}><X size={18} /></button>
        </div>

        {error && (
          <div style={{ background: "rgba(239, 68, 68, 0.12)", border: "1px solid rgba(239, 68, 68, 0.3)", color: "#f87171", padding: "0.65rem 0.85rem", borderRadius: "8px", fontSize: "0.85rem", marginBottom: "1rem" }}>
            {error}
          </div>
        )}

        {msg && (
          <div style={{ background: "rgba(16, 185, 129, 0.12)", border: "1px solid rgba(16, 185, 129, 0.3)", color: "#34d399", padding: "0.65rem 0.85rem", borderRadius: "8px", fontSize: "0.85rem", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Check size={16} /> {msg}
          </div>
        )}

        <div style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", padding: "1rem", marginBottom: "1.25rem" }}>
          <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.95rem" }}>Enable Nightly Automated Scan</div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                Runs while you sleep and generates a tailored morning report ready when you open the app.
              </div>
            </div>
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              style={{ width: "20px", height: "20px", accentColor: "var(--accent-gold)", cursor: "pointer" }}
            />
          </label>
        </div>

        <div className="form-group">
          <label className="form-label">Morning Delivery Time</label>
          <input
            type="time"
            className="form-input"
            value={scheduleTime}
            onChange={(e) => setScheduleTime(e.target.value)}
          />
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "1.5rem" }}>
          <Shield size={14} color="var(--accent-gold)" /> Respects per-domain rate limits, jitter, and robots.txt Crawl-delay.
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <button className="btn-secondary" onClick={handleRunNow} disabled={running}>
            <Play size={14} /> {running ? "Running Scan..." : "Trigger Run Now"}
          </button>
          <div style={{ display: "flex", gap: "0.75rem" }}>
            <button className="btn-secondary" onClick={onClose}>Cancel</button>
            <button className="btn-primary" onClick={handleSave}>Save Schedule</button>
          </div>
        </div>
      </div>
    </div>
  );
}
