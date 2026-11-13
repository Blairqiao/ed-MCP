from ed_mcp.importance import AlertRules, score_thread


def test_staff_announcement_and_plain_question():
    result = score_thread(
        {"type": "announcement", "content": "<document><paragraph>Midterm</paragraph></document>"},
        "Staff",
        AlertRules(),
    )
    assert (result.score, result.important) == (10, True)
    assert result.reasons == ["announcement", "posted by staff", "keywords: midterm"]
    plain = score_thread({"type": "question", "title": "Hello"}, "student", AlertRules())
    assert (plain.score, plain.reasons, plain.important) == (0, [], False)


def test_keyword_cap_category_and_anonymous_watch():
    rules = AlertRules(
        keywords=["one", "two", "three", "four"], categories=["General"], watch_user_ids=[7]
    )
    result = score_thread(
        {
            "title": "one two three four",
            "subcategory": "GENERAL",
            "user_id": 7,
            "is_anonymous": True,
        },
        None,
        rules,
    )
    assert result.score == 8
    assert result.reasons == ["keywords: one, two, three", "category: GENERAL"]


def test_rules_from_dict_merges_weights_and_ignores_unknown():
    rules = AlertRules.from_dict({"threshold": 8, "weights": {"keyword": 9}, "other": 1})
    assert rules.threshold == 8
    assert rules.weights["keyword"] == 9
    assert rules.weights["announcement"] == 5
    assert "other" not in rules.to_dict()
