import React, { useState, useMemo } from 'react';
import {
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Building2,
  MapPin,
  Calendar,
  Sparkles,
  BookmarkPlus,
  BookmarkCheck,
  Search,
  Filter,
  Layers
} from 'lucide-react';

export default function JobResultsTable({
  jobs = [],
  onSaveToTracker = null,
  savedJobs = {}
}) {
  // Search & Filter State
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPlatform, setSelectedPlatform] = useState('all');
  const [pageSize, setPageSize] = useState(25); // 10, 25, 50, 'all'
  const [currentPage, setCurrentPage] = useState(1);

  if (!jobs || jobs.length === 0) return null;

  // Compute unique platforms and their counts
  const platformCounts = useMemo(() => {
    const counts = { all: jobs.length };
    jobs.forEach(job => {
      const src = (job.source || 'web').toLowerCase();
      counts[src] = (counts[src] || 0) + 1;
    });
    return counts;
  }, [jobs]);

  // Filtered jobs
  const filteredJobs = useMemo(() => {
    return jobs.filter(job => {
      // Platform filter
      if (selectedPlatform !== 'all' && (job.source || '').toLowerCase() !== selectedPlatform) {
        return false;
      }
      // Search query filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const titleMatch = (job.title || '').toLowerCase().includes(q);
        const compMatch = (job.company || '').toLowerCase().includes(q);
        const locMatch = (job.location || '').toLowerCase().includes(q);
        const idMatch = (job.source_job_id || '').toLowerCase().includes(q);
        const descMatch = (job.description || '').toLowerCase().includes(q);
        if (!titleMatch && !compMatch && !locMatch && !idMatch && !descMatch) {
          return false;
        }
      }
      return true;
    });
  }, [jobs, selectedPlatform, searchQuery]);

  // Pagination calculation
  const totalPages = pageSize === 'all' ? 1 : Math.max(1, Math.ceil(filteredJobs.length / pageSize));
  const activePage = Math.min(currentPage, totalPages);

  const paginatedJobs = useMemo(() => {
    if (pageSize === 'all') return filteredJobs;
    const start = (activePage - 1) * pageSize;
    return filteredJobs.slice(start, start + pageSize);
  }, [filteredJobs, activePage, pageSize]);

  const handlePlatformSelect = (plat) => {
    setSelectedPlatform(plat);
    setCurrentPage(1);
  };

  const handleSearchChange = (e) => {
    setSearchQuery(e.target.value);
    setCurrentPage(1);
  };

  const handlePageSizeChange = (newSize) => {
    setPageSize(newSize);
    setCurrentPage(1);
  };

  return (
    <div className="job-results-wrapper">
      {/* Interactive Controls Toolbar */}
      <div className="job-table-toolbar">
        <div className="toolbar-left">
          <div className="results-badge">
            <Layers size={13} />
            <span>Discovered <strong>{jobs.length} Matches</strong> across {Object.keys(platformCounts).length - 1} Platforms</span>
          </div>

          {/* Quick in-table search filter */}
          <div className="table-search-input-wrap">
            <Search size={13} className="search-input-icon" />
            <input
              type="text"
              className="table-search-input"
              placeholder="Filter by title, company, skills..."
              value={searchQuery}
              onChange={handleSearchChange}
            />
            {searchQuery && (
              <button
                className="btn-clear-search"
                onClick={() => setSearchQuery('')}
              >
                ×
              </button>
            )}
          </div>
        </div>

        {/* Page size toggle */}
        <div className="toolbar-right">
          <span className="page-size-label">View:</span>
          <div className="page-size-toggle">
            {[10, 25, 50, 'all'].map((size) => (
              <button
                key={size}
                className={`page-size-btn ${pageSize === size ? 'active' : ''}`}
                onClick={() => handlePageSizeChange(size)}
              >
                {size === 'all' ? 'All' : size}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Platform Filter Pills */}
      <div className="platform-filter-row">
        <div className="platform-filter-label">
          <Filter size={12} />
          <span>Platform:</span>
        </div>
        <div className="platform-chips-scroll">
          {Object.entries(platformCounts).map(([plat, count]) => {
            const isSelected = selectedPlatform === plat;
            return (
              <button
                key={plat}
                className={`platform-chip ${isSelected ? 'active' : ''}`}
                onClick={() => handlePlatformSelect(plat)}
              >
                <span className="platform-name">{plat.toUpperCase()}</span>
                <span className="platform-count">{count}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Results Table */}
      <div className="job-table-scroll-container">
        <table className="job-matrix-table">
          <thead>
            <tr>
              <th style={{ width: '45px', textAlign: 'center' }}>#</th>
              <th style={{ minWidth: '220px' }}>Job Title</th>
              <th style={{ minWidth: '140px' }}>Company</th>
              <th style={{ minWidth: '120px' }}>Job ID</th>
              <th style={{ minWidth: '110px' }}>Platform</th>
              <th style={{ minWidth: '120px' }}>Location</th>
              <th style={{ minWidth: '100px' }}>Posted Date</th>
              <th style={{ minWidth: '160px' }}>Fitness Score</th>
              <th style={{ width: '110px', textAlign: 'center' }}>Direct Apply</th>
              {onSaveToTracker && (
                <th style={{ width: '80px', textAlign: 'center' }}>Track</th>
              )}
            </tr>
          </thead>
          <tbody>
            {paginatedJobs.length === 0 ? (
              <tr>
                <td colSpan={onSaveToTracker ? 10 : 9} className="empty-filter-cell">
                  No listings found matching "{searchQuery}". Try adjusting your filters.
                </td>
              </tr>
            ) : (
              paginatedJobs.map((job, idx) => {
                const globalIdx = pageSize === 'all' ? idx + 1 : (activePage - 1) * pageSize + idx + 1;
                const jobId = job.source_job_id || `job_${globalIdx}`;
                const fitFraming = job.fit_framing || (job.fitness_score >= 80 ? 'Strong Match' : 'Worth a Look');
                const fitDisplay = job.fitness_display || `${job.fitness_score || 75}% Fit (${fitFraming})`;
                const badgeClass = job.fit_badge_color || (job.fitness_score >= 80 ? 'emerald' : job.fitness_score >= 60 ? 'amber' : 'slate');
                const isSaved = savedJobs[job.source_job_id] || savedJobs[jobId];

                return (
                  <tr key={jobId} className="job-row">
                    {/* 1. # */}
                    <td className="cell-index">{globalIdx}</td>

                    {/* 2. Job Title */}
                    <td className="cell-title">
                      <div className="job-title-text" title={job.title}>
                        {job.title}
                      </div>
                      {job.match_explanation && (
                        <div className="job-explanation-snippet" title={job.match_explanation}>
                          {job.match_explanation.slice(0, 90)}...
                        </div>
                      )}
                    </td>

                    {/* 3. Company */}
                    <td className="cell-company">
                      <span className="company-badge">
                        <Building2 size={12} className="meta-icon" />
                        {job.company}
                      </span>
                    </td>

                    {/* 4. Job ID */}
                    <td className="cell-id">
                      <code className="job-id-tag" title={jobId}>
                        {jobId.length > 15 ? `${jobId.slice(0, 13)}…` : jobId}
                      </code>
                    </td>

                    {/* 5. Platform */}
                    <td className="cell-platform">
                      <span className="platform-tag">
                        {(job.source || 'web').toUpperCase()}
                      </span>
                    </td>

                    {/* 6. Location */}
                    <td className="cell-location">
                      <span className="location-text" title={job.location}>
                        <MapPin size={11} className="meta-icon" />
                        {job.location || 'Remote'}
                      </span>
                    </td>

                    {/* 7. Posted Date */}
                    <td className="cell-date">
                      <span className="date-text">
                        <Calendar size={11} className="meta-icon" />
                        {job.posted_date || 'Recently'}
                      </span>
                    </td>

                    {/* 8. Fitness Score */}
                    <td className="cell-fitness">
                      <div className={`fitness-pill ${badgeClass}`} title={job.match_explanation || fitDisplay}>
                        <Sparkles size={11} />
                        <span>{fitDisplay}</span>
                      </div>
                    </td>

                    {/* 9. Apply Link */}
                    <td className="cell-apply" style={{ textAlign: "center" }}>
                      {job.apply_url ? (
                        <a
                          href={job.apply_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn-table-apply"
                          title="Open direct job application"
                        >
                          <span>Apply</span>
                          <ExternalLink size={11} />
                        </a>
                      ) : (
                        <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>—</span>
                      )}
                    </td>

                    {/* 10. Save to Tracker */}
                    {onSaveToTracker && (
                      <td style={{ textAlign: "center" }}>
                        <button
                          type="button"
                          className={`btn-table-action bookmark ${isSaved ? 'saved' : ''}`}
                          onClick={() => onSaveToTracker(job)}
                          title={isSaved ? "Saved in Tracker" : "Save to Application Tracker"}
                        >
                          {isSaved ? <BookmarkCheck size={13} color="#34d399" /> : <BookmarkPlus size={13} />}
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer - Shifted to Right */}
      {pageSize !== 'all' && totalPages > 1 && (
        <div className="job-table-pagination">
          <div className="pagination-info">
            <span className="pagination-text">
              Showing <strong>{(activePage - 1) * pageSize + 1}</strong>–<strong>{Math.min(activePage * pageSize, filteredJobs.length)}</strong> of <strong>{filteredJobs.length}</strong> matching positions
            </span>
          </div>

          <div className="pagination-controls">
            <button
              className="btn-page-nav"
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={activePage === 1}
            >
              <ChevronLeft size={14} /> Prev
            </button>

            <div className="page-numbers-row">
              {Array.from({ length: totalPages }, (_, i) => i + 1)
                .filter(page => page === 1 || page === totalPages || Math.abs(page - activePage) <= 1)
                .map((page, pIdx, arr) => {
                  const showEllipsis = pIdx > 0 && page - arr[pIdx - 1] > 1;
                  return (
                    <React.Fragment key={page}>
                      {showEllipsis && <span className="page-ellipsis">…</span>}
                      <button
                        className={`btn-page-num ${activePage === page ? 'active' : ''}`}
                        onClick={() => setCurrentPage(page)}
                      >
                        {page}
                      </button>
                    </React.Fragment>
                  );
                })}
            </div>

            <button
              className="btn-page-nav"
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              disabled={activePage === totalPages}
            >
              Next <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
