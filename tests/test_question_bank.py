import pytest

from jobagent.application.question_bank import answer_question, classify_question
from jobagent.tracking.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


@pytest.mark.parametrize(
    "question,expected_kind",
    [
        ("Are you legally authorised to work in the UK?", "work_authorization"),
        ("Will you now or in the future require visa sponsorship?", "sponsorship"),
        ("What is your notice period?", "notice_period"),
        ("Are you willing to relocate?", "relocation"),
        ("What is your salary expectation?", "salary_expectation"),
        ("LinkedIn Profile URL", "linkedin_url"),
        ("Portfolio / personal website", "portfolio_url"),
        ("How did you hear about this role?", "referral_source"),
        ("Gender (optional)", "diversity_optional"),
        ("Why do you want to work here?", "cover_letter_prompt"),
        ("What is your favourite programming language for elephants?", "other"),
    ],
)
def test_classify_question(question, expected_kind):
    assert classify_question(question) == expected_kind


def test_work_authorization_answered_from_profile(profile, preferences, store):
    qa = answer_question("Are you authorised to work in the UK?", profile, preferences, store)
    assert qa is not None
    assert qa.answer == profile.work_authorization
    assert qa.confidence >= 0.9


def test_salary_expectation_answered_from_preferences(profile, preferences, store):
    qa = answer_question("What is your salary expectation?", profile, preferences, store)
    assert qa is not None
    assert "35,000" in qa.answer or "35000" in qa.answer


def test_diversity_question_answered_with_prefer_not_to_say(profile, preferences, store):
    qa = answer_question("What is your ethnicity?", profile, preferences, store)
    assert qa is not None
    assert qa.answer == "Prefer not to say"


def test_unclassifiable_question_returns_none(profile, preferences, store):
    qa = answer_question("Explain the Fibonacci sequence relevance to elephants", profile, preferences, store)
    assert qa is None


def test_learned_answer_takes_priority_over_config(profile, preferences, store):
    store.set_learned_answer("notice_period", "Immediately available")
    qa = answer_question("What is your notice period?", profile, preferences, store)
    assert qa.answer == "Immediately available"
    assert qa.source.startswith("learned:")


def test_learning_a_kind_answers_future_questions_of_same_kind(profile, preferences, store):
    # "other" kind, first time: no confident answer available.
    assert answer_question("Describe a time you led a rebrand project", profile, preferences, store) is None
