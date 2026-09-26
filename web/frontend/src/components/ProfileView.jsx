import React, { useState, useEffect } from 'react';
import {
  UserCheck,
  Upload,
  FileText,
  Download,
  Trash2,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Briefcase,
  MapPin,
  Clock,
  DollarSign,
  Building2,
  Award,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Save,
  Check,
  ShieldCheck,
  Sparkles,
  Info
} from 'lucide-react';
import {
  getProfile,
  updateProfile,
  uploadResume,
  getResumeDownloadUrl,
  deleteProfileResume
} from '../api';

export default function ProfileView({ onProfileUpdated }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [error, setError] = useState(null);
  const [showRawText, setShowRawText] = useState(false);

  // Profile Form State
  const [name, setName] = useState('');
  const [role, setRole] = useState('');
  const [location, setLocation] = useState('Bangalore');
  const [seniority, setSeniority] = useState('mid');
  const [noticePeriod, setNoticePeriod] = useState('Immediate');
  const [expectedCtc, setExpectedCtc] = useState('18-25 LPA');
  const [companyType, setCompanyType] = useState('Product-based');
  const [jobType, setJobType] = useState('Full-time');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [linkedinUrl, setLinkedinUrl] = useState('');
  const [resumeText, setResumeText] = useState('');
  const [resumeFilename, setResumeFilename] = useState('');
  const [resumeFilePath, setResumeFilePath] = useState('');
  const [resumeUploadedAt, setResumeUploadedAt] = useState('');
  const [skills, setSkills] = useState([]);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  const fetchProfile = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getProfile();
      if (res.has_profile && res.profile) {
        const p = res.profile;
        setName(p.name || '');
        setRole(p.role || '');
        setLocation(p.location || 'Bangalore');
        setSeniority(p.seniority || 'mid');
        setNoticePeriod(p.notice_period || 'Immediate');
        setExpectedCtc(p.expected_ctc_lpa || '18-25 LPA');
        setCompanyType(p.company_type || 'Product-based');
        setJobType(p.job_type || 'Full-time');
        setEmail(p.email || '');
        setPhone(p.phone || '');
        setLinkedinUrl(p.linkedin_url || '');
        setResumeText(p.resume_text || '');
        setResumeFilename(p.resume_filename || '');
        setResumeFilePath(p.resume_file_path || '');
        setResumeUploadedAt(p.resume_uploaded_at || '');
        setSkills(p.skills || []);
      }
    } catch (err) {
      console.error('Failed to load profile:', err);
      setError('Could not load profile. Please refresh.');
    } finally {
      setLoading(false);
      setHasUnsavedChanges(false);
    }
  };

  useEffect(() => {
    fetchProfile();
  }, []);

  const handleFieldChange = (setter) => (e) => {
    setter(e.target.value);
    setHasUnsavedChanges(true);
    setSaveSuccess(false);
  };

  const handleSaveProfile = async (e) => {
    if (e) e.preventDefault();
    if (!role.trim()) {
      setError('Target Role / Title is required.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await updateProfile({
        name: name.trim() || 'Applicant',
        role: role.trim(),
        location: location.trim(),
        seniority,
        notice_period: noticePeriod,
        expected_ctc_lpa: expectedCtc.trim(),
        company_type: companyType,
        job_type: jobType,
        email: email.trim(),
        phone: phone.trim(),
        linkedin_url: linkedinUrl.trim(),
        resume_text: resumeText,
        resume_filename: resumeFilename,
        resume_uploaded_at: resumeUploadedAt,
        skills,
      });
      if (res.status === 'ok') {
        setSaveSuccess(true);
        setHasUnsavedChanges(false);
        if (onProfileUpdated) onProfileUpdated(res.profile);
        setTimeout(() => setSaveSuccess(false), 3500);
      }
    } catch (err) {
      console.error('Save error:', err);
      setError(err.message || 'Failed to save profile changes');
    } finally {
      setSaving(false);
    }
  };

  const handleFileUpload = async (e) => {
    const selected = e.target.files?.[0];
    if (!selected) return;

    setUploading(true);
    setError(null);
    try {
      const res = await uploadResume(selected);
      if (res.status === 'ok') {
        const p = res.profile;
        setResumeText(p.resume_text || '');
        setResumeFilename(p.resume_filename || selected.name);
        setResumeFilePath(p.resume_file_path || '');
        setResumeUploadedAt(p.resume_uploaded_at || new Date().toISOString());
        setSkills(res.skills || p.skills || []);

        if (p.name && (!name || name === 'Applicant')) setName(p.name);
        if (p.email && !email) setEmail(p.email);
        if (p.phone && !phone) setPhone(p.phone);
        if (p.linkedin_url && !linkedinUrl) setLinkedinUrl(p.linkedin_url);
        if (p.job_type) setJobType(p.job_type);

        setSaveSuccess(true);
        setHasUnsavedChanges(false);
        if (onProfileUpdated) onProfileUpdated(p);
        setTimeout(() => setSaveSuccess(false), 3500);
      }
    } catch (err) {
      console.error('Resume upload error:', err);
      setError(err.message || 'Failed to upload and parse resume');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleDeleteResume = async () => {
    if (!window.confirm('Are you sure you want to remove this resume from your profile?')) return;
    try {
      const res = await deleteProfileResume();
      if (res.status === 'ok') {
        setResumeText('');
        setResumeFilename('');
        setResumeFilePath('');
        setResumeUploadedAt('');
        setSkills([]);
        if (onProfileUpdated) onProfileUpdated(res.profile);
      }
    } catch (err) {
      setError(err.message || 'Failed to remove resume');
    }
  };

  const initials = (name || 'Candidate')
    .split(' ')
    .filter(Boolean)
    .map(p => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase() || 'C';

  const formatUploadDate = (isoStr) => {
    if (!isoStr) return 'Recently';
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
      return 'Recently';
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-secondary)' }}>
        <RefreshCw size={28} className="spin" style={{ marginBottom: '1rem', color: 'var(--accent-gold)' }} />
        <span>Loading Candidate Profile...</span>
      </div>
    );
  }

  return (
    <div className="profile-view-container">
      {/* Top Action Bar */}
      <div className="profile-page-header">
        <div className="page-header-left">
          <div className="page-header-icon-wrap">
            <UserCheck size={20} className="text-terracotta" />
          </div>
          <div>
            <h1 className="page-header-title">Candidate Profile & Target Criteria</h1>
            <p className="page-header-subtitle">
              Single source of truth for verified job spiders, resume tailoring, and autonomous bots.
            </p>
          </div>
        </div>

        <div className="page-header-actions">
          {hasUnsavedChanges && (
            <span className="badge-unsaved">Unsaved changes •</span>
          )}
          {saveSuccess && (
            <span className="badge-saved">
              <Check size={13} /> Saved successfully
            </span>
          )}
          <button
            type="button"
            className="btn-primary"
            onClick={handleSaveProfile}
            disabled={saving}
          >
            {saving ? (
              <>
                <RefreshCw size={14} className="animate-spin" />
                <span>Saving...</span>
              </>
            ) : (
              <>
                <Save size={14} />
                <span>Save Profile</span>
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="profile-error-alert animate-fade-in">
          <AlertCircle size={16} className="error-icon" />
          <span>{error}</span>
        </div>
      )}

      {/* Hero Overview Banner */}
      <div className="profile-hero-card">
        <div className="profile-hero-left">
          <div className="hero-avatar-squircle">
            <span className="hero-avatar-initials">{initials}</span>
            <span className="hero-status-beacon" />
          </div>

          <div className="hero-info-content">
            <h2 className="hero-name">{name || 'Candidate Profile'}</h2>
            <div className="hero-meta-badges">
              <span className="hero-meta-badge hero-meta-badge-accent">
                <Briefcase size={13} /> {role || 'Specify Target Role'}
              </span>
              <span className="hero-meta-badge">
                <MapPin size={13} /> {location || 'India'}
              </span>
              <span className="hero-meta-badge hero-meta-badge-accent">
                <Clock size={13} /> {jobType}
              </span>
              <span className="hero-meta-badge">
                <Award size={13} /> Active Searcher
              </span>
            </div>
          </div>
        </div>

        {/* Quick Info Bento Tiles */}
        <div className="hero-metrics-bento">
          <div className="hero-bento-tile">
            <span className="tile-label">Job Type</span>
            <span className="tile-value terra">{jobType}</span>
          </div>
          <div className="hero-bento-tile">
            <span className="tile-label">Notice Period</span>
            <span className="tile-value amber">{noticePeriod}</span>
          </div>
          <div className="hero-bento-tile">
            <span className="tile-label">Expected CTC</span>
            <span className="tile-value emerald">{expectedCtc || 'Flexible'}</span>
          </div>
          <div className="hero-bento-tile">
            <span className="tile-label">Company Type</span>
            <span className="tile-value blue">{companyType}</span>
          </div>
          <div className="hero-bento-tile">
            <span className="tile-label">Seniority</span>
            <span className="tile-value mono">{seniority.toUpperCase()}</span>
          </div>
        </div>
      </div>

      {/* Main Grid: 2 Columns */}
      <div className="profile-grid-layout">
        
        {/* Column 1: Career & Target Preferences Form */}
        <div className="profile-card-section">
          <div className="card-section-header">
            <Briefcase size={18} className="text-terracotta" />
            <h3 className="card-section-title">Target Job Preferences</h3>
          </div>

          <form onSubmit={handleSaveProfile} className="profile-form-body">
            {/* Candidate Full Name */}
            <div className="form-group">
              <label className="form-label">
                Candidate Full Name <span className="text-danger">*</span>
              </label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Alex Sharma / Tanuj"
                value={name}
                onChange={handleFieldChange(setName)}
                required
              />
              <span className="form-helper-note">
                Used in tailored application letters, resumes, and form submissions.
              </span>
            </div>

            {/* Target Role & Target Location */}
            <div className="form-grid-2col">
              <div className="form-group">
                <label className="form-label">
                  Target Role / Title <span className="text-danger">*</span>
                </label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. React Developer, Backend Engineer"
                  value={role}
                  onChange={handleFieldChange(setRole)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">
                  Target Location
                </label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Bangalore, Hyderabad, Remote"
                  value={location}
                  onChange={handleFieldChange(setLocation)}
                />
              </div>
            </div>

            {/* Job Type & Seniority Level */}
            <div className="form-grid-2col">
              <div className="form-group">
                <label className="form-label">Job Type / Commitment</label>
                <select
                  className="form-select"
                  value={jobType}
                  onChange={handleFieldChange(setJobType)}
                >
                  <option value="Full-time">Full-time</option>
                  <option value="Part-time">Part-time</option>
                  <option value="Contract">Contract / Freelance</option>
                  <option value="Internship">Internship</option>
                  <option value="Any">Any (Full-time & Part-time)</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Seniority Level</label>
                <select
                  className="form-select"
                  value={seniority}
                  onChange={handleFieldChange(setSeniority)}
                >
                  <option value="entry">Fresher / Junior (0-2 yrs)</option>
                  <option value="mid">Mid-level (2-5 yrs)</option>
                  <option value="senior">Senior Level (5-8 yrs)</option>
                  <option value="lead">Lead / Principal (8+ yrs)</option>
                  <option value="any">Any Seniority</option>
                </select>
              </div>
            </div>

            {/* Notice Period & Expected CTC */}
            <div className="form-grid-2col">
              <div className="form-group">
                <label className="form-label">Notice Period</label>
                <select
                  className="form-select"
                  value={noticePeriod}
                  onChange={handleFieldChange(setNoticePeriod)}
                >
                  <option value="Immediate">Immediate (0 Days)</option>
                  <option value="15 Days">15 Days</option>
                  <option value="30 Days">30 Days (1 Month)</option>
                  <option value="60 Days">60 Days (2 Months)</option>
                  <option value="90 Days">90 Days (3 Months)</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Expected CTC (LPA / USD)</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. 18-25 LPA or $120k"
                  value={expectedCtc}
                  onChange={handleFieldChange(setExpectedCtc)}
                />
              </div>
            </div>

            {/* Company Type Preference */}
            <div className="form-group">
              <label className="form-label">Target Company Ecosystem</label>
              <select
                className="form-select"
                value={companyType}
                onChange={handleFieldChange(setCompanyType)}
              >
                <option value="Product-based">Product-based Companies & Tech Tier 1</option>
                <option value="Startup">Early & Growth-stage Startups (Funded)</option>
                <option value="MNC">Global MNC & Enterprise Tech</option>
                <option value="Service-based">IT Services & Consulting</option>
                <option value="Any">Any Company Type</option>
              </select>
            </div>

            {/* Contact Details Header */}
            <div className="form-divider-title">
              Contact & Professional Links
            </div>

            <div className="form-grid-2col">
              <div className="form-group">
                <label className="form-label">Email Address</label>
                <input
                  type="email"
                  className="form-input"
                  placeholder="candidate@example.com"
                  value={email}
                  onChange={handleFieldChange(setEmail)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Phone Number</label>
                <input
                  type="tel"
                  className="form-input"
                  placeholder="+91 9876543210"
                  value={phone}
                  onChange={handleFieldChange(setPhone)}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">LinkedIn Profile URL</label>
              <input
                type="url"
                className="form-input"
                placeholder="https://linkedin.com/in/yourprofile"
                value={linkedinUrl}
                onChange={handleFieldChange(setLinkedinUrl)}
              />
            </div>

            <div className="form-submit-row">
              <button
                type="submit"
                className="btn-primary"
                disabled={saving}
              >
                {saving ? <RefreshCw size={14} className="animate-spin" /> : <CheckCircle size={14} />}
                <span>Save Profile Criteria</span>
              </button>
            </div>
          </form>
        </div>

        {/* Column 2: Resume & Document Vault */}
        <div className="profile-sidebar-column">
          
          <div className="profile-card-section">
            <div className="card-section-header flex-between">
              <div className="section-title-wrap">
                <FileText size={18} className="text-terracotta" />
                <h3 className="card-section-title">Candidate Resume Vault</h3>
              </div>
              <span className={`vault-status-badge ${resumeText ? 'active' : 'empty'}`}>
                {resumeText ? '✓ Active Resume' : '⚠️ No Resume'}
              </span>
            </div>

            {/* Active Resume Card */}
            {resumeText ? (
              <div className="resume-active-file-card">
                <div className="resume-file-identity">
                  <div className="resume-file-icon-wrap">
                    <FileText size={22} />
                  </div>

                  <div className="resume-file-details">
                    <h4 className="resume-file-name">
                      {resumeFilename || (resumeFilePath ? resumeFilePath.split('/').pop() : 'Candidate_Resume.pdf')}
                    </h4>
                    <span className="resume-file-meta">
                      Updated {formatUploadDate(resumeUploadedAt)} • {resumeText.length.toLocaleString()} characters parsed
                    </span>
                  </div>
                </div>

                {/* Resume Actions Bar */}
                <div className="resume-actions-row">
                  <a
                    href={getResumeDownloadUrl()}
                    download
                    className="btn-secondary btn-sm"
                    title="Download active resume"
                  >
                    <Download size={13} />
                    <span>Download</span>
                  </a>

                  <label className="btn-secondary btn-sm btn-upload-label">
                    <Upload size={13} />
                    <span>{uploading ? 'Processing...' : 'Replace Resume'}</span>
                    <input type="file" accept=".pdf,.docx,.doc,.txt,.png,.jpg,.jpeg,.webp" onChange={handleFileUpload} disabled={uploading} style={{ display: 'none' }} />
                  </label>

                  <button
                    type="button"
                    className="btn-danger-outline btn-sm ml-auto"
                    onClick={handleDeleteResume}
                    title="Remove resume from profile"
                  >
                    <Trash2 size={13} />
                    <span>Remove</span>
                  </button>
                </div>
              </div>
            ) : (
              /* Drag & Drop Upload Zone */
              <label className="resume-dropzone">
                <div className="dropzone-icon-wrap">
                  <Upload size={28} className="text-terracotta" />
                </div>
                <span className="dropzone-title">
                  {uploading ? 'Parsing resume text & skills...' : 'Click or drag Resume (PDF, DOCX, Images) here'}
                </span>
                <span className="dropzone-sub">
                  Supports all PDF (digital & scanned), DOCX, TXT, Images up to 15MB
                </span>
                <input type="file" accept=".pdf,.docx,.doc,.txt,.png,.jpg,.jpeg,.webp" onChange={handleFileUpload} disabled={uploading} style={{ display: 'none' }} />
              </label>
            )}

            {/* Extracted Skills Cloud */}
            {skills && skills.length > 0 && (
              <div className="skills-cloud-wrap">
                <div className="skills-cloud-header">
                  <Sparkles size={14} className="text-terracotta" />
                  <span className="skills-cloud-title">
                    Extracted Skills & Competencies ({skills.length})
                  </span>
                </div>
                <div className="skills-tags-list">
                  {skills.map((skill, i) => (
                    <span key={i} className="skill-pill">
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Extracted Resume Text Collapsible Accordion */}
            {resumeText && (
              <div className="resume-text-accordion">
                <button
                  type="button"
                  className="btn-accordion-toggle"
                  onClick={() => setShowRawText(!showRawText)}
                >
                  <span>Parsed Resume Plain Text Preview</span>
                  {showRawText ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                </button>

                {showRawText && (
                  <div className="accordion-content-box animate-fade-in">
                    <textarea
                      className="form-input resume-textarea-preview"
                      rows={8}
                      value={resumeText}
                      onChange={handleFieldChange(setResumeText)}
                    />
                    <span className="form-helper-note">
                      You can make manual adjustments to the parsed resume text here if desired.
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Unified Integration Guarantee Info Box */}
          <div className="profile-trust-card">
            <ShieldCheck size={20} className="trust-card-icon" />
            <div className="trust-card-body">
              <strong className="trust-card-title">
                Profile-First Integration Active
              </strong>
              <p className="trust-card-text">
                All commands (<code>/job-skill search</code>, <code>/job-skill apply linkedin</code>, <code>/job-skill automate</code>) directly and exclusively source this candidate profile and resume.
              </p>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
