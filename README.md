# Ed Discussion MCP server

An MCP server for reading and managing Ed Discussion courses, threads, lessons, and alerts from an agent. It uses Ed's unofficial API, which can change without notice.

## Setup

Install dependencies with `uv sync`. Create an API token at [Ed API tokens](https://edstem.org/us/settings/api-tokens), replacing `us` in the URL with your region if needed. Copy `.env.example` to `.env`, set `ED_API_TOKEN` and your `ED_REGION`, then check the connection:

```sh
cp .env.example .env
uv run ed-mcp check
```

`ED_API_BASE_URL` optionally overrides the regional API URL; `ED_STATE_DIR` changes the default `~/.ed-mcp` state directory.

## Register with an agent

For Claude Code, substitute your token and use the absolute project path:

```sh
claude mcp add ed-discussion -e ED_API_TOKEN='<token>' -- uv --directory /Users/blair/Desktop/project/ed-MCP run ed-mcp serve
```

A generic MCP configuration is:

```json
{
  "mcpServers": {
    "ed-discussion": {
      "command": "uv",
      "args": ["--directory", "/Users/blair/Desktop/project/ed-MCP", "run", "ed-mcp", "serve"],
      "env": {"ED_API_TOKEN": "..."}
    }
  }
}
```

Set `ED_REGION` in the agent's environment when your region is not `us`.

## Tools

| Tool | Description |
| --- | --- |
| `list_courses` | List courses and roles to find course IDs. |
| `whoami` | Show the current user and active courses. |
| `get_course_info` | Show course details and discussion categories. |
| `list_threads` | List a page of threads; filters apply to that page. |
| `get_thread` | Read a thread, comments, and links by ID or course number. |
| `search_threads` | Search a course's threads. |
| `list_announcements` | Read recent announcements. |
| `get_links` | Find links in thread bodies, or in a specified thread and its comments. |
| `list_course_users` | List course users, optionally by role. |
| `get_user_activity` | Show a user's course activity. |
| `list_lessons` | List lessons, requirements, readings, and due dates. |
| `get_lesson` | Read lesson slides and links. |
| `list_resources` | List course resources and URLs. |
| `create_thread` | Create a post, question, or announcement. |
| `edit_thread` | Edit a thread. |
| `delete_thread` | Delete a thread. |
| `post_comment` | Post a comment or answer. |
| `reply_to_comment` | Reply to a comment. |
| `edit_comment` | Edit a comment. |
| `delete_comment` | Delete a comment. |
| `thread_action` | Moderate or follow a thread. |
| `comment_action` | Endorse or unendorse a comment. |
| `accept_answer` | Accept an answer. |
| `upload_file` | Upload a local file and return its URL and Markdown. |
| `get_posts_in_range(course_id, start, end="now", include_comments=True, max_threads=200, output="text")` | Retrieve posts created in a time window for summaries. |
| `digest_all_courses(start, end="now", include_comments=False, max_threads_per_course=100)` | Collect posts across courses for a period. |
| `check_new_posts(course_id=None, only_important=True, backfill=0)` | Check courses for new posts. |
| `get_recent_alerts(since="7d", important_only=True, limit=50)` | Read stored alerts. |
| `get_alert_rules()` | Show importance rules. |
| `update_alert_rules(...)` | Change importance rules. |
| `reset_alert_cursor(course_id=None)` | Reset the alert cursor for one or all courses. |

The `summarize_period` MCP prompt guides a period summary. Digest and alert features are built in subsequent slices. Write content accepts Markdown or Ed XML; actions use your Ed account and may be public.

## Example prompts

- “Summarise all posts in CS101 from Nov 1 to Nov 8”
- “Any important new posts?”
- “What links were shared in thread #42?”
- “What's due this week in lessons?”

## Alerts

Importance scoring considers announcements, pinned posts, staff authors, keywords, chosen categories, watched users, and popular posts. Inspect rules with `get_alert_rules` and change them with `update_alert_rules`.

The watcher is part of the alert slice:

```sh
uv run ed-mcp watch [--interval 300] [--course ID ...] [--once] [--no-notify] [--webhook URL] [--backfill N] [--all]
```

It prints JSON lines for important posts, sends macOS notifications, optionally POSTs JSON to a webhook, and stores every alert in `~/.ed-mcp/state.db` for `get_recent_alerts` to read.

To run it at login on macOS, save the following as `~/Library/LaunchAgents/com.user.ed-mcp-watch.plist`, substituting your token and absolute paths if necessary. Create `/Users/blair/.ed-mcp` before loading it.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.user.ed-mcp-watch</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/blair/.local/bin/uv</string>
    <string>--directory</string><string>/Users/blair/Desktop/project/ed-MCP</string>
    <string>run</string><string>ed-mcp</string><string>watch</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>EnvironmentVariables</key>
  <dict><key>ED_API_TOKEN</key><string>YOUR_TOKEN</string></dict>
  <key>StandardOutPath</key><string>/Users/blair/.ed-mcp/watch.log</string>
  <key>StandardErrorPath</key><string>/Users/blair/.ed-mcp/watch.log</string>
</dict>
</plist>
```

```sh
launchctl load ~/Library/LaunchAgents/com.user.ed-mcp-watch.plist
```

## Safety

The token grants full access to your Ed account. Keep `.env` private and set `ED_READ_ONLY=1` to hide write tools. The delete thread, delete comment, edit comment, and watch/unwatch endpoints are unverified.
