# core/llm_client.py
import asyncio
import logging
from typing import List, Dict, Optional

from groq import AsyncGroq

from config.settings import REQUEST_DELAY

logger = logging.getLogger(__name__)


def make_client(api_key: str, model: str) -> AsyncGroq:
    """
    Initialize and return an AsyncGroq client.
    Groq-only version — no Gemini dependencies.
    """
    if not api_key:
        raise ValueError("GROQ_API_KEY is required")
    
    return AsyncGroq(api_key=api_key)


async def chat_with_fallback(
    client: AsyncGroq,
    messages: List[Dict[str, str]],
    model_chain: List[str],
    json_mode: bool = False,
    max_tokens: int = 1000,
    temperature: float = 0.1,
) -> str:
    """
    Try Groq models in order until one succeeds or all fail.
    Handles 429 rate limits by falling back to next model in chain.
    
    Args:
        client: AsyncGroq instance
        messages: List of message dicts for the chat
        model_chain: List of model IDs to try in order (e.g., ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"])
        json_mode: If True, request JSON output format
        max_tokens: Max tokens for response
        temperature: Sampling temperature
    
    Returns:
        str: The response content from the first successful model
    
    Raises:
        RuntimeError: If all models in the chain fail
    """
    last_error = None
    
    for i, model in enumerate(model_chain):
        try:
            logger.info(f"LLM → trying model: {model} (attempt {i+1}/{len(model_chain)})")
            
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"} if json_mode else None,
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from LLM")
                
            # Log if we succeeded on a fallback model
            if i > 0:
                logger.warning(f"✓ Fallback succeeded with {model} after {i} failed attempt(s)")
                
            return content.strip()
            
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            
            # Only fallback on rate limits or model-specific errors
            if "429" in error_str or "rate limit" in error_str or "model_not_found" in error_str or "invalid_model" in error_str:
                logger.warning(f"⚠ {model} failed ({type(e).__name__}: {str(e)[:80]}), trying next in chain...")
                await asyncio.sleep(2)  # Brief pause before next attempt
                continue
            else:
                # Non-recoverable error (auth, bad JSON, etc.) — don't fallback
                logger.error(f"❌ Non-recoverable error with {model}: {e}")
                raise
    
    # All models failed
    raise RuntimeError(f"All Groq models failed. Last error: {last_error}")
