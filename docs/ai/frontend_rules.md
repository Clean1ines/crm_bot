# Frontend Rules

Frontend work must preserve the existing product design and behavior.

Do not assume the design is generic dark SaaS, generic shadcn, generic Tailwind, or any other template. Infer the actual design system from the repository before changing UI.

## Before frontend edits

Inspect:
- frontend root;
- package scripts;
- framework;
- routing;
- global styles;
- theme tokens;
- component library;
- layout shell;
- navigation;
- forms;
- tables;
- cards;
- dialogs;
- existing responsive patterns;
- API client usage;
- nearby components related to the task.

## Design preservation

Do:
- reuse existing tokens;
- reuse existing components;
- preserve spacing rhythm;
- preserve typography;
- preserve color semantics;
- preserve layout conventions;
- preserve interaction patterns;
- preserve responsive behavior.

Do not:
- introduce random colors;
- introduce one-off shadows;
- introduce one-off spacing;
- change visual language casually;
- flatten nuanced UI into a generic template;
- rewrite components unrelated to the task;
- break generated API client usage;
- break existing routes or query keys.

## TypeScript

Keep TypeScript strict and clean.

Avoid:
- `any`;
- broad type assertions;
- ignoring generated API types;
- duplicated frontend DTOs when generated types exist.

Prefer:
- existing generated types;
- local view-models only when necessary;
- narrow component props;
- explicit loading/error/empty states.

## Behavior

Preserve:
- authentication flows;
- API calls;
- cache keys;
- mutations;
- uploads;
- streaming;
- routing;
- forms;
- validation.

If behavior must change, make the change explicit and covered by checks.

## Responsive UI

When touching layout:
- check desktop;
- check tablet assumptions;
- check narrow mobile widths;
- avoid horizontal overflow;
- preserve accessible focus states;
- keep controls usable.

## Frontend validation

Run checks from the actual `frontend/package.json`.

Usually:
- lint;
- type-check;
- build;
- tests if present.

If tests are absent, do not invent fake test success. State that no frontend tests exist only in the final task summary.
