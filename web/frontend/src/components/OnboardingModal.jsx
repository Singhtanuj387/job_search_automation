import React, { useState } from 'react';
import { Upload, CheckCircle, FileText, ArrowRight, X, UserCheck, AlertCircle } from 'lucide-react';
import { uploadResume, updateProfile } from '../api';

export default function OnboardingModal({ isOpen, onClose, onComplete, initialProfile }) {
  if (!isOpen) return null;

  const [step, setStep] = useState(1);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [resumeText, setResumeText] = useState(initialProfile?.resume_text || "");
  const [name, setName] = useState(initialProfile?.name || "");
  const [role, setRole] = useState(initialProfile?.role || "");
  const [location, setLocation] = useState(initialProfile?.location || "Bangalore");
  const [seniority, setSeniority] = useState(initialProfile?.seniority || "mid");
  const [companyType, setCompanyType] = useState(initialProfile?.company_type || "Product-based");
  const [jobType, setJobType] = useState(initialProfile?.job_type || "Full-time");
  const [noticePeriod, setNoticePeriod] = useState(initialProfile?.notice_period || "Immediate");
  const [expectedCtc, setExpectedCtc] = useState(initialProfile?.expected_ctc_lpa || "18-25 LPA");
  const [error, setError] = useState("");

  const handleFileUpload = async (e) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    setFile(selected);
    setUploading(true);
    setError("");

    try {
      const res = await uploadResume(selected);
      setResumeText(res.profile.resume_text);
      if (res.profile.name) setName(res.profile.name);
      if (res.profile.role) setRole(res.profile.role);
      if (res.profile.location && res.profile.location !== "any") setLocation(res.profile.location);
      setStep(2);
    } catch (err) {
      setError(err.message || "Error uploading resume");
    } finally {
      setUploading(false);
    }
  };

  const handleFinish = async () => {
    if (!role.trim()) {
      setError("Please specify your target role.");
      return;
    }
    setError("");
    try {
      const res = await updateProfile({
        name: name.trim() || "Applicant",
        role: role.trim(),
        location: location.trim(),
        seniority,
        company_type: companyType,
        job_type: jobType,
        notice_period: noticePeriod,
        expected_ctc_lpa: expectedCtc.trim(),
        resume_text: resumeText,
      });
      onComplete(res.profile);
      onClose();
    } catch (err) {
      setError(err.message || "Failed to save profile");
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-card" style={{ maxWidth: "600px" }}>
        <div className="modal-header">
          <div className="modal-title">
            <div className="page-header-icon-wrap" style={{ width: "36px", height: "36px", borderRadius: "10px" }}>
              <UserCheck size={18} className="text-terracotta" />
            </div>
            <span>Get me job Onboarding</span>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close onboarding modal">
            <X size={16} />
          </button>
        </div>

        {/* Stepper Progress Bar */}
        <div className="onboarding-stepper">
          <div className={`step-indicator ${step === 1 ? 'active' : 'completed'}`}>
            <span className="step-num">{step > 1 ? '✓' : '1'}</span>
            <span className="step-label">Upload Resume</span>
          </div>
          <div className="step-divider" />
          <div className={`step-indicator ${step === 2 ? 'active' : ''}`}>
            <span className="step-num">2</span>
            <span className="step-label">Target Preferences</span>
          </div>
        </div>

        {error && (
          <div className="modal-banner error">
            <AlertCircle size={16} style={{ marginTop: "1px", flexShrink: 0 }} />
            <div>{error}</div>
          </div>
        )}

        {step === 1 && (
          <div>
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "1.25rem", lineHeight: "1.5" }}>
              Upload your resume (PDF, DOCX, Image). We’ll extract your tech stack, calculate holistic Fitness Scores,
              and auto-tailor applications for every matching job.
            </p>

            <label className="resume-dropzone">
              <div className="dropzone-icon-wrap">
                <Upload size={24} className="text-terracotta" />
              </div>
              <span className="dropzone-title">
                {uploading ? "Extracting resume text, OCR & skills..." : "Click or drag Resume (PDF, DOCX, Images) here"}
              </span>
              <span className="dropzone-sub">
                Supports all formats (PDF digital & scanned, DOCX, TXT up to 15MB)
              </span>
              <input
                type="file"
                accept=".pdf,.docx,.doc,.txt,.png,.jpg,.jpeg,.webp"
                onChange={handleFileUpload}
                disabled={uploading}
                style={{ display: "none" }}
              />
            </label>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "1.5rem" }}>
              <button type="button" className="btn-secondary" onClick={() => setStep(2)}>
                <span>Skip resume for now</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "1.25rem", lineHeight: "1.5" }}>
              Specify your target search criteria. These are saved to your Candidate Profile and power autonomous spiders.
            </p>

            <div className="form-grid-2" style={{ marginBottom: "1rem" }}>
              <div className="form-group">
                <label className="form-label">Candidate Full Name</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Alex Sharma / Tanuj"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Job Type / Commitment</label>
                <select className="form-select" value={jobType} onChange={(e) => setJobType(e.target.value)}>
                  <option value="Full-time">Full-time</option>
                  <option value="Part-time">Part-time</option>
                  <option value="Contract">Contract / Freelance</option>
                  <option value="Internship">Internship</option>
                  <option value="Any">Any (Full-time & Part-time)</option>
                </select>
              </div>
            </div>

            <div className="form-grid-2" style={{ marginBottom: "1rem" }}>
              <div className="form-group">
                <label className="form-label">Notice Period</label>
                <select className="form-select" value={noticePeriod} onChange={(e) => setNoticePeriod(e.target.value)}>
                  <option value="Immediate">Immediate (0 Days)</option>
                  <option value="15 Days">15 Days</option>
                  <option value="30 Days">30 Days</option>
                  <option value="60 Days">60 Days</option>
                  <option value="90 Days">90 Days</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Expected CTC (LPA / USD)</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. 18-28 LPA"
                  value={expectedCtc}
                  onChange={(e) => setExpectedCtc(e.target.value)}
                />
              </div>
            </div>

            <div className="form-grid-2" style={{ marginBottom: "1rem" }}>
              <div className="form-group">
                <label className="form-label">Target Role / Title <span className="text-danger">*</span></label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Backend Engineer, React Developer"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  autoFocus
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Target Location</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Bangalore, Hyderabad, Remote"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                />
              </div>
            </div>

            <div className="form-grid-2" style={{ marginBottom: "1rem" }}>
              <div className="form-group">
                <label className="form-label">Company Type</label>
                <select className="form-select" value={companyType} onChange={(e) => setCompanyType(e.target.value)}>
                  <option value="Product-based">Product-based</option>
                  <option value="Startup">Startup (Funded)</option>
                  <option value="MNC">Global MNC</option>
                  <option value="Service-based">Service-based</option>
                  <option value="Any">Any Company Type</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Seniority Level</label>
                <select className="form-select" value={seniority} onChange={(e) => setSeniority(e.target.value)}>
                  <option value="entry">Fresher / Junior (0-2 yrs)</option>
                  <option value="mid">Mid-level (2-5 yrs)</option>
                  <option value="senior">Senior Level (5-8 yrs)</option>
                  <option value="lead">Lead / Principal (8+ yrs)</option>
                  <option value="any">Any Seniority</option>
                </select>
              </div>
            </div>


            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <button type="button" className="btn-secondary" onClick={() => setStep(1)}>
                Back
              </button>
              <button type="button" className="btn-primary" onClick={handleFinish}>
                <CheckCircle size={15} />
                <span>Save Profile & Launch</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
