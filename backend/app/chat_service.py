"""
Silo, the chatbot. PLACEHOLDER ONLY: no AI model is connected, nothing here makes a network call,
needs a key, or costs money.

The route (chat_routes.py) calls ONE function: `answer(question)`. To plug in an AI later, add a
provider class below, register it in `_PROVIDERS` and set CHAT_PROVIDER. The route never changes.
(README: "Plugging in an AI later".)

Rules that hold for EVERY provider, enforced here so a provider cannot forget them:
  - every answer ends with ENDING (added once, in `_with_ending`, after the provider has answered);
  - an unknown CHAT_PROVIDER, a provider that fails, or an empty answer falls back to the
    placeholder and never crashes the request;
  - nothing about the question or the person asking is stored or logged. Do not add logging of
    `question` here or in a provider.

Rules a real provider must also keep (they cannot be checked from here): answer only from the
checked guide content, say it does not know when unsure, no live place status, no map links.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from . import config

log = logging.getLogger("silong.chat")

# Every answer ends with exactly this.
ENDING = "AI-generated. Follow official advisories first."

PLACEHOLDER_TEXT = (
    "Silo is not available yet. If you are in danger, call 911. "
    "For now, follow the official advisories from PAGASA, NDRRMC and the Batangas City CDRRMO."
)


@dataclass(frozen=True)
class ChatAnswer:
    """What the screen needs (SiloAnswer in the frontend): the text and the guide topic, or None."""
    answer: str
    topic: Optional[str] = None


class PlaceholderProvider:
    """The default. A fixed answer. No guide, no AI, no network."""
    name = "placeholder"

    def answer(self, question: str, timeout: float) -> ChatAnswer:
        return ChatAnswer(answer=PLACEHOLDER_TEXT, topic=None)  # topic None = nothing matched


# ---------------------------------------------------------------------------------------------
# FUTURE PROVIDER SLOT: "gemini". NOT BUILT. Nothing below runs today.
#
# To build it:
#   1. Fill in GeminiProvider.answer. Read the key ONLY from the environment
#      (os.getenv("GEMINI_API_KEY")); never write a key in the code or commit one.
#   2. Use `timeout` (config.CHAT_TIMEOUT_SECONDS) for the call.
#   3. Return ChatAnswer(answer=<text WITHOUT the ending line>, topic=<guide entry or None>).
#   4. Add it to _PROVIDERS below:  "gemini": GeminiProvider,
#   5. Add its package to requirements.txt, and set CHAT_PROVIDER=gemini in .env.
# ---------------------------------------------------------------------------------------------
class GeminiProvider:
    name = "gemini"

    def answer(self, question: str, timeout: float) -> ChatAnswer:
        raise NotImplementedError("The Gemini provider is not built yet.")


# Providers that are built. GeminiProvider is deliberately NOT listed yet.
_PROVIDERS = {
    PlaceholderProvider.name: PlaceholderProvider,
}

_warned_about = set()


def _choose_provider():
    name = (config.CHAT_PROVIDER or "placeholder").strip().lower()
    provider_class = _PROVIDERS.get(name)
    if provider_class is None:
        if name not in _warned_about:  # one warning per name, not one per question
            _warned_about.add(name)
            log.warning("CHAT_PROVIDER is '%s', which is not built yet. Using the placeholder.", name)
        provider_class = PlaceholderProvider
    return provider_class()


def _with_ending(text: str) -> str:
    """The one place the ending is added. Never doubled, never missing."""
    text = (text or "").strip()
    while text.endswith(ENDING):
        text = text[: -len(ENDING)].rstrip()
    return f"{text}\n\n{ENDING}" if text else ENDING


def answer(question: str) -> ChatAnswer:
    """
    THE entry point: one question in, one answer out. No history, nothing stored.
    Always returns an answer that ends with ENDING.
    """
    provider = _choose_provider()
    try:
        result = provider.answer(question, config.CHAT_TIMEOUT_SECONDS)
        if not result.answer or not result.answer.strip():
            raise ValueError("empty answer")
    except Exception as e:  # noqa: BLE001  (a broken provider must never break the screen)
        log.warning("Chat provider '%s' failed (%s). Using the placeholder.", provider.name, type(e).__name__)
        result = PlaceholderProvider().answer(question, config.CHAT_TIMEOUT_SECONDS)
    return ChatAnswer(answer=_with_ending(result.answer), topic=result.topic)
