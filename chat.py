"""Terminal chat for the Olist sales analytics agent."""
import sys
import time

from agent import Agent
from db import DatabaseError
from llm import BASE_URL, MODEL, LLMError, check_server

HELP = "Ask about Olist sales in plain English. Commands: 'reset' (new conversation), 'quit'."


def main():
    print("Loading database and schema...")
    try:
        agent = Agent()
        check_server()
    except (DatabaseError, LLMError) as e:
        sys.exit(f"Cannot start: {e}")
    print(f"Model: {MODEL} at {BASE_URL}")
    print(HELP)

    while True:
        try:
            q = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q.lower() in ("quit", "exit"):
            break
        if q.lower() == "reset":
            agent.reset()
            print("(conversation cleared)")
            continue

        start = time.time()
        try:
            reply = agent.ask(q)
        except LLMError as e:
            # Keep the chat open: the model server may come back.
            print(f"\nAgent: {e}")
            continue

        if reply.question and reply.question != q:
            print(f"\n(Interpreted as: {reply.question})")
        print(f"\nAgent: {reply.text}")
        if reply.table:
            print("\n" + reply.table)
        if reply.sql:
            print("\nSQL used:\n" + reply.sql)
        print(f"\n({time.time() - start:.0f}s, {reply.attempts} attempt(s))")


if __name__ == "__main__":
    main()
