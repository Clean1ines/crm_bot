# Pilot v0.1 Work-Item Evidence

Each verified backlog item has one evidence record:

```text
docs/releases/pilot-v0.1/evidence/<TASK_ID>.md
```

The evidence record is created after independent acceptance and before the task commit.

Use `result_commit: SELF` inside the commit. Report the actual immutable SHA in the final response. A later release evidence rollup may replace `SELF` in a separate documentation commit.

Evidence must distinguish:

- commands actually executed;
- checks not executed;
- automated evidence;
- manual evidence;
- task completion;
- parent requirement/release completion.
