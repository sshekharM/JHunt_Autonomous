# Perf-smell gate

**FAIL** — checked 11; 5 BLOCK · 2 WARN

- **WARN** `app/routers/admin/ops.py:32` PERF-UNBOUNDED-LOAD: Possible unbounded result load — add LIMIT/pagination
- **WARN** `app/routers/admin/portals.py:23` PERF-UNBOUNDED-LOAD: Possible unbounded result load — add LIMIT/pagination
- **BLOCK** `app/routers/onboarding.py:147` PERF-N1-LOOP-QUERY: Query/await inside loop — likely N+1; batch or eager-load
- **BLOCK** `app/routers/onboarding.py:169` PERF-N1-LOOP-QUERY: Query/await inside loop — likely N+1; batch or eager-load
- **BLOCK** `app/routers/onboarding.py:259` PERF-N1-LOOP-QUERY: Query/await inside loop — likely N+1; batch or eager-load
- **BLOCK** `app/routers/onboarding.py:277` PERF-N1-LOOP-QUERY: Query/await inside loop — likely N+1; batch or eager-load
- **BLOCK** `app/routers/onboarding.py:306` PERF-N1-LOOP-QUERY: Query/await inside loop — likely N+1; batch or eager-load
