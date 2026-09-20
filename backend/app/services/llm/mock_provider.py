"""
Deterministic and fast MockLLMProvider for offline verification and automated tests.
Does NOT depend on brittle exact string matching.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, List, Optional, Set

from app.schemas.contracts import BotType
from app.schemas.llm import LLMRequest, LLMResponse, LLMStreamChunk
from app.services.llm.base import LLMProvider


class MockLLMProvider(LLMProvider):
    """
    In-memory deterministic LLM provider for unit and scenario testing.
    Produces realistic speech-friendly Hindi/Hinglish responses without external dependencies.
    """

    def __init__(
        self,
        chunk_delay_s: float = 0.0,
        simulate_timeout: bool = False,
        simulate_rate_limit: bool = False,
        simulate_failure: bool = False,
        simulate_empty: bool = False,
    ) -> None:
        self.chunk_delay_s = chunk_delay_s
        self.simulate_timeout = simulate_timeout
        self.simulate_rate_limit = simulate_rate_limit
        self.simulate_failure = simulate_failure
        self.simulate_empty = simulate_empty
        self._cancelled_requests: Set[str] = set()
        self.generation_count: int = 0
        self.last_request: Optional[LLMRequest] = None

    def _determine_response_text(self, request: LLMRequest) -> str:
        """
        Synthesizes realistic conversational Hindi/Hinglish text based on intent heuristics.
        """
        # Strip optional "DisplayName: " prefix from labeled user turns
        raw_msg = request.user_message.strip()
        if ": " in raw_msg:
            maybe_name, maybe_body = raw_msg.split(": ", 1)
            if len(maybe_name.split()) <= 3 and maybe_body:
                raw_msg = maybe_body
        msg = raw_msg.strip().lower()
        bot = request.selected_bot

        # Check speaker facts first (e.g. Scenario 5)
        if any(k in msg for k in ["kya bataya tha", "what did i tell you", "kya bola tha", "remember"]):
            if request.speaker_facts:
                facts_str = ", ".join(request.speaker_facts)
                if bot == BotType.DOST:
                    return f"Aapne mujhe bataya tha: {facts_str}!"
                return f"Ji bilkul, aapne mujhe pehle yeh jankari di thi: {facts_str}."
            # Asking about another participant — use third person from OTHER PARTICIPANTS facts
            other = ""
            if request.system_prompt and "OTHER PARTICIPANTS" in request.system_prompt:
                other = request.system_prompt
            if "cricket" in other.lower() and "rahul" in other.lower():
                return "Rahul ne bataya tha ki usse cricket pasand hai."
            return "Aapne pehle kuch khaas jankari nahi share ki thi."

        # Check explicit English request (Requirement 10)
        if "english" in msg or "in english" in msg:
            if "ai" in msg:
                return "Artificial intelligence refers to systems designed to perform tasks that typically require human intelligence, such as learning, reasoning, and problem solving."
            if "cloud" in msg:
                return "Cloud computing is the delivery of computing services over the internet, including storage, servers, and software, without local infrastructure."
            return f"Certainly! Regarding your question about {request.user_message}, here is an explanation in English."

        # Check simplified follow-up (e.g. Scenario 4 Priya: "Thoda aur simple batao")
        if any(k in msg for k in ["simple batao", "aur simple", "simpler", "aasan", "short mein"]):
            if bot == BotType.DOST:
                return "Aasan shabdon mein, AI bas computer ka smart brain hai jo khud se cheezein seekh sakta hai."
            return "Bohot saral bhasha mein kahein toh, AI ek aisa system hai jo sikhakar decisions lena seekhta hai."

        # Check pronoun/contextual follow-up (e.g. Scenario 3 "Unki koi famous movie")
        if any(k in msg for k in ["unki", "unka", "uska", "uski", "famous movie", "movie batao", "real life example"]):
            # Check context messages for topic
            context_text = " ".join([m.get("content", "").lower() for m in request.context_messages])
            if "shah rukh" in context_text or "srk" in context_text or "shah rukh" in msg:
                if bot == BotType.DOST:
                    return "Shah Rukh Khan ki sabse famous movies mein se Dilwale Dulhania Le Jayenge, Chak De India aur Swades shamil hain!"
                return "Unki lokpriya filmon mein Dilwale Dulhania Le Jayenge, Swades aur Veer-Zaara pramukh hain."
            if "cloud" in context_text or "cloud" in msg:
                if bot == BotType.DOST:
                    return "Real life example Google Drive ya Netflix hai, jahan saara data cloud par rehta hai aur aap kahin se bhi access kar sakte hain."
                return "Real life mein jaise hum Google Photos use karte hain, photos server par safe rehte hain, wahi cloud hai."

        # Check AI topic (e.g. Scenario 1)
        if "ai" in msg or "artificial intelligence" in msg:
            if bot == BotType.DOST:
                return "Simple words mein bolein toh AI ek aisi technology hai jo machines ko human-like tasks karne mein help karti hai — jaise samajhna, seekhna aur decisions lena."
            return "Saral bhasha mein kahein toh AI ek aisi suvidha hai jisse computer insano ki tarah vichaar karna aur naye patterns seekhna shuru karta hai."

        # Check Cloud topic (e.g. Scenario 2)
        if "cloud" in msg:
            if bot == BotType.DOST:
                return "Cloud computing ka matlab hai apna data aur software internet par run karna, bina apne laptop ki hard drive par depend kiye."
            return "Cloud computing ka taatparya hai internet ke madhyam se data storage aur computing suvidhaon ka upyog karna."

        # Check Shah Rukh Khan topic
        if "shah rukh" in msg or "srk" in msg:
            if bot == BotType.DOST:
                return "Shah Rukh Khan Indian cinema ke legendary superstar hain, jinhe pyaar se King Khan aur Baadshah bhi bulaya jata hai!"
            return "Shah Rukh Khan Bhartiya cinema ke atyant lokpriya aur prabhavshali abhineta hain."

        # Heuristic fallback
        if bot == BotType.DOST:
            return f"Bilkul dost! '{request.user_message}' ke baare mein baat karein toh yeh kaafi badhiya sawal hai."
        return f"Zaroor, '{request.user_message}' ko dhyan se samajhte hain aur aage badhte hain."

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        """
        Yields chunked words from the determined response text.
        """
        self.generation_count += 1
        self.last_request = request

        if request.request_id in self._cancelled_requests:
            return

        if self.simulate_timeout:
            await asyncio.sleep(0.05)
            raise TimeoutError("Simulated LLM provider timeout")

        if self.simulate_rate_limit:
            raise RuntimeError("Simulated LLM rate limit (HTTP 429: Quota exceeded)")

        if self.simulate_failure:
            raise RuntimeError("Simulated internal LLM service error (HTTP 500)")

        if self.simulate_empty:
            yield LLMStreamChunk(
                request_id=request.request_id,
                bot=request.selected_bot,
                text_delta="",
                sequence=0,
                timestamp=datetime.now(timezone.utc),
                is_final=True,
            )
            return

        full_text = self._determine_response_text(request)
        words = full_text.split(" ")

        for seq, word in enumerate(words):
            if request.request_id in self._cancelled_requests:
                break

            delta = word + (" " if seq < len(words) - 1 else "")
            if self.chunk_delay_s > 0:
                await asyncio.sleep(self.chunk_delay_s)
            else:
                await asyncio.sleep(0.001)

            yield LLMStreamChunk(
                request_id=request.request_id,
                bot=request.selected_bot,
                text_delta=delta,
                sequence=seq,
                timestamp=datetime.now(timezone.utc),
                is_final=(seq == len(words) - 1),
            )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Aggregates stream output into a single response.
        """
        t_start = time.perf_counter()
        accumulated: List[str] = []
        first_token_latency: Optional[float] = None

        async for chunk in self.stream(request):
            if first_token_latency is None:
                first_token_latency = round((time.perf_counter() - t_start) * 1000.0, 2)
            accumulated.append(chunk.text_delta)

        t_complete = time.perf_counter()
        text = "".join(accumulated).strip()

        return LLMResponse(
            request_id=request.request_id,
            bot=request.selected_bot,
            text=text,
            model="mock-gemini-2.5-flash",
            provider="mock",
            finish_reason="stop" if request.request_id not in self._cancelled_requests else "cancelled",
            latency_ms=round((t_complete - t_start) * 1000.0, 2),
            first_token_latency_ms=first_token_latency,
            token_count=len(text.split()),
            timestamp=datetime.now(timezone.utc),
        )

    async def cancel(self, request_id: str) -> None:
        self._cancelled_requests.add(request_id)

    async def health_check(self) -> bool:
        return True
