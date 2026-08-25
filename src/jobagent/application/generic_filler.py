"""Fills an application form without vendor-specific selectors.

Rather than hardcoding CSS selectors for Greenhouse/Lever/Workday/etc (which
drift constantly as those products ship new frontends), this walks the
form's actual DOM once per page load, computes each field's accessible
label the same way a screen reader would (associated <label>, aria-label,
placeholder, nearest legend/label text), and classifies each label with the
same question_bank used for free-text application questions. That makes it
work across ATS vendors without per-vendor maintenance, at the cost of
occasionally missing an unusually-marked-up field — which is exactly the
"escalate rather than guess" case this module is built around.

The DOM-walking step (`extract_fields`) needs a live Playwright page and
isn't unit-tested here. `plan_field`, the decision logic that decides
fill/select/upload/skip/escalate for a given field, is pure and is unit
tested (tests/test_generic_filler.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from difflib import SequenceMatcher
from typing import Optional

from jobagent.application.question_bank import answer_question, classify_question
from jobagent.config import Preferences, Profile
from jobagent.models import JobListing
from jobagent.tracking.store import Store

_MIN_FILL_CONFIDENCE = 0.7
_MIN_OPTION_MATCH_RATIO = 0.5

_RESUME_LABEL_HINTS = ["resume", "resumé", "cv", "curriculum vitae"]
_COVER_LETTER_LABEL_HINTS = ["cover letter", "cover_letter", "covering letter", "letter of motivation"]

# Walks all form inputs, resolves each one's accessible label, groups
# radio/checkbox inputs sharing a `name` into one logical question with its
# option list, and tags every element with a stable data-jobagent-id so the
# Python side can address it after this snapshot.
EXTRACTION_JS = r"""
() => {
  function labelFor(el) {
    let label = el.getAttribute('aria-label');
    if (label) return label.trim();
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) return lab.innerText.trim();
    }
    const parentLabel = el.closest('label');
    if (parentLabel) return parentLabel.innerText.trim();
    const placeholder = el.getAttribute('placeholder');
    if (placeholder) return placeholder.trim();
    const container = el.closest('div, li, fieldset, .field, .form-group');
    if (container) {
      const textEl = container.querySelector('label, legend, .label, [class*="label"]');
      if (textEl && textEl !== el) return textEl.innerText.trim();
    }
    return '';
  }

  const results = [];
  let counter = 0;
  const inputs = Array.from(document.querySelectorAll('form input, form textarea, form select'));

  const radioGroups = {};
  inputs.forEach(el => {
    if ((el.type === 'radio' || el.type === 'checkbox') && el.name) {
      (radioGroups[el.name] = radioGroups[el.name] || []).push(el);
    }
  });

  inputs.forEach(el => {
    if (['hidden', 'submit', 'button', 'image'].includes(el.type)) return;
    if ((el.type === 'radio' || el.type === 'checkbox') && el.name) return;
    const id = 'jobagent-' + (counter++);
    el.setAttribute('data-jobagent-id', id);
    const entry = {
      jobagentId: id,
      label: labelFor(el),
      type: el.tagName.toLowerCase() === 'select' ? 'select'
            : el.tagName.toLowerCase() === 'textarea' ? 'textarea'
            : (el.type || 'text'),
      required: !!el.required,
      accept: el.getAttribute('accept') || '',
      name: el.name || '',
    };
    if (entry.type === 'select') {
      entry.options = Array.from(el.options).map(o => ({ value: o.value, text: o.text.trim() }));
    }
    results.push(entry);
  });

  Object.entries(radioGroups).forEach(([name, els]) => {
    const first = els[0];
    const fieldset = first.closest('fieldset');
    let groupLabel = '';
    if (fieldset) {
      const legend = fieldset.querySelector('legend');
      if (legend) groupLabel = legend.innerText.trim();
    }
    if (!groupLabel) {
      const container = first.closest('div, li, .field, .form-group');
      if (container) {
        const textEl = container.querySelector('label, legend, .label, [class*="label"]');
        if (textEl) groupLabel = textEl.innerText.trim();
      }
    }
    const options = els.map(el => {
      const id = 'jobagent-' + (counter++);
      el.setAttribute('data-jobagent-id', id);
      return { jobagentId: id, optionLabel: labelFor(el) || el.value || '' };
    });
    results.push({
      jobagentId: null,
      label: groupLabel,
      type: first.type === 'checkbox' ? 'checkbox_group' : 'radio_group',
      required: !!first.required,
      name,
      options,
    });
  });

  return results;
}
"""


@dataclass
class FormField:
    label: str
    input_type: str
    dom_id: Optional[str] = None
    name: str = ""
    required: bool = False
    accept: str = ""
    options: list[dict] = dc_field(default_factory=list)


@dataclass
class FieldDecision:
    field: FormField
    action: str  # fill | select | upload | choose_option | skip_optional | escalate
    value: Optional[str] = None
    file_path: Optional[str] = None
    option_id: Optional[str] = None
    source: Optional[str] = None


def parse_field(raw: dict) -> FormField:
    return FormField(
        label=raw.get("label", ""),
        input_type=raw.get("type", "text"),
        dom_id=raw.get("jobagentId"),
        name=raw.get("name", ""),
        required=bool(raw.get("required")),
        accept=raw.get("accept", ""),
        options=raw.get("options", []),
    )


def _best_option_match(answer: str, option_texts: list[str]) -> Optional[str]:
    answer_l = answer.strip().lower()
    if not answer_l or not option_texts:
        return None
    best, best_ratio = None, 0.0
    for text in option_texts:
        text_l = text.strip().lower()
        if not text_l:
            continue
        if answer_l == text_l or answer_l in text_l or text_l in answer_l:
            return text
        ratio = SequenceMatcher(None, answer_l, text_l).ratio()
        if ratio > best_ratio:
            best, best_ratio = text, ratio
    return best if best_ratio >= _MIN_OPTION_MATCH_RATIO else None


def _plan_file_field(f: FormField, resume_path: Optional[str], cover_letter_path: Optional[str]) -> FieldDecision:
    label_l = f.label.lower()
    if any(h in label_l for h in _RESUME_LABEL_HINTS):
        if resume_path:
            return FieldDecision(f, "upload", file_path=resume_path, source="resume")
        return FieldDecision(f, "escalate", source="missing_resume_file")
    if any(h in label_l for h in _COVER_LETTER_LABEL_HINTS):
        if cover_letter_path:
            return FieldDecision(f, "upload", file_path=cover_letter_path, source="cover_letter")
        return FieldDecision(f, "skip_optional" if not f.required else "escalate")
    return FieldDecision(f, "escalate" if f.required else "skip_optional", source="unknown_file_field")


def _plan_choice_field(
    f: FormField, profile: Profile, preferences: Preferences, store: Store, job, llm
) -> FieldDecision:
    qa = answer_question(f.label, profile, preferences, store, job=job, llm=llm)
    option_texts = [
        opt.get("text") or opt.get("optionLabel", "") for opt in f.options
    ]
    if qa and qa.confidence >= _MIN_FILL_CONFIDENCE:
        matched = _best_option_match(qa.answer, option_texts)
        if matched is not None:
            if f.input_type == "select":
                return FieldDecision(f, "select", value=matched, source=qa.source)
            matching_option = next(
                (o for o in f.options if (o.get("optionLabel", "") == matched)), None
            )
            if matching_option:
                return FieldDecision(f, "choose_option", option_id=matching_option["jobagentId"], source=qa.source)
    return FieldDecision(f, "escalate" if f.required else "skip_optional")


def plan_field(
    f: FormField,
    profile: Profile,
    preferences: Preferences,
    store: Store,
    job: Optional[JobListing] = None,
    llm=None,
    resume_path: Optional[str] = None,
    cover_letter_path: Optional[str] = None,
) -> FieldDecision:
    if f.input_type == "file":
        return _plan_file_field(f, resume_path, cover_letter_path)

    if f.input_type in ("select", "radio_group", "checkbox_group"):
        return _plan_choice_field(f, profile, preferences, store, job, llm)

    if not f.label.strip():
        return FieldDecision(f, "escalate" if f.required else "skip_optional", source="no_label")

    qa = answer_question(f.label, profile, preferences, store, job=job, llm=llm)
    if qa and qa.confidence >= _MIN_FILL_CONFIDENCE:
        return FieldDecision(f, "fill", value=qa.answer, source=qa.source)

    if classify_question(f.label) == "diversity_optional":
        return FieldDecision(f, "skip_optional", source="policy:optional_diversity")

    return FieldDecision(f, "escalate" if f.required else "skip_optional")


def apply_decision(session, decision: FieldDecision) -> None:
    page = session.page
    f = decision.field
    if decision.action == "fill":
        page.locator(f'[data-jobagent-id="{f.dom_id}"]').fill(decision.value or "")
    elif decision.action == "upload":
        page.locator(f'[data-jobagent-id="{f.dom_id}"]').set_input_files(decision.file_path)
    elif decision.action == "select":
        page.locator(f'[data-jobagent-id="{f.dom_id}"]').select_option(label=decision.value)
    elif decision.action == "choose_option":
        page.locator(f'[data-jobagent-id="{decision.option_id}"]').check()


def extract_fields(session) -> list[FormField]:
    raw_fields = session.page.evaluate(EXTRACTION_JS)
    return [parse_field(r) for r in raw_fields]


def fill_form(
    session,
    profile: Profile,
    preferences: Preferences,
    store: Store,
    job: Optional[JobListing] = None,
    llm=None,
    resume_path: Optional[str] = None,
    cover_letter_path: Optional[str] = None,
) -> list[FieldDecision]:
    fields = extract_fields(session)
    decisions = [
        plan_field(
            f, profile, preferences, store, job=job, llm=llm,
            resume_path=resume_path, cover_letter_path=cover_letter_path,
        )
        for f in fields
    ]
    for decision in decisions:
        if decision.action in ("fill", "upload", "select", "choose_option"):
            apply_decision(session, decision)
    return decisions
