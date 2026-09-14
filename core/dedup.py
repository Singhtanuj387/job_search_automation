"""
Fuzzy Deduplication Engine for Normalized Job Postings.
Matches jobs across sources using (company, title, location) fuzzy similarity.
"""
import re
from typing import Dict, List, Tuple
from core.models import NormalizedJob

try:
    from rapidfuzz import fuzz
except ImportError:
    import difflib

    class _FuzzFallback:
        @staticmethod
        def token_sort_ratio(s1: str, s2: str) -> float:
            return difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio() * 100.0

    fuzz = _FuzzFallback()


LEGAL_SUFFIXES = re.compile(
    r"\b(inc\.?|llc\.?|ltd\.?|limited|gmbh|corp\.?|corporation|technologies|technology|solutions|co\.?|group|pvt\.?)\b",
    re.IGNORECASE,
)
TITLE_NOISE = re.compile(
    r"(\(m/f/d\)|\(f/m/d\)|\(remote\)|\(hybrid\)|\b(full-time|part-time|contract)\b)",
    re.IGNORECASE,
)


def normalize_company(company: str) -> str:
    """Cleans company name by removing corporate entity designators and punctuation."""
    c = LEGAL_SUFFIXES.sub("", company.lower())
    c = re.sub(r"[^\w\s]", " ", c)
    return " ".join(c.split())


def normalize_title(title: str) -> str:
    """Cleans job title by removing employment tags and expanding common abbreviations."""
    t = TITLE_NOISE.sub("", title.lower())
    t = re.sub(r"\bsr\.?\b", "senior", t)
    t = re.sub(r"\bjr\.?\b", "junior", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return " ".join(t.split())


def normalize_location(location: str) -> str:
    """Normalizes location keywords, mapping city synonyms and remote indicators."""
    loc = (location or "").lower()
    if any(k in loc for k in ["remote", "worldwide", "anywhere", "telecommute", "work from home"]):
        return "remote"
    loc = loc.replace("bengaluru", "bangalore")
    loc = re.sub(r"[^\w\s]", " ", loc)
    return " ".join(loc.split())


def are_jobs_duplicate(
    job_a: NormalizedJob,
    job_b: NormalizedJob,
    title_threshold: float = 85.0,
    company_threshold: float = 85.0,
    location_threshold: float = 75.0,
) -> bool:
    """
    Computes fuzzy matching score across company, title, and location.
    """
    comp_a = normalize_company(job_a.company)
    comp_b = normalize_company(job_b.company)
    if not comp_a or not comp_b:
        return False

    comp_score = fuzz.token_sort_ratio(comp_a, comp_b)
    if comp_score < company_threshold:
        return False

    title_a = normalize_title(job_a.title)
    title_b = normalize_title(job_b.title)
    title_score = fuzz.token_sort_ratio(title_a, title_b)
    if title_score < title_threshold:
        return False

    loc_a = normalize_location(job_a.location)
    loc_b = normalize_location(job_b.location)
    if loc_a == "remote" and loc_b == "remote":
        loc_score = 100.0
    elif not loc_a or not loc_b or loc_a == "any" or loc_b == "any" or loc_a == "unspecified" or loc_b == "unspecified":
        loc_score = 80.0
    elif hasattr(fuzz, "token_set_ratio"):
        loc_score = fuzz.token_set_ratio(loc_a, loc_b)
    else:
        loc_score = fuzz.token_sort_ratio(loc_a, loc_b)

    return loc_score >= location_threshold


def deduplicate_jobs(
    jobs: List[NormalizedJob],
) -> Tuple[List[NormalizedJob], Dict[str, float]]:
    """
    Groups and merges duplicate jobs from different sources.
    Prefers records with higher confidence and longer descriptions.
    """
    if not jobs:
        return [], {
            "total_raw_jobs": 0,
            "unique_jobs": 0,
            "duplicates_pruned": 0,
            "reduction_rate": 0.0,
        }

    clusters: List[List[NormalizedJob]] = []

    for job in jobs:
        matched = False
        for cluster in clusters:
            # Compare against representative (first item) of cluster
            if are_jobs_duplicate(job, cluster[0]):
                cluster.append(job)
                matched = True
                break
        if not matched:
            clusters.append([job])

    unique_jobs: List[NormalizedJob] = []
    for cluster in clusters:
        # Choose best candidate based on (confidence, description length)
        best = max(
            cluster,
            key=lambda j: (j.confidence, len(j.description or ""))
        )
        unique_jobs.append(best)

    total_in = len(jobs)
    total_out = len(unique_jobs)
    pruned = total_in - total_out
    reduction_rate = (pruned / total_in * 100.0) if total_in > 0 else 0.0

    metrics = {
        "total_raw_jobs": total_in,
        "unique_jobs": total_out,
        "duplicates_pruned": pruned,
        "reduction_rate": round(reduction_rate, 2),
    }

    return unique_jobs, metrics
