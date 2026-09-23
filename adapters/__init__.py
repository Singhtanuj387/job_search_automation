"""
Adapters package registry.
Registers all 18 supported acquisition adapters across Indian job portals,
direct ATS boards, and global tech platforms.
"""
from adapters.arbeitnow import ArbeitnowAdapter
from adapters.career_page_jsonld import CareerPageJsonLdAdapter
from adapters.greenhouse import GreenhouseAdapter
from adapters.jobicy import JobicyAdapter
from adapters.lever import LeverAdapter
from adapters.seek import SeekAdapter
from adapters.remotive import RemotiveAdapter
from adapters.indian_platforms import (
    NaukriAdapter,
    LinkedInAdapter,
    InstahyreAdapter,
    CutshortAdapter,
    HiristAdapter,
    IndeedIndiaAdapter,
    FounditAdapter,
    ShineAdapter,
    TimesJobsAdapter,
    GlassdoorAdapter,
    WellfoundAdapter,
    WeWorkRemotelyAdapter,
)

ALL_ADAPTERS = {
    # 1. Indian Job Portals (Primary per SKILL.md)
    "naukri": NaukriAdapter,
    "linkedin": LinkedInAdapter,
    "instahyre": InstahyreAdapter,
    "cutshort": CutshortAdapter,
    "hirist": HiristAdapter,
    "indeed": IndeedIndiaAdapter,
    "foundit": FounditAdapter,
    "shine": ShineAdapter,
    "timesjobs": TimesJobsAdapter,
    "glassdoor": GlassdoorAdapter,
    # 2. Startup & Remote Platforms
    "wellfound": WellfoundAdapter,
    "weworkremotely": WeWorkRemotelyAdapter,
    # 3. Direct ATS & Global Platforms
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "arbeitnow": ArbeitnowAdapter,
    "jobicy": JobicyAdapter,
    "remotive": RemotiveAdapter,
    "seek": SeekAdapter,
    "career_jsonld": CareerPageJsonLdAdapter,
}
