import asyncio
from dataclasses import dataclass
from typing import Literal

from fastapi import Response
from fastapi.responses import JSONResponse

from .settings import Settings

FaultMode = Literal["error", "timeout", "malformed", "rate_limit"]
FaultScope = Literal["products", "inventories", "*"]


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "errorMessage": message},
    )


@dataclass
class FaultState:
    mode: FaultMode | None = None
    scope: FaultScope = "*"
    remaining: int | None = None
    latency_ms: int = 0


class FaultInjector:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()
        self._state = FaultState()

    def current(self) -> FaultState:
        return self._state

    async def set(
        self,
        *,
        mode: FaultMode | None,
        scope: FaultScope = "*",
        count: int | None = None,
        latency_ms: int = 0,
    ) -> FaultState:
        async with self._lock:
            if mode is None:
                self._state = FaultState()
            else:
                self._state = FaultState(mode=mode, scope=scope, remaining=count, latency_ms=latency_ms)
            return self._state

    async def clear(self) -> FaultState:
        return await self.set(mode=None)

    def applies_to(self, scope: str) -> bool:
        state = self._state
        if state.mode is None:
            return False

        if state.remaining is not None and state.remaining <= 0:
            return False

        return state.scope in ("*", scope)

    async def gate(self, scope: str) -> Response | None:
        if not self.applies_to(scope):
            return None

        state = self._state
        if state.remaining is not None:
            state.remaining -= 1

        if state.latency_ms:
            await asyncio.sleep(state.latency_ms / 1000)

        if state.mode == "error":
            return error_response(500, "INTERNAL_ERROR", "Injected inventory service failure")

        if state.mode == "timeout":
            await asyncio.sleep(self._settings.fault_timeout_seconds)
            return error_response(504, "GATEWAY_TIMEOUT", "Injected timeout")

        if state.mode == "malformed":
            return Response(
                content=b'{"items": [ this is not valid json',
                status_code=200,
                media_type="application/json",
            )

        if state.mode == "rate_limit":
            return error_response(429, "TOO_MANY_REQUESTS", "Injected rate limit")
        return None
