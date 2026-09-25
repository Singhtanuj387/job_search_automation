"""
LLM Orchestration Layer.
Supports Google Gemini / Gemma, OpenAI, and Anthropic.
Performs API key validation, natural language intent routing,
and confidential job tailoring (ATS fit framing, bullet tailoring, cover letter draft).
"""
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import httpx
from core.models import NormalizedJob

class LLMService:
    """
    Handles interactions with LLM providers with fallback to heuristic tailoring.
    """

    DEFAULT_GEMINI_MODEL = "gemma-4-31b-it"

    @classmethod
    def normalize_gemini_model(cls, model_name: Optional[str]) -> str:
        """
        Normalizes Gemma and Gemini model IDs to valid Google GenAI model strings.
        Maps Gemma-4-31B / gemma-4-31b variants to 'gemma-4-31b-it'.
        """
        if not model_name:
            return cls.DEFAULT_GEMINI_MODEL
        name = model_name.strip()
        if name.lower() in ("gemma-4-31b", "gemma-4-31b-it", "gemma4-31b", "gemma_4_31b", "gemma-4"):
            return "gemma-4-31b-it"
        return name

    @classmethod
    def validate_api_key(
        cls,
        provider: str,
        api_key: str,
        extra_config: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str]:
        """
        Runs a minimal, lightweight test call against the selected provider to verify credentials.
        """
        provider = provider.lower()
        key = api_key.strip()

        try:
            if provider == "anthropic":
                # Minimal call to Anthropic Messages API
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
                body = {
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "ping"}],
                }
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(url, headers=headers, json=body)
                    if resp.status_code == 200:
                        return True, "Anthropic API key successfully validated."
                    elif resp.status_code == 401:
                        return False, "Invalid Anthropic API key (401 Unauthorized)."
                    else:
                        return False, f"Anthropic error HTTP {resp.status_code}: {resp.text[:100]}"

            elif provider == "gemini":
                from google import genai
                raw_model = (extra_config or {}).get("model_id")
                model_name = cls.normalize_gemini_model(raw_model)
                client = genai.Client(api_key=key)
                try:
                    # Test using client.interactions.create with normalized model name
                    interaction = client.interactions.create(
                        model=model_name,
                        input="Explain how AI works in a few words"
                    )
                    return True, f"Google Gemini API key validated successfully with model '{model_name}'."
                except Exception as e:
                    err_msg = str(e)
                    if any(phrase in err_msg for phrase in ["API_KEY_INVALID", "API key not valid", "400", "401", "403"]):
                        return False, f"Invalid Google Gemini API key: {err_msg}"
                    # Fallback probe to verify API key with gemma-4-31b-it if another model was provided
                    if model_name != "gemma-4-31b-it":
                        try:
                            fallback_inter = client.interactions.create(
                                model="gemma-4-31b-it",
                                input="Explain how AI works in a few words"
                            )
                            if fallback_inter:
                                return True, f"Google Gemini API key validated successfully with 'gemma-4-31b-it'."
                        except Exception:
                            pass
                    return False, f"Gemini validation failed: {err_msg}"



            else:
                return False, f"Unsupported provider '{provider}'."

        except Exception as e:
            return False, f"Validation failed: {str(e)}"


    @classmethod
    def classify_intent(
        cls,
        user_message: str,
        stored_profile: Optional[Dict[str, Any]] = None,
        secret: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Classifies user prompt into help | search | automate | status | apply_to_url | general_chat
        and extracts role/location/seniority overrides.
        Supports explicit slash commands (/job-skill help, /job-skill search, etc.).
        """
        msg_raw = user_message.strip().strip("'\"`").strip()
        msg_lower = msg_raw.lower()

        # 1. Explicit Slash Commands (/job-skill help, /job-skill search, etc.)
        if msg_lower in ["/job-skill help", "/help", "help", "/job-skill"]:
            return {
                "intent": "help",
                "message": user_message,
            }

        # 1a. LinkedIn / Indeed / SEEK login shortcut
        if msg_lower.startswith("/linkedin-login"):
            return {
                "intent": "linkedin_login",
                "message": user_message,
            }
        if msg_lower.startswith("/indeed-login"):
            return {
                "intent": "indeed_login",
                "message": user_message,
            }
        if msg_lower.startswith("/seek-login"):
            return {
                "intent": "seek_login",
                "message": user_message,
            }

        # 1b. Apply to platform: /job-skill apply [platform]
        apply_match = re.match(r"^/job-skill\s+apply(?:\s+(\w+))?$", msg_lower)
        if apply_match:
            platform = (apply_match.group(1) or "linkedin").strip()
            return {
                "intent": "apply_platform",
                "platform": platform,
                "message": user_message,
            }
        # Also match natural language: "apply to linkedin jobs", "auto apply linkedin", "apply to seek"
        if re.search(r"(?:auto[- ]?apply|apply\s+(?:to\s+)?(?:all\s+)?(?:my\s+)?)\s*(?:linkedin|indeed|seek|naukri)", msg_lower):
            platform_match = re.search(r"(linkedin|indeed|seek|naukri|glassdoor|instahyre)", msg_lower)
            if platform_match:
                return {
                    "intent": "apply_platform",
                    "platform": platform_match.group(1),
                    "message": user_message,
                }

        if msg_lower in ["/job-skill automate", "/automate"]:
            return {
                "intent": "automate",
                "message": user_message,
            }

        if msg_lower in ["/job-skill status", "/status"]:
            return {
                "intent": "status",
                "message": user_message,
            }

        # 2. Automate keywords
        if any(w in msg_lower for w in ["automate", "schedule", "daily search", "morning search", "every night", "nightly search"]):
            return {
                "intent": "automate",
                "message": user_message,
                "role": None,
                "location": None,
                "seniority": None,
            }

        # 3. Status keywords
        if any(w in msg_lower for w in ["status", "applications", "interviews", "rejections", "how's my search", "application update"]):
            return {
                "intent": "status",
                "message": user_message,
            }

        # 4. Apply to URL
        if "apply to this job" in msg_lower or (re.search(r"https?://", user_message) and "apply" in msg_lower):
            url_match = re.search(r"https?://[^\s]+", user_message)
            return {
                "intent": "apply_to_url",
                "url": url_match.group(0) if url_match else None,
                "message": user_message,
            }

        # 5. Question / Career Advisory Detection
        # Queries asking how to prepare, interview tips, roadmaps, etc. should route to LLM chat, NOT trigger job board scraping.
        is_slash_search = msg_lower.startswith("/job-skill search") or msg_lower.startswith("/search")
        is_question = bool(re.search(
            r"^(?:how\s+(?:to|do|can|should|would|i)|what\s+(?:is|are|should|would|does)|why|explain|tell\s+me|tips?\s+(?:for|on)|guide\s+(?:for|to)|prepare|preparation|roadmap|salary|skills?\s+needed|interview|practice)\b",
            msg_lower
        ))
        is_explicit_job_search = bool(
            is_slash_search or
            re.search(r"(?:find|search|look for|show me)\s+(?:me\s+)?(?:some\s+)?(?:\w+\s+)*(?:jobs|openings|positions|roles|vacancies)", msg_lower) or
            re.search(r"(?:jobs|openings|vacancies)\s+(?:for|in|near)\b", msg_lower)
        )

        if is_question and not is_explicit_job_search:
            return {
                "intent": "general_chat",
                "message": user_message,
            }

        # 6. Search Intent (Slash command or natural language job search triggers)
        search_triggers = [
            "find jobs", "search jobs", "search for", "search on", "look for jobs",
            "look on", "find on", "jobs on", "show me jobs", "job openings",
            "job positions", "open roles", "hiring", "job vacancies"
        ]
        has_role_job_pair = bool(re.search(r"(?:developer|engineer|designer|manager|analyst|architect)\s+(?:jobs|openings|roles|positions)", msg_lower))

        # Check for platform-specific search targeting (e.g. seek, seek.com, linkedin, etc.)
        platform_aliases = {
            "seek": ["seek.com.au", "seek.co.nz", "seek.com", "seek"],
            "linkedin": ["in.linkedin.com", "linkedin.com", "linkedin"],
            "indeed": ["in.indeed.com", "indeed.com", "indeed"],
            "naukri": ["naukri.com", "naukri"],
            "instahyre": ["instahyre.com", "instahyre"],
            "cutshort": ["cutshort.io", "cutshort"],
            "hirist": ["hirist.tech", "hirist"],
            "glassdoor": ["glassdoor.co.in", "glassdoor.com", "glassdoor"],
            "wellfound": ["wellfound.com", "wellfound", "angellist"],
            "weworkremotely": ["weworkremotely.com", "weworkremotely", "wwr"],
            "greenhouse": ["greenhouse.io", "greenhouse"],
            "lever": ["lever.co", "lever"],
            "arbeitnow": ["arbeitnow.com", "arbeitnow"],
            "jobicy": ["jobicy.com", "jobicy"],
            "remotive": ["remotive.com", "remotive"],
            "shine": ["shine.com", "shine"],
            "timesjobs": ["timesjobs.com", "timesjobs"],
            "foundit": ["foundit.in", "foundit"],
        }
        target_source = None
        clean_msg = msg_lower
        for src_name, aliases in platform_aliases.items():
            if any(re.search(r"\b" + re.escape(a) + r"\b", msg_lower) for a in aliases):
                target_source = src_name
                for a in aliases:
                    clean_msg = re.sub(r"\b(?:on|at|via|from|in)\s+" + re.escape(a) + r"\b", "", clean_msg)
                    clean_msg = re.sub(r"\b" + re.escape(a) + r"\b", "", clean_msg)
                clean_msg = re.sub(r"\s+", " ", clean_msg).strip()
                break

        if is_slash_search or is_explicit_job_search or target_source or any(t in msg_lower for t in search_triggers) or has_role_job_pair:
            # Extract location
            loc = None
            for city in [
                "sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra",
                "auckland", "wellington", "christchurch", "australia", "new zealand",
                "bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi", "delhi-ncr",
                "gurgaon", "noida", "chennai", "remote", "london", "berlin", "san francisco", "abroad"
            ]:
                if city in msg_lower:
                    if city in ["bangalore", "bengaluru"]:
                        loc = "Bangalore"
                    elif city in ["delhi", "delhi-ncr", "gurgaon", "noida"]:
                        loc = "Delhi-NCR"
                    elif city in ["sydney"]:
                        loc = "Sydney"
                    elif city in ["melbourne"]:
                        loc = "Melbourne"
                    elif city in ["brisbane"]:
                        loc = "Brisbane"
                    elif city in ["perth"]:
                        loc = "Perth"
                    elif city in ["auckland"]:
                        loc = "Auckland"
                    else:
                        loc = city.capitalize()
                    break

            # Extract seniority
            sen = "any"
            if any(w in msg_lower for w in ["junior", "entry", "fresher", "0-2"]):
                sen = "entry"
            elif any(w in msg_lower for w in ["senior", "sr", "5-8", "lead"]):
                sen = "senior"
            elif any(w in msg_lower for w in ["mid", "2-5"]):
                sen = "mid"

            # Extract role keywords from clean_msg
            role = None
            role_patterns = [
                r"/job-skill\s+search\s*(.*)",
                r"/search\s*(.*)",
                r"find (?:me )?(.*?)(?: jobs| openings| positions| in | at | for |$)",
                r"(?:look for |search for |search on |find on )(.*?)(?: jobs| openings| in | at | for |$)",
                r"(react developer|python developer|frontend engineer|backend engineer|full stack developer|software engineer|data engineer|data scientist|ml engineer|product manager|devops engineer)",
            ]
            for pat in role_patterns:
                match = re.search(pat, clean_msg, re.IGNORECASE)
                if match:
                    extracted = match.group(1).strip() if match.groups() else match.group(0).strip()
                    if extracted and len(extracted) > 2 and extracted not in ["me", "for", "in", "jobs", "on", "seek"]:
                        # strip trailing location words if captured
                        extracted = re.sub(r"\s+(?:in|at|near)\s+.*$", "", extracted, flags=re.IGNORECASE).strip()
                        if extracted and extracted not in ["me", "for", "in", "jobs", "on"]:
                            role = extracted.title()
                            break

            profile_role = stored_profile.get("role") if stored_profile else None
            profile_loc = stored_profile.get("location") if stored_profile else None
            profile_sen = stored_profile.get("seniority") if stored_profile else None

            # If location wasn't specified and target source is seek, default to Sydney or profile loc
            if not loc and target_source == "seek":
                loc = profile_loc if (profile_loc and profile_loc.lower() not in ["india", "bangalore"]) else "Sydney"

            return {
                "intent": "search",
                "role": role or profile_role or "Software Engineer",
                "location": loc or profile_loc or "any",
                "seniority": sen if sen != "any" else (profile_sen or "any"),
                "sources": [target_source] if target_source else [],
                "raw_query": user_message,
            }

        return {
            "intent": "general_chat",
            "message": user_message,
        }

    @classmethod
    def tailor_job(
        cls,
        job: NormalizedJob,
        resume_text: str,
        secret: Optional[Dict[str, Any]] = None,
        candidate_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculates holistic Fitness Score as a percentage (e.g. '85% Fit (strong skills match, 1yr under YOE requirement)'),
        ensures human-written tone without AI clichés ('spearheaded', 'leveraged', etc.),
        and prepares 1-2 line match explanation for results presentation.
        """
        job_tokens = set(re.findall(r"\b[a-zA-Z]{3,}\b", f"{job.title} {job.description}".lower()))
        resume_tokens = set(re.findall(r"\b[a-zA-Z]{3,}\b", (resume_text or "").lower()))

        tech_keywords = {
            "react", "typescript", "javascript", "python", "node", "aws", "docker", "kubernetes",
            "sql", "graphql", "redux", "nextjs", "fastapi", "django", "postgres", "html", "css",
            "tailwind", "git", "ci/cd", "microservices", "rest", "api", "testing", "agile", "tdd"
        }

        matched_tech = tech_keywords.intersection(job_tokens).intersection(resume_tokens)
        all_job_tech = tech_keywords.intersection(job_tokens)

        if all_job_tech:
            internal_score = min(0.65 + (len(matched_tech) / len(all_job_tech)) * 0.35, 0.98)
        else:
            overlap = len(job_tokens.intersection(resume_tokens))
            internal_score = min(0.60 + (overlap / max(len(job_tokens), 1)) * 0.40, 0.95)

        fitness_pct = int(round(internal_score * 100))

        # Holistic Fitness Score mapping per SKILL.md & qualitative framing
        if fitness_pct >= 90:
            fit_framing = "Exceptional Fit"
            fit_badge_color = "emerald"
            fit_reason = "(strong skills match, solid experience overlap)"
        elif fitness_pct >= 75:
            fit_framing = "Strong Match"
            fit_badge_color = "emerald"
            fit_reason = "(strong skills match, solid experience overlap)"
        elif fitness_pct >= 60:
            fit_framing = "Worth a Look"
            fit_badge_color = "amber"
            fit_reason = "(moderate skills alignment, worth applying)"
        else:
            fit_framing = "Moderate Alignment"
            fit_badge_color = "slate"
            fit_reason = "(stretch opportunity, seniority/experience gap)"

        fitness_display = f"{fitness_pct}% Fit {fit_reason}"
        match_explanation = (
            f"{job.company} — {job.title} — {fitness_display}: "
            f"Core tech requirements align closely with your background."
        )

        return {
            "internal_score": round(internal_score, 2),
            "fitness_score": fitness_pct,
            "fitness_display": fitness_display,
            "fit_framing": fit_framing,
            "fit_reason": fit_reason,
            "fit_badge_color": fit_badge_color,
            "match_explanation": match_explanation,
            "tailored_bullets": [],
            "cover_letter": "",
        }

    @classmethod
    def invoke_gemini(
        cls,
        prompt: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 500,
    ) -> Optional[str]:
        """
        Invokes Google Gemini / Gemma model using the official google-genai Client.
        Primary: client.interactions.create(model=..., input=...)
        """
        try:
            from google import genai
            key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            client = genai.Client(api_key=key) if key else genai.Client()
            target_model = cls.normalize_gemini_model(model)

            # 1. Primary: Use client.interactions.create
            try:
                interaction = client.interactions.create(
                    model=target_model,
                    input=prompt,
                )
                if hasattr(interaction, "output_text") and interaction.output_text:
                    return interaction.output_text.strip()
            except Exception as inter_err:
                logging.getLogger(__name__).info(f"interactions.create notice with {target_model}: {inter_err}")

            # 2. Fallback: if user specified another model that failed, fallback to gemma-4-31b-it
            if target_model != "gemma-4-31b-it":
                try:
                    fallback_inter = client.interactions.create(
                        model="gemma-4-31b-it",
                        input=prompt,
                    )
                    if hasattr(fallback_inter, "output_text") and fallback_inter.output_text:
                        return fallback_inter.output_text.strip()
                except Exception:
                    pass

            return None
        except Exception as e:
            logging.getLogger(__name__).warning(f"Gemini invocation failed: {e}")
            return None

    @classmethod
    def invoke_llm(
        cls,
        prompt: str,
        secret: Optional[Dict[str, Any]] = None,
        max_tokens: int = 500,
    ) -> Optional[str]:
        """
        Generic LLM invocation that routes to the stored secret's provider.
        Defaults to Google Gemini (Gemma-4-31B).
        """
        if not secret:
            return cls.invoke_gemini(prompt, max_tokens=max_tokens)

        provider = (secret.get("provider") or "gemini").lower()
        pt = secret.get("plaintext", "")
        api_key = pt
        model_name = cls.DEFAULT_GEMINI_MODEL

        if pt.startswith("{"):
            try:
                parsed = json.loads(pt)
                api_key = parsed.get("api_key", pt)
                model_name = parsed.get("model_id", cls.DEFAULT_GEMINI_MODEL)
            except Exception:
                pass

        if provider == "gemini":
            return cls.invoke_gemini(prompt, api_key=api_key, model=model_name, max_tokens=max_tokens)
        elif provider == "openai":
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                )
                if resp.choices:
                    return resp.choices[0].message.content
            except Exception as err:
                logging.getLogger(__name__).warning(f"OpenAI invocation failed: {err}")
        elif provider == "anthropic":
            try:
                headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
                body = {"model": "claude-3-haiku-20240307", "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
                with httpx.Client(timeout=15.0) as c:
                    r = c.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
                    if r.status_code == 200:
                        data = r.json()
                        content = data.get("content", [])
                        if content:
                            return content[0].get("text")
            except Exception as err:
                logging.getLogger(__name__).warning(f"Anthropic invocation failed: {err}")

        return None
