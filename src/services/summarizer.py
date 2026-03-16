"""
Summarization service using LLM to create conversation summaries.
"""

from typing import List, Dict
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

class SummarizerService:
    """
    Service for generating summaries of conversation histories.
    Uses a separate LLM call to produce a concise summary.
    """

    def __init__(self, model: str = None, temperature: float = 0.5):
        """
        Initialize the summarizer with a specific model and temperature.

        Args:
            model: Groq model ID (defaults to settings.GROQ_MODEL or 'llama-3.3-70b-versatile').
            temperature: LLM temperature (default 0.5).
        """
        self.model = model or getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
        self.temperature = temperature
        self.llm = ChatGroq(
            model=self.model,
            temperature=self.temperature,
            groq_api_key=settings.GROQ_API_KEY,
        )
        logger.info(f"SummarizerService initialized with model {self.model}")

    async def summarize(self, messages: List[Dict[str, str]]) -> str:
        """
        Generate a summary of a conversation given a list of messages.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                     Example: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

        Returns:
            A string containing the summary.

        Raises:
            Exception: If the LLM call fails.
        """
        if not messages:
            logger.warning("Empty message list provided to summarize")
            return ""

        logger.info(f"Summarizing {len(messages)} messages")

        # Build a conversation text from messages
        conversation = ""
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            conversation += f"{role}: {content}\n"

        # Create summarization prompt
        system_prompt = (
            "You are a helpful assistant that summarizes conversations. "
            "Create a concise summary of the following conversation, capturing the key points "
            "and the overall context. The summary will be used later as context for the AI, "
            "so make sure it includes important details that might be needed for future responses."
        )
        user_prompt = f"Conversation:\n{conversation}\n\nSummary:"

        try:
            # Call LLM
            response = await self.llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            summary = response.content.strip()
            logger.info(f"Summary generated ({len(summary)} chars)")
            return summary
        except Exception as e:
            logger.exception("Failed to generate summary")
            raise
