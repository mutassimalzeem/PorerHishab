# AI coach implementation map

Base: origin/main 19f6c87 (PR #27); underlying files identical to prior HEAD f37bae6.
Preserved uncommitted AI-11B CRUD and the user's model formatting edit.

| Area | Existing implementation | Milestone approach |
|---|---|---|
| Auth / ownership | Shared JWT dependency, user-owned transactions | Reuse; enforce ownership on every new query |
| Categorization | Taxonomy, preferences, rules, validated LLM, correction history | Reuse; Bangla rules, safe batch endpoint, preserve confirmed values |
| Finance chat | Broad keyword routing, all-time evidence, mandatory LLM/vector path | Date-aware SQL route at existing API; retain internal legacy modules for compatibility |
| Forecast / decisions | Decimal monthly baseline, explicit balance purchase assessment | Reuse baseline arithmetic in separate opt-in obligation scenarios; preserve existing paths |
| Savings | Stateless plan and LLM actions | Keep endpoints; add persistent goals and deterministic recommendations |
| Insights | Analytics endpoints and LLM summaries | Keep schemas; add stateless deterministic nudges with stable keys and expiry |
| Provider | Multiple ChatOpenAI clients, inconsistent timeouts | Shared configurable bounded factory and safe fallbacks; no new infrastructure |
| Accounts | Nullable current_balance, no freshness/reconciliation metadata | Never infer a trustworthy current balance; require caller-confirmed balance |
| Database | Scheduled items migration at ec735533a563 | One additive savings_goals migration; no duplicate categorization fields |

No external notification delivery or insight persistence is necessary: active insights are
recomputed, expire by evidence period, and have stable keys suitable for client deduplication.
Goal savings are explicitly self-reported, nullable, and never inferred from transactions.
