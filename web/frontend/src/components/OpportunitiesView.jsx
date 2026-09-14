import React, { useState, useEffect, useMemo } from 'react';
import {
  Compass,
  Search,
  Filter,
  RefreshCw,
  Sparkles,
  Building2,
  MapPin,
  Calendar,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  BookmarkPlus,
  BookmarkCheck,
  Layers,
  Award,
  Globe2,
  TrendingUp,
  X,
  Trash2,
  AlertTriangle,
  CheckCircle2
} from 'lucide-react';
import { getOpportunities, getOpportunitiesStats, saveOpportunityToTracker, clearAllOpportunities } from '../api';

const PLATFORM_META = {
  linkedin: { name: 'LinkedIn India', color: '#0a66c2', bg: 'rgba(10, 102, 194, 0.15)', tag: 'LI' },
  naukri: { name: 'Naukri.com', color: '#275df5', bg: 'rgba(39, 93, 245, 0.15)', tag: 'NK' },
  instahyre: { name: 'Instahyre', color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', tag: 'INS' },
  cutshort: { name: 'Cutshort', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.15)', tag: 'CS' },
  weworkremotely: { name: 'WeWorkRemotely', color: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.15)', tag: 'WWR' },
  hirist: { name: 'Hirist', color: '#06b6d4', bg: 'rgba(6, 182, 212, 0.15)', tag: 'HIR' },
  indeed: { name: 'Indeed India', color: '#6366f1', bg: 'rgba(99, 102, 241, 0.15)', tag: 'IND' },
  wellfound: { name: 'Wellfound', color: '#ea580c', bg: 'rgba(234, 88, 12, 0.15)', tag: 'WF' },
  greenhouse: { name: 'Greenhouse ATS', color: '#14b8a6', bg: 'rgba(20, 184, 166, 0.15)', tag: 'GH' },
  lever: { name: 'Lever ATS', color: '#84cc16', bg: 'rgba(132, 204, 22, 0.15)', tag: 'LEV' },
  foundit: { name: 'Foundit', color: '#a855f7', bg: 'rgba(168, 85, 247, 0.15)', tag: 'FND' },
  shine: { name: 'Shine.com', color: '#ec4899', bg: 'rgba(236, 72, 153, 0.15)', tag: 'SHN' },
  glassdoor: { name: 'Glassdoor', color: '#22c55e', bg: 'rgba(34, 197, 94, 0.15)', tag: 'GLS' },
  timesjobs: { name: 'TimesJobs', color: '#f43f5e', bg: 'rgba(244, 63, 94, 0.15)', tag: 'TJ' },
  arbeitnow: { name: 'Arbeitnow', color: '#38bdf8', bg: 'rgba(56, 189, 248, 0.15)', tag: 'ARB' },
  jobicy: { name: 'Jobicy', color: '#d946ef', bg: 'rgba(217, 70, 239, 0.15)', tag: 'JBC' },
  remotive: { name: 'Remotive', color: '#eab308', bg: 'rgba(234, 179, 8, 0.15)', tag: 'REM' },
  career_jsonld: { name: 'Direct Career Pages', color: '#94a3b8', bg: 'rgba(148, 163, 184, 0.15)', tag: 'DIR' },
};

export default function OpportunitiesView({ onOpenChat = null }) {
  const [opportunities, setOpportunities] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPlatform, setSelectedPlatform] = useState('all');
  const [minScoreFilter, setMinScoreFilter] = useState('all'); // 'all' | '90' | '75' | '60'
  const [pageSize, setPageSize] = useState(25);
  const [currentPage, setCurrentPage] = useState(1);

  // Saved Map for Tracker
  const [savedMap, setSavedMap] = useState({});

  // Clear Opportunities Modal
  const [showClearModal, setShowClearModal] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [clearError, setClearError] = useState(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [opps, st] = await Promise.all([
        getOpportunities(),
        getOpportunitiesStats(),
      ]);
      setOpportunities(opps);
      setStats(st);
    } catch (err) {
      console.error("Failed to load opportunities:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Compute Platform Counts from opportunities
  const platformCounts = useMemo(() => {
    const counts = { all: opportunities.length };
    opportunities.forEach(opp => {
      const src = (opp.source || 'web').toLowerCase();
      counts[src] = (counts[src] || 0) + 1;
    });
    return counts;
  }, [opportunities]);

  // Filtered Opportunities
  const filteredOpportunities = useMemo(() => {
    return opportunities.filter(opp => {
      // Platform filter
      if (selectedPlatform !== 'all' && (opp.source || '').toLowerCase() !== selectedPlatform) {
        return false;
      }
      // Min score filter
      if (minScoreFilter !== 'all') {
        const threshold = parseInt(minScoreFilter, 10);
        if ((opp.fitness_score || 0) < threshold) return false;
      }
      // Search text query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const titleMatch = (opp.title || '').toLowerCase().includes(q);
        const compMatch = (opp.company || '').toLowerCase().includes(q);
        const locMatch = (opp.location || '').toLowerCase().includes(q);
        const descMatch = (opp.match_explanation || '').toLowerCase().includes(q);
        const idMatch = (opp.source_job_id || '').toLowerCase().includes(q);
        if (!titleMatch && !compMatch && !locMatch && !descMatch && !idMatch) {
          return false;
        }
      }
      return true;
    });
  }, [opportunities, selectedPlatform, minScoreFilter, searchQuery]);

  // Reset pagination when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, selectedPlatform, minScoreFilter, pageSize]);

  // Pagination calculation
  const totalPages = pageSize === 'all' ? 1 : Math.max(1, Math.ceil(filteredOpportunities.length / pageSize));
  const activePage = Math.min(currentPage, totalPages);

  const paginatedOpportunities = useMemo(() => {
    if (pageSize === 'all') return filteredOpportunities;
    const start = (activePage - 1) * pageSize;
    return filteredOpportunities.slice(start, start + pageSize);
  }, [filteredOpportunities, activePage, pageSize]);

  // Handle Save to Tracker
  const handleSaveToTracker = async (opp) => {
    try {
      const res = await saveOpportunityToTracker(opp.id);
      setSavedMap(prev => ({
        ...prev,
        [opp.id]: true
      }));
    } catch (err) {
      console.error("Save to tracker failed:", err);
    }
  };

  // Handle Clear All Opportunities
  const handleClearAll = async () => {
    setClearing(true);
    setClearError(null);
    try {
      await clearAllOpportunities(true);
      setShowClearModal(false);
      setOpportunities([]);
      await loadData();
    } catch (err) {
      console.error("Failed to clear opportunities:", err);
      setClearError(err.message || "Failed to clear opportunities");
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="opportunities-view">
      {/* Top Header Bar */}
      <div className="opportunities-header">
        <div className="header-text">
          <div className="header-title-row">
            <h1 className="opportunities-title">Total Job Opportunities</h1>
            <span className="live-opportunities-pill">
              {opportunities.length} Total Discovered
            </span>
          </div>
          <p className="opportunities-subtitle">
            Persistent aggregate catalog of all unique jobs discovered across 18 verified platforms & searches.
          </p>
        </div>

        <div className="header-actions">
          {onOpenChat && (
            <button
              type="button"
              className="btn-primary"
              onClick={onOpenChat}
              style={{ padding: "0.45rem 0.85rem", fontSize: "0.82rem" }}
            >
              <Search size={14} /> Run New Search
            </button>
          )}
          <button
            type="button"
            className="btn-secondary"
            onClick={loadData}
            disabled={loading}
            title="Refresh opportunities list"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            <span>Refresh</span>
          </button>
          <button
            type="button"
            className="btn-danger-outline"
            onClick={() => {
              setClearError(null);
              setShowClearModal(true);
            }}
            disabled={loading || opportunities.length === 0}
            title="Clear all stored job opportunities"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              fontSize: "0.82rem",
              padding: "0.45rem 0.85rem",
              borderRadius: "var(--radius-md)",
              border: "1px solid rgba(239, 68, 68, 0.35)",
              background: "rgba(239, 68, 68, 0.08)",
              color: "#f87171",
              cursor: (loading || opportunities.length === 0) ? "not-allowed" : "pointer",
              transition: "all 0.15s ease",
            }}
          >
            <Trash2 size={14} />
            <span>Clear All</span>
          </button>
        </div>
      </div>

      {/* 4 Metric Stat Cards */}
      <div className="opp-stats-grid">
        <div className="opp-stat-card">
          <div className="stat-card-icon gold">
            <Globe2 size={20} />
          </div>
          <div className="stat-card-body">
            <span className="stat-card-value">{stats?.total_opportunities ?? opportunities.length}</span>
            <span className="stat-card-label">Total Discovered Roles</span>
          </div>
        </div>

        <div className="opp-stat-card">
          <div className="stat-card-icon emerald">
            <Award size={20} />
          </div>
          <div className="stat-card-body">
            <span className="stat-card-value">{stats?.exceptional_count ?? 0}</span>
            <span className="stat-card-label">Exceptional Matches (≥90%)</span>
          </div>
        </div>

        <div className="opp-stat-card">
          <div className="stat-card-icon blue">
            <TrendingUp size={20} />
          </div>
          <div className="stat-card-body">
            <span className="stat-card-value">{stats?.high_match_count ?? 0}</span>
            <span className="stat-card-label">Strong Matches (≥75%)</span>
          </div>
        </div>

        <div className="opp-stat-card">
          <div className="stat-card-icon purple">
            <Layers size={20} />
          </div>
          <div className="stat-card-body">
            <span className="stat-card-value">{stats?.platforms_count ?? Object.keys(platformCounts).length - 1}</span>
            <span className="stat-card-label">Active Sourced Platforms</span>
          </div>
        </div>
      </div>

      {/* Interactive Controls & Filters Toolbar */}
      <div className="opp-toolbar">
        <div className="toolbar-top">
          {/* Search-as-you-type input */}
          <div className="opp-search-box">
            <Search size={15} className="opp-search-icon" />
            <input
              type="text"
              className="opp-search-input"
              placeholder="Filter by title, company, technology, location, or Job ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button
                type="button"
                className="btn-clear-search"
                onClick={() => setSearchQuery('')}
              >
                <X size={13} />
              </button>
            )}
          </div>

          {/* Fitness Tier Filter Pills */}
          <div className="opp-tier-pills">
            <button
              type="button"
              className={`opp-tier-pill ${minScoreFilter === 'all' ? 'active' : ''}`}
              onClick={() => setMinScoreFilter('all')}
            >
              All Matches
            </button>
            <button
              type="button"
              className={`opp-tier-pill emerald ${minScoreFilter === '90' ? 'active' : ''}`}
              onClick={() => setMinScoreFilter('90')}
            >
              ≥90% Exceptional
            </button>
            <button
              type="button"
              className={`opp-tier-pill blue ${minScoreFilter === '75' ? 'active' : ''}`}
              onClick={() => setMinScoreFilter('75')}
            >
              ≥75% Strong
            </button>
            <button
              type="button"
              className={`opp-tier-pill amber ${minScoreFilter === '60' ? 'active' : ''}`}
              onClick={() => setMinScoreFilter('60')}
            >
              ≥60% Alignment
            </button>
          </div>
        </div>

        {/* Platform Filter Pills */}
        <div className="opp-platform-pills">
          <button
            type="button"
            className={`platform-chip ${selectedPlatform === 'all' ? 'active' : ''}`}
            onClick={() => setSelectedPlatform('all')}
          >
            All Platforms ({platformCounts.all || 0})
          </button>

          {Object.entries(platformCounts)
            .filter(([key]) => key !== 'all')
            .sort((a, b) => b[1] - a[1])
            .map(([srcKey, count]) => {
              const meta = PLATFORM_META[srcKey] || { name: srcKey.toUpperCase(), tag: srcKey.slice(0, 3).toUpperCase() };
              return (
                <button
                  key={srcKey}
                  type="button"
                  className={`platform-chip ${selectedPlatform === srcKey ? 'active' : ''}`}
                  onClick={() => setSelectedPlatform(srcKey)}
                >
                  <span className="platform-tag-mini">{meta.tag}</span>
                  <span>{meta.name}</span>
                  <span className="platform-count-bubble">{count}</span>
                </button>
              );
            })}
        </div>
      </div>

      {/* Main Results Table */}
      <div className="opp-table-card">
        <div className="opp-table-header-bar">
          <div className="table-summary-info">
            Showing <strong>{filteredOpportunities.length}</strong> of <strong>{opportunities.length}</strong> unique opportunities
            {selectedPlatform !== 'all' && ` • Platform: ${PLATFORM_META[selectedPlatform]?.name || selectedPlatform}`}
            {minScoreFilter !== 'all' && ` • Score ≥ ${minScoreFilter}%`}
          </div>

          {/* Page size picker */}
          <div className="page-size-selector">
            <span className="page-size-label">Rows per page:</span>
            {[10, 25, 50, 'all'].map(size => (
              <button
                key={size}
                type="button"
                className={`btn-page-size ${pageSize === size ? 'active' : ''}`}
                onClick={() => setPageSize(size)}
              >
                {size === 'all' ? 'All' : size}
              </button>
            ))}
          </div>
        </div>

        {filteredOpportunities.length === 0 ? (
          <div className="opp-empty-state">
            <Compass size={36} color="var(--accent-gold)" style={{ opacity: 0.6, marginBottom: "0.75rem" }} />
            <h3 style={{ fontSize: "1rem", color: "var(--text-primary)", marginBottom: "0.3rem" }}>
              No matching job opportunities found
            </h3>
            <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
              Try adjusting your search keyword, platform filter, or score thresholds.
            </p>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setSearchQuery('');
                setSelectedPlatform('all');
                setMinScoreFilter('all');
              }}
            >
              Reset Filters
            </button>
          </div>
        ) : (
          <div className="job-table-scroll-container">
            <table className="job-matrix-table">
              <thead>
                <tr>
                  <th style={{ width: "40px", textAlign: "center" }}>#</th>
                  <th style={{ minWidth: "200px" }}>Job Title</th>
                  <th style={{ minWidth: "140px" }}>Company</th>
                  <th style={{ minWidth: "90px" }}>Job ID</th>
                  <th style={{ minWidth: "120px" }}>Platform</th>
                  <th style={{ minWidth: "110px" }}>Location</th>
                  <th style={{ minWidth: "95px" }}>Date</th>
                  <th style={{ minWidth: "155px" }}>Fitness Score</th>
                  <th style={{ width: "110px", textAlign: "center" }}>Direct Apply</th>
                  <th style={{ width: "80px", textAlign: "center" }}>Track</th>
                </tr>
              </thead>
              <tbody>
                {paginatedOpportunities.map((opp, idx) => {
                  const globalIdx = pageSize === 'all' ? idx + 1 : (activePage - 1) * pageSize + idx + 1;
                  const srcMeta = PLATFORM_META[opp.source] || {
                    name: opp.source ? opp.source.toUpperCase() : 'WEB',
                    color: '#f59e0b',
                    bg: 'rgba(245, 158, 11, 0.15)',
                    tag: opp.source ? opp.source.slice(0, 3).toUpperCase() : 'JOB'
                  };

                  const isSaved = savedMap[opp.id];
                  const jid = opp.source_job_id || `${opp.source ? opp.source.slice(0, 3).toUpperCase() : 'JOB'}-${opp.id}`;
                  const fitScore = opp.fitness_score || 75;
                  const fitBadgeColor = opp.fit_badge_color || (fitScore >= 90 ? 'emerald' : fitScore >= 75 ? 'emerald' : 'amber');

                  return (
                    <tr key={opp.id} className="job-row-item">
                      <td style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.76rem" }}>
                        {globalIdx}
                      </td>

                      <td>
                        <div className="job-title-cell">
                          <span className="job-title-text" title={opp.title}>
                            {opp.title}
                          </span>
                        </div>
                      </td>

                      <td>
                        <div className="job-company-cell">
                          <Building2 size={12} className="company-icon" />
                          <span className="company-name-text" title={opp.company}>
                            {opp.company}
                          </span>
                        </div>
                      </td>

                      <td>
                        <code className="job-id-code" title={jid}>
                          {jid}
                        </code>
                      </td>

                      <td>
                        <span
                          className="table-platform-badge"
                          style={{
                            color: srcMeta.color,
                            backgroundColor: srcMeta.bg,
                            borderColor: `${srcMeta.color}40`,
                          }}
                        >
                          <span className="badge-tag">{srcMeta.tag}</span>
                          <span className="badge-name">{srcMeta.name}</span>
                        </span>
                      </td>

                      <td>
                        <div className="job-location-cell">
                          <MapPin size={11} className="loc-icon" />
                          <span>{opp.location || 'Remote'}</span>
                        </div>
                      </td>

                      <td>
                        <div className="job-date-cell">
                          <Calendar size={11} className="date-icon" />
                          <span>{opp.posted_date || 'Recently'}</span>
                        </div>
                      </td>

                      <td>
                        <div className={`fitness-score-pill ${fitBadgeColor}`} title={opp.fit_reason || opp.match_explanation}>
                          <Sparkles size={11} className="sparkle-score-icon" />
                          <span className="score-number">{fitScore}% Fit</span>
                          <span className="score-framing">({opp.fit_framing || 'Strong Match'})</span>
                        </div>
                      </td>

                      <td style={{ textAlign: "center" }}>
                        {opp.apply_url ? (
                          <a
                            href={opp.apply_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="btn-table-action apply"
                            title="Open direct job application"
                          >
                            <span>Apply</span>
                            <ExternalLink size={10} />
                          </a>
                        ) : (
                          <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>—</span>
                        )}
                      </td>

                      <td style={{ textAlign: "center" }}>
                        <button
                          type="button"
                          className={`btn-table-action bookmark ${isSaved ? 'saved' : ''}`}
                          onClick={() => handleSaveToTracker(opp)}
                          title={isSaved ? "Saved to Application Tracker" : "Save to Application Tracker"}
                        >
                          {isSaved ? <BookmarkCheck size={13} color="#34d399" /> : <BookmarkPlus size={13} />}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {pageSize !== 'all' && totalPages > 1 && (
          <div className="table-pagination-footer">
            <span className="pagination-info">
              Page <strong>{activePage}</strong> of <strong>{totalPages}</strong> ({filteredOpportunities.length} items)
            </span>

            <div className="pagination-buttons">
              <button
                type="button"
                className="btn-page-nav"
                disabled={activePage <= 1}
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              >
                <ChevronLeft size={14} /> Previous
              </button>

              <div className="page-number-chips">
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  let pageNum;
                  if (totalPages <= 5) {
                    pageNum = i + 1;
                  } else if (activePage <= 3) {
                    pageNum = i + 1;
                  } else if (activePage >= totalPages - 2) {
                    pageNum = totalPages - 4 + i;
                  } else {
                    pageNum = activePage - 2 + i;
                  }
                  return (
                    <button
                      key={pageNum}
                      type="button"
                      className={`btn-page-num ${activePage === pageNum ? 'active' : ''}`}
                      onClick={() => setCurrentPage(pageNum)}
                    >
                      {pageNum}
                    </button>
                  );
                })}
              </div>

              <button
                type="button"
                className="btn-page-nav"
                disabled={activePage >= totalPages}
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              >
                Next <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Clear Confirmation Modal */}
      {showClearModal && (
        <div className="modal-overlay" style={{ zIndex: 1100 }}>
          <div className="modal-content" style={{ maxWidth: "450px" }}>
            <div className="modal-header" style={{ borderBottom: "1px solid var(--border-subtle)", padding: "1rem 1.25rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", color: "#f87171" }}>
                <AlertTriangle size={20} />
                <h3 style={{ fontSize: "1.05rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>Clear All Opportunities?</h3>
              </div>
              <button
                type="button"
                className="modal-close"
                onClick={() => setShowClearModal(false)}
                title="Close"
              >
                <X size={16} />
              </button>
            </div>

            <div style={{ padding: "1.25rem" }}>
              <p style={{ fontSize: "0.88rem", color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: "1rem" }}>
                This will clear all <strong>{opportunities.length}</strong> discovered job opportunities from the catalog and clean up unapplied listings from your pipeline.
              </p>

              <div style={{
                background: "var(--badge-emerald-bg)",
                border: "1px solid var(--badge-emerald-border)",
                borderRadius: "var(--radius-md)",
                padding: "0.75rem 1rem",
                fontSize: "0.8rem",
                color: "var(--badge-emerald-text)",
                marginBottom: "1.25rem",
                display: "flex",
                alignItems: "flex-start",
                gap: "0.5rem"
              }}>
                <CheckCircle2 size={16} style={{ flexShrink: 0, marginTop: "2px" }} />
                <span><strong>Applied jobs are safe:</strong> Any applications already submitted or moved to interview/offer in your Application Tracker will remain completely untouched.</span>
              </div>

              {clearError && (
                <div style={{
                  background: "rgba(239, 68, 68, 0.12)",
                  border: "1px solid rgba(239, 68, 68, 0.3)",
                  borderRadius: "var(--radius-md)",
                  padding: "0.6rem 0.8rem",
                  color: "#f87171",
                  fontSize: "0.82rem",
                  marginBottom: "1.25rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem"
                }}>
                  <AlertTriangle size={15} style={{ flexShrink: 0 }} />
                  <span>{clearError}</span>
                </div>
              )}

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowClearModal(false)}
                  disabled={clearing}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={handleClearAll}
                  disabled={clearing}
                  style={{
                    background: "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)",
                    borderColor: "#ef4444",
                    color: "#fff",
                    boxShadow: "0 2px 8px rgba(239, 68, 68, 0.35)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.4rem",
                  }}
                >
                  {clearing ? (
                    <>
                      <RefreshCw size={14} className="spin" />
                      <span>Clearing...</span>
                    </>
                  ) : (
                    <>
                      <Trash2 size={14} />
                      <span>Yes, Clear All</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

