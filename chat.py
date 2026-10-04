"""Terminal chat for the Olist sales analytics agent."""
import time

from agent import Agent

HELP = "Ask about Olist sales in plain English. Commands: 'reset' (new conversation), 'quit'."


def main():
    print("Loading database and schema...")
    agent = Agent()
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
        reply = agent.ask(q)

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
