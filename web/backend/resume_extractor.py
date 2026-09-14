"""
Enhanced Resume Data Extractor.
Extracts structured fields from resume text for auto-filling job application forms.
Extends the basic ResumeParser with deeper extraction of experience, education, and skills.
"""
import re
from typing import Any, Dict, List, Optional


class ResumeExtractor:
    """
    Extracts structured application-ready data from resume plain text.
    All extraction is regex/heuristic-based with optional LLM enhancement.
    """

    @classmethod
    def extract_all(cls, resume_text: str, profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Master extraction method. Returns a dict with all fields needed for job applications.
        Profile data overrides resume extraction where available.
        """
        profile = profile or {}
        text = resume_text or ""

        contact = cls.extract_contact_info(text)
        experience = cls.extract_experience(text)
        education = cls.extract_education(text)
        skills = cls.extract_skills(text)

        full_name = profile.get("name") or contact.get("name", "")
        parts = full_name.split() if full_name else []
        first_name = parts[0] if parts else ""
        last_name = parts[-1] if len(parts) > 1 else ""

        # Experience years helper (numeric)
        exp_years = experience.get("years_of_experience", "")
        exp_years_num = 0
        if exp_years:
            try:
                m = re.search(r"\d+", str(exp_years))
                if m:
                    exp_years_num = int(m.group(0))
            except Exception:
                pass

        return {
            # Contact
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "email": profile.get("email") or contact.get("email", ""),
            "phone": profile.get("phone") or contact.get("phone", ""),
            "linkedin_url": profile.get("linkedin_url") or contact.get("linkedin_url", ""),
            "github_url": profile.get("github_url") or contact.get("github_url", ""),

            # Professional
            "current_title": profile.get("role") or experience.get("current_title", ""),
            "current_company": experience.get("current_company", ""),
            "years_of_experience": experience.get("years_of_experience", ""),
            "experience_years": exp_years_num,
            "location": profile.get("location") or contact.get("location", ""),
            "notice_period": profile.get("notice_period") or "Immediate",
            "expected_ctc": profile.get("expected_ctc_lpa") or "",

            # Education
            "highest_degree": education.get("highest_degree", ""),
            "university": education.get("university", ""),
            "graduation_year": education.get("graduation_year", ""),
            "gpa": education.get("gpa", ""),
            "education": [education] if education.get("highest_degree") or education.get("university") else [],

            # Skills
            "skills": skills,
            "skills_text": ", ".join(skills) if skills else "",

            # Raw text for LLM fallback
            "resume_text": text,
        }

    @classmethod
    def extract_contact_info(cls, text: str) -> Dict[str, str]:
        """Extracts contact details from resume text."""
        # Handle emails split across line breaks e.g. foo@gmail\ncom
        clean_text_for_contact = re.sub(r"(@[\w\.-]+)\s*[\r\n\s]+\s*([a-zA-Z]{2,6})\b", r"\1.\2", text)
        email_match = re.search(r"[\w\.\-\+]+@[\w\.-]+\.[a-zA-Z]{2,}", clean_text_for_contact)
        phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3,5}\)?[-.\s]?\d{3,5}[-.\s]?\d{3,5}", text)
        linkedin_match = re.search(r"https?://(?:www[\.-]?)?(?:linkedin|inkedin)\.com/in/[\w\-]+", text, re.IGNORECASE)
        linkedin_url = ""
        if linkedin_match:
            linkedin_url = re.sub(r"https?://(?:www[\.-]?)?(?:linkedin|inkedin)\.com", "https://www.linkedin.com", linkedin_match.group(0))
        github_match = re.search(r"(https?://(?:www\.)?github\.com/[\w\-]+)", text)

        # Name: first non-empty line that isn't an email/URL/phone
        name = ""
        for line in text.strip().split("\n")[:5]:
            line = line.strip()
            if line and len(line) < 50 and not any(c in line for c in "@:/+") and not re.match(r"^\d", line):
                name = line
                break

        # Location extraction
        location = ""
        loc_patterns = [
            r"(?:Location|Address|City|Based in)[:\s]*([A-Za-z\s,]+?)(?:\n|$|\|)",
            r"\b(Moradabad|Bangalore|Bengaluru|Hyderabad|Pune|Mumbai|Delhi|Chennai|Noida|Gurgaon|Gurugram|Kolkata|Roorkee|Dehradun|Chandigarh|Jaipur|Ahmedabad|Remote|New York|San Francisco|London|Berlin)(?:,\s*(?:India|USA|UK|Germany|[A-Za-z\s]+))?\b",
        ]
        for pat in loc_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                location = m.group(0).strip().rstrip(",").strip()
                break

        return {
            "name": name,
            "email": email_match.group(0) if email_match else "",
            "phone": phone_match.group(0).strip() if phone_match else "",
            "linkedin_url": linkedin_url,
            "github_url": github_match.group(1) if github_match else "",
            "location": location,
        }

    @classmethod
    def extract_experience(cls, text: str) -> Dict[str, Any]:
        """Extracts current title, company, and years of experience."""
        current_title = ""
        current_company = ""
        years_of_experience = ""

        # Find "Experience" or "Work Experience" section
        exp_section = ""
        exp_match = re.search(
            r"(?:WORK\s*)?EXPERIENCE|PROFESSIONAL\s*EXPERIENCE|EMPLOYMENT\s*HISTORY",
            text, re.IGNORECASE
        )
        if exp_match:
            exp_start = exp_match.end()
            # Find next section header
            next_section = re.search(
                r"\n(?:EDUCATION|SKILLS|PROJECTS|CERTIFICATIONS|AWARDS|PUBLICATIONS|LANGUAGES|INTERESTS|REFERENCES)\b",
                text[exp_start:], re.IGNORECASE
            )
            if next_section:
                exp_section = text[exp_start:exp_start + next_section.start()]
            else:
                exp_section = text[exp_start:exp_start + 2000]

        if exp_section:
            # First role is typically the current/most recent
            # Pattern: Title at/| Company or Company — Title
            role_patterns = [
                r"([A-Z][A-Za-z\s/&]+?)\s*(?:at|@|\|)\s*([A-Z][A-Za-z\s&,.]+?)(?:\n|$|\|)",
                r"([A-Z][A-Za-z\s&,.]+?)\s*[-—–]\s*([A-Z][A-Za-z\s/&]+?)(?:\n|$|\|)",
                r"\*\*([^*]+)\*\*\s*(?:at|@|-)\s*([^\n|]+)",
                r"([A-Z][A-Za-z\s/&]{3,35})\s*\n\s*(?:[A-Za-z\s,]+?\n\s*)?([A-Za-z0-9\s&,.\-]{3,40})\s*/\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|20\d\d)",
            ]
            for pat in role_patterns:
                m = re.search(pat, exp_section.strip()[:500])
                if m:
                    g1 = m.group(1).strip()
                    g2 = m.group(2).strip()
                    # Determine which is title vs company
                    title_words = {"engineer", "developer", "manager", "analyst", "designer", "architect",
                                   "lead", "director", "intern", "consultant", "specialist", "scientist"}
                    if any(w in g1.lower() for w in title_words):
                        current_title = g1
                        current_company = g2
                    else:
                        current_company = g1
                        current_title = g2
                    break

        # Years of experience: look for explicit mentions
        yoe_patterns = [
            r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience|exp\.?)",
            r"(?:experience|exp\.?)(?:\s*[-:])?\s*(\d+)\+?\s*(?:years?|yrs?)",
            r"over\s+(\d+)\s+years",
        ]
        for pat in yoe_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                years_of_experience = m.group(1)
                break

        # Fallback: count year ranges in experience entries
        if not years_of_experience:
            year_ranges = re.findall(r"(20\d{2})\s*[-–—]\s*(20\d{2}|present|current)", text, re.IGNORECASE)
            if year_ranges:
                earliest = min(int(yr[0]) for yr in year_ranges)
                latest_candidates = []
                for yr in year_ranges:
                    if yr[1].lower() in ("present", "current"):
                        latest_candidates.append(2026)
                    else:
                        latest_candidates.append(int(yr[1]))
                latest = max(latest_candidates) if latest_candidates else 2026
                yoe = latest - earliest
                if 0 < yoe < 40:
                    years_of_experience = str(yoe)

        return {
            "current_title": current_title,
            "current_company": current_company,
            "years_of_experience": years_of_experience,
        }

    @classmethod
    def extract_education(cls, text: str) -> Dict[str, str]:
        """Extracts education details."""
        highest_degree = ""
        university = ""
        graduation_year = ""
        gpa = ""

        # Find education section
        edu_match = re.search(r"EDUCATION|ACADEMIC", text, re.IGNORECASE)
        if edu_match:
            edu_start = edu_match.end()
            next_section = re.search(
                r"\n(?:EXPERIENCE|SKILLS|PROJECTS|CERTIFICATIONS|AWARDS|WORK)\b",
                text[edu_start:], re.IGNORECASE
            )
            edu_section = text[edu_start:edu_start + (next_section.start() if next_section else 1000)]

            # Degree patterns
            degree_patterns = [
                (r"(?:Ph\.?D\.?|Doctor(?:ate)?)", "Ph.D."),
                (r"(?:M\.?S\.?|M\.?Sc\.?|Master(?:s|'s)?(?:\s+of\s+(?:Science|Arts|Engineering|Business|Technology))?|MBA|M\.?Tech\.?|M\.?E\.?)", "Master's"),
                (r"(?:B\.?S\.?|B\.?Sc\.?|Bachelor(?:s|'s)?(?:\s+of\s+(?:Science|Arts|Engineering|Technology))?|B\.?Tech\.?|B\.?E\.?|B\.?A\.?)", "Bachelor's"),
            ]
            for pat, label in degree_patterns:
                if re.search(pat, edu_section, re.IGNORECASE):
                    highest_degree = label
                    # Try to get full degree name
                    full_match = re.search(rf"({pat}[\w\s.,()]*?)(?:\n|,|\|)", edu_section, re.IGNORECASE)
                    if full_match:
                        degree_text = full_match.group(1).strip()
                        if len(degree_text) < 80:
                            highest_degree = degree_text
                    break

            # University name: look for "University", "Institute", "College"
            uni_match = re.search(
                r"([A-Z][\w\s&'.-]*(?:University|Institute|College|School|Academy)[\w\s&'.-]*?)(?:\n|,|\||\d{4})",
                edu_section, re.IGNORECASE
            )
            if uni_match:
                university = uni_match.group(1).strip()

            # Graduation year
            year_matches = re.findall(r"20\d{2}", edu_section)
            if year_matches:
                graduation_year = max(year_matches)

            # GPA
            gpa_match = re.search(r"(?:GPA|CGPA|Grade)[:\s]*(\d+\.?\d*)\s*/?\s*(\d+\.?\d*)?", edu_section, re.IGNORECASE)
            if gpa_match:
                gpa = gpa_match.group(1)
                if gpa_match.group(2):
                    gpa = f"{gpa}/{gpa_match.group(2)}"

        return {
            "highest_degree": highest_degree,
            "university": university,
            "graduation_year": graduation_year,
            "gpa": gpa,
        }

    @classmethod
    def extract_skills(cls, text: str) -> List[str]:
        """Extracts a list of technical/professional skills."""
        skills = []

        # Find skills section
        skills_match = re.search(r"(?:TECHNICAL\s*)?SKILLS|TECHNOLOGIES|COMPETENCIES|EXPERTISE", text, re.IGNORECASE)
        if skills_match:
            s_start = skills_match.end()
            next_section = re.search(
                r"\n(?:EXPERIENCE|EDUCATION|PROJECTS|CERTIFICATIONS|AWARDS|WORK)\b",
                text[s_start:], re.IGNORECASE
            )
            skills_section = text[s_start:s_start + (next_section.start() if next_section else 800)]

            # Split on common separators
            for line in skills_section.strip().split("\n"):
                line = line.strip().lstrip("-•*·")
                if not line or len(line) > 200:
                    continue
                # Split by commas, pipes, semicolons
                parts = re.split(r"[,|;]", line)
                for part in parts:
                    part = re.sub(r"^\s*[-•*·:]\s*", "", part).strip()
                    # Clean category labels like "Languages:" or "Frameworks:"
                    part = re.sub(r"^[A-Za-z\s]+:\s*", "", part).strip()
                    if part and 1 < len(part) < 40 and not re.match(r"^\d+$", part):
                        skills.append(part)

        # Fallback: scan for known tech keywords
        if not skills:
            known_skills = [
                "Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Rust", "Ruby", "PHP",
                "React", "Angular", "Vue", "Node.js", "Express", "Django", "Flask", "FastAPI", "Spring",
                "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "Jenkins", "CI/CD",
                "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Kafka", "RabbitMQ",
                "Git", "Linux", "REST", "GraphQL", "Microservices", "Agile", "Scrum",
                "Machine Learning", "TensorFlow", "PyTorch", "Data Science", "SQL",
                "HTML", "CSS", "Tailwind", "Sass", "Bootstrap",
            ]
            text_lower = text.lower()
            for skill in known_skills:
                if skill.lower() in text_lower:
                    skills.append(skill)

        return list(dict.fromkeys(skills))  # deduplicate preserving order

    @classmethod
    def get_field_value(cls, field_label: str, resume_data: Dict[str, Any]) -> Optional[str]:
        """
        Given a form field label (from a job application), attempts to find the matching
        value from extracted resume data.
        Returns None if no match found (caller should ask the user).
        """
        # Clean asterisks, colons, parentheses
        label = re.sub(r"[\*:\(\)\?]+", "", field_label).lower().strip()

        # Direct field mappings
        mappings = {
            "full name": "full_name",
            "name": "full_name",
            "first name": "first_name",
            "last name": "last_name",
            "email": "email",
            "email address": "email",
            "phone": "phone",
            "phone number": "phone",
            "mobile": "phone",
            "mobile number": "phone",
            "mobile phone": "phone",
            "mobile phone number": "phone",
            "contact number": "phone",
            "phone country code": "phone",
            "linkedin": "linkedin_url",
            "linkedin url": "linkedin_url",
            "linkedin profile": "linkedin_url",
            "current title": "current_title",
            "current job title": "current_title",
            "current role": "current_title",
            "job title": "current_title",
            "headline": "current_title",
            "current company": "current_company",
            "current employer": "current_company",
            "company": "current_company",
            "organization": "current_company",
            "years of experience": "years_of_experience",
            "total experience": "years_of_experience",
            "experience": "years_of_experience",
            "work experience": "years_of_experience",
            "location": "location",
            "city": "location",
            "current location": "location",
            "address": "location",
            "notice period": "notice_period",
            "availability": "notice_period",
            "when can you start": "notice_period",
            "start date": "notice_period",
            "expected salary": "expected_ctc",
            "expected ctc": "expected_ctc",
            "salary expectation": "expected_ctc",
            "compensation": "expected_ctc",
            "desired salary": "expected_ctc",
            "education": "highest_degree",
            "degree": "highest_degree",
            "highest qualification": "highest_degree",
            "qualification": "highest_degree",
            "university": "university",
            "college": "university",
            "school": "university",
            "graduation year": "graduation_year",
            "year of graduation": "graduation_year",
            "gpa": "gpa",
            "cgpa": "gpa",
            "skills": "skills_text",
            "technical skills": "skills_text",
            "key skills": "skills_text",
        }

        # Try exact match
        if label in mappings:
            field_key = mappings[label]
            value = resume_data.get(field_key, "")
            if not value and field_key == "years_of_experience":
                exp_yr = resume_data.get("experience_years")
                if exp_yr is not None and str(exp_yr).strip() not in ("", "0"):
                    value = str(exp_yr)
            if value:
                # Handle first/last name splitting
                if label == "first name" and " " in str(value):
                    return str(value).split()[0]
                elif label == "last name" and " " in str(value):
                    return " ".join(str(value).split()[1:])
                return str(value)

        # Try partial match
        for key_label, field_key in mappings.items():
            if key_label in label or label in key_label:
                value = resume_data.get(field_key, "")
                if not value and field_key == "years_of_experience":
                    exp_yr = resume_data.get("experience_years")
                    if exp_yr is not None and str(exp_yr).strip() not in ("", "0"):
                        value = str(exp_yr)
                if value:
                    return str(value)

        return None
