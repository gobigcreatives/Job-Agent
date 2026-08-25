"""Formats the end-of-cycle report (requirement #13). Every number here
should be independently reconstructable from the Store, so a summary can be
regenerated after the fact (`jobagent report`) as well as printed live at
the end of a run.
"""
from __future__ import annotations

from jobagent.models import RunSummary

_MAX_TOP_APPLICATIONS = 10


def format_summary(summary: RunSummary) -> str:
    lines = [
        "JOB SEARCH SUMMARY",
        "",
        f"Jobs discovered: {summary.jobs_discovered}",
        f"Relevant jobs: {summary.jobs_relevant}",
        f"Skipped: {summary.jobs_skipped}",
        f"Applications submitted: {summary.applications_submitted}",
        f"Waiting for input: {summary.waiting_for_input}",
        f"Manual verification required: {summary.manual_verification_required}",
        f"Failed: {summary.failed}",
    ]

    ranked = sorted(
        (r for r in summary.top_applications if r.score is not None),
        key=lambda r: r.score.total,
        reverse=True,
    )[:_MAX_TOP_APPLICATIONS]

    if ranked:
        lines += ["", "Top applications:", ""]
        for i, result in enumerate(ranked, start=1):
            lines.append(f"{i}. {result.job.company or 'Unknown company'}")
            lines.append(f"   {result.job.title}")
            lines.append(f"   Match: {result.score.total:.0f}%")
            if i != len(ranked):
                lines.append("")

    return "\n".join(lines)
