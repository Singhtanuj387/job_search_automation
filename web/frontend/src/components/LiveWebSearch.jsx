import React, { useState, useEffect, useRef } from 'react';
import {
  Globe,
  Loader2,
  CheckCircle2,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Building2,
  Sparkles,
  MapPin,
  Terminal,
  Copy,
  Check,
  CheckCheck,
  FileCheck2,
  Layers,
  Cpu,
  Search
} from 'lucide-react';

const PLATFORM_META = {
  linkedin: { name: 'LinkedIn India', color: '#0a66c2', bg: 'rgba(10, 102, 194, 0.15)', tag: 'LI', cat: 'Indian Portals' },
  naukri: { name: 'Naukri.com', color: '#275df5', bg: 'rgba(39, 93, 245, 0.15)', tag: 'NK', cat: 'Indian Portals' },
  instahyre: { name: 'Instahyre', color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', tag: 'INS', cat: 'Indian Portals' },
  cutshort: { name: 'Cutshort', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.15)', tag: 'CS', cat: 'Startup Boards' },
  weworkremotely: { name: 'WeWorkRemotely', color: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.15)', tag: 'WWR', cat: 'Remote & Global' },
  hirist: { name: 'Hirist', color: '#06b6d4', bg: 'rgba(6, 182, 212, 0.15)', tag: 'HIR', cat: 'Indian Portals' },
  indeed: { name: 'Indeed India', color: '#6366f1', bg: 'rgba(99, 102, 241, 0.15)', tag: 'IND', cat: 'Indian Portals' },
  wellfound: { name: 'Wellfound', color: '#ea580c', bg: 'rgba(234, 88, 12, 0.15)', tag: 'WF', cat: 'Startup Boards' },
  greenhouse: { name: 'Greenhouse ATS', color: '#14b8a6', bg: 'rgba(20, 184, 166, 0.15)', tag: 'GH', cat: 'Direct ATS' },
  lever: { name: 'Lever ATS', color: '#84cc16', bg: 'rgba(132, 204, 22, 0.15)', tag: 'LEV', cat: 'Direct ATS' },
  foundit: { name: 'Foundit (Monster)', color: '#a855f7', bg: 'rgba(168, 85, 247, 0.15)', tag: 'FND', cat: 'Indian Portals' },
  shine: { name: 'Shine.com', color: '#ec4899', bg: 'rgba(236, 72, 153, 0.15)', tag: 'SHN', cat: 'Indian Portals' },
  glassdoor: { name: 'Glassdoor India', color: '#22c55e', bg: 'rgba(34, 197, 94, 0.15)', tag: 'GLS', cat: 'Indian Portals' },
  timesjobs: { name: 'TimesJobs', color: '#f43f5e', bg: 'rgba(244, 63, 94, 0.15)', tag: 'TJ', cat: 'Indian Portals' },
  arbeitnow: { name: 'Arbeitnow', color: '#38bdf8', bg: 'rgba(56, 189, 248, 0.15)', tag: 'ARB', cat: 'Remote & Global' },
  jobicy: { name: 'Jobicy', color: '#d946ef', bg: 'rgba(217, 70, 239, 0.15)', tag: 'JBC', cat: 'Remote & Global' },
  remotive: { name: 'Remotive', color: '#eab308', bg: 'rgba(234, 179, 8, 0.15)', tag: 'REM', cat: 'Remote & Global' },
  career_jsonld: { name: 'Direct Career Pages', color: '#94a3b8', bg: 'rgba(148, 163, 184, 0.15)', tag: 'DIR', cat: 'Direct ATS' },
};

export default function LiveWebSearch({
  sources = [],
  active = false,
  tailoringMessage = null,
  eventsLog = [],
  collapsible = false,
  defaultExpanded = true
}) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [showLogs, setShowLogs] = useState(false);
  const [expandedRows, setExpandedRows] = useState({});
  const [allExpanded, setAllExpanded] = useState(false);
  const [copiedKey, setCopiedKey] = useState(null);
  const terminalEndRef = useRef(null);

  useEffect(() => {
    if (showLogs && terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [eventsLog, showLogs]);

  if (!sources || sources.length === 0) return null;

  const totalResults = sources.reduce((acc, s) => acc + (s.count || 0), 0);
  const completedSources = sources.filter(s => s.status === 'done' || s.count !== undefined).length;
  const progressPercent = Math.min(100, Math.round((completedSources / Math.max(sources.length, 1)) * 100));

  const toggleRowExpand = (srcKey) => {
    setExpandedRows(prev => {
      const current = prev[srcKey] !== undefined ? prev[srcKey] : (active && false);
      return {
        ...prev,
        [srcKey]: !current
      };
    });
  };

  const handleToggleAll = (e) => {
    e.stopPropagation();
    const nextState = !allExpanded;
    setAllExpanded(nextState);
    const updated = {};
    sources.forEach(s => {
      updated[s.source] = nextState;
    });
    setExpandedRows(updated);
  };

  const handleCopyQuery = (e, query, key) => {
    e.stopPropagation();
    navigator.clipboard.writeText(query);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1800);
  };

  // Filter sources according to selected tab
  const filteredSources = sources.filter(s => {
    const meta = PLATFORM_META[s.source] || {};
    if (categoryFilter === 'all') return true;
    if (categoryFilter === 'with_results') return (s.count || 0) > 0;
    if (categoryFilter === 'active') return s.status === 'searching';
    return meta.cat === categoryFilter;
  });

  const categories = [
    { id: 'all', label: `All (${sources.length})` },
    { id: 'with_results', label: `With Matches (${sources.filter(s => (s.count || 0) > 0).length})` },
    { id: 'Indian Portals', label: `Indian Portals (${sources.filter(s => PLATFORM_META[s.source]?.cat === 'Indian Portals').length})` },
    { id: 'Direct ATS', label: `Direct ATS (${sources.filter(s => PLATFORM_META[s.source]?.cat === 'Direct ATS').length})` },
    { id: 'Remote & Global', label: `Remote & Global (${sources.filter(s => PLATFORM_META[s.source]?.cat === 'Remote & Global').length})` },
    { id: 'Startup Boards', label: `Startup Boards (${sources.filter(s => PLATFORM_META[s.source]?.cat === 'Startup Boards').length})` },
  ];

  return (
    <div className={`live-web-search-box ${active ? 'is-active' : 'is-complete'}`}>
      {/* Header bar with animated radar & scan metrics */}
      <div
        className="live-search-header-bar"
        onClick={() => collapsible && setIsExpanded(!isExpanded)}
        style={{ cursor: collapsible ? 'pointer' : 'default' }}
      >
        <div className="header-left">
          <div className="globe-pulse-wrap">
            <Globe size={16} className={`globe-icon ${active ? 'animate-spin-slow' : ''}`} />
            {active && <span className="live-ping-dot" />}
          </div>
          <div className="header-titles">
            <span className="header-title">
              {active
                ? `Scanning 18 Verified Platforms Live (${completedSources}/${sources.length} scanned • ${progressPercent}%)`
                : `Verified 18 Platforms • ${totalResults} Total Job Opportunities Discovered`}
            </span>
            <span className="header-subtitle">
              Simultaneous concurrent spidering across verified ATS APIs, job portals & public boards
            </span>
          </div>
        </div>

        <div className="header-right">
          {/* Toggle Terminal Activity */}
          <button
            type="button"
            className={`btn-toggle-terminal ${showLogs ? 'active' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              setShowLogs(!showLogs);
            }}
            title="Toggle live execution logs"
          >
            <Terminal size={12} />
            <span>Logs</span>
            {eventsLog.length > 0 && <span className="log-count-dot" />}
          </button>

          {active ? (
            <span className="live-active-tag">
              <Loader2 size={12} className="animate-spin" />
              <span>Scraping Live</span>
            </span>
          ) : (
            <span className="live-complete-tag">
              <CheckCircle2 size={12} />
              <span>{totalResults} Matches Ready</span>
            </span>
          )}

          {collapsible && (
            <button className="btn-collapse-toggle" aria-label="Toggle live search">
              {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            </button>
          )}
        </div>
      </div>

      {/* Progress Line */}
      {active && (
        <div className="live-scan-progress-track">
          <div
            className="live-scan-progress-bar"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      )}

      {/* Expandable Body */}
      {isExpanded && (
        <div className="live-search-body">
          {/* Interactive Category Filter Pills + Expand/Collapse All Action */}
          <div className="live-filter-tabs">
            <div className="filter-tabs-left">
              {categories.map(cat => (
                <button
                  key={cat.id}
                  type="button"
                  className={`filter-pill-btn ${categoryFilter === cat.id ? 'active' : ''}`}
                  onClick={() => setCategoryFilter(cat.id)}
                >
                  {cat.label}
                </button>
              ))}
            </div>

            <div className="filter-tabs-right">
              <button
                type="button"
                className="filter-pill-btn btn-expand-all"
                onClick={handleToggleAll}
                title={allExpanded ? "Collapse all platform cards" : "Expand all platform cards"}
              >
                {allExpanded ? "Collapse All" : "Expand All"}
              </button>
            </div>
          </div>

          {/* Live Activity Stream Terminal */}
          {showLogs && (
            <div className="live-events-terminal">
              <div className="terminal-header">
                <div className="terminal-dots">
                  <span className="term-dot red" />
                  <span className="term-dot yellow" />
                  <span className="term-dot green" />
                </div>
                <span className="term-title">Engine Execution Stream • spider-worker</span>
                <span className="term-sub">18 concurrent streams</span>
              </div>
              <div className="terminal-log-content">
                {eventsLog.length === 0 ? (
                  <div className="terminal-log-line muted">
                    [0.00s] Initialized 18-platform spider queue. Rate limiter calibrated to respectful jitter (0.5s-1.5s)...
                  </div>
                ) : (
                  eventsLog.map((log, idx) => (
                    <div key={idx} className="terminal-log-line">
                      <span className="log-time">{log.time || `[00:${String(idx).padStart(2, '0')}]`}</span>
                      <span className={`log-badge ${log.type || 'info'}`}>{log.badge || 'PROBE'}</span>
                      <span className="log-text">{log.text}</span>
                    </div>
                  ))
                )}
                <div ref={terminalEndRef} />
              </div>
            </div>
          )}

          {/* Platform Cards List (Rock-Solid Non-Squishing Layout) */}
          <div className="platform-cards-list">
            {filteredSources.map((s, sIdx) => {
              const meta = PLATFORM_META[s.source] || {
                name: s.source ? s.source.toUpperCase() : 'PLATFORM',
                color: '#f59e0b',
                bg: 'rgba(245, 158, 11, 0.15)',
                tag: s.source ? s.source.slice(0, 3).toUpperCase() : 'JOB',
                cat: 'Web'
              };

              const isDone = s.status === 'done' || (s.count !== undefined && !active);
              const isSearching = active && s.status === 'searching';
              const count = s.count || 0;
              const isRowOpen = expandedRows[s.source] !== undefined
                ? expandedRows[s.source]
                : (active && isSearching);

              return (
                <div
                  key={sIdx}
                  className={`platform-search-card ${isSearching ? 'is-searching' : isDone ? 'is-done' : 'is-pending'}`}
                >
                  {/* Card Header Row */}
                  <div
                    className="platform-card-header"
                    onClick={() => toggleRowExpand(s.source)}
                    title="Click to view/hide scraped jobs from this platform"
                  >
                    <div className="card-header-left">
                      {/* Brand Tag */}
                      <span
                        className="platform-brand-badge"
                        style={{ color: meta.color, backgroundColor: meta.bg, borderColor: `${meta.color}40` }}
                      >
                        {meta.tag}
                      </span>

                      <div className="platform-names">
                        <span className="platform-primary-name">{meta.name}</span>
                        <span className="platform-domain">{s.domain}</span>
                      </div>
                    </div>

                    <div className="card-header-right">
                      {/* Live Status or Count */}
                      {isSearching ? (
                        <span className="status-live-scraping">
                          <Loader2 size={12} className="animate-spin" />
                          <span>Scraping Live...</span>
                        </span>
                      ) : isDone ? (
                        count > 0 ? (
                          <span className="status-results-badge success">
                            +{count} {count === 1 ? 'Job' : 'Jobs'} Found
                          </span>
                        ) : (
                          <span className="status-results-badge empty">
                            0 in Batch
                          </span>
                        )
                      ) : (
                        <span className="status-results-badge pending">
                          Queued
                        </span>
                      )}

                      <button
                        type="button"
                        className="btn-card-chevron"
                        aria-label="Expand platform details"
                      >
                        {isRowOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                      </button>
                    </div>
                  </div>

                  {/* Card Expanded Content */}
                  {isRowOpen && (
                    <div className="platform-card-details">
                      {/* Search query code bar with copy button */}
                      <div className="platform-query-bar">
                        <code className="platform-query-code">
                          {s.site_query || `site:${s.domain} "Software Engineer"`}
                        </code>
                        <button
                          type="button"
                          className="btn-copy-query"
                          onClick={(e) => handleCopyQuery(e, s.site_query || s.domain, s.source)}
                          title="Copy search query"
                        >
                          {copiedKey === s.source ? (
                            <>
                              <Check size={11} color="#34d399" />
                              <span style={{ color: "#34d399" }}>Copied</span>
                            </>
                          ) : (
                            <>
                              <Copy size={11} />
                              <span>Copy</span>
                            </>
                          )}
                        </button>
                      </div>

                      {/* Scraped Job Previews */}
                      {s.jobs && s.jobs.length > 0 ? (
                        <div className="scraped-jobs-preview-container">
                          {s.jobs.slice(0, 5).map((job, jIdx) => (
                            <div key={jIdx} className="scraped-job-item">
                              <div className="scraped-job-info">
                                <span className="scraped-job-title">{job.title}</span>
                                <div className="scraped-job-meta">
                                  {job.company && (
                                    <span className="job-meta-pill company">
                                      <Building2 size={11} />
                                      {job.company}
                                    </span>
                                  )}
                                  {job.location && (
                                    <span className="job-meta-pill location">
                                      <MapPin size={11} />
                                      {job.location}
                                    </span>
                                  )}
                                </div>
                              </div>

                              {job.url && (
                                <a
                                  href={job.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="btn-direct-apply-preview"
                                  title="Open direct job application"
                                >
                                  <span>Apply</span>
                                  <ExternalLink size={10} />
                                </a>
                              )}
                            </div>
                          ))}

                          {count > 5 && (
                            <div className="more-jobs-indicator">
                              +{count - 5} additional {meta.name} listings available in main results table below
                            </div>
                          )}
                        </div>
                      ) : isSearching ? (
                        <div className="platform-scanning-placeholder">
                          <div className="shimmer-line" />
                          <span>Streaming listings from {s.domain}...</span>
                        </div>
                      ) : (
                        <div className="platform-empty-note">
                          No open listings matched the target seniority/location filters in this query batch.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Interactive Tailoring Stage Pipeline */}
          {tailoringMessage && (
            <div className="tailoring-pipeline-card">
              <div className="tailoring-banner-header">
                <div className="tailor-badge-wrap">
                  <Sparkles size={15} className="sparkle-tailor-icon animate-spin-slow" />
                </div>
                <div className="tailor-text-wrap">
                  <span className="tailor-title">Opportunity Fitness & Direct Apply Matcher</span>
                  <span className="tailor-desc">{tailoringMessage}</span>
                </div>
              </div>

              {/* 4-Stage Visual Stepper */}
              <div className="tailor-stages-stepper">
                <div className="stage-step completed">
                  <div className="step-icon"><CheckCheck size={12} /></div>
                  <span className="step-label">Spider 18 Sites</span>
                </div>
                <div className="step-connector completed" />
                <div className="stage-step completed">
                  <div className="step-icon"><Layers size={12} /></div>
                  <span className="step-label">Deduplicate</span>
                </div>
                <div className="step-connector in-progress"></div>
                <div className="stage-step in-progress">
                  <div className="step-icon"><Cpu size={12} className="animate-spin" /></div>
                  <span className="step-label">Fitness Scoring</span>
                </div>
                <div className="step-connector queued" />
                <div className="stage-step queued">
                  <div className="step-icon"><FileCheck2 size={12} /></div>
                  <span className="step-label">Direct Apply</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
