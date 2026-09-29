"""Todo Agent entrypoint.

Builds a LangChain agent with database-backed tools and runs a short
demonstration, then drops into an interactive loop.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain.agents import create_agent

from database import init_db
from tools import ALL_TOOLS

load_dotenv()

MODEL="google_genai:gemini-3.5-flash-lite"

SYSTEM_PROMPT = """You are a dedicated Task Management Assistant.

You manage a database of todos and can query, filter, search, add, and update
tasks using the tools provided. Always use the tools to read or change data —
never invent tasks or ids.

When responding to the user:
- Summarize results as clean, readable markdown.
- Use bullet lists for multiple tasks and include id, status, and priority.
- Be concise and confirm any changes you make (adds/updates) explicitly.
"""


def build_agent():
    """Create the LangChain agent wired to the todo tools."""
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        raise RuntimeError(
            "Set GEMINI_API_KEY (or GOOGLE_API_KEY) in your .env for Google GenAI."
        )
    # langchain-google-genai reads GOOGLE_API_KEY; mirror GEMINI_API_KEY to it.
    if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

    return create_agent(model=MODEL, tools=ALL_TOOLS, system_prompt=SYSTEM_PROMPT)


def run_query(agent, prompt: str) -> str:
    """Invoke the agent with a single user prompt and return its text reply."""
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    return result["messages"][-1].content


def demo(agent) -> None:
    """Run the required demonstration queries."""
    print("=" * 60)
    print("DEMO 1: Retrieve all pending tasks")
    print("=" * 60)
    print(run_query(agent, "Show me all pending tasks."))

    print("\n" + "=" * 60)
    print("DEMO 2: Search for tasks by keyword")
    print("=" * 60)
    print(run_query(agent, "Search for tasks about 'login'."))

    print("\n" + "=" * 60)
    print("DEMO 3: Add a task, then list everything")
    print("=" * 60)
    print(
        run_query(
            agent,
            "Add a high priority task titled 'Prepare demo slides' with the "
            "description 'Slides for the Friday stakeholder review', then show "
            "me the full task list.",
        )
    )


def interactive_loop(agent) -> None:
    """Simple REPL for chatting with the agent."""
    print("\nInteractive mode — type your request, or 'exit' to quit.\n")
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if user_input.lower() in {"exit", "quit", "q"}:
            print("Goodbye!")
            break
        if not user_input:
            continue
        print(run_query(agent, user_input))
        print()


def main() -> None:
    init_db()
    agent = build_agent()
    demo(agent)
    interactive_loop(agent)


if __name__ == "__main__":
    main()
