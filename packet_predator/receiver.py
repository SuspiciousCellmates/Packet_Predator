"""Lifecycle-managed physical receive worker."""

from __future__ import annotations

import threading
from typing import Any, Callable

from .adapters.nrf905 import Nrf905Error
from .nrf905_transport import Nrf905Transport
from .transport import CarrierFrame


class PhysicalReceiver:
    """Continuously move physical frames into the workbench service."""

    def __init__(
        self,
        transport: Nrf905Transport,
        consume: Callable[[CarrierFrame], dict[str, Any]],
        set_state: Callable[[str, dict[str, Any] | None], dict[str, Any]],
    ) -> None:
        self._transport = transport
        self._consume = consume
        self._set_state = set_state
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._set_state("starting", None)
            self._thread = threading.Thread(
                target=self._run,
                name="PacketPredatorPhysicalReceiver",
                daemon=False,
            )
            self._thread.start()

    def stop(self, timeout_s: float = 2.0) -> None:
        with self._lock:
            thread = self._thread
            if thread is None:
                self._set_state("stopped", None)
                return
            self._stop.set()
        thread.join(timeout_s)
        if thread.is_alive():
            raise RuntimeError("The physical receiver did not stop within the shutdown deadline.")
        with self._lock:
            self._thread = None

    def _run(self) -> None:
        faulted = False
        self._set_state("listening", None)
        try:
            while not self._stop.is_set():
                item = self._transport.wait_for_frame(self._stop)
                if item is not None:
                    batch = [item]
                    while not self._stop.is_set():
                        available = self._transport.poll()
                        if not available:
                            break
                        batch.extend(available)
                    for captured in batch:
                        self._consume(captured)
        except Nrf905Error as exc:
            faulted = True
            self._set_state("faulted", exc.as_dict())
        except Exception as exc:
            faulted = True
            self._set_state(
                "faulted",
                {"code": "PHYSICAL_RECEIVER_FAILED", "message": str(exc)},
            )
        finally:
            if not faulted:
                self._set_state("stopped", None)
