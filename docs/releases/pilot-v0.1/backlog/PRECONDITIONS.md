# Pilot v0.1 Backlog Preconditions

## S1 implementation prerequisite

Before any S1 production implementation, ADR-0002 and ADR-0003 must be `accepted`.

ADR-0002 acceptance must explicitly include all of the following:

- update identity contains a stable non-secret Telegram bot account identity or approved bot-generation identity in addition to surface, project/platform scope, and `update_id`;
- replacing a bot account cannot collide with historical update IDs from the prior bot account;
- initial durable intake uses insert-on-conflict semantics that cannot reset an existing lifecycle;
- duplicate webhook delivery cannot overwrite status, owner, lease, attempts, completion, failure, original payload, or outbound state;
- same identity with different payload is an anomaly, not an update of the stored payload;
- one durable logical update may have serial retry attempts but at most one active processing owner and one effectively-once internal business outcome;
- R25 remains an explicitly accepted residual external-delivery risk rather than a closable exactly-once guarantee.

ADR-0003 acceptance must explicitly include:

- PostgreSQL thread execution lease as correctness authority;
- PostgreSQL state revision/CAS in S1;
- no production fallback to `NullThreadLock`;
- no final outbound response from stale lease or stale revision owners.

If an accepted ADR omits or contradicts these task-card constraints, the work item is `blocked` by a decision conflict. The agent must not choose whichever version is easier to implement.
