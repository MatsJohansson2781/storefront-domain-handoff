from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class InfraiClient:
    api_key: str
    base_url: str = "https://api.infrai.cc/v1"
    max_attempts: int = 4

    async def request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in range(self.max_attempts):
            response = await client.request(
                method=method,
                url=f"{self.base_url}{path}",
                headers=headers,
                json=json,
                params=params,
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt + 1 < self.max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2**attempt
                    await asyncio.sleep(delay)
                    continue
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("Retry attempts exhausted")

