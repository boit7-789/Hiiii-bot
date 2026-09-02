from __future__ import annotations

import asyncio
import logging
from typing import Any, List
from quizbot.shared import config

logger = logging.getLogger(__name__)


def _extract_keys(raw_val: Any) -> List[str]:
    """Helper to parse single keys or comma-separated keys from config."""
    if not raw_val:
        return []
    if isinstance(raw_val, str):
        return [k.strip() for k in raw_val.split(",") if k.strip()]
    if isinstance(raw_val, list):
        return [str(k).strip() for k in raw_val if str(k).strip()]
    return []


class UniversalFreeAIEngine:
    """
    Races up to 12 free AI API platforms concurrently.
    The fastest provider to deliver a valid answer wins; all other tasks are cancelled.
    """

    def __init__(self):
        # 1. Groq Cloud (Ultra-fast LPU)
        self.groq_keys = _extract_keys(getattr(config, "GROQ_API_KEYS", None) or getattr(config, "GROQ_API_KEY", ""))
        # 2. Cerebras Cloud (Wafer-scale high-speed inference)
        self.cerebras_keys = _extract_keys(getattr(config, "CEREBRAS_API_KEYS", None) or getattr(config, "CEREBRAS_API_KEY", ""))
        # 3. SambaNova Cloud (Hardware-accelerated)
        self.sambanova_keys = _extract_keys(getattr(config, "SAMBANOVA_API_KEYS", None) or getattr(config, "SAMBANOVA_API_KEY", ""))
        # 4. Mistral AI (Free Experiment Tier)
        self.mistral_keys = _extract_keys(getattr(config, "MISTRAL_API_KEYS", None) or getattr(config, "MISTRAL_API_KEY", ""))
        # 5. OpenRouter (Free community models)
        self.openrouter_keys = _extract_keys(getattr(config, "OPENROUTER_API_KEYS", None) or getattr(config, "OPENROUTER_API_KEY", ""))
        # 6. GitHub Models (Personal Access Token)
        self.github_keys = _extract_keys(getattr(config, "GITHUB_MODELS_KEYS", None) or getattr(config, "GITHUB_TOKEN", ""))
        # 7. Hugging Face (Serverless Inference)
        self.hf_keys = _extract_keys(getattr(config, "HUGGINGFACE_API_KEYS", None) or getattr(config, "HF_TOKEN", ""))
        # 8. DeepInfra (Free starter balance)
        self.deepinfra_keys = _extract_keys(getattr(config, "DEEPINFRA_API_KEYS", None) or getattr(config, "DEEPINFRA_API_KEY", ""))
        # 9. Together AI (Free starter quota)
        self.together_keys = _extract_keys(getattr(config, "TOGETHER_API_KEYS", None) or getattr(config, "TOGETHER_API_KEY", ""))
        # 10. Cloudflare Workers AI
        self.cloudflare_token = getattr(config, "CLOUDFLARE_API_TOKEN", "")
        self.cloudflare_account = getattr(config, "CLOUDFLARE_ACCOUNT_ID", "")
        # 11. Google Gemini (Google AI Studio)
        self.gemini_keys = _extract_keys(getattr(config, "GEMINI_API_KEYS", None) or getattr(config, "GEMINI_API_KEY", ""))
        # 12. Cohere (Trial developer tier)
        self.cohere_keys = _extract_keys(getattr(config, "COHERE_API_KEYS", None) or getattr(config, "CO_API_KEY", ""))

    async def _query_openai_compat(self, base_url: str, key: str, model: str, prompt: str, timeout: float = 7.0) -> str:
        """Universal handler for OpenAI-compatible REST endpoints."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(base_url=base_url, api_key=key, timeout=timeout)
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout,
            )
            content = resp.choices[0].message.content
            if content:
                return content.strip()
            raise ValueError(f"Empty response from {model} at {base_url}")
        finally:
            await client.close()

    async def _query_gemini(self, key: str, prompt: str) -> str:
        """Native Google Gemini handler."""
        from google import genai
        client = genai.Client(api_key=key)
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            ),
        )
        if resp and resp.text:
            return resp.text.strip()
        raise ValueError("Empty response from Gemini")

    async def _query_cohere(self, key: str, prompt: str) -> str:
        """Native Cohere API handler."""
        import cohere
        client = cohere.AsyncClientV2(api_key=key)
        resp = await client.chat(
            model="command-r-plus-08-2024",
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.message and resp.message.content:
            return resp.message.content[0].text.strip()
        raise ValueError("Empty response from Cohere")

    def _build_tasks(self, prompt: str) -> List[asyncio.Task]:
        """Spawns parallel tasks for all configured providers."""
        tasks: List[asyncio.Task] = []

        # 1. Groq (Fastest LPU)
        for key in self.groq_keys[:2]:
            tasks.append(asyncio.create_task(
                self._query_openai_compat("https://api.groq.com/openai/v1", key, "llama-3.3-70b-versatile", prompt)
            ))

        # 2. Cerebras (Wafer-scale speed)
        for key in self.cerebras_keys[:2]:
            tasks.append(asyncio.create_task(
                self._query_openai_compat("https://api.cerebras.ai/v1", key, "llama-3.3-70b", prompt)
            ))

        # 3. SambaNova
        for key in self.sambanova_keys[:2]:
            tasks.append(asyncio.create_task(
                self._query_openai_compat("https://api.sambanova.ai/v1", key, "Meta-Llama-3.3-70B-Instruct", prompt)
            ))

        # 4. Mistral AI
        for key in self.mistral_keys[:1]:
            tasks.append(asyncio.create_task(
                self._query_openai_compat("https://api.mistral.ai/v1", key, "mistral-small-latest", prompt)
            ))

        # 5. OpenRouter (:free routing)
        for key in self.openrouter_keys[:1]:
            tasks.append(asyncio.create_task(
                self._query_openai_compat("https://openrouter.ai/api/v1", key, "meta-llama/llama-3.3-70b-instruct:free", prompt)
            ))

        # 6. GitHub Models (GPT-4o mini)
        for key in self.github_keys[:1]:
            tasks.append(asyncio.create_task(
                self._query_openai_compat("https://models.inference.ai.azure.com", key, "gpt-4o-mini", prompt)
            ))

        # 7. Hugging Face Serverless
        for key in self.hf_keys[:1]:
            tasks.append(asyncio.create_task(
                self._query_openai_compat("https://api-inference.huggingface.co/v1/", key, "Qwen/Qwen2.5-72B-Instruct", prompt, timeout=9.0)
            ))

        # 8. DeepInfra
        for key in self.deepinfra_keys[:1]:
            tasks.append(asyncio.create_task(
                self._query_openai_compat("https://api.deepinfra.com/v1/openai", key, "meta-llama/Meta-Llama-3.3-70B-Instruct", prompt)
            ))

        # 9. Together AI
        for key in self.together_keys[:1]:
            tasks.append(asyncio.create_task(
                self._query_openai_compat("https://api.together.xyz/v1", key, "meta-llama/Llama-3.3-70B-Instruct-Turbo", prompt)
            ))

        # 10. Cloudflare Workers AI
        if self.cloudflare_token and self.cloudflare_account:
            cf_url = f"https://api.cloudflare.com/client/v4/accounts/{self.cloudflare_account}/ai/v1"
            tasks.append(asyncio.create_task(
                self._query_openai_compat(cf_url, self.cloudflare_token, "@cf/meta/llama-3.3-70b-instruct-fp8-fast", prompt)
            ))

        # 11. Google Gemini
        for key in self.gemini_keys[:2]:
            tasks.append(asyncio.create_task(
                self._query_gemini(key, prompt)
            ))

        # 12. Cohere
        for key in self.cohere_keys[:1]:
            try:
                tasks.append(asyncio.create_task(
                    self._query_cohere(key, prompt)
                ))
            except Exception:
                pass

        return tasks

    async def ask_fast(self, prompt: str) -> str:
        tasks = self._build_tasks(prompt)
        if not tasks:
            return "⚠️ No AI API keys configured. Add at least one free provider key (e.g. GROQ_API_KEY, CEREBRAS_API_KEY, or GEMINI_API_KEYS)."

        pending = set(tasks)
        last_error = ""

        # Race all tasks concurrently; the first to finish returns immediately
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for completed in done:
                try:
                    result = completed.result()
                    if result:
                        # Cancel remaining slower queries to conserve tokens and bandwidth
                        for rem in pending:
                            rem.cancel()
                        return result
                except Exception as exc:
                    last_error = str(exc)
                    logger.warning("Provider failed during race: %s", exc)

        return f"❌ All free AI services failed or timed out. Error: {last_error[:100]}"

    def get_all_keys(self) -> List[str]:
        """Backward-compatibility fallback method for legacy callers."""
        return self.gemini_keys or self.groq_keys or ["dummy_key"]


ai_engine = UniversalFreeAIEngine()
ai_key_pool = ai_engine  # Alias to prevent ImportError in older imports
