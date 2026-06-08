# Conversation Runtime Context

## Назначение

`conversation_runtime` — runtime клиентского диалога.

Этот context владеет threads, messages, turns, runtime state, recent history, session locks and message-level orchestration.

Он отвечает за то, как входящее клиентское сообщение превращается в orchestrated answer flow.

## Owns

Canonical concepts:

- `ClientThread`;
- `ClientMessage`;
- `ConversationTurn`;
- `ConversationState`;
- `ThreadId`;
- `ChannelMessageId`;
- `RuntimeMemoryRef`;
- `AnswerPlan`;
- `EvidencePlan`.

Use cases that belong here:

- `ReceiveClientMessage`;
- `ProcessClientMessage`;
- `PersistAssistantReply`;
- `GenerateClientAnswer`.

Domain events that belong here:

- `ClientMessageReceived`;
- `ClientAnswerGenerated`;
- `ClientAnswerEscalated`;
- `ConversationTurnPersisted`.

## Does not own

This context does not own:

- Telegram transport implementation;
- manager assignment workflow;
- knowledge extraction;
- knowledge publication;
- generic LLM provider routing;
- generic work item leasing;
- source document processing.

## Relationship to agent graph

The agent graph is an implementation/runtime adapter for conversation orchestration.

It must not become the source of truth for domain concepts.

Graph nodes can orchestrate operations, but domain/application policies must remain in bounded contexts.

## Relationship to Knowledge Workbench

Conversation Runtime consumes published knowledge surfaces.

It must not publish draft Workbench artifacts directly.

It may emit feedback/events that later improve knowledge, but curation/publication belongs to Knowledge Workbench.

## Placement rules

New canonical conversation runtime code goes here.

Do not add new generic dumping-ground files named:

- `service.py`;
- `services.py`;
- `repository.py`;
- `dto.py`.

Use explicit names such as:

- `domain/entities/client_thread.py`;
- `domain/entities/client_message.py`;
- `application/use_cases/process_client_message.py`;
- `application/ports/message_repository.py`;
- `interfaces/http/client_message_endpoint.py`.
