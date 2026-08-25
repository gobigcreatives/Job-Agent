"""Generates a cover letter for a specific job (pipeline step GENERATE COVER
LETTER). Same factual-grounding constraint as CV tailoring: draws only on
the candidate's real profile/resume and the job description in front of it.
"""
from __future__ import annotations

from jobagent.config import Profile
from jobagent.generation.llm import LLMClient
from jobagent.models import JobListing

_SYSTEM_PROMPT = """You write concise, specific cover letters for job applications.

Rules:
- Ground every claim in the candidate's actual resume/skills — never invent
  experience, employers, or achievements.
- Reference something concrete from the job description to show the letter
  isn't generic.
- 3-4 short paragraphs. No placeholder brackets like [Company Name] — use
  the real values given.
- Output only the letter body text, no subject line, no commentary."""


def generate_cover_letter(base_resume: str, job: JobListing, profile: Profile, llm: LLMClient) -> str:
    prompt = (
        f"CANDIDATE: {profile.name}\nEmail: {profile.email}\n\n"
        f"CANDIDATE BACKGROUND (resume):\n{base_resume}\n\n"
        f"JOB\nTitle: {job.title}\nCompany: {job.company}\n"
        f"Description:\n{job.description[:6000]}\n\n"
        "Write the cover letter."
    )
    return llm.complete(_SYSTEM_PROMPT, prompt, max_tokens=1200)
