import React, { useState, useEffect, useMemo } from 'react';
import { Briefcase, ExternalLink, ShieldCheck, TrendingUp, RefreshCw, Mail, Search, Filter, Layers, CheckCircle2 } from 'lucide-react';
import { getTracker, updateTrackerStatus, getAutoImprovement, getGmailPrivacyQuery } from '../api';

const COLUMNS = [
  { id: "found", label: "Found", badgeColor: "blue", headerBg: "var(--badge-blue-bg)" },
  { id: "applied", label: "Applied", badgeColor: "amber", headerBg: "var(--badge-amber-bg)" },
  { id: "interview", label: "Interviewing", badgeColor: "emerald", headerBg: "var(--badge-emerald-bg)" },
  { id: "offer", label: "Offer", badgeColor: "emerald", headerBg: "var(--badge-emerald-bg)" },
  { id: "rejected", label: "Rejected", badgeColor: "slate", headerBg: "var(--bg-tertiary)" },
];

const PLATFORM_COLORS = {
  linkedin: { color: '#0a66c2', bg: 'rgba(10, 102, 194, 0.15)', name: 'LinkedIn' },
  greenhouse: { color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', name: 'Greenhouse' },
  naukri: { color: '#2563eb', bg: 'rgba(37, 99, 235, 0.15)', name: 'Naukri' },
  instahyre: { color: '#059669', bg: 'rgba(5, 150, 105, 0.15)', name: 'Instahyre' },
  weworkremotely: { color: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.15)', name: 'WeWorkRemotely' },
  arbeitnow: { color: '#0284c7', bg: 'rgba(2, 132, 199, 0.15)', name: 'Arbeitnow' },
  cutshort: { color: '#d97706', bg: 'rgba(217, 119, 6, 0.15)', name: 'Cutshort' },
  jobicy: { color: '#c026d3', bg: 'rgba(192, 38, 211, 0.15)', name: 'Jobicy' },
  indeed: { color: '#4f46e5', bg: 'rgba(79, 70, 229, 0.15)', name: 'Indeed' },
  wellfound: { color: '#ea580c', bg: 'rgba(234, 88, 12, 0.15)', name: 'Wellfound' },
  glassdoor: { color: '#16a34a', bg: 'rgba(22, 163, 74, 0.15)', name: 'Glassdoor' },
  timesjobs: { color: '#f43f5e', bg: 'rgba(244, 63, 94, 0.15)', name: 'TimesJobs' },
  hirist: { color: '#0891b2', bg: 'rgba(8, 145, 178, 0.15)', name: 'Hirist' },
  seek: { color: '#e60278', bg: 'rgba(230, 2, 120, 0.15)', name: 'SEEK' },
};

export default function TrackerView() {
  const [entries, setEntries] = useState([]);
  const [autoImprove, setAutoImprove] = useState(null);
  const [privacyInfo, setPrivacyInfo] = useState(null);
  const [loading, setLoading] = useState(true);

  // Search & Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPlatform, setSelectedPlatform] = useState('all');

  const loadData = async () => {
    setLoading(true);
    try {
      const [list, ai, priv] = await Promise.all([
        getTracker(),
        getAutoImprovement(),
        getGmailPrivacyQuery(),
      ]);
      setEntries(list);
      setAutoImprove(ai.has_recommendations ? ai.analysis : null);
      setPrivacyInfo(priv);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleStatusChange = async (id, newStatus) => {
    try {
      await updateTrackerStatus(id, newStatus);
      await loadData();
    } catch (e) {
      console.error(e);
    }
  };

  // Get available platform options from current entries
  const availablePlatforms = useMemo(() => {
    const set = new Set();
    entries.forEach(e => {
      const s = (e.source || '').trim().toLowerCase();
      if (s) set.add(s);
    });
    return Array.from(set).sort();
  }, [entries]);

  // Filter entries
  const filteredEntries = useMemo(() => {
    return entries.filter(item => {
      if (selectedPlatform !== 'all') {
        const src = (item.source || '').trim().toLowerCase();
        if (src !== selectedPlatform.toLowerCase()) return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const t = (item.title || '').toLowerCase();
        const c = (item.company || '').toLowerCase();
        const l = (item.location || '').toLowerCase();
        const s = (item.source || '').toLowerCase();
        if (!t.includes(q) && !c.includes(q) && !l.includes(q) && !s.includes(q)) {
          return false;
        }
      }
      return true;
    });
  }, [entries, selectedPlatform, searchQuery]);

  return (
    <div className="tracker-view">
      {/* Top Header Bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
        <div>
          <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--text-primary)" }}>Application Pipeline</h2>
          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginTop: "0.2rem" }}>
            Real-time pipeline: all discovered opportunities appear in <strong>Found</strong>, and automatically move to <strong>Applied</strong> when submitted.
          </p>
        </div>
        <button className="btn-secondary" onClick={loadData} disabled={loading}>
          <RefreshCw size={14} className={loading ? "spin" : ""} /> Refresh
        </button>
      </div>

      {/* Pipeline Summary Metrics Banner */}
      <div style={{
        display: "flex",
        gap: "0.75rem",
        flexWrap: "wrap",
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-md)",
        padding: "0.75rem 1rem",
        marginBottom: "1.25rem",
        alignItems: "center",
      }}>
        <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", fontWeight: 600, display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <Layers size={15} color="var(--accent-gold)" /> Pipeline Total:
          <span style={{ color: "var(--text-primary)", fontWeight: 700 }}>{entries.length}</span>
        </div>
        <div style={{ width: "1px", height: "16px", background: "var(--border-subtle)" }} />
        {COLUMNS.map(col => {
          const count = entries.filter(e => e.status === col.id).length;
          return (
            <div key={col.id} style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8rem" }}>
              <span style={{ color: "var(--text-muted)" }}>{col.label}:</span>
              <span className={`fit-badge ${col.badgeColor}`} style={{ fontSize: "0.75rem", padding: "1px 6px" }}>{count}</span>
            </div>
          );
        })}
      </div>

      {/* Search & Platform Filter Bar */}
      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginBottom: "1.25rem", alignItems: "center" }}>
        <div style={{ position: "relative", flex: "1 1 240px" }}>
          <Search size={14} style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
          <input
            type="text"
            className="form-input"
            placeholder="Search pipeline by role, company, or platform..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ paddingLeft: "32px", fontSize: "0.85rem", height: "36px" }}
          />
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Filter size={14} color="var(--text-muted)" />
          <select
            className="form-select"
            value={selectedPlatform}
            onChange={(e) => setSelectedPlatform(e.target.value)}
            style={{ fontSize: "0.85rem", height: "36px", padding: "0 2rem 0 0.75rem" }}
          >
            <option value="all">All Platforms ({entries.length})</option>
            {availablePlatforms.map(p => {
              const pCount = entries.filter(e => (e.source || '').toLowerCase() === p).length;
              const meta = PLATFORM_COLORS[p];
              return (
                <option key={p} value={p}>
                  {meta ? meta.name : p.toUpperCase()} ({pCount})
                </option>
              );
            })}
          </select>
        </div>
      </div>

      {/* Auto-Improvement Diagnostic Alert */}
      {autoImprove && (
        <div style={{ background: "rgba(245, 158, 11, 0.1)", border: "1px solid rgba(245, 158, 11, 0.3)", borderRadius: "var(--radius-md)", padding: "1rem", marginBottom: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--accent-gold)", fontWeight: 600, fontSize: "0.9rem", marginBottom: "0.4rem" }}>
            <TrendingUp size={16} /> Auto-Improvement Calibration Alert
          </div>
          <p style={{ fontSize: "0.85rem", color: "var(--text-primary)", marginBottom: "0.4rem" }}>
            <strong>Pattern Detected:</strong> {autoImprove.detected_pattern}
          </p>
          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.4rem" }}>
            <strong>Diagnosis:</strong> {autoImprove.diagnosis}
          </p>
          <p style={{ fontSize: "0.85rem", color: "#34d399" }}>
            <strong>Action Taken:</strong> {autoImprove.action_taken}
          </p>
        </div>
      )}

      {/* Gmail Privacy Scoping Badge */}
      {privacyInfo && (
        <div style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", padding: "0.75rem 1rem", marginBottom: "1.25rem", display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "0.8rem", boxShadow: "0 1px 3px rgba(0, 0, 0, 0.04)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--text-secondary)" }}>
            <Mail size={16} color="var(--accent-gold)" />
            <span>
              <strong>Gmail Scope Guarantee:</strong> Search queries strictly restricted to tracked employers:
              <code style={{ marginLeft: "0.4rem", color: "var(--text-primary)", background: "var(--bg-tertiary)", padding: "2px 6px", borderRadius: "4px", border: "1px solid var(--border-subtle)" }}>
                {privacyInfo.privacy_query.slice(0, 50)}...
              </code>
            </span>
          </div>
          <span style={{ display: "flex", alignItems: "center", gap: "0.3rem", color: "var(--badge-emerald-text)", fontWeight: 600 }}>
            <ShieldCheck size={14} /> Readonly
          </span>
        </div>
      )}

      {/* Kanban Columns */}
      <div className="tracker-board" style={{ overflowX: "auto", paddingBottom: "1rem" }}>
        {COLUMNS.map((col) => {
          const colEntries = filteredEntries.filter((e) => e.status === col.id);
          return (
            <div key={col.id} className="tracker-column" style={{ minWidth: "260px" }}>
              <div className="tracker-col-header" style={{ background: col.headerBg, padding: "0.5rem 0.75rem", borderRadius: "var(--radius-md)", marginBottom: "0.5rem" }}>
                <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  {col.label}
                </span>
                <span className={`fit-badge ${col.badgeColor}`}>{colEntries.length}</span>
              </div>

              {/* Scrollable Column Container */}
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", maxHeight: "68vh", overflowY: "auto", paddingRight: "4px" }}>
                {colEntries.length === 0 && (
                  <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontStyle: "italic", textAlign: "center", padding: "2rem 0" }}>
                    No postings in this stage
                  </div>
                )}
                {colEntries.map((item) => {
                  const pMeta = PLATFORM_COLORS[(item.source || '').toLowerCase()];
                  return (
                    <div key={item.id} className="tracker-card">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                        <div className="tracker-card-title" title={item.title}>
                          {item.title}
                        </div>
                        {item.apply_url && (
                          <a href={item.apply_url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--text-muted)", flexShrink: 0 }} title="Open Job Posting">
                            <ExternalLink size={13} />
                          </a>
                        )}
                      </div>

                      <div className="tracker-card-comp">{item.company} • {item.location}</div>

                      {/* Source & Notes */}
                      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap", marginTop: "0.2rem" }}>
                        {item.source && (
                          <span style={{
                            fontSize: "0.7rem",
                            fontWeight: 600,
                            padding: "1px 6px",
                            borderRadius: "4px",
                            color: pMeta ? pMeta.color : "var(--text-muted)",
                            background: pMeta ? pMeta.bg : "var(--bg-primary)",
                            border: `1px solid ${pMeta ? pMeta.color + '40' : 'var(--border-subtle)'}`,
                          }}>
                            {pMeta ? pMeta.name : item.source.toUpperCase()}
                          </span>
                        )}
                        {item.notes && (
                          <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontStyle: "italic", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "160px" }} title={item.notes}>
                            {item.notes}
                          </span>
                        )}
                      </div>

                      {/* Status Transition Control */}
                      <div style={{ marginTop: "0.5rem", display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid var(--border-subtle)", paddingTop: "0.4rem" }}>
                        <select
                          className="form-select"
                          style={{ padding: "0.2rem 0.4rem", fontSize: "0.75rem", width: "auto" }}
                          value={item.status}
                          onChange={(e) => handleStatusChange(item.id, e.target.value)}
                        >
                          <option value="found">Found</option>
                          <option value="applied">Applied</option>
                          <option value="interview">Interview</option>
                          <option value="offer">Offer</option>
                          <option value="rejected">Rejected</option>
                        </select>
                        <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                          {item.status_updated_at ? item.status_updated_at.slice(0, 10) : ""}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
