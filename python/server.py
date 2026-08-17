"""
server.py

API REST + Server-Sent Events em cima do AffinityMonitor.

Instalar dependencias:
    pip install fastapi uvicorn

Rodar:
    python server.py
    (ou: uvicorn server:app --host 0.0.0.0 --port 8000)

Endpoints:
    GET  /windows            -> todas as janelas visiveis + status
    GET  /windows/protected  -> so as protegidas
    GET  /windows/{hwnd}     -> detalhe de uma janela especifica
    GET  /events             -> stream SSE de mudancas em tempo real
    GET  /health              -> healthcheck simples
"""

import asyncio
import json
import queue
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from affinity_core import AffinityMonitor, WindowState

monitor = AffinityMonitor(poll_interval=1.5)
event_subscribers: list[queue.Queue] = []


def broadcast_change(window: WindowState, is_protected: bool):
    payload = {
        "type": "affinity_change",
        "protected": is_protected,
        "window": window.to_dict(),
    }
    dead = []
    for q in event_subscribers:
        try:
            q.put_nowait(payload)
        except queue.Full:
            dead.append(q)
    for q in dead:
        event_subscribers.remove(q)


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor.on_change(broadcast_change)
    monitor.start()
    yield
    monitor.stop()


app = FastAPI(title="Display Affinity Detector", lifespan=lifespan)

# CORS liberado pra facilitar consumo de um frontend na hackathon
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/windows")
def list_windows():
    return {"count": len(monitor.snapshot()), "windows": monitor.snapshot()}


@app.get("/windows/protected")
def list_protected():
    protected = monitor.protected_only()
    return {"count": len(protected), "windows": protected}


@app.get("/windows/{hwnd}")
def get_window(hwnd: int):
    w = monitor.get(hwnd)
    if w is None:
        raise HTTPException(status_code=404, detail="Janela nao encontrada ou nao visivel")
    return w


@app.get("/events")
async def stream_events():
    q: queue.Queue = queue.Queue(maxsize=100)
    event_subscribers.append(q)

    async def event_generator():
        try:
            # snapshot inicial pro cliente ja abrir sabendo o estado atual
            yield f"data: {json.dumps({'type': 'snapshot', 'windows': monitor.snapshot()})}\n\n"
            while True:
                try:
                    payload = await asyncio.get_event_loop().run_in_executor(
                        None, q.get, True, 15
                    )
                    yield f"data: {json.dumps(payload)}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            if q in event_subscribers:
                event_subscribers.remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
