"""
server.py

API REST + Server-Sent Events em cima do AffinityMonitor.

Instalar dependencias:
    pip install fastapi uvicorn

Rodar:
    python server.py

IMPORTANTE (seguranca): por padrao o servidor escuta so em 127.0.0.1
(localhost), ou seja, so processos na sua propria maquina conseguem
acessar. Os dados expostos aqui (titulos de janela) podem conter
informacao sensivel -- nomes de conversa, arquivos abertos, abas do
navegador. Se precisar expor na rede local (por exemplo, pra um
frontend rodando em outro dispositivo durante a demo), troque o host
abaixo para "0.0.0.0" conscientemente, sabendo que qualquer outro
dispositivo na mesma rede vai conseguir ler esses dados.

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

# CORS restrito a localhost por padrao. Ajuste allow_origins se o
# frontend for servido de outro endereco -- evite "*" em producao,
# ja que os dados expostos aqui podem ser sensiveis (titulos de janela).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET"],
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
    # host="127.0.0.1": so acessivel da propria maquina.
    # Trocar para "0.0.0.0" expoe a API pra qualquer dispositivo na
    # mesma rede -- so faca isso se tiver certeza do motivo.
    uvicorn.run(app, host="127.0.0.1", port=8000)
