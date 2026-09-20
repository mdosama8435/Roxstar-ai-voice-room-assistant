"""
Independent Benchmark Suite for LLM Providers (Requirement 23).
Measures Gemini and NVIDIA performance on identical controlled prompts.
Reports raw objective metrics (TTFT, total latency, length, errors) without rankings or recommendations.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.schemas.contracts import BotType
from app.schemas.llm import LLMRequest
from app.services.llm.base import LLMProvider
from app.services.llm.factory import create_concrete_provider
from app.services.personas.dost import AI_DOST_SYSTEM_INSTRUCTIONS


BENCHMARK_PROMPTS = [
    {
        "id": "p1",
        "title": "AI Explanation",
        "user_message": "AI kya hota hai? Simple Hinglish mein batao.",
        "context_messages": [],
        "speaker_facts": [],
    },
    {
        "id": "p2",
        "title": "Cloud Computing",
        "user_message": "Cloud computing kya hoti hai? Ek simple example do.",
        "context_messages": [],
        "speaker_facts": [],
    },
    {
        "id": "p3",
        "title": "Shah Rukh Khan",
        "user_message": "Shah Rukh Khan kaun hain?",
        "context_messages": [],
        "speaker_facts": [],
    },
    {
        "id": "p4",
        "title": "SRK Follow-up (Contextual)",
        "user_message": "Unki koi famous movie batao.",
        "context_messages": [
            {"role": "user", "content": "Rahul: Shah Rukh Khan kaun hain?"},
            {"role": "model", "content": "AI Dost: Shah Rukh Khan Bollywood ke mashhoor King Khan hain."},
        ],
        "speaker_facts": [],
    },
    {
        "id": "p5",
        "title": "Speaker Memory Retrieval",
        "user_message": "Rahul ne tumhe apne baare mein kya bataya tha?",
        "context_messages": [
            {"role": "user", "content": "Rahul: Mera naam Rahul hai aur mujhe cricket khelna bohot pasand hai."},
            {"role": "model", "content": "AI Dost: Arre wah Rahul bhai, cricket toh sabka favourite hai!"},
        ],
        "speaker_facts": ["Name: Rahul", "Likes/Interest: Cricket Khelna Bohot Pasand Hai"],
    },
]


async def run_single_benchmark(
    provider: LLMProvider,
    prompt_spec: Dict[str, Any],
) -> Dict[str, Any]:
    req = LLMRequest(
        request_id=f"bench-{prompt_spec['id']}-{int(time.time()*1000)}",
        room_id="bench-room",
        participant_identity="human-rahul",
        selected_bot=BotType.DOST,
        turn_id=f"turn-{prompt_spec['id']}",
        user_message=prompt_spec["user_message"],
        system_prompt=AI_DOST_SYSTEM_INSTRUCTIONS,
        context_messages=prompt_spec["context_messages"],
        speaker_facts=prompt_spec["speaker_facts"],
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_output_tokens,
    )

    t_start = time.perf_counter()
    ttft_ms: Optional[float] = None
    chunks: List[str] = []
    error_msg: Optional[str] = None
    success = False

    try:
        async for chunk in provider.stream(req):
            if ttft_ms is None and chunk.text_delta:
                ttft_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            chunks.append(chunk.text_delta)

        success = True
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {str(exc)}"

    total_latency_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
    response_text = "".join(chunks).strip()

    return {
        "prompt_id": prompt_spec["id"],
        "prompt_title": prompt_spec["title"],
        "success": success,
        "time_to_first_token_ms": ttft_ms,
        "total_latency_ms": total_latency_ms,
        "response_length_chars": len(response_text),
        "response_preview": response_text[:120] if response_text else None,
        "error": error_msg,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def benchmark_provider(provider_name: str) -> Dict[str, Any]:
    print(f"\n==================================================")
    print(f"BENCHMARKING PROVIDER: {provider_name.upper()}")
    print(f"==================================================")

    try:
        provider = create_concrete_provider(provider_name)
    except Exception as e:
        print(f"Provider '{provider_name}' initialization failed: {e}")
        return {
            "provider": provider_name,
            "configured": False,
            "error": str(e),
            "results": [],
        }

    results = []
    for prompt_spec in BENCHMARK_PROMPTS:
        print(f"Running [{prompt_spec['id']}] {prompt_spec['title']}...", end="", flush=True)
        res = await run_single_benchmark(provider, prompt_spec)
        if res["success"]:
            print(f" OK (TTFT={res['time_to_first_token_ms']}ms, Total={res['total_latency_ms']}ms, Chars={res['response_length_chars']})")
        else:
            print(f" FAILED: {res['error']}")
        results.append(res)
        # Bounded pause between queries
        await asyncio.sleep(2.0)

    model_name = getattr(provider, "default_model", "unknown")
    return {
        "provider": provider_name,
        "model": model_name,
        "configured": True,
        "results": results,
    }


async def main():
    parser = argparse.ArgumentParser(description="Independent LLM Provider Benchmark Suite")
    parser.add_argument("--providers", nargs="+", default=["gemini", "nvidia"], help="Providers to benchmark")
    parser.add_argument("--output", default="benchmark_results.json", help="Path to write JSON output")
    args = parser.parse_args()

    all_benchmarks: Dict[str, Any] = {
        "benchmark_timestamp": datetime.now(timezone.utc).isoformat(),
        "providers_tested": args.providers,
        "measurements": {},
    }

    for p in args.providers:
        all_benchmarks["measurements"][p] = await benchmark_provider(p)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_benchmarks, f, indent=2, ensure_ascii=False)

    print(f"\nBenchmark completed. Results recorded to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
