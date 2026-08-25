import pytest

from jobagent.application.generic_filler import FormField, plan_field
from jobagent.tracking.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


def test_text_field_filled_from_config(profile, preferences, store):
    field = FormField(label="Email address", input_type="email", dom_id="jobagent-0")
    decision = plan_field(field, profile, preferences, store)
    assert decision.action == "fill"
    assert decision.value == profile.email


def test_required_unanswerable_text_field_escalates(profile, preferences, store):
    field = FormField(label="Describe your ideal team culture", input_type="textarea", dom_id="jobagent-0", required=True)
    decision = plan_field(field, profile, preferences, store)
    assert decision.action == "escalate"


def test_optional_unanswerable_text_field_is_skipped_not_escalated(profile, preferences, store):
    field = FormField(label="Describe your ideal team culture", input_type="textarea", dom_id="jobagent-0", required=False)
    decision = plan_field(field, profile, preferences, store)
    assert decision.action == "skip_optional"


def test_resume_file_field_uploads_when_path_given(profile, preferences, store):
    field = FormField(label="Resume/CV", input_type="file", dom_id="jobagent-0", required=True)
    decision = plan_field(field, profile, preferences, store, resume_path="/tmp/resume.txt")
    assert decision.action == "upload"
    assert decision.file_path == "/tmp/resume.txt"


def test_resume_file_field_escalates_when_no_path_given(profile, preferences, store):
    field = FormField(label="Resume/CV", input_type="file", dom_id="jobagent-0", required=True)
    decision = plan_field(field, profile, preferences, store)
    assert decision.action == "escalate"


def test_optional_cover_letter_upload_skipped_when_not_generated(profile, preferences, store):
    field = FormField(label="Cover Letter (optional)", input_type="file", dom_id="jobagent-0", required=False)
    decision = plan_field(field, profile, preferences, store)
    assert decision.action == "skip_optional"


def test_select_field_matches_option_text(profile, preferences, store):
    field = FormField(
        label="Are you willing to relocate?", input_type="select", dom_id="jobagent-0", required=True,
        options=[{"value": "yes", "text": "Yes"}, {"value": "no", "text": "No"}],
    )
    decision = plan_field(field, profile, preferences, store)
    assert decision.action == "select"
    assert decision.value == "No"  # profile fixture sets willing_to_relocate: false


def test_radio_group_matches_option_and_targets_correct_dom_id(profile, preferences, store):
    field = FormField(
        label="Do you require visa sponsorship?", input_type="radio_group", required=True,
        options=[
            {"jobagentId": "opt-yes", "optionLabel": "Yes"},
            {"jobagentId": "opt-no", "optionLabel": "No"},
        ],
    )
    decision = plan_field(field, profile, preferences, store)
    assert decision.action == "choose_option"
    assert decision.option_id == "opt-no"  # profile fixture sets requires_sponsorship: false


def test_unlabeled_required_field_escalates(profile, preferences, store):
    field = FormField(label="", input_type="text", dom_id="jobagent-0", required=True)
    decision = plan_field(field, profile, preferences, store)
    assert decision.action == "escalate"


def test_diversity_question_select_matches_prefer_not_to_say(profile, preferences, store):
    field = FormField(
        label="Gender identity", input_type="select", dom_id="jobagent-0", required=False,
        options=[{"value": "m", "text": "Male"}, {"value": "f", "text": "Female"}, {"value": "x", "text": "Prefer not to say"}],
    )
    decision = plan_field(field, profile, preferences, store)
    assert decision.action == "select"
    assert decision.value == "Prefer not to say"
