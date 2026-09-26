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
      <div className="tracker-header">
        <div className="tracker-header-text">
          <div className="tracker-title-row">
            <h1 className="tracker-title">Application Pipeline Tracker</h1>
            <span className="tracker-total-pill">
              {entries.length} Active Positions
            </span>
          </div>
          <p className="tracker-subtitle">
            Autonomous multi-stage Kanban tracking. Discovered roles auto-sync to <strong>Found</strong> and move to <strong>Applied</strong> upon bot submission.
          </p>
        </div>
        <button
          type="button"
          className="btn-secondary"
          onClick={loadData}
          disabled={loading}
          title="Refresh pipeline status"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Pipeline Summary Metrics Strip */}
      <div className="pipeline-summary-strip">
        <div className="summary-total-metric">
          <Layers size={15} className="text-terracotta" />
          <span className="summary-label">Pipeline:</span>
          <span className="summary-count">{entries.length}</span>
        </div>
        <div className="summary-strip-divider" />
        <div className="summary-stages-list">
          {COLUMNS.map(col => {
            const count = entries.filter(e => e.status === col.id).length;
            return (
              <div key={col.id} className="summary-stage-pill">
                <span className={`summary-stage-dot ${col.badgeColor}`} />
                <span className="summary-stage-label">{col.label}:</span>
                <span className="summary-stage-num">{count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Search & Platform Filter Bar */}
      <div className="tracker-filters-bar">
        <div className="tracker-search-box">
          <Search size={14} className="tracker-search-icon" />
          <input
            type="text"
            className="tracker-search-input"
            placeholder="Search pipeline by role, company, location, or platform..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="tracker-platform-select-box">
          <Filter size={14} className="tracker-filter-icon" />
          <select
            className="tracker-select"
            value={selectedPlatform}
            onChange={(e) => setSelectedPlatform(e.target.value)}
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
        <div className="tracker-ai-alert animate-fade-in">
          <div className="ai-alert-header">
            <TrendingUp size={16} />
            <span>Auto-Improvement Calibration Alert</span>
          </div>
          <p className="ai-alert-text">
            <strong>Pattern Detected:</strong> {autoImprove.detected_pattern}
          </p>
          <p className="ai-alert-text">
            <strong>Diagnosis:</strong> {autoImprove.diagnosis}
          </p>
          <p className="ai-alert-text success">
            <strong>Action Taken:</strong> {autoImprove.action_taken}
          </p>
        </div>
      )}

      {/* Gmail Privacy Scoping Badge */}
      {privacyInfo && (
        <div className="tracker-privacy-banner">
          <div className="privacy-banner-left">
            <Mail size={16} className="text-terracotta" />
            <span>
              <strong>Gmail Scoped Sync:</strong> Search strictly restricted to verified employer domains:
              <code className="privacy-query-code">
                {privacyInfo.privacy_query.slice(0, 52)}...
              </code>
            </span>
          </div>
          <span className="privacy-badge-secure">
            <ShieldCheck size={14} /> Readonly Verified
          </span>
        </div>
      )}

      {/* Kanban Board */}
      <div className="tracker-board">
        {COLUMNS.map((col) => {
          const colEntries = filteredEntries.filter((e) => e.status === col.id);
          return (
            <div key={col.id} className="tracker-column">
              <div className="tracker-col-header">
                <div className="col-header-title">
                  <span className={`col-indicator-dot ${col.badgeColor}`} />
                  <span className="col-label-text">{col.label}</span>
                </div>
                <span className="col-count-pill">{colEntries.length}</span>
              </div>

              {/* Scrollable Column Container */}
              <div className="tracker-cards-container">
                {colEntries.length === 0 && (
                  <div className="tracker-empty-col">
                    <span>No postings in stage</span>
                  </div>
                )}
                {colEntries.map((item) => {
                  const pMeta = PLATFORM_COLORS[(item.source || '').toLowerCase()];
                  return (
                    <div key={item.id} className="tracker-card">
                      <div className="tracker-card-head">
                        <span className="tracker-card-title" title={item.title}>
                          {item.title}
                        </span>
                        {item.apply_url && (
                          <a
                            href={item.apply_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="card-ext-link"
                            title="Open verified posting"
                          >
                            <ExternalLink size={13} />
                          </a>
                        )}
                      </div>

                      <div className="tracker-card-comp">
                        {item.company} • {item.location}
                      </div>

                      {/* Source & Notes */}
                      <div className="tracker-card-tags">
                        {item.source && (
                          <span
                            className="tracker-source-pill"
                            style={{
                              color: pMeta ? pMeta.color : "var(--text-secondary)",
                              background: pMeta ? pMeta.bg : "var(--bg-tertiary)",
                              borderColor: pMeta ? `${pMeta.color}40` : "var(--border-subtle)",
                            }}
                          >
                            {pMeta ? pMeta.name : item.source.toUpperCase()}
                          </span>
                        )}
                        {item.notes && (
                          <span className="tracker-notes-text" title={item.notes}>
                            {item.notes}
                          </span>
                        )}
                      </div>

                      {/* Status Transition Control */}
                      <div className="tracker-card-footer">
                        <select
                          className="tracker-status-select"
                          value={item.status}
                          onChange={(e) => handleStatusChange(item.id, e.target.value)}
                        >
                          <option value="found">Found</option>
                          <option value="applied">Applied</option>
                          <option value="interview">Interview</option>
                          <option value="offer">Offer</option>
                          <option value="rejected">Rejected</option>
                        </select>
                        <span className="tracker-date-pill">
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
