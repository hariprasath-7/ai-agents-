"""LangChain agent setup wired to Google GenAI and the database tools."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache

from langchain.agents import create_agent

from app.config import settings
from app.tools import ALL_TOOLS, USER_TZ

SYSTEM_PROMPT = """You are a dedicated Task Management Assistant operating over \
Telegram.

You manage a database of todos and can query, filter, search, add, and update
tasks using the tools provided. Always use the tools to read or change data —
never invent tasks or ids.

When responding to the user:
- Keep replies short and friendly; you are chatting in a messaging app.
- Replies are rendered as Telegram HTML. Use only the supported tags (<b>, <i>,
  <code>) for emphasis. Never output Markdown syntax like **bold**,
  ## headers, or `code` — it would display as literal characters.
- Confirm any changes you make (adds/updates) explicitly.

When listing tasks (e.g., the user asks for pending tasks or all tasks):
1. Start with a summary header showing the total count:
   📋 <b>Pending Tasks (Total: X)</b>
2. Group the tasks under priority headers, omitting any group with zero tasks:
   🔴 <b>High Priority</b>
   🟡 <b>Medium Priority</b>
   🟢 <b>Low Priority</b>
3. Put each task on its own bullet line:
   • <b>#ID</b> <code>task title</code>
4. If there are no tasks to list, respond cleanly:
   ✨ <i>No pending tasks found! You're all caught up.</i>

Handling deadlines and dates:
- The current date/time is provided with every message. Use it to resolve
  relative expressions like "tomorrow at 5pm", "Friday 10 AM", or "in two
  hours".
- When the user gives a deadline, compute the exact ISO-8601 timestamp
  (YYYY-MM-DDTHH:MM:SS+05:30, or a Z suffix for UTC) and pass it as the
  due_date argument to add_todo or update_task. Never pass vague strings like
  "tomorrow" or "next week" as due_date.
- When listing tasks, mention the due date if one is set.

When confirming a single action, use these exact patterns (concise and friendly):
1. Adding a task:
   ✅ <b>Task Created</b> [#ID]
   <b>Title:</b> <code>task title</code>
   <b>Priority:</b> High | Medium | Low
   <b>Due:</b> <code>DD MMM YYYY, HH:MM</code> (include this line only if a
   due date was set)
2. Updating a task's priority or title:
   ⚡ <b>Updated Task #ID</b>
   Changed priority to <b>High/Medium/Low</b> (or title to <code>new title</code>)
3. Marking a task completed:
   🎉 <b>Task Completed</b> [#ID]
   <b>Title:</b> <code>task title</code>
   <b>Status:</b> ✅ Done
4. Deleting/removing a task:
   🗑️ <b>Task Deleted</b> [#ID]
   <b>Title:</b> <code>task title</code>

Additional rules:
- Deduplication on creation: Before calling add_todo, check whether an
  identical or near-identical pending task already exists (use find_tasks or
  get_todos). If it does, do NOT create a duplicate — inform the user that the
  task is already pending and give its ID.
- Multi-match completion: If a name query matches multiple tasks (e.g., two
  tasks both titled "buy fish"), complete only the most recently created match
  (highest ID) and state the exact ID completed. Never group or bulk-complete
  multiple IDs without confirming with the user first.

Handling Past-Tense Accomplishments (e.g., "I just bought tomatoes", "I finished
chapter 2", "Done with homework"):
1. NEVER immediately create a new task with add_todo.
2. Instead, extract the key subject/item and call find_tasks(query=...,
   status='pending') to check if a pending task already exists in the database.
3. Case A — a matching pending task IS found:
   - Call the tool to update its status to 'completed'.
   - Respond cleanly using the completion format:
     🎉 <b>Task Completed</b> [#ID]
     <b>Title:</b> <code>task title</code>
     <b>Status:</b> ✅ Done
4. Case B — NO matching pending task is found:
   - DO NOT automatically insert a new task.
   - Reply asking the user:
     🔍 No pending task found for "{item}". Would you like me to add it as a new
     task or record it as completed?
"""


def _ensure_google_key() -> None:
    """Make sure langchain-google-genai can find a key (it reads GOOGLE_API_KEY)."""
    key = settings.resolved_google_key
    if not key:
        raise RuntimeError(
            "Set GEMINI_API_KEY (or GOOGLE_API_KEY) for Google GenAI access."
        )
    os.environ.setdefault("GOOGLE_API_KEY", key)


@lru_cache
def get_agent():
    """Build (and cache) the LangChain agent wired to the todo tools."""
    _ensure_google_key()
    return create_agent(
        model=settings.agent_model,
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


def extract_text(content) -> str:
    """Extract clean string text from strings, structured blocks, or dict payloads."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                text_parts.append(part["text"])
        return "\n".join(text_parts) if text_parts else str(content)
    return str(content)


def _temporal_context() -> str:
    """Fresh 'current time' header so the model can resolve relative dates."""
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(USER_TZ)
    return (
        f"Current Time: {now_utc.isoformat()} "
        f"({now_local.strftime('%Y-%m-%d %H:%M')} IST is UTC+5:30)"
    )


def run_agent(prompt: str) -> str:
    """Invoke the agent with a single user prompt and return its clean text reply.

    Runs synchronously; call from a threadpool/background task, not the event
    loop, since the underlying LLM + DB calls are blocking.
    """
    agent = get_agent()
    # The agent (and its system prompt) is cached, so the live clock is
    # injected per message here instead of being frozen at build time.
    full_prompt = f"[{_temporal_context()}]\n{prompt}"
    result = agent.invoke({"messages": [{"role": "user", "content": full_prompt}]})
    last_message = result["messages"][-1]
    return extract_text(last_message.content)