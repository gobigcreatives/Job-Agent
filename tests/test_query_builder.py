from jobagent.search.query_builder import generate_queries


def test_generates_multiple_queries(profile, preferences):
    queries = generate_queries(profile, preferences)
    assert len(queries) > 10


def test_queries_are_deduplicated(profile, preferences):
    queries = generate_queries(profile, preferences)
    assert len(queries) == len(set(q.lower() for q in queries))


def test_excludes_linkedin_and_indeed(profile, preferences):
    queries = generate_queries(profile, preferences)
    role_location_queries = [q for q in queries if "jobs London" in q]
    assert role_location_queries
    for q in role_location_queries:
        assert "-site:linkedin.com" in q
        assert "-site:indeed.com" in q


def test_includes_role_and_location_combinations(profile, preferences):
    queries = generate_queries(profile, preferences)
    joined = " | ".join(queries)
    assert '"Social Media Manager" jobs London' in joined
    assert "remote" in joined.lower()


def test_includes_ats_restricted_queries(profile, preferences):
    queries = generate_queries(profile, preferences)
    assert any("site:boards.greenhouse.io" in q for q in queries)


def test_seniority_qualified_queries_present(profile, preferences):
    # None of the fixture's target roles trigger a seniority-qualified
    # variant (they already contain "Manager", the fixture's seniority), so
    # verify the mechanism directly against a role that doesn't.
    from dataclasses import replace

    prefs = replace(preferences, target_roles=["Social Media Strategist"])
    queries = generate_queries(profile, prefs)
    assert any('"Manager Social Media Strategist"' in q for q in queries)


def test_seniority_not_duplicated_when_role_already_contains_it(profile, preferences):
    queries = generate_queries(profile, preferences)
    assert not any('"Manager Content Manager"' in q for q in queries)
