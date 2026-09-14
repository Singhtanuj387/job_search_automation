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
    <div className="profile-view-container" style={{
      padding: '1.75rem 2rem 3rem',
      height: '100%',
      overflowY: 'auto',
      maxWidth: '1280px',
      margin: '0 auto',
      width: '100%'
    }}>
      {/* Top Action Bar */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '1.5rem',
        paddingBottom: '1rem',
        borderBottom: '1px solid var(--border-subtle)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{
            background: 'var(--accent-bg)',
            padding: '0.6rem',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--accent-gold-glow)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <UserCheck size={22} color="var(--accent-gold)" />
          </div>
          <div>
            <h1 style={{ fontSize: '1.4rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
              Candidate Profile & Preferences
            </h1>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
              Single source of truth for searches, LinkedIn auto-apply, and nightly automations
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {hasUnsavedChanges && (
            <span style={{ fontSize: '0.78rem', color: 'var(--badge-amber-text)', background: 'var(--badge-amber-bg)', padding: '0.3rem 0.65rem', borderRadius: '20px', border: '1px solid var(--badge-amber-border)', fontWeight: 600 }}>
              Unsaved changes •
            </span>
          )}
          {saveSuccess && (
            <span style={{ fontSize: '0.78rem', color: 'var(--badge-emerald-text)', background: 'var(--badge-emerald-bg)', padding: '0.3rem 0.65rem', borderRadius: '20px', border: '1px solid var(--badge-emerald-border)', display: 'flex', alignItems: 'center', gap: '0.3rem', fontWeight: 600 }}>
              <Check size={13} /> Saved successfully
            </span>
          )}
          <button
            type="button"
            className="btn-primary"
            onClick={handleSaveProfile}
            disabled={saving}
            style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', padding: '0.55rem 1.15rem' }}
          >
            {saving ? (
              <>
                <RefreshCw size={15} className="spin" />
                <span>Saving...</span>
              </>
            ) : (
              <>
                <Save size={15} />
                <span>Save Profile Changes</span>
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.12)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: 'var(--radius-md)',
          padding: '0.75rem 1rem',
          color: '#f87171',
          fontSize: '0.85rem',
          marginBottom: '1.5rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.6rem'
        }}>
          <AlertCircle size={16} style={{ flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      )}

      {/* Hero Overview Banner */}
      <div style={{
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-lg)',
        padding: '1.5rem',
        marginBottom: '1.75rem',
        boxShadow: 'var(--shadow-card)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '1.25rem'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
          {/* Avatar Ring */}
          <div style={{
            width: '64px',
            height: '64px',
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #e05a2b 0%, #d9653b 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '1.4rem',
            fontWeight: 800,
            color: '#ffffff',
            boxShadow: '0 4px 14px rgba(217, 101, 59, 0.3)',
            border: '2px solid var(--bg-secondary)',
            flexShrink: 0
          }}>
            {initials}
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.25rem' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
                {name || 'Candidate Profile'}
              </h2>
              <span style={{
                fontSize: '0.72rem',
                fontWeight: 600,
                color: 'var(--badge-emerald-text)',
                background: 'var(--badge-emerald-bg)',
                border: '1px solid var(--badge-emerald-border)',
                padding: '0.15rem 0.5rem',
                borderRadius: '12px'
              }}>
                Active Candidate
              </span>
            </div>
            <div style={{ fontSize: '0.9rem', color: 'var(--accent-gold)', fontWeight: 600 }}>
              {role || 'Specify Target Role'} • {location || 'India'}
            </div>
          </div>
        </div>

        {/* Quick Info Tags */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem' }}>
          <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '0.45rem 0.75rem', fontSize: '0.78rem' }}>
            <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.7rem' }}>Notice Period</span>
            <strong style={{ color: 'var(--badge-amber-text)' }}>{noticePeriod}</strong>
          </div>
          <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '0.45rem 0.75rem', fontSize: '0.78rem' }}>
            <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.7rem' }}>Expected CTC</span>
            <strong style={{ color: 'var(--badge-emerald-text)' }}>{expectedCtc || 'Not specified'}</strong>
          </div>
          <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '0.45rem 0.75rem', fontSize: '0.78rem' }}>
            <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.7rem' }}>Company Type</span>
            <strong style={{ color: 'var(--badge-blue-text)' }}>{companyType}</strong>
          </div>
          <div style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '0.45rem 0.75rem', fontSize: '0.78rem' }}>
            <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.7rem' }}>Seniority</span>
            <strong style={{ color: 'var(--text-primary)' }}>{seniority.toUpperCase()}</strong>
          </div>
        </div>
      </div>

      {/* Main Grid: 2 Columns */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.15fr 1fr', gap: '1.5rem', alignItems: 'start' }}>
        
        {/* Column 1: Career & Target Preferences Form */}
        <div style={{
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: '1.5rem',
          boxShadow: 'var(--shadow-card)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--border-subtle)' }}>
            <Briefcase size={18} color="var(--accent-gold)" />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0 }}>Target Job Preferences</h3>
          </div>

          <form onSubmit={handleSaveProfile} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {/* Candidate Full Name */}
            <div className="form-group">
              <label className="form-label" style={{ fontSize: '0.82rem', fontWeight: 600 }}>
                Candidate Full Name <span style={{ color: '#ef4444' }}>*</span>
              </label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Alex Sharma / Tanuj"
                value={name}
                onChange={handleFieldChange(setName)}
                required
              />
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                Used in tailored application letters, resumes, and form submissions.
              </span>
            </div>

            {/* Target Role & Target Location */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.85rem' }}>
              <div className="form-group">
                <label className="form-label" style={{ fontSize: '0.82rem', fontWeight: 600 }}>
                  Target Role / Title <span style={{ color: '#ef4444' }}>*</span>
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
                <label className="form-label" style={{ fontSize: '0.82rem', fontWeight: 600 }}>
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

            {/* Notice Period & Expected CTC */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.85rem' }}>
              <div className="form-group">
                <label className="form-label" style={{ fontSize: '0.82rem', fontWeight: 600 }}>
                  Notice Period
                </label>
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
                <label className="form-label" style={{ fontSize: '0.82rem', fontWeight: 600 }}>
                  Expected CTC (LPA / USD)
                </label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. 18-25 LPA or $120k"
                  value={expectedCtc}
                  onChange={handleFieldChange(setExpectedCtc)}
                />
              </div>
            </div>

            {/* Company Type & Seniority Level */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.85rem' }}>
              <div className="form-group">
                <label className="form-label" style={{ fontSize: '0.82rem', fontWeight: 600 }}>
                  Company Type
                </label>
                <select
                  className="form-select"
                  value={companyType}
                  onChange={handleFieldChange(setCompanyType)}
                >
                  <option value="Product-based">Product-based</option>
                  <option value="Startup">Startup (Funded)</option>
                  <option value="MNC">Global MNC</option>
                  <option value="Service-based">Service-based</option>
                  <option value="Any">Any Company Type</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label" style={{ fontSize: '0.82rem', fontWeight: 600 }}>
                  Seniority Level
                </label>
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

            {/* Contact Details Header */}
            <div style={{ marginTop: '0.5rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)' }}>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.5px' }}>
                Contact & Professional Links
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.85rem' }}>
              <div className="form-group">
                <label className="form-label" style={{ fontSize: '0.8rem' }}>Email Address</label>
                <input
                  type="email"
                  className="form-input"
                  placeholder="candidate@example.com"
                  value={email}
                  onChange={handleFieldChange(setEmail)}
                />
              </div>

              <div className="form-group">
                <label className="form-label" style={{ fontSize: '0.8rem' }}>Phone Number</label>
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
              <label className="form-label" style={{ fontSize: '0.8rem' }}>LinkedIn Profile URL</label>
              <input
                type="url"
                className="form-input"
                placeholder="https://linkedin.com/in/yourprofile"
                value={linkedinUrl}
                onChange={handleFieldChange(setLinkedinUrl)}
              />
            </div>

            <div style={{ marginTop: '0.5rem', display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="submit"
                className="btn-primary"
                disabled={saving}
                style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}
              >
                {saving ? <RefreshCw size={14} className="spin" /> : <CheckCircle size={14} />}
                <span>Save Changes</span>
              </button>
            </div>
          </form>
        </div>

        {/* Column 2: Resume & Document Vault */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          
          <div style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-lg)',
            padding: '1.5rem',
            boxShadow: 'var(--shadow-card)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--border-subtle)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <FileText size={18} color="var(--accent-gold)" />
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0 }}>Candidate Resume Vault</h3>
              </div>
              <span style={{ fontSize: '0.75rem', color: resumeText ? 'var(--badge-emerald-text)' : 'var(--badge-amber-text)', background: resumeText ? 'var(--badge-emerald-bg)' : 'var(--badge-amber-bg)', border: '1px solid ' + (resumeText ? 'var(--badge-emerald-border)' : 'var(--badge-amber-border)'), padding: '0.2rem 0.5rem', borderRadius: '10px', fontWeight: 600 }}>
                {resumeText ? '✓ Active Resume' : '⚠️ No Resume'}
              </span>
            </div>

            {/* Active Resume Card */}
            {resumeText ? (
              <div style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: '1.15rem',
                marginBottom: '1rem',
                position: 'relative'
              }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.85rem' }}>
                  <div style={{
                    background: 'var(--accent-bg)',
                    border: '1px solid var(--border-focus)',
                    padding: '0.65rem',
                    borderRadius: 'var(--radius-md)',
                    color: 'var(--accent-gold)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}>
                    <FileText size={24} />
                  </div>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <h4 style={{ fontSize: '0.92rem', fontWeight: 600, margin: '0 0 0.2rem 0', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                      {resumeFilename || (resumeFilePath ? resumeFilePath.split('/').pop() : 'Candidate_Resume.pdf')}
                    </h4>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      Updated: {formatUploadDate(resumeUploadedAt)} • {resumeText.length.toLocaleString()} characters parsed
                    </span>
                  </div>
                </div>

                {/* Resume Actions Bar */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)' }}>
                  <a
                    href={getResumeDownloadUrl()}
                    download
                    className="btn-secondary"
                    style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '0.35rem', textDecoration: 'none', padding: '0.35rem 0.7rem' }}
                    title="Download active resume"
                  >
                    <Download size={13} />
                    <span>Download</span>
                  </a>

                  <label className="btn-secondary" style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer', padding: '0.35rem 0.7rem', margin: 0 }}>
                    <Upload size={13} />
                    <span>{uploading ? 'Processing...' : 'Replace Resume'}</span>
                    <input type="file" accept=".pdf,.docx,.doc,.txt,.png,.jpg,.jpeg,.webp" onChange={handleFileUpload} disabled={uploading} style={{ display: 'none' }} />
                  </label>

                  <button
                    type="button"
                    className="btn-danger-outline"
                    onClick={handleDeleteResume}
                    style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '0.35rem 0.7rem', marginLeft: 'auto' }}
                    title="Remove resume from profile"
                  >
                    <Trash2 size={13} />
                    <span>Remove</span>
                  </button>
                </div>
              </div>
            ) : (
              /* Drag & Drop Upload Zone */
              <label style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '2rem 1.5rem',
                border: '2px dashed var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                cursor: 'pointer',
                background: 'var(--bg-tertiary)',
                transition: 'border 0.2s, background 0.2s',
                marginBottom: '1rem'
              }}>
                <Upload size={32} color="var(--accent-gold)" style={{ marginBottom: '0.65rem' }} />
                <span style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>
                  {uploading ? 'Parsing resume text & skills...' : 'Click or drag Resume (PDF, DOCX, Images) here'}
                </span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem', textAlign: 'center' }}>
                  Supports all PDF (digital & scanned), DOCX, TXT, Images up to 15MB
                </span>
                <input type="file" accept=".pdf,.docx,.doc,.txt,.png,.jpg,.jpeg,.webp" onChange={handleFileUpload} disabled={uploading} style={{ display: 'none' }} />
              </label>
            )}

            {/* Extracted Skills Cloud */}
            {skills && skills.length > 0 && (
              <div style={{ marginTop: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.6rem' }}>
                  <Sparkles size={14} color="var(--accent-gold)" />
                  <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    Extracted Skills & Competencies ({skills.length})
                  </span>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', maxHeight: '120px', overflowY: 'auto' }}>
                  {skills.map((skill, i) => (
                    <span
                      key={i}
                      style={{
                        background: 'var(--badge-blue-bg)',
                        color: 'var(--badge-blue-text)',
                        border: '1px solid var(--badge-blue-border)',
                        padding: '0.2rem 0.55rem',
                        borderRadius: '6px',
                        fontSize: '0.72rem',
                        fontWeight: 600
                      }}
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Extracted Resume Text Collapsible Accordion */}
            {resumeText && (
              <div style={{ marginTop: '1.25rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)' }}>
                <button
                  type="button"
                  onClick={() => setShowRawText(!showRawText)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    width: '100%',
                    background: 'none',
                    border: 'none',
                    color: 'var(--text-secondary)',
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                    padding: '0.25rem 0'
                  }}
                >
                  <span style={{ fontWeight: 600 }}>Parsed Resume Plain Text Preview</span>
                  {showRawText ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                </button>

                {showRawText && (
                  <div style={{ marginTop: '0.6rem' }}>
                    <textarea
                      className="form-input"
                      rows={8}
                      value={resumeText}
                      onChange={handleFieldChange(setResumeText)}
                      style={{
                        fontFamily: 'monospace',
                        fontSize: '0.75rem',
                        lineHeight: 1.45,
                        background: 'var(--bg-primary)',
                        color: 'var(--text-primary)',
                        border: '1px solid var(--border-subtle)'
                      }}
                    />
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', marginTop: '0.25rem' }}>
                      You can make manual adjustments to the parsed resume text here if desired.
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Unified Integration Guarantee Info Box */}
          <div style={{
            background: 'var(--badge-emerald-bg)',
            border: '1px solid var(--badge-emerald-border)',
            borderRadius: 'var(--radius-lg)',
            padding: '1.25rem',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '0.85rem'
          }}>
            <ShieldCheck size={20} color="var(--badge-emerald-text)" style={{ flexShrink: 0, marginTop: '2px' }} />
            <div style={{ fontSize: '0.8rem', color: 'var(--badge-emerald-text)', lineHeight: 1.5 }}>
              <strong style={{ color: 'var(--badge-emerald-text)', display: 'block', marginBottom: '0.25rem' }}>
                Profile-First Integration Active
              </strong>
              All commands (<code>/job-skill search</code>, <code>/job-skill apply linkedin</code>, <code>/job-skill automate</code>) directly and exclusively source this candidate profile and resume. The system no longer reads random files from the uploads directory.
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
