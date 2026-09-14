import React, { useState } from 'react';
import { Upload, CheckCircle, FileText, ArrowRight, X } from 'lucide-react';
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
      <div className="modal-card" style={{ maxWidth: "560px" }}>
        <div className="modal-header">
          <div className="modal-title">Job Search Profile (India Edition)</div>
          <button className="close-btn" onClick={onClose}><X size={18} /></button>
        </div>

        {error && (
          <div style={{ background: "rgba(239, 68, 68, 0.15)", border: "1px solid rgba(239, 68, 68, 0.3)", color: "#f87171", padding: "0.6rem 0.8rem", borderRadius: "8px", fontSize: "0.85rem", marginBottom: "1rem" }}>
            {error}
          </div>
        )}

        {step === 1 && (
          <div>
            <p style={{ fontSize: "0.9rem", color: "var(--text-secondary)", marginBottom: "1.25rem" }}>
              Upload your resume (PDF, DOCX, Image). We’ll parse your tech stack, calculate holistic Fitness Scores,
              and auto-generate tailored .docx resumes and cover letters for every matching opportunity.
            </p>
            <label style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "2.5rem 1rem",
              border: "2px dashed var(--border-subtle)",
              borderRadius: "var(--radius-md)",
              cursor: "pointer",
              background: "var(--bg-tertiary)",
              transition: "border 0.2s"
            }}>
              <Upload size={36} color="var(--accent-gold)" style={{ marginBottom: "0.75rem" }} />
              <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>
                {uploading ? "Extracting resume text, OCR & skills..." : "Click to select or drag Resume (PDF, DOCX, Images)"}
              </span>
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                All formats supported (Digital or scanned PDF, DOCX, TXT, PNG, JPG up to 15MB)
              </span>
              <input type="file" accept=".pdf,.docx,.doc,.txt,.png,.jpg,.jpeg,.webp" onChange={handleFileUpload} disabled={uploading} style={{ display: "none" }} />
            </label>
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "1.25rem" }}>
              <button className="btn-secondary" onClick={() => setStep(2)}>
                Skip resume for now <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
              Specify your preferences. We remember this permanently and tailor all applications accordingly.
            </p>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <div className="form-group">
                <label className="form-label" style={{ fontSize: "0.8rem" }}>Candidate Full Name</label>
                <input
                  className="form-input"
                  placeholder="e.g. Alex Sharma"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label" style={{ fontSize: "0.8rem" }}>Notice Period</label>
                <select className="form-select" value={noticePeriod} onChange={(e) => setNoticePeriod(e.target.value)}>
                  <option value="Immediate">Immediate</option>
                  <option value="15 Days">15 Days</option>
                  <option value="30 Days">30 Days</option>
                  <option value="60 Days">60 Days</option>
                  <option value="90 Days">90 Days</option>
                </select>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <div className="form-group">
                <label className="form-label" style={{ fontSize: "0.8rem" }}>Target Role / Title</label>
                <input
                  className="form-input"
                  placeholder="e.g. Backend Engineer, React Developer"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  autoFocus
                />
              </div>

              <div className="form-group">
                <label className="form-label" style={{ fontSize: "0.8rem" }}>Target Location</label>
                <input
                  className="form-input"
                  placeholder="e.g. Bangalore, Hyderabad, Pune, Remote India"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                />
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <div className="form-group">
                <label className="form-label" style={{ fontSize: "0.8rem" }}>Company Type</label>
                <select className="form-select" value={companyType} onChange={(e) => setCompanyType(e.target.value)}>
                  <option value="Product-based">Product-based</option>
                  <option value="Startup">Startup (Funded)</option>
                  <option value="MNC">Global MNC</option>
                  <option value="Service-based">Service-based</option>
                  <option value="Any">Any Company Type</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label" style={{ fontSize: "0.8rem" }}>Seniority Level</label>
                <select className="form-select" value={seniority} onChange={(e) => setSeniority(e.target.value)}>
                  <option value="entry">Fresher / Junior (0-2 yrs)</option>
                  <option value="mid">Mid-level (2-5 yrs)</option>
                  <option value="senior">Senior Level (5-8 yrs)</option>
                  <option value="lead">Lead / Principal (8+ yrs)</option>
                  <option value="any">Any Seniority</option>
                </select>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" style={{ fontSize: "0.8rem" }}>Expected CTC (LPA / USD)</label>
              <input
                className="form-input"
                placeholder="e.g. 18-28 LPA"
                value={expectedCtc}
                onChange={(e) => setExpectedCtc(e.target.value)}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "1.25rem" }}>
              <button className="btn-secondary" onClick={() => setStep(1)}>Back</button>
              <button className="btn-primary" onClick={handleFinish}>
                Save Profile & Start <CheckCircle size={15} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
