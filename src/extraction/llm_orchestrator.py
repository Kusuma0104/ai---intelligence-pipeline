import asyncio
import json
import os
import random
from typing import Optional

import aiohttp
from pydantic import BaseModel, Field

from src.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
)
from src.extraction.classifiers import (
    classify_is_remote,
    classify_pricing,
    classify_role_family,
)
from src.extraction.chunker import chunk_text
from src.extraction.schemas import LLMExtraction, PricingModel
from src.utils.logging import get_logger

logger = get_logger("llm")


class JobLLMFields(BaseModel):
    company: str = ""
    is_remote: bool
    role_family: str
    confidence: float = Field(ge=0.0, le=1.0)


class PricingLLMFields(BaseModel):
    pricingModel: PricingModel
    startupName: str
    confidence: float = Field(ge=0.0, le=1.0)


class LLMOrchestrator:
    def __init__(self):
        self.providers = [
            ("Gemini Flash", self.call_gemini),
            ("Groq Llama 3", self.call_groq),
            ("DeepSeek", self.call_deepseek),
        ]

    def enabled(self) -> bool:
        return bool(GEMINI_API_KEY or GROQ_API_KEY or DEEPSEEK_API_KEY)

    def build_prompt(self, text: str, source_url: str) -> str:
        return f"""
    Extract the main AI entity from the text below.
    Use only facts present in the text. If a field is unknown, use null.
    Do not invent companies, URLs, or metrics.

    Return ONLY valid JSON with these fields:
    {{
    "schemaVersion": "1.0",
    "recordType": "LLM_EXTRACTION",
    "entity_name": "string or null",
    "entity_type": "startup/product/research_paper/other or null",
    "description": "short description from the source or null",
    "website": "https://example.com or null",
    "source_url": "{source_url}",
    "confidence": 0.0
    }}

    Text:
    {text}
    """

    def build_job_prompt(self, text: str) -> str:
        return f"""
    Classify this job posting. Use only the source text.
    Return ONLY JSON:
    {{
    "company": "company name or empty string",
    "is_remote": true,
    "role_family": "Engineering|Research|Product|Design|Sales|Marketing|People|Finance|Legal|Operations|Other",
    "confidence": 0.0
    }}

    Text:
    {text}
    """

    def build_product_prompt(self, text: str) -> str:
        return f"""
    Extract product pricing and parent startup name from the source text only.
    pricingModel must be one of: FREE, FREEMIUM, PAID, ENTERPRISE.
    Return ONLY JSON:
    {{
    "pricingModel": "FREEMIUM",
    "startupName": "string",
    "confidence": 0.0
    }}

    Text:
    {text}
    """

    async def request(self, session, url, headers, payload, provider_name):
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
                        retry_after = response.headers.get("Retry-After")
                        delay = (
                            float(retry_after)
                            if retry_after
                            else min(base_delay * (2 ** attempt) + random.uniform(0, 1), 30)
                        )
                        logger.info("%s: 429 rate limit. Retrying in %.2fs", provider_name, delay)
                        await asyncio.sleep(delay)
                        continue

                    if response.status == 413:
                        logger.info("%s: 413 payload too large", provider_name)
                        raise ValueError("PAYLOAD_TOO_LARGE")

                    if response.status >= 400:
                        error_text = await response.text()
                        raise RuntimeError(
                            f"{provider_name} HTTP {response.status}: {error_text[:300]}"
                        )

                    return await response.json()

            except asyncio.TimeoutError:
                if attempt == max_retries - 1:
                    raise
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), 30)
                logger.info("%s: timeout. Retrying in %.2fs", provider_name, delay)
                await asyncio.sleep(delay)

        raise RuntimeError(f"{provider_name}: retries exhausted")

    def extract_json_from_response(self, data: dict, provider_name: str):
        if provider_name == "Gemini Flash":
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            text = data["choices"][0]["message"]["content"]

        text = text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)

    async def call_gemini(self, session, prompt: str):
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not configured")

        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{GEMINI_MODEL}:generateContent"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        data = await self.request(
            session,
            url,
            {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            payload,
            "Gemini Flash",
        )
        return self.extract_json_from_response(data, "Gemini Flash")

    async def call_groq(self, session, prompt: str):
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY not configured")

        payload = {
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        data = await self.request(
            session,
            "https://api.groq.com/openai/v1/chat/completions",
            {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            payload,
            "Groq Llama 3",
        )
        return self.extract_json_from_response(data, "Groq Llama 3")

    async def call_deepseek(self, session, prompt: str):
        if not DEEPSEEK_API_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY not configured")

        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        data = await self.request(
            session,
            "https://api.deepseek.com/chat/completions",
            {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            payload,
            "DeepSeek",
        )
        return self.extract_json_from_response(data, "DeepSeek")

    def _grounded(self, value: str, source_text: str) -> bool:
        if not value:
            return  False
        haystack = source_text.lower()
        token = value.lower().strip()
        if token in haystack:
            return True
        compact_source = "".join(ch for ch in haystack if ch.isalnum())
        compact_value = "".join(ch for ch in token if ch.isalnum())
        return bool(compact_value) and compact_value in compact_source

    async def _complete_json(self, prompt: str) -> Optional[dict]:

        if not prompt:
            return None

        chunk_sizes = [12000, 8000, 6000, 4000]

        async with aiohttp.ClientSession() as session:
            for provider_name, provider in self.providers:
                logger.info("Trying provider: %s", provider_name)

                provider_succeeded = False

                for max_chars in chunk_sizes:
                    chunks = chunk_text(
                        prompt,
                        max_chars=max_chars,
                        overlap=min(500, max_chars // 10),
                    )

                    if not chunks:
                        continue

                    # For extraction, the first chunk contains the prompt
                    # instructions and the beginning of the source text.
                    prompt_to_send = chunks[0]

                    logger.info(
                        "%s: trying chunk size=%d, chunks=%d",
                        provider_name,
                        max_chars,
                        len(chunks),
                    )

                    try:
                        result = await provider(session, prompt_to_send)

                        logger.info(
                            "SUCCESS: %s with chunk size=%d",
                            provider_name,
                            max_chars,
                        )

                        provider_succeeded = True
                        return result

                    except ValueError as exc:
                        if str(exc) == "PAYLOAD_TOO_LARGE":
                            logger.warning(
                                "%s: 413 at chunk size=%d; reducing payload",
                                provider_name,
                                max_chars,
                            )
                            continue

                        logger.warning(
                            "FAILED: %s -> %s",
                            provider_name,
                            exc,
                        )
                        break

                    except Exception as exc:
                        logger.warning(
                            "FAILED: %s -> %s",
                            provider_name,
                            exc,
                        )
                        break

                if not provider_succeeded:
                    logger.warning(
                        "Provider %s exhausted; trying next provider",
                        provider_name,
                    )

        logger.warning("All LLM providers failed")
        return None

    async def extract(
        self,
        text: str,
        source_url: str,
    ) -> Optional[LLMExtraction]:
        result = await self._complete_json(
            self.build_prompt(text, source_url)
        )

        if not result:
            return None

        try:
            validated = LLMExtraction(**result)
        except Exception as exc:
            logger.warning(
                "LLM extraction failed schema validation: %s",
                exc,
            )
            return None

        if not self._grounded(validated.entity_name, text):
            logger.warning(
                "Discarding ungrounded entity_name=%s for %s",
                validated.entity_name,
                source_url,
            )
            return None

        return validated

        if not prompt:
            return None

        chunk_sizes = [12000, 8000, 6000, 4000]

        async with aiohttp.ClientSession() as session:
            for provider_name, provider in self.providers:
                logger.info("Tryig provider: %s", provider_name)

                provider_succeeded = False

                for max_chars in chunk_sizes:
                    chunks = chunk_text(
                        prompt,
                        max_chars=max_chars,
                        overlap=min(500, max_chars // 10),
                    )

                    if not chunks:
                        continue

                    # For extraction, the first chunk contains the prompt
                    # instructions and the beginning of the source text.
                    prompt_to_send = chunks[0]

                    logger.info(
                        "%s: trying chunk size=%d, chunks=%d",
                        provider_name,
                        max_chars,
                        len(chunks),
                    )

                    try:
                        result = await provider(session, prompt_to_send)

                        logger.info(
                            "SUCCESS: %s with chunk size=%d",
                            provider_name,
                            max_chars,
                        )

                        provider_succeeded = True
                        return result

                    except ValueError as exc:
                        if str(exc) == "PAYLOAD_TOO_LARGE":
                            logger.warning(
                                "%s: 413 at chunk size=%d; reducing payload",
                                provider_name,
                                max_chars,
                            )
                            continue

                        logger.warning(
                            "FAILED: %s -> %s",
                            provider_name,
                            exc,
                        )
                        break

                    except Exception as exc:
                        logger.warning(
                            "FAILED: %s -> %s",
                            provider_name,
                            exc,
                        )
                        break

                if not provider_succeeded:
                    logger.warning(
                        "Provider %s exhausted; trying next provider",
                        provider_name,
                    )

        logger.warning("All LLM providers failed")
        return None

        async def extract(self, text: str, source_url: str) -> Optional[LLMExtraction]:
            result = await self._complete_json(self.build_prompt(text, source_url))
            if not result:
                return None

            try:
                validated = LLMExtraction(**result)
            except Exception as exc:
                logger.warning("LLM extraction failed schema validation: %s", exc)
                return None

            if not self._grounded(validated.entity_name, text):
                logger.warning(
                    "Discarding ungrounded entity_name=%s for %s",
                    validated.entity_name,
                    source_url,
                )
            return None

        return validated

    async def classify_job(
        self,
        title: str,
        description: str,
        company: str = "",
        location: str = "",
        source_name: str = "",
    ) -> JobLLMFields:
        fallback = JobLLMFields(
            company=company,
            is_remote=classify_is_remote(title, description, location, source_name),
            role_family=classify_role_family(title, description),
            confidence=0.4,
        )
        if not self.enabled():
            return fallback

        source = f"Title: {title}\nCompany: {company}\nLocation: {location}\n\n{description}"
        result = await self._complete_json(self.build_job_prompt(source[:12000]))
        if not result:
            return fallback

        try:
            parsed = JobLLMFields(**result)
        except Exception:
            return fallback

        if parsed.company and not self._grounded(parsed.company, source):
            parsed.company = company
        if not parsed.company:
            parsed.company = company
        return parsed

    async def classify_product(
        self,
        name: str,
        description: str,
        pricing_raw: str,
        fallback_startup: str,
    ) -> PricingLLMFields:
        fallback = PricingLLMFields(
            pricingModel=classify_pricing(pricing_raw, description),
            startupName=fallback_startup or name,
            confidence=0.4,
        )
        if not self.enabled():
            return fallback

        source = f"Product: {name}\nPricing: {pricing_raw}\n\n{description}"
        result = await self._complete_json(self.build_product_prompt(source[:8000]))
        if not result:
            return fallback

        try:
            parsed = PricingLLMFields(**result)
        except Exception:
            return fallback

        if parsed.startupName and not self._grounded(parsed.startupName, source + " " + fallback_startup):
            parsed.startupName = fallback.startupName
        return parsed


async def main():
    orchestrator = LLMOrchestrator()
    demo_text = (
        "OpenAI develops artificial intelligence systems and products. "
        "The company builds AI models and tools for developers and users."
    )
    result = await orchestrator.extract(demo_text, "https://openai.com/")
    if result:
        print(result.model_dump_json(indent=2))
    else:
        print("No grounded LLM extraction (missing keys or ungrounded output).")


if __name__ == "__main__":
    asyncio.run(main())
