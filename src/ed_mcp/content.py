"""Convert Ed's document format and extract links."""

import html
import re
from html.parser import HTMLParser


def _inline(text: str) -> str:
    codes = []

    def save(match):
        codes.append(f"<code>{html.escape(match.group(1), quote=True)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", save, text)
    text = html.escape(text, quote=True).replace("&#x27;", "'")
    text = re.sub(r"\*\*(.+?)\*\*", r"<bold>\1</bold>", text)
    text = re.sub(r"(?<!\*)\*(.+?)\*(?!\*)", r"<italic>\1</italic>", text)
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<link href="\2">\1</link>', text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<link href="\2">\1</link>', text)
    text = re.sub(r"\$([^$]+)\$", r"<math>\1</math>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def markdown_to_ed_xml(text: str) -> str:
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            language = line[3:].strip()
            i += 1
            code = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            escaped = html.escape("\n".join(code), quote=True).replace("&#x27;", "'")
            if language:
                lang = html.escape(language, quote=True).replace("&#x27;", "'")
                blocks.append(f'<snippet language="{lang}" runnable="false">{escaped}</snippet>')
            else:
                blocks.append(f"<pre>{escaped}</pre>")
        elif not line.strip():
            pass
        elif match := re.match(r"^(#{1,6})\s+(.+)$", line):
            blocks.append(
                f'<heading level="{len(match.group(1))}">{_inline(match.group(2))}</heading>'
            )
        elif match := re.match(r"^>\s*\[!(success|info|warning|error)\]\s*(.*)$", line, re.I):
            parts = [match.group(2)]
            while i + 1 < len(lines) and lines[i + 1].startswith("> "):
                i += 1
                parts.append(lines[i][2:])
            body = _inline(" ".join(parts))
            blocks.append(
                f'<callout type="{match.group(1).lower()}"><paragraph>{body}</paragraph></callout>'
            )
        elif re.match(r"^[-*]\s+", line) or re.match(r"^\d+\.\s+", line):
            bullet = bool(re.match(r"^[-*]\s+", line))
            pattern = r"^[-*]\s+" if bullet else r"^\d+\.\s+"
            items = []
            while i < len(lines) and re.match(pattern, lines[i]):
                body = _inline(re.sub(pattern, "", lines[i]))
                items.append(f"<list-item><paragraph>{body}</paragraph></list-item>")
                i += 1
            i -= 1
            style = "bullet" if bullet else "number"
            blocks.append(f'<list style="{style}">{"".join(items)}</list>')
        elif match := re.match(r"^\s*!\[[^\]]*\]\(([^)\s]+)\)\s*$", line):
            src = html.escape(match.group(1), quote=True)
            blocks.append(f'<figure><image src="{src}"/></figure>')
        else:
            blocks.append(f"<paragraph>{_inline(line)}</paragraph>")
        i += 1
    return f'<document version="2.0">{"".join(blocks)}</document>'


def ensure_ed_xml(content: str) -> str:
    return content if content.lstrip().startswith("<document") else markdown_to_ed_xml(content)


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "list-item":
            self.parts.append("- ")
        elif tag == "link":
            self.links.append((len(self.parts), attrs.get("href", "")))
        elif tag == "image":
            self.parts.append(f"[image: {attrs.get('src', '')}]")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "link" and self.links:
            start, url = self.links.pop()
            label = "".join(self.parts[start:])
            if url and label != url:
                self.parts.append(f" ({url})" if label else url)
        if tag in {"paragraph", "heading", "list-item", "pre", "snippet", "callout"}:
            if not self.parts or not self.parts[-1].endswith("\n"):
                self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def ed_xml_to_text(xml: str | None) -> str:
    if not xml:
        return ""
    parser = _TextParser()
    parser.feed(xml)
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()


_URL = re.compile(r"https?://[^\s<>\"']+")


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.seen = set()
        self.pending = []

    def add(self, url, text, kind):
        if url not in self.seen:
            self.seen.add(url)
            self.results.append({"url": url, "text": text, "kind": kind})
            return len(self.results) - 1
        return None

    def handle_starttag(self, tag, attrs):
        indices = []
        for name, value in attrs:
            if (
                name in {"href", "src", "url"}
                and value
                and value.startswith(("http://", "https://"))
            ):
                index = self.add(value, "", tag)
                if index is not None:
                    indices.append(index)
        self.pending.append((tag, indices, []))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.pending) - 1, -1, -1):
            if self.pending[i][0] == tag:
                _, indices, parts = self.pending.pop(i)
                for index in indices:
                    self.results[index]["text"] = "".join(parts).strip()
                break

    def handle_data(self, data):
        for _, _, parts in self.pending:
            parts.append(data)
        for match in _URL.finditer(data):
            url = match.group().rstrip(".,;:!?)")
            self.add(url, url, "url")


def extract_links(xml: str | None) -> list[dict]:
    if not xml:
        return []
    parser = _LinkParser()
    parser.feed(xml)
    return parser.results
