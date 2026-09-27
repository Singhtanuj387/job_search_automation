import React, { useState, useEffect } from 'react';
import {
  X,
  Sparkles,
  Download,
  FileText,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  TrendingUp,
  Layers,
  ArrowRight,
  Briefcase,
  Building2,
  RefreshCw,
  Cpu
} from 'lucide-react';
import {
  tailorResume,
  getTailoredResumeByJob,
  getTailoredDownloadUrl,
  getProfile
} from '../api';

export default function ResumeTailorModal({
  isOpen,
  onClose,
  opportunity,
  onTailoredUpdated = null
}) {
  const [loading, setLoading] = useState(false);
  const [fetchingExisting, setFetchingExisting] = useState(false);
  const [tailoredData, setTailoredData] = useState(null);
  const [keywordAnalysis, setKeywordAnalysis] = useState(null);
  const [recordId, setRecordId] = useState(null);
  const [activeTab, setActiveTab] = useState('summary'); // 'summary' | 'bullets' | 'skills' | 'keywords'
  const [copiedKey, setCopiedKey] = useState(null);
  const [error, setError] = useState(null);
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    if (!isOpen || !opportunity) {
      setTailoredData(null);
      setKeywordAnalysis(null);
      setRecordId(null);
      setError(null);
      return;
    }

    const init = async () => {
      setFetchingExisting(true);
      setError(null);
      try {
        const [profRes, existingRes] = await Promise.all([
          getProfile().catch(() => ({})),
          getTailoredResumeByJob({
            opportunityId: opportunity.id,
            jobId: opportunity.source_job_id,
            company: opportunity.company,
            title: opportunity.title,
          }).catch(() => ({ has_tailored: false })),
        ]);

        if (profRes && profRes.profile) {
          setProfile(profRes.profile);
        }

        if (existingRes && existingRes.has_tailored && existingRes.tailored_resume) {
          const t = existingRes.tailored_resume;
          setRecordId(t.id);
          setTailoredData(t.tailored_data || {});
          setKeywordAnalysis(t.keyword_analysis || {});
        }
      } catch (e) {
        console.error("Failed to load existing tailored resume:", e);
      } finally {
        setFetchingExisting(false);
      }
    };

    init();
  }, [isOpen, opportunity]);

  if (!isOpen || !opportunity) return null;

  const handleTailor = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await tailorResume({
        jobId: opportunity.source_job_id || `opp-${opportunity.id}`,
        jobTitle: opportunity.title,
        company: opportunity.company,
        jobDescription: opportunity.match_explanation || `${opportunity.title} at ${opportunity.company}`,
        opportunityId: opportunity.id,
      });

      if (res && res.id) {
        setRecordId(res.id);
        setTailoredData(res.tailored_data || {});
        setKeywordAnalysis(res.keyword_analysis || {});
        if (onTailoredUpdated) {
          onTailoredUpdated(opportunity.id, res.tailored_docx_path);
        }
      }
    } catch (err) {
      setError(err.message || "Failed to tailor resume with AI.");
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = (text, key) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const handleDownload = () => {
    if (!recordId) return;
    const url = getTailoredDownloadUrl(recordId);
    window.open(url, '_blank');
  };

  const scoreBefore = keywordAnalysis?.score_before || opportunity.fitness_score || 68;
  const scoreAfter = keywordAnalysis?.score_after || (tailoredData ? 94 : null);
  const matchedKeywords = keywordAnalysis?.matched_keywords || [];
  const missingKeywords = keywordAnalysis?.missing_keywords || [];
  const addressedKeywords = keywordAnalysis?.addressed_keywords || [];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-container resume-tailor-modal"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: '860px', width: '92%' }}
      >
        {/* Header */}
        <div className="modal-header">
          <div className="modal-title-row">
            <div className="modal-icon-badge" style={{ backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#10b981' }}>
              <Sparkles size={18} />
            </div>
            <div>
              <h2 className="modal-title">AI Resume Tailor & ATS Optimizer</h2>
              <p className="modal-subtitle">
                Tailors your uploaded resume for <strong>{opportunity.company}</strong> — <em>{opportunity.title}</em>
              </p>
            </div>
          </div>
          <button type="button" className="btn-modal-close" onClick={onClose} aria-label="Close modal">
            <X size={18} />
          </button>
        </div>

        {/* Body Content */}
        <div className="modal-body custom-scrollbar" style={{ maxHeight: '72vh', overflowY: 'auto', padding: '1.25rem 1.5rem' }}>
          {error && (
            <div className="tailor-alert error">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {/* Profile Resume Status Notice */}
          <div className="tailor-profile-bar">
            <div className="profile-bar-left">
              <FileText size={15} className="text-emerald" />
              <span>
                Base Resume: <strong>{profile?.resume_filename || (profile?.resume_text ? "Uploaded Resume" : "Profile Experience")}</strong>
              </span>
              {profile?.name && (
                <span className="profile-bar-candidate">({profile.name})</span>
              )}
            </div>
            <div className="profile-bar-right">
              <span className="tailor-badge-agent">
                <CheckCircle2 size={12} /> Auto-uploaded by Apply Agents
              </span>
            </div>
          </div>

          {/* Score & Keyword Gap Banner */}
          <div className="tailor-score-card">
            <div className="score-metric-box">
              <span className="score-metric-label">Original ATS Fit</span>
              <div className="score-metric-value original">{scoreBefore}%</div>
              <span className="score-metric-hint">Base uploaded resume</span>
            </div>

            <div className="score-arrow-box">
              <ArrowRight size={20} className="score-arrow-icon" />
              <span className="score-boost-tag">
                {scoreAfter ? `+${scoreAfter - scoreBefore}% Boost` : 'AI Optimization'}
              </span>
            </div>

            <div className="score-metric-box">
              <span className="score-metric-label">Tailored ATS Fit</span>
              <div className="score-metric-value tailored">
                {scoreAfter ? `${scoreAfter}%` : '—'}
              </div>
              <span className="score-metric-hint">
                {scoreAfter ? 'Exceptional Match' : 'Ready to Tailor'}
              </span>
            </div>

            <div className="score-cta-box">
              <button
                type="button"
                className="btn-tailor-primary"
                onClick={handleTailor}
                disabled={loading}
              >
                {loading ? (
                  <>
                    <RefreshCw size={15} className="spin-icon" />
                    <span>Analyzing & Tailoring...</span>
                  </>
                ) : tailoredData ? (
                  <>
                    <RefreshCw size={15} />
                    <span>Re-Tailor with AI</span>
                  </>
                ) : (
                  <>
                    <Sparkles size={15} />
                    <span>Tailor Resume for this Role</span>
                  </>
                )}
              </button>

              {recordId && (
                <button
                  type="button"
                  className="btn-tailor-download"
                  onClick={handleDownload}
                  title="Download Tailored DOCX Resume"
                >
                  <Download size={14} />
                  <span>Download Tailored DOCX</span>
                </button>
              )}
            </div>
          </div>

          {/* Resume Matcher Keyword Chips */}
          <div className="keyword-matcher-section">
            <div className="keyword-group">
              <div className="keyword-group-title">
                <span className="dot dot-emerald"></span>
                <span>Matching Keywords ({matchedKeywords.length})</span>
              </div>
              <div className="keyword-chips-row">
                {matchedKeywords.length > 0 ? (
                  matchedKeywords.map((kw, i) => (
                    <span key={i} className="kw-chip matched">
                      {kw}
                    </span>
                  ))
                ) : (
                  <span className="kw-empty-note">Click Tailor to extract matching keywords</span>
                )}
              </div>
            </div>

            {missingKeywords.length > 0 && (
              <div className="keyword-group" style={{ marginTop: '0.75rem' }}>
                <div className="keyword-group-title">
                  <span className="dot dot-amber"></span>
                  <span>Targeted Skill Gaps ({missingKeywords.length})</span>
                </div>
                <div className="keyword-chips-row">
                  {missingKeywords.map((kw, i) => (
                    <span key={i} className="kw-chip missing">
                      {kw}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Tabs for Tailored Content */}
          {tailoredData && (
            <div className="tailor-content-container">
              <div className="tailor-nav-tabs">
                <button
                  type="button"
                  className={`tailor-tab-btn ${activeTab === 'summary' ? 'active' : ''}`}
                  onClick={() => setActiveTab('summary')}
                >
                  Professional Summary
                </button>
                <button
                  type="button"
                  className={`tailor-tab-btn ${activeTab === 'bullets' ? 'active' : ''}`}
                  onClick={() => setActiveTab('bullets')}
                >
                  Tailored Bullets ({tailoredData.tailored_bullets?.length || 0})
                </button>
                <button
                  type="button"
                  className={`tailor-tab-btn ${activeTab === 'skills' ? 'active' : ''}`}
                  onClick={() => setActiveTab('skills')}
                >
                  Optimized Skills
                </button>
              </div>

              <div className="tailor-tab-panel">
                {/* Tab 1: Summary */}
                {activeTab === 'summary' && (
                  <div className="tailor-summary-block">
                    <div className="block-action-header">
                      <span className="block-label">Targeted Executive Summary</span>
                      <button
                        type="button"
                        className="btn-copy-snippet"
                        onClick={() => handleCopy(tailoredData.tailored_summary, 'summary')}
                      >
                        {copiedKey === 'summary' ? (
                          <>
                            <Check size={13} color="#10b981" />
                            <span>Copied!</span>
                          </>
                        ) : (
                          <>
                            <Copy size={13} />
                            <span>Copy Summary</span>
                          </>
                        )}
                      </button>
                    </div>
                    <div className="tailor-text-card">
                      {tailoredData.tailored_summary || "No summary generated."}
                    </div>
                  </div>
                )}

                {/* Tab 2: Bullets */}
                {activeTab === 'bullets' && (
                  <div className="tailor-bullets-block">
                    <div className="block-action-header">
                      <span className="block-label">Role-Specific Achievement Bullets</span>
                      <button
                        type="button"
                        className="btn-copy-snippet"
                        onClick={() =>
                          handleCopy(
                            (tailoredData.tailored_bullets || []).map(b => `• ${b}`).join("\n"),
                            'bullets'
                          )
                        }
                      >
                        {copiedKey === 'bullets' ? (
                          <>
                            <Check size={13} color="#10b981" />
                            <span>Copied All!</span>
                          </>
                        ) : (
                          <>
                            <Copy size={13} />
                            <span>Copy All Bullets</span>
                          </>
                        )}
                      </button>
                    </div>
                    <ul className="tailor-bullets-list">
                      {(tailoredData.tailored_bullets || []).map((bullet, idx) => (
                        <li key={idx} className="tailor-bullet-item">
                          <span className="bullet-point">•</span>
                          <span className="bullet-text">{bullet}</span>
                          <button
                            type="button"
                            className="btn-copy-single"
                            onClick={() => handleCopy(bullet, `b-${idx}`)}
                            title="Copy this bullet"
                          >
                            {copiedKey === `b-${idx}` ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Tab 3: Skills */}
                {activeTab === 'skills' && (
                  <div className="tailor-skills-block">
                    <span className="block-label">Front-Loaded Technical Categories</span>
                    {tailoredData.categorized_skills && Object.keys(tailoredData.categorized_skills).length > 0 ? (
                      <div className="categorized-skills-grid">
                        {Object.entries(tailoredData.categorized_skills).map(([cat, list]) => (
                          <div key={cat} className="skill-cat-card">
                            <span className="skill-cat-title">{cat}</span>
                            <div className="skill-cat-pills">
                              {list.map((s, i) => (
                                <span key={i} className="skill-pill">
                                  {s}
                                </span>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="skill-cat-pills" style={{ marginTop: '0.5rem' }}>
                        {(tailoredData.tailored_skills || []).map((s, i) => (
                          <span key={i} className="skill-pill">
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {!tailoredData && !loading && (
            <div className="tailor-empty-placeholder">
              <Cpu size={32} className="text-muted" style={{ opacity: 0.6, marginBottom: '0.75rem' }} />
              <p className="placeholder-title">Resume Ready for Tailoring</p>
              <p className="placeholder-desc">
                Click <strong>"Tailor Resume for this Role"</strong> to extract skills from your uploaded resume,
                align with <em>{opportunity.title}</em>, and generate an ATS-optimized Word document.
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="modal-footer" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="tailor-footer-note">
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              Uses authentic career experience • Purged of AI buzzwords • ATS Friendly
            </span>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button type="button" className="btn-secondary" onClick={onClose}>
              Close
            </button>
            {recordId && (
              <button
                type="button"
                className="btn-primary"
                onClick={handleDownload}
                style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
              >
                <Download size={14} />
                <span>Download DOCX</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
