from ed_mcp.format import compact_thread, compact_thread_detail, thread_url


def test_compact_thread():
    thread = {
        "id": 3,
        "course_id": 1,
        "user_id": 42,
        "content": "<document><paragraph>abcdef</paragraph></document>",
    }
    users = {42: {"name": "Ada", "course_role": "staff"}}
    result = compact_thread(thread, users, "us", body_chars=3)
    assert (result["author"], result["author_role"], result["body"]) == ("Ada", "staff", "abc…")
    assert result["number"] is None
    assert (
        compact_thread({**thread, "user": {"name": "Embedded"}}, {42: {"id": 42}}, "us")["author"]
        == "Embedded"
    )
    assert compact_thread({**thread, "is_anonymous": True}, users, "us")["author_role"] is None
    assert compact_thread({**thread, "is_anonymous": True}, users, "us")["author"] == "Anonymous"
    assert compact_thread(thread, {}, "us")["author"] == "user 42"
    assert thread_url(1, 3, "us") == "https://edstem.org/us/courses/1/discussion/3"


def test_detail_recursive_links():
    payload = {
        "thread": {
            "id": 3,
            "course_id": 1,
            "content": '<link href="https://a">A</link>',
            "comments": [
                {
                    "content": '<link href="https://a">A</link>',
                    "comments": [{"id": 8, "content": '<image src="https://b"/>'}],
                }
            ],
        }
    }
    result = compact_thread_detail(payload, "us")
    assert result["comments"][0]["replies"][0]["id"] == 8
    assert [link["url"] for link in result["links"]] == ["https://a", "https://b"]
