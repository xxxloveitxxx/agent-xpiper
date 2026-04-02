import os
from config.settings import PROVIDER


def _groq_client(api_key: str, model: str):
    from groq import Groq, AsyncGroq
    sync_client  = Groq(api_key=api_key)
    async_client = AsyncGroq(api_key=api_key)

    def sync_chat(messages, json_mode=False, max_tokens=1000):
        kwargs = dict(model=model, messages=messages, max_tokens=max_tokens, temperature=0.1)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = sync_client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content

    async def async_chat(messages, json_mode=False, max_tokens=1000):
        kwargs = dict(model=model, messages=messages, max_tokens=max_tokens, temperature=0.1)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = await async_client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content

    return sync_chat, async_chat


def _gemini_client(api_key: str, model: str):
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    gemini = genai.GenerativeModel(model)
    JSON_HINT = "\n\nRespond with ONLY valid JSON. No markdown, no backticks."

    def _extract(response) -> str:
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return text.strip()

    def _convert(messages, json_mode):
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                parts.append(f"[System]: {content}")
            elif role == "assistant":
                parts.append(f"[Assistant]: {content}")
            else:
                parts.append(content)
        prompt = "\n\n".join(parts)
        if json_mode:
            prompt += JSON_HINT
        return prompt

    def sync_chat(messages, json_mode=False, max_tokens=1000):
        resp = gemini.generate_content(
            _convert(messages, json_mode),
            generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens, temperature=0.1),
        )
        return _extract(resp)

    async def async_chat(messages, json_mode=False, max_tokens=1000):
        resp = await gemini.generate_content_async(
            _convert(messages, json_mode),
            generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens, temperature=0.1),
        )
        return _extract(resp)

    return sync_chat, async_chat


def make_client(api_key: str, model: str):
    if PROVIDER == "gemini":
        return _gemini_client(api_key, model)
    return _groq_client(api_key, model)
