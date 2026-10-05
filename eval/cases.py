"""Evaluation cases for the agent.

Each case is one conversation sent to a fresh Agent. A turn is a message, or
{"ask": message, "checks": [...]} to also check that intermediate reply.
The case-level `checks` apply to the reply to the LAST turn.

Expected values were computed with hand-written SQL against
data/olist.duckdb (see the README's ground-truth table). They are specific to
this dataset; the agent itself hardcodes none of them. `issue` links a case to
a known bug; `category` groups the results:
  grounding   single questions with a checked numeric answer
  multi-turn  follow-ups that must build on earlier turns
  clarify     genuinely ambiguous requests and what happens after clarifying
  cannot      questions the data cannot answer
  held-out    per-order questions with no similar example in the prompt
  references  follow-ups that point at an item of the previous ANSWER ("it",
              "that seller", "the second one") or at "the previous year"

`eval: True` marks the 25 cases of the evaluation set (the assignment asks for
about 15-25). The remaining cases are a separate regression set for specific
past bugs and reference variants; they are not part of the eval and only run
with `run_eval.py --regression`.

Check types:
  table_has     every item must appear in the result table ("a|b" = either form)
  kind          reply kind must match ("answer", "clarify", "cannot"; or a list)
  only_values   every value in column `col` (index or header text) must be in `allowed`
  text_has      every item must appear in the summary text
  text_lacks    no item may appear in the summary text
  superlative   the first number after "highest/peak/largest/..." must be `value`
  row_count     the result must have exactly `rows` rows
  no_data       CANNOT, or an answer whose table has no real values
  value_is      a one-cell result must be exactly `value` ("a|b" = either form)
  question_has  every item must appear in the standalone question the agent answered
  question_lacks  no item may appear in that question (no leaked context)
  sql_has       every item must appear in the executed SQL (e.g. a resolved filter value)
Several checks can be combined; all must pass.
"""

TOP5_2017 = ["bed_bath_table", "watches_gifts", "health_beauty", "sports_leisure",
             "computers_accessories"]

_ALL = [
    # ---- grounding -------------------------------------------------------
    {
        "name": "top 5 categories 2017",
        "eval": True,
        "category": "grounding",
        "turns": ["Top 5 categories by revenue in 2017"],
        "checks": [{"type": "table_has",
                    "items": ["497,970.94", "486,519.02", "481,142.73", "447,546.59", "400,490.61"]}],
    },
    {
        "name": "late vs on-time reviews",
        "eval": True,
        "category": "grounding",
        # Late = delivered after the estimated DATE (delivery on the day is on time).
        "turns": ["Average review score for late deliveries vs on-time deliveries"],
        "checks": [{"type": "table_has", "items": ["2.27", "4.29", "6381|6,381", "89443|89,443"]}],
    },
    {
        "name": "amount paid by payment type",
        "eval": True,
        "category": "grounding",
        "turns": ["Total amount paid by payment type"],
        "checks": [{"type": "table_has",
                    "items": ["12,350,042.56", "2,826,802.30", "349,874.40", "212,417.75"]}],
    },
    {
        "name": "top 3 sellers by orders",
        "category": "grounding",
        "turns": ["Top 3 sellers by number of orders"],
        "checks": [{"type": "table_has", "items": ["6560211a19b47992c3666cc44a7e94c0",
                                                   "1847|1,847", "1804|1,804", "1697|1,697"]}],
    },
    {
        "name": "top seller by revenue",
        "category": "grounding",
        "turns": ["Which seller has the highest revenue?"],
        "checks": [{"type": "table_has", "items": ["4869f7a5dfa277a7dca6462dcf3b52b2", "229,237.63"]}],
    },
    {
        "name": "worst-reviewed categories",
        "eval": True,
        "category": "grounding",
        # "Worst reviews" states the measure, so no clarifying question. Small
        # groups must stay in (with their order counts), not be filtered out.
        "turns": ["Which categories have the worst reviews?"],
        "checks": [{"type": "table_has", "items": ["security_and_services", "2.50"]}],
    },
    {
        "name": "Sao Paulo last quarter",
        "eval": True,
        "category": "grounding",
        # Decisions: "São Paulo" = the state (SP) unless "city" is said; "last
        # quarter" = the last complete quarter in the data (2018 Q2; Q3 stops on
        # Sep 3). Revenue or order count accepted; the answer must name the quarter.
        "turns": ["How did São Paulo do last quarter?"],
        "checks": [{"type": "table_has", "items": ["1,173,308.82|8984|8,984"]},
                   {"type": "text_has", "items": ["Q2 2018"]}],
    },
    {
        "name": "no 2018 note on a 2017 question",
        "category": "grounding",
        "issue": "#10",
        "turns": ["How many orders were delivered in 2017?"],
        "checks": [{"type": "table_has", "items": ["43428|43,428"]},
                   {"type": "text_lacks", "items": ["2018 is a partial year"]}],
    },
    {
        "name": "summary names the real peak month",
        "eval": True,
        "category": "grounding",
        "issue": "#12",
        "turns": ["Monthly revenue in SP for 2017"],
        "checks": [{"type": "table_has", "items": ["355,815.00"]},
                   {"type": "text_has", "items": ["355,815"]},
                   {"type": "superlative", "value": "355,815"}],
    },
    {
        "name": "row-level result with identical rows",
        "eval": True,
        "category": "grounding",
        "issue": "#4",
        # This order has 3 line items of the same product at the same price.
        "turns": ["List the price of every item in order 00143d0f86d6fbd9f9b38ab440ac16f5"],
        "checks": [{"type": "kind", "kind": "answer"},
                   {"type": "row_count", "rows": 3},
                   {"type": "table_has", "items": ["21.33"]}],
    },
    # ---- multi-turn ------------------------------------------------------
    {
        "name": "assignment chain: top 5 -> state -> delivered -> 2018",
        "eval": True,
        "category": "multi-turn",
        # The example conversation from the assignment, checked at every turn.
        # Turns 2-4 keep 2017's top 5 categories; turn 4 compares delivered
        # revenue in both years (SP / bed_bath_table is the largest cell).
        "turns": [
            {"ask": "What were our top 5 product categories by revenue in 2017?",
             "checks": [{"type": "table_has", "items": ["497,970.94", "486,519.02", "481,142.73",
                                                        "447,546.59", "400,490.61"]}]},
            {"ask": "Break that down by customer state.",
             "checks": [{"type": "table_has", "items": ["207,392.78"]},
                        {"type": "only_values", "col": "categ", "allowed": TOP5_2017}]},
            {"ask": "Only count orders that were actually delivered.",
             "checks": [{"type": "table_has", "items": ["204,224.73"]},
                        {"type": "only_values", "col": "categ", "allowed": TOP5_2017}]},
            {"ask": "How does that compare with 2018?",
             "checks": [{"type": "table_has", "items": ["204,224.73", "267,983.44"]}]},
        ],
    },
    {
        "name": "follow-up keeps the top 3",
        "eval": True,
        "category": "multi-turn",
        "issue": "#9",
        "turns": ["Top 3 categories by revenue in 2018", "break that down by quarter"],
        "checks": [{"type": "only_values", "col": "categ",
                    "allowed": ["health_beauty", "watches_gifts", "bed_bath_table"]}],
    },
    {
        "name": "new question after a clarifying question",
        "eval": True,
        "category": "multi-turn",
        # The user ignores the clarifying question and asks something else.
        "turns": ["Who are our best sellers?", "How many orders were canceled in 2017?"],
        "checks": [{"type": "table_has", "items": ["265"]}],
    },
    # ---- clarify ---------------------------------------------------------
    {
        "name": "best sellers asks to clarify",
        "eval": True,
        "category": "clarify",
        "turns": ["Who are our best sellers?"],
        "checks": [{"type": "kind", "kind": "clarify"}],
    },
    {
        "name": "clarified best sellers by revenue",
        "eval": True,
        "category": "clarify",
        "issue": "#8",
        # The seller id must be there: the top seller is also the only seller in
        # its city, so 229,237.63 alone passes for a by-city table.
        "turns": ["Which sellers are best?", "by revenue"],
        "checks": [{"type": "table_has", "items": ["4869f7a5dfa277a7dca6462dcf3b52b2", "229,237.63"]}],
    },
    {
        "name": "clarified best sellers by number of orders",
        "category": "clarify",
        "turns": ["Who are our best sellers?", "most orders"],
        "checks": [{"type": "table_has", "items": ["6560211a19b47992c3666cc44a7e94c0", "1847|1,847"]}],
    },
    {
        "name": "'yes' to a clarifying question asks again",
        "eval": True,
        "category": "clarify",
        "turns": ["Who are our best sellers?", "yes"],
        "checks": [{"type": "kind", "kind": "clarify"}],
    },
    # ---- cannot ----------------------------------------------------------
    {
        "name": "profit margin is out of scope",
        "eval": True,
        "category": "cannot",
        "turns": ["What was our profit margin last year?"],
        "checks": [{"type": "kind", "kind": "cannot"}],
    },
    {
        "name": "customer age is not in the data",
        "eval": True,
        "category": "cannot",
        "turns": ["What is the age distribution of our customers?"],
        "checks": [{"type": "kind", "kind": "cannot"}],
    },
    {
        "name": "year outside the data",
        "eval": True,
        "category": "cannot",
        "turns": ["What was our revenue in 2020?"],
        "checks": [{"type": "no_data"}],
    },
    {
        "name": "not a data question",
        "eval": True,
        "category": "cannot",
        # Small talk gets a natural reply in code: no SQL, no query, no result.
        "turns": ["heey how are you"],
        "checks": [{"type": "kind", "kind": "chat"}, {"type": "text_has", "items": ["How can I help"]}],
    },
    # ---- held-out --------------------------------------------------------
    # Per-order questions the prompt has no example for: they check that the
    # order_facts view generalises beyond the benchmark questions.
    {
        "name": "average delivery days by state",
        "eval": True,
        "category": "held-out",
        # Whole days (date diff) or fractional days are both accepted.
        "turns": ["Average delivery time in days by customer state"],
        "checks": [{"type": "table_has", "items": ["29.34|29.39", "8.70|8.76"]}],
    },
    {
        "name": "late deliveries per year",
        "category": "held-out",
        "turns": ["How many deliveries were late in each year?"],
        "checks": [{"type": "table_has", "items": ["2453|2,453", "4078|4,078"]}],
    },
    {
        "name": "average amount paid per order by state",
        "category": "held-out",
        "turns": ["Average amount paid per order by customer state, excluding canceled orders"],
        "checks": [{"type": "table_has", "items": ["264.63", "142.95"]}],
    },
    # ---- references ------------------------------------------------------
    # Follow-ups that point at an item of the previous answer. The item is
    # resolved in code from the stored result; the standalone question must
    # name it, and must not pick up anything the user did not point at.
    {
        "name": "'it' = the item the previous question asked for",
        "eval": True,
        "category": "references",
        "turns": ["Which category had the worst reviews?",
                  {"ask": "How many orders did it have?",
                   "checks": [{"type": "question_has", "items": ["security_and_services"]},
                              {"type": "sql_has", "items": ["security_and_services"]},
                              {"type": "value_is", "value": "2"}]}],
    },
    {
        "name": "'that seller'",
        "eval": True,
        "category": "references",
        "turns": ["Which seller has the highest revenue?",
                  {"ask": "How many orders did that seller have?",
                   "checks": [{"type": "question_has", "items": ["4869f7a5dfa277a7dca6462dcf3b52b2"]},
                              {"type": "sql_has", "items": ["4869f7a5dfa277a7dca6462dcf3b52b2"]},
                              {"type": "value_is", "value": "1131|1,131"}]}],
    },
    {
        "name": "'that category' after a one-item answer",
        "category": "references",
        "turns": ["Which category had the highest revenue in 2018?",
                  {"ask": "How many distinct sellers sold in that category in 2018?",
                   "checks": [{"type": "question_has", "items": ["health_beauty"]},
                              {"type": "sql_has", "items": ["health_beauty"]},
                              {"type": "value_is", "value": "393"}]}],
    },
    {
        "name": "'that category' after a list asks which one",
        "eval": True,
        "category": "references",
        # Five categories were listed, so "that category" is ambiguous.
        "turns": ["Top 5 categories by revenue in 2017",
                  {"ask": "What was the average review score for that category?",
                   "checks": [{"type": "kind", "kind": "clarify"}]}],
    },
    {
        "name": "'the second one'",
        "eval": True,
        "category": "references",
        # 4.07 over all data, 4.14 if the 2017 period is carried over.
        "turns": ["Top 5 categories by revenue in 2017",
                  {"ask": "What was the average review score of the second one?",
                   "checks": [{"type": "question_has", "items": ["watches_gifts"]},
                              {"type": "sql_has", "items": ["watches_gifts"]},
                              {"type": "table_has", "items": ["4.07|4.14"]}]}],
    },
    {
        "name": "'previous year' with a year to anchor on",
        "category": "references",
        # The same 3 categories lead in 2017, so either reading (2017 alone, or
        # side by side) must show their 2017 revenue.
        "turns": ["Top 3 categories by revenue in 2018",
                  {"ask": "What about the previous year?",
                   "checks": [{"type": "question_has", "items": ["2017"]},
                              {"type": "table_has", "items": ["497,970.94", "486,519.02"]}]}],
    },
    {
        "name": "'previous year' with no anchor asks, then answers",
        "eval": True,
        "category": "references",
        "turns": ["Which category had the worst reviews?",
                  {"ask": "What about the previous year?",
                   "checks": [{"type": "kind", "kind": "clarify"}]},
                  {"ask": "2017",
                   "checks": [{"type": "table_has", "items": ["diapers_and_hygiene"]}]}],
    },
    {
        "name": "unrelated new question does not inherit the previous answer",
        "eval": True,
        "category": "references",
        "turns": ["Which seller has the highest revenue?",
                  {"ask": "How many orders were canceled in 2017?",
                   "checks": [{"type": "question_lacks", "items": ["4869f7a5dfa277a7dca6462dcf3b52b2", "seller"]},
                              {"type": "value_is", "value": "265"}]}],
    },
    {
        "name": "several follow-ups on a referenced item",
        "category": "references",
        "turns": ["Top 5 categories by revenue in 2017",
                  {"ask": "How many orders did the second one have?",
                   "checks": [{"type": "question_has", "items": ["watches_gifts"]},
                              {"type": "sql_has", "items": ["watches_gifts"]},
                              {"type": "value_is", "value": "2114|2,114"}]},
                  {"ask": "And in 2018?",
                   "checks": [{"type": "question_has", "items": ["watches_gifts", "2018"]},
                              {"type": "value_is", "value": "3485|3,485"}]}],
    },
    {
        "name": "naming a different item does not leak the listed ones",
        "eval": True,
        "category": "references",
        "turns": ["Top 5 categories by revenue in 2017",
                  {"ask": "What was revenue for toys in 2017?",
                   "checks": [{"type": "question_lacks", "items": ["bed_bath_table", "watches_gifts",
                                                                   "health_beauty"]},
                              {"type": "table_has", "items": ["305,991.37"]}]}],
    },
]

# The evaluation set (25 cases) and the separate regression set.
CASES = [c for c in _ALL if c.get("eval")]
REGRESSION_CASES = [c for c in _ALL if not c.get("eval")]
