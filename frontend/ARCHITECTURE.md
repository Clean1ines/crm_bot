# Architecture & Structure Guide: MRAK-OS-FACTORY (Frontend)

**Standard:** Feature-Sliced Design (FSD)  
**Last Updated:** 2026-03-03  
**Status:** Phase 3 — Full migration completed. All code is organized according to FSD layers.

## 1. Global Aliases (tsconfig)
Проект использует Path Aliases для исключения длинных относительных путей:
- `@app/*` — `src/app/*` (инициализация приложения, глобальный store)
- `@pages/*` — `src/pages/*` (страницы)
- `@widgets/*` — `src/widgets/*` (крупные составные блоки UI)
- `@features/*` — `src/features/*` (пользовательские сценарии, действия)
- `@entities/*` — `src/entities/*` (бизнес-сущности и их логика)
- `@shared/*` — `src/shared/*` (инфраструктура, переиспользуемые утилиты и UI-кит)

## 2. Layer: App (`@app`)
Сборка приложения, инициализация store, корневой компонент.
- **Entry point**: `src/app/main.tsx`
- **Root component**: `src/app/App.tsx`
- **Global store**: `src/app/store/index.ts` — агрегатор слайсов из разных сущностей (использует Zustand).  
  Старый `src/store/useAppStore.ts` оставлен как прокси для обратной совместимости, но новые импорты должны идти через `@/app/store`.

## 3. Layer: Pages (`@pages`)
Страницы приложения, каждая в своей папке.
- `login/` — страница входа.
- `workspace/` — основная рабочая область (холст, чат, панели).

## 4. Layer: Widgets (`@widgets`)
Крупные самодостаточные блоки, собирающие фичи и сущности.
- `chat-panel/` — панель чата (содержит `ChatCanvas`).
- `chat-window/` — окно чата с боковой панелью (содержит `ChatInterface`).
- `header/` — верхняя панель с меню.
- `layout/` — защищённый лэйаут (оборачивает страницы).
- `node-picker/` — панель выбора узлов (содержит `NodeListPanel`).
- `sidebar/` — боковая панель проектов.
- `workflow-editor/` — редактор графа (логика `useCanvasEngine`, компонент `IOSCanvas`).
- `workflow-header/` — заголовок конкретного воркфлоу.
- `workflow-shell/` — оболочка редактора (`IOSShell`).

## 5. Layer: Features (`@features`)
Пользовательские сценарии, реализованные как хуки или компоненты, изменяющие состояние.
- `auth/protect-routes/` — защита маршрутов (`AuthGuard`).
- `chat/send-message/` — отправка сообщения (`useSendMessage`).
- `node/edit-content/` — редактирование узла (`EditNodeModal`).
- `node/view-details/` — просмотр деталей узла (`NodeModal`).
- `project/create/` — создание проекта (`CreateProjectModal`).
- `project/edit/` — редактирование проекта (`EditProjectModal`).
- `workflow/create/` — создание воркфлоу (`CreateWorkflowModal`).
- `workflow/edit/` — редактирование воркфлоу (`EditWorkflowModal`).

## 6. Layer: Entities (`@entities`)
Бизнес-сущности, каждая содержит модель (слайс), API и UI (если нужно).
- `ai-config/` — модели и режимы ИИ.
  - `api/useModels.ts`, `useModes.ts`
  - `model/config.slice.ts`
- `artifact/` — артефакты.
  - `api/useArtifacts.ts`, `useArtifactTypes.ts`
  - `model/artifact.slice.ts`
- `chat/` — чат.
  - `api/useMessages.ts`
  - `model/chat.slice.ts`
  - `ui/ChatMessage.tsx`
- `node/` — узлы графа.
  - `lib/validation.ts` — валидация данных узла.
  - `ui/Node.tsx` (ранее IOSNode).
- `project/` — проекты.
  - `api/useProjects.ts`, `useProjectData.ts`, `useSelectedProject.ts`
  - `model/slice.ts`
  - `ui/ProjectItem.tsx`
- `session/` — сессия пользователя.
  - `model/session.slice.ts`
- `workflow/` — воркфлоу (холсты).
  - `api/useWorkflows.ts`

## 7. Layer: Shared (`@shared`)
Инфраструктурный код, не зависящий от бизнес-логики.
- `api/` — HTTP-клиент, утилиты запросов, `streaming.ts`.
- `assets/` — статика (например, `react.svg`).
- `lib/` — утилиты, хуки, константы.
  - `constants/` — `canvas.ts` (размеры, параметры холста).
  - `hooks/` — `useMediaQuery.ts`.
  - `notification/` — `useNotifications.ts` (система уведомлений).
  - `deterministicRandom.ts`, `graphUtils.ts`, `logger.ts`, `types.ts`.
- `ui/` — примитивы интерфейса.
  - `modal/` — базовые модалки.
  - `theme/` — глобальные эффекты темы.
  - `toast/` — компоненты уведомлений (`Notification.tsx`, `Toast.tsx`).

## 8. Store (Zustand)
- Слайсы живут в `entities/*/model/*.slice.ts`.
- Агрегатор — `app/store/index.ts` экспортирует `useAppStore`.
- Для совместимости оставлен прокси-файл `src/store/useAppStore.ts`, который реэкспортирует из `@/app/store`.

## 9. Тесты
- Модульные тесты лежат рядом с тестируемыми файлами в папках `__tests__`.
- E2E тесты — в корневой директории `tests/e2e/`.

## 10. Правила импортов
- Слои могут импортировать только нижележащие:
  - `app` → все.
  - `pages` → `widgets`, `features`, `entities`, `shared`.
  - `widgets` → `features`, `entities`, `shared`.
  - `features` → `entities`, `shared`.
  - `entities` → `shared`.
  - `shared` → только из себя (или внешние библиотеки).
- Запрещены импорты из вышележащих слоёв (например, `entities` не может импортировать из `features`).

---

**Примечание:** Все старые папки (`components`, `hooks`, `constants`, `styles`, `store`) удалены. Код полностью соответствует Feature-Sliced Design.