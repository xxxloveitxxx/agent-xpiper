# core/llm_client.py
import asyncio
import logging
from typing import List, Dict, Optional, Tuple

from groq import AsyncGroq


from config.settings import PROVIDER, GROQ_MODELS, REQUEST_DELAY

logger = logging.getLogger(__name__)


def make_client(api_key: str, model: str) -> Tuple[Optional[genai.Client], Optional[AsyncGroq]]:
    """Return initialized client for Groq or Gemini."""
    if PROVIDER == "gemini":
        return genai.Client(api_key=api_key), None
    else:
        return None, AsyncGroq(api_key=api_key)


async def chat_with_fallback(
    client: AsyncGroq,
    messages: List[Dict[str, str]],
    model_chain: List[str],
    json_mode: bool = False,
    max_tokens: int = 1000,
    temperature: float = 0.1,
) -> str:
    """
    Try models in order until one succeeds or all fail.
    Handles 429 rate limits by falling back to next model.
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
                
            # If we succeeded on a fallback, log it
            if i > 0:
                logger.warning(f"✓ Fallback succeeded with {model} after {i} failed attempt(s)")
                
            return content.strip()
            
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            
            # Only fallback on rate limits or model-specific errors
            if "429" in error_str or "rate limit" in error_str or "model_not_found" in error_str:
                logger.warning(f"⚠ {model} failed ({type(e).__name__}), trying next in chain...")
                await asyncio.sleep(2)  # Brief pause before next attempt
                continue
            else:
                # Non-recoverable error (auth, bad JSON, etc.) — don't fallback
                logger.error(f"❌ Non-recoverable error with {model}: {e}")
                raise
    
    # All models failed
    raise RuntimeError(f"All models failed. Last error: {last_error}")
