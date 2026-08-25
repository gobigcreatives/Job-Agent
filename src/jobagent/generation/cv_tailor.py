"""Tailors the candidate's base resume to a specific job (pipeline step
TAILOR CV). The LLM may reorder, re-emphasize, and rewrite — it must never
invent employers, dates, titles, or skills the base resume doesn't contain.
"""
from __future__ import annotations

from jobagent.config import Profile
from jobagent.generation.llm import LLMClient
from jobagent.models import JobListing

_SYSTEM_PROMPT = """You are tailoring a job candidate's resume for one specific vacancy.

Rules (do not break these):
- Never invent employers, job titles, dates, qualifications, or skills that
  are not present in the base resume provided.
- You MAY reorder sections, reorder bullet points, re-emphasize relevant
  achievements, and rewrite phrasing to better match the target role's
  language — as long as every fact stays true to the base resume.
- Keep it concise and factual. No commentary, no explanation of what you
  changed — output only the finished resume.
- Output plain Markdown, ready to read as a resume."""


def tailor_resume(base_resume: str, job: JobListing, profile: Profile, llm: LLMClient) -> str:
    prompt = (
        f"CANDIDATE: {profile.name}, {profile.seniority} level, "
        f"{profile.experience_years} years experience.\n\n"
        f"BASE RESUME:\n{base_resume}\n\n"
        f"TARGET JOB\nTitle: {job.title}\nCompany: {job.company}\n"
        f"Description:\n{job.description[:6000]}\n\n"
        "Rewrite the base resume to best match this job, following the rules."
    )
    return llm.complete(_SYSTEM_PROMPT, prompt, max_tokens=2500)
