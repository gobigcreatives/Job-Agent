import pytest

from jobagent.config import ConfigError, load_domain_policy, load_preferences, load_profile


def test_load_profile(config_dir):
    profile = load_profile(config_dir)
    assert profile.name == "Jamie Test"
    assert "Social media strategy" in profile.skills
    assert profile.resume_text.startswith("<!--") or "Jamie" in profile.resume_text or len(profile.resume_text) > 0


def test_load_preferences(config_dir):
    prefs = load_preferences(config_dir)
    assert "Social Media Manager" in prefs.target_roles
    assert prefs.scoring.auto_apply_min_score == 80
    assert prefs.limits.max_applications_per_day == 15


def test_load_domain_policy(config_dir):
    policy = load_domain_policy(config_dir)
    assert "linkedin.com" in policy.blocked
    assert "indeed.com" in policy.blocked
    assert "boards.greenhouse.io" in policy.allowed


def test_scoring_weights_must_sum_to_one(config_dir):
    prefs_path = config_dir / "preferences.yaml"
    text = prefs_path.read_text().replace("skills_match: 0.30", "skills_match: 0.99")
    prefs_path.write_text(text)
    with pytest.raises(ConfigError, match="sum to 1.0"):
        load_preferences(config_dir)


def test_domain_policy_requires_linkedin_and_indeed_blocked(config_dir):
    policy_path = config_dir / "domain_policy.yaml"
    text = policy_path.read_text().replace("  - linkedin.com\n", "")
    policy_path.write_text(text)
    with pytest.raises(ConfigError, match="linkedin.com"):
        load_domain_policy(config_dir)


def test_missing_config_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="Missing config file"):
        load_profile(tmp_path / "nonexistent")
