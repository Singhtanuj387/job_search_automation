"""
Document Generator & Materials Packager.
Generates ATS-optimized DOCX resumes and cover letters tailored per job
using human-written tone (banning AI clichés), and bundles them into a ZIP archive.
"""
import io
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

# AI clichés banned per SKILL.md
BANNED_CLICHES = {
    r"\bspearheaded\b": "led",
    r"\bleveraged\b": "used",
    r"\bresults-driven\b": "practical",
    r"\bdynamic professional\b": "software engineer",
    r"\bcutting-edge\b": "modern",
    r"\bsynergy\b": "collaboration",
    r"\bseamlessly\b": "smoothly",
    r"\butilize\b": "use",
    r"\butilized\b": "used",
    r"\bproven track record\b": "track record",
    r"\bpassionate about\b": "focused on",
}


def sanitize_filename(name: str) -> str:
    """Sanitizes text to safe filename characters."""
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', name).strip('_')


def purge_ai_cliches(text: str) -> str:
    """Replaces overly polished AI buzzwords with natural, concrete human phrasing."""
    cleaned = text
    for pattern, replacement in BANNED_CLICHES.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    return cleaned


class DocumentGenerator:
    """
    Generates tailored DOCX resumes, cover letters, and ZIP bundles.
    """

    @classmethod
    def generate_resume(
        cls,
        candidate_name: str,
        profile: Dict[str, Any],
        job: Dict[str, Any],
        tailored_bullets: List[str],
    ) -> docx.Document:
        """
        Creates an ATS-optimized, clean 2-page DOCX resume tailored to the target job.
        """
        doc = docx.Document()

        # Set standard margins (0.75 inch)
        for section in doc.sections:
            section.top_margin = Inches(0.75)
            section.bottom_margin = Inches(0.75)
            section.left_margin = Inches(0.75)
            section.right_margin = Inches(0.75)

        # 1. Header (Name & Contact)
        name_p = doc.add_paragraph()
        name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        name_run = name_p.add_run(candidate_name or "Candidate Name")
        name_run.bold = True
        name_run.font.size = Pt(20)
        name_run.font.color.rgb = RGBColor(30, 41, 59)

        contact_parts = []
        if profile.get("location"):
            contact_parts.append(profile["location"])
        if profile.get("email"):
            contact_parts.append(profile["email"])
        if profile.get("phone"):
            contact_parts.append(profile["phone"])
        if profile.get("linkedin_url"):
            contact_parts.append(profile["linkedin_url"])
        if profile.get("notice_period"):
            contact_parts.append(f"Notice: {profile['notice_period']}")

        contact_p = doc.add_paragraph(" | ".join(contact_parts) if contact_parts else "India | Open to Opportunities")
        contact_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact_p.paragraph_format.space_after = Pt(12)

        # Helper to add clean section heading
        def add_section_header(title: str):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(title.upper())
            run.bold = True
            run.font.size = Pt(11)
            run.font.color.rgb = RGBColor(15, 23, 42)
            return p

        # 2. Professional Summary
        add_section_header("Professional Summary")
        summary_text = (
            f"Software Engineer with experience building scalable backend services and responsive web applications. "
            f"Demonstrated background aligning with {job.get('company', 'target employer')}'s requirements for {job.get('title', 'the role')}. "
            f"Focused on clean code, automated testing, API performance, and reliable delivery."
        )
        summary_text = purge_ai_cliches(summary_text)
        sum_p = doc.add_paragraph(summary_text)
        sum_p.paragraph_format.space_after = Pt(8)

        # 3. Technical Skills
        add_section_header("Core Technical Skills")
        skills_p = doc.add_paragraph()
        skills_p.add_run("Languages & Frameworks: ").bold = True
        skills_p.add_run("Python, JavaScript, TypeScript, React, FastAPI, Node.js, HTML5/CSS3\n")
        skills_p.add_run("Databases & Cloud: ").bold = True
        skills_p.add_run("PostgreSQL, MongoDB, Redis, Docker, AWS, Git, CI/CD\n")
        skills_p.add_run("Architecture & Practices: ").bold = True
        skills_p.add_run("RESTful APIs, Microservices, Unit Testing, Agile, Performance Tuning")
        skills_p.paragraph_format.space_after = Pt(8)

        # 4. Experience & Tailored Bullets
        add_section_header("Work Experience")

        role_p = doc.add_paragraph()
        title_run = role_p.add_run(f"{profile.get('role', 'Software Engineer')} — Previous Experience")
        title_run.bold = True
        date_run = role_p.add_run("  |  Recent")
        date_run.font.color.rgb = RGBColor(100, 116, 139)

        # Add tailored bullets (cleansed of AI clichés)
        bullets = tailored_bullets or [
            f"Built and maintained core production services, meeting delivery timelines for {job.get('company', 'the team')}.",
            "Designed and documented REST endpoints, improving query latency and data throughput.",
            "Wrote unit and integration test suites, reducing regression rates across releases.",
        ]
        for bullet in bullets:
            cleaned_bullet = purge_ai_cliches(bullet)
            bp = doc.add_paragraph(style="List Bullet")
            bp.paragraph_format.space_after = Pt(3)
            bp.add_run(cleaned_bullet)

        # 5. Key Projects
        add_section_header("Key Projects")
        proj_p = doc.add_paragraph()
        proj_run = proj_p.add_run("Automated Data Pipeline & Web Application")
        proj_run.bold = True
        doc.add_paragraph(
            "Architected a modular data pipeline with rate-limiting, deduplication, and search filtering. "
            "Delivered a fast web dashboard with instant search indexing.",
            style="List Bullet",
        )

        # 6. Education
        add_section_header("Education")
        edu_p = doc.add_paragraph()
        edu_run = edu_p.add_run("Bachelor of Technology in Computer Science / Engineering")
        edu_run.bold = True
        doc.add_paragraph("Coursework in Data Structures, Algorithms, Database Systems, Computer Networks.")

        return doc

    @classmethod
    def generate_cover_letter(
        cls,
        candidate_name: str,
        profile: Dict[str, Any],
        job: Dict[str, Any],
        cover_letter_text: Optional[str] = None,
    ) -> docx.Document:
        """
        Creates a clean, human-written DOCX cover letter (< 300 words).
        """
        doc = docx.Document()

        for section in doc.sections:
            section.top_margin = Inches(0.8)
            section.bottom_margin = Inches(0.8)
            section.left_margin = Inches(0.8)
            section.right_margin = Inches(0.8)

        # Candidate Header
        name_p = doc.add_paragraph()
        name_run = name_p.add_run(candidate_name or "Candidate Name")
        name_run.bold = True
        name_run.font.size = Pt(16)

        contact_parts = []
        if profile.get("email"):
            contact_parts.append(profile["email"])
        if profile.get("phone"):
            contact_parts.append(profile["phone"])
        if profile.get("location"):
            contact_parts.append(profile["location"])

        doc.add_paragraph(" | ".join(contact_parts) if contact_parts else "India")
        doc.add_paragraph(datetime.now().strftime("%B %d, %Y"))

        # Recipient
        comp = job.get("company", "Hiring Team")
        role = job.get("title", "Software Engineer")
        doc.add_paragraph(f"\nTo the Engineering Hiring Team\n{comp}")

        # Letter Body
        if cover_letter_text and len(cover_letter_text.strip()) > 50:
            body = purge_ai_cliches(cover_letter_text.strip())
        else:
            notice = profile.get("notice_period") or "available on standard notice"
            body = (
                f"I am writing to apply for the {role} position at {comp}.\n\n"
                f"Having worked across modern application stacks with an emphasis on backend stability and clean user interfaces, "
                f"I am confident I can contribute directly to your team's current development goals. My background includes designing "
                f"reliable APIs, automating data workflows, and shipping features collaboratively.\n\n"
                f"I appreciate {comp}'s product focus and engineering culture. I am currently based in {profile.get('location', 'India')}, "
                f"{notice}, and ready to step in and add value to your codebase.\n\n"
                f"Thank you for your time and consideration. I look forward to discussing the role."
            )
            body = purge_ai_cliches(body)

        clean_name = (candidate_name or profile.get("name") or "Applicant").replace("_", " ").strip()
        has_signoff = "sincerely" in body.lower() or "regards" in body.lower()

        for paragraph_text in body.split("\n\n"):
            p = doc.add_paragraph(paragraph_text.strip())
            p.paragraph_format.space_after = Pt(8)

        # Sign-off if not already included in body
        if not has_signoff:
            doc.add_paragraph(f"\nSincerely,\n{clean_name}")

        return doc

    @classmethod
    def create_application_package(
        cls,
        run_id: str,
        candidate_name: str,
        profile: Dict[str, Any],
        jobs: List[Dict[str, Any]],
        output_dir: str = "data/materials",
    ) -> Dict[str, Any]:
        """
        Generates individual docx resumes, docx cover letters, and bundles them into a ZIP archive.
        ZIP structure:
        [Name]_Applications_[Date].zip
        ├── [Company]_[City]/
        │   ├── [Name]_Resume_[Company]_[RoleShort].docx
        │   └── [Name]_CoverLetter_[Company].docx
        """
        run_folder = Path(output_dir) / run_id
        run_folder.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime("%Y%m%d")
        c_name_clean = sanitize_filename(candidate_name or "Applicant")
        zip_filename = f"{c_name_clean}_Applications_{date_str}.zip"
        zip_path = run_folder / zip_filename

        generated_files: List[Dict[str, str]] = []

        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for job in jobs:
                company = job.get("company", "Company")
                title = job.get("title", "Role")
                location = job.get("location", "India")
                job_id = job.get("source_job_id") or job.get("job_id") or "job"

                company_clean = sanitize_filename(company)
                city_clean = sanitize_filename(location.split(",")[0] if "," in location else location)
                role_clean = sanitize_filename(title[:25])
                subfolder = f"{company_clean}_{city_clean}"

                # 1. Generate DOCX Resume
                resume_doc = cls.generate_resume(
                    candidate_name=candidate_name,
                    profile=profile,
                    job=job,
                    tailored_bullets=job.get("tailored_bullets", []),
                )
                resume_filename = f"{c_name_clean}_Resume_{company_clean}_{role_clean}.docx"
                resume_path = run_folder / f"{job_id}_resume.docx"
                resume_doc.save(str(resume_path))

                # Add to ZIP under company folder
                zf.write(str(resume_path), arcname=f"{subfolder}/{resume_filename}")

                # 2. Generate DOCX Cover Letter
                letter_doc = cls.generate_cover_letter(
                    candidate_name=candidate_name,
                    profile=profile,
                    job=job,
                    cover_letter_text=job.get("cover_letter"),
                )
                letter_filename = f"{c_name_clean}_CoverLetter_{company_clean}_{role_clean}.docx"
                letter_path = run_folder / f"{job_id}_letter.docx"
                letter_doc.save(str(letter_path))

                # Add to ZIP under company folder
                zf.write(str(letter_path), arcname=f"{subfolder}/{letter_filename}")

                generated_files.append({
                    "job_id": job_id,
                    "company": company,
                    "title": title,
                    "resume_file": resume_filename,
                    "letter_file": letter_filename,
                    "resume_download_url": f"/api/materials/{run_id}/resume/{job_id}",
                    "letter_download_url": f"/api/materials/{run_id}/cover-letter/{job_id}",
                })

        return {
            "run_id": run_id,
            "zip_filename": zip_filename,
            "zip_path": str(zip_path),
            "zip_download_url": f"/api/materials/{run_id}/zip",
            "files": generated_files,
        }
