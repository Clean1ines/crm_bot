# Quality Bar

Every change must preserve or improve the current engineering quality.

## Required properties

Code must be:
- clean;
- typed;
- secure;
- performant;
- scalable;
- readable;
- testable;
- maintainable;
- consistent with nearby code;
- aligned with repository architecture.

## Unacceptable code

Do not produce:
- quick hacks;
- broad rewrites;
- untyped dynamic payload handling deep in the system;
- unnecessary abstraction;
- copy-paste logic;
- hidden side effects;
- global mutable state without need;
- generic generated-looking code;
- TODO-based incomplete implementation;
- code that passes tests only because tests were weakened;
- code that lowers the quality of the project.

## Definition of production-ready

Production-ready means:
- behavior is correct for expected and failure paths;
- errors are handled safely;
- logs are useful and do not leak secrets;
- external services can fail without corrupting state;
- database operations are parameterized and scoped;
- async code remains async-safe;
- expensive work is bounded;
- contracts are typed;
- tests cover the changed behavior;
- complexity remains low;
- the diff is small enough to review.

## Final self-check

Before finishing, verify:
- Did I inspect enough existing code?
- Did I preserve architecture boundaries?
- Did I avoid `Any` and broad ignores?
- Did I avoid increasing complexity?
- Did I avoid leaking secrets?
- Did I run relevant checks?
- Does the final diff look like careful human maintenance?
