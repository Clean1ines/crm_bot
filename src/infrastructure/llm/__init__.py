"""Infrastructure LLM adapters package.

Keep this package initializer side-effect free.

Import concrete adapters from their modules directly, for example:
`src.contexts.llm_runtime`.

This avoids loading retired Workbench LLM modules when unrelated code imports a
current adapter such as the AI Playground Groq key rotator.
"""
