"""
Exponential Backoff and Retry Policy Engine.
"""

import asyncio
import random
import time
from typing import Callable, Any, Dict, Optional
from agentos.config import settings


class RetryEngine:
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.3,
        max_delay: float = 4.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def calculate_delay(self, attempt: int) -> float:
        """Compute exponential backoff with optional full jitter."""
        delay = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        if self.jitter:
            delay = random.uniform(self.base_delay, delay)
        return round(delay, 3)

    async def execute_with_retry(
        self,
        func: Callable[[], Any],
        is_transient_error: Callable[[Exception], bool]
    ) -> Any:
        """Execute async or sync function with automated backoff retry."""
        attempt = 1
        last_exc = None

        while attempt <= self.max_retries:
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func()
                else:
                    return func()
            except Exception as e:
                last_exc = e
                if not is_transient_error(e) or attempt >= self.max_retries:
                    raise e
                    
                delay = self.calculate_delay(attempt)
                await asyncio.sleep(delay)
                attempt += 1

        if last_exc:
            raise last_exc
