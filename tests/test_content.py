from ed_mcp.content import ed_xml_to_text, ensure_ed_xml, extract_links, markdown_to_ed_xml


def test_markdown_conversion():
    xml = markdown_to_ed_xml(
        "# Hello\n**bold** *italic* [x](https://x) `**x**` <\n```py\na < b\n```\n"
        "```\nraw\n```\n- one\n- two\n1. first\n2. second\n> [!INFO] hello\n> there"
    )
    for expected in [
        '<heading level="1">Hello</heading>',
        "<bold>bold</bold>",
        "<italic>italic</italic>",
        '<link href="https://x">x</link>',
        "<code>**x**</code>",
        "&lt;",
        '<snippet language="py" runnable="false">a &lt; b</snippet>',
        "<pre>raw</pre>",
        '<list style="bullet">',
        '<list style="number">',
        '<callout type="info"><paragraph>hello there</paragraph></callout>',
    ]:
        assert expected in xml
    assert ensure_ed_xml('  <document version="2.0"/>') == '  <document version="2.0"/>'


def test_text_and_links():
    xml = (
        '<document><paragraph>A &amp; B <link href="https://a">site</link></paragraph>'
        "<list><list-item><paragraph>one</paragraph></list-item></list><paragraph>"
        '<image src="https://img"/> https://bare and <link href="https://a">again</link>'
        '<link href="mailto:x">mail</link></paragraph></document>'
    )
    assert (
        ed_xml_to_text(xml) == "A & B site (https://a)\n- one\n[image: https://img] https://bare "
        "and again (https://a)mail (mailto:x)"
    )
    assert [(x["url"], x["kind"]) for x in extract_links(xml)] == [
        ("https://a", "link"),
        ("https://img", "image"),
        ("https://bare", "url"),
    ]
    assert ed_xml_to_text(None) == ""


def test_markdown_image():
    from ed_mcp.content import markdown_to_ed_xml

    url = "https://static.us.edusercontent.com/files/abc"
    assert markdown_to_ed_xml(f"![a.png]({url})") == (
        f'<document version="2.0"><figure><image src="{url}"/></figure></document>'
    )
    inline = markdown_to_ed_xml(f"see ![a.png]({url}) here")
    assert "!" not in inline and f'<link href="{url}">a.png</link>' in inline
