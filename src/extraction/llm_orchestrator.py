import os
import json
import asyncio
import random
from typing import Optional

import aiohttp
from dotenv import load_dotenv

from src.extraction.schemas import LLMExtraction

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")


class LLMOrchestrator:
    def __init__(self):
        self.providers = [
            ("Gemini Flash", self.call_gemini),
            ("Groq GPT-OSS-120B", self.call_groq),
            ("DeepSeek", self.call_deepseek),
        ]

    def build_prompt(self, text: str, source_url: str) -> str:
        return f"""
Extract the main AI entity from the text below.

Return ONLY valid JSON with these fields:
{{
  "schemaVersion": "1.0",
  "recordType": "LLM_EXTRACTION",
  "entity_name": "string",
  "entity_type": "startup/product/research_paper/other",
  "description": "short description",
  "website": "https://example.com or null",
  "source_url": "{source_url}",
  "confidence": 0.0
}}

Text:
{text}
"""

    async def request(
        self,
        session,
        url: str,
        headers: dict,
        payload: dict,
        provider_name: str,
    ):
        max_retries = 4
        base_delay = 1

        for attempt in range(max_retries):
            try:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:

                    if response.status == 429:
                        delay = min(
                            base_delay * (2 ** attempt)
                            + random.uniform(0, 1),
                            30,
                        )
                        print(
                            f"{provider_name}: 429 rate limit. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                        continue

                    if response.status == 413:
                        print(f"{provider_name}: 413 payload too large.")
                        raise ValueError("PAYLOAD_TOO_LARGE")

                    if response.status >= 400:
                        error_text = await response.text()
                        raise RuntimeError(
                            f"{provider_name} HTTP {response.status}: "
                            f"{error_text[:300]}"
                        )

                    return await response.json()

            except asyncio.TimeoutError:
                if attempt == max_retries - 1:
                    raise

                delay = min(
                    base_delay * (2 ** attempt)
                    + random.uniform(0, 1),
                    30,
                )
                print(
                    f"{provider_name}: timeout. "
                    f"Retrying in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)

        raise RuntimeError(f"{provider_name}: retries exhausted")

    def extract_json_from_response(self, data: dict, provider_name: str):
        try:
            if provider_name == "Gemini Flash":
                text = data["candidates"][0]["content"]["parts"][0]["text"]

            else:
                text = data["choices"][0]["message"]["content"]

            text = text.strip()

            if text.startswith("```"):
                text = text.replace("```json", "")
                text = text.replace("```", "")
                text = text.strip()

            return json.loads(text)

        except Exception as exc:
            raise ValueError(
                f"{provider_name}: invalid JSON response: {exc}"
            )

    async def call_gemini(self, session, text: str, source_url: str):
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not configured")

        url = (
            "https://generativelanguage.googleapis.com/"
            "v1beta/models/gemini-3.6-flash:generateContent"
        )
        headers = {
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type" : "application/json",
            
        }

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": self.build_prompt(
                                text, source_url
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }

        data = await self.request(
            session,
            url,
            headers,
            payload,
            "Gemini Flash",
        )

        return self.extract_json_from_response(
            data,
            "Gemini Flash",
        )

    async def call_groq(self, session, text: str, source_url: str):
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY not configured")

        url = "https://api.groq.com/openai/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "openai/gpt-oss-120b",
            "messages": [
                {
                    "role": "user",
                    "content": self.build_prompt(
                        text,
                        source_url,
                    ),
                }
            ],
            "temperature": 0,
            "response_format": {
                "type": "json_object"
            },
        }

        data = await self.request(
            session,
            url,
            headers,
            payload,
            "Groq Llama 3",
        )

        return self.extract_json_from_response(
            data,
            "Groq Llama 3",
        )

    async def call_deepseek(
        self,
        session,
        text: str,
        source_url: str,
    ):
        if not DEEPSEEK_API_KEY:
            raise RuntimeError(
                "DEEPSEEK_API_KEY not configured"
            )

        url = "https://api.deepseek.com/chat/completions"

        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "deepseek-v4-flash",
            "messages": [
                {
                    "role": "user",
                    "content": self.build_prompt(
                        text,
                        source_url,
                    ),
                }
            ],
            "temperature": 0,
            "response_format": {
                "type": "json_object"
            },
        }

        data = await self.request(
            session,
            url,
            headers,
            payload,
            "DeepSeek",
        )

        return self.extract_json_from_response(
            data,
            "DeepSeek",
        )

    def chunk_text(
        self,
        text: str,
        max_chars: int = 12000,
        overlap: int = 500,
    ):
        if len(text) <= max_chars:
            return [text]

        paragraphs = text.split("\n\n")
        chunks = []
        current = ""

        for paragraph in paragraphs:
            if len(current) + len(paragraph) + 2 <= max_chars:
                current += paragraph + "\n\n"
            else:
                if current.strip():
                    chunks.append(current.strip())

                overlap_text = (
                    current[-overlap:]
                    if len(current) > overlap
                    else current
                )

                current = overlap_text + paragraph + "\n\n"

        if current.strip():
            chunks.append(current.strip())

        return chunks

    async def extract(
        self,
        text: str,
        source_url: str,
    ) -> Optional[LLMExtraction]:

        chunks = self.chunk_text(text)

        async with aiohttp.ClientSession() as session:

            for provider_name, provider in self.providers:

                try:
                    print(
                        f"Trying provider: {provider_name}"
                    )

                    # If text is large, process chunks.
                    results = []

                    for chunk in chunks:
                        try:
                            result = await provider(
                                session,
                                chunk,
                                source_url,
                            )
                            results.append(result)

                        except ValueError as exc:
                            if str(exc) == "PAYLOAD_TOO_LARGE":
                                smaller_chunks = self.chunk_text(
                                    chunk,
                                    max_chars=6000,
                                    overlap=300,
                                )

                                for smaller in smaller_chunks:
                                    result = await provider(
                                        session,
                                        smaller,
                                        source_url,
                                    )
                                    results.append(result)
                            else:
                                raise

                    if not results:
                        continue

                    result = results[0]

                    # Validate against Pydantic schema.
                    validated = LLMExtraction(
                        **result
                    )

                    print(
                        f"SUCCESS: {provider_name}"
                    )

                    return validated

                except Exception as exc:
                    print(
                        f"FAILED: {provider_name} -> {exc}"
                    )
                    print("Falling back to next provider...")

        print("All LLM providers failed.")
        return None


async def main():
    orchestrator = LLMOrchestrator()

    demo_text = """
    OpenAI develops artificial intelligence systems and products.
    The company builds AI models and tools for developers and users.
    """

    source_url = "https://openai.com/"

    result = await orchestrator.extract(
        demo_text,
        source_url,
    )

    if result:
        print("\nFinal extracted record:")
        print(result.model_dump_json(indent=2))
    else:
        print("\nNo provider returned a valid result.")


if __name__ == "__main__":
    asyncio.run(main())