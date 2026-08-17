# Display Affinity Detector

Ferramenta para identificar, em tempo real, quais janelas do Windows estão
protegidas contra captura de tela via `SetWindowDisplayAffinity`
(`WDA_EXCLUDEFROMCAPTURE` / `WDA_MONITOR`).

Feita para uma hackathon com foco em observabilidade: em vez de tentar
contornar a proteção, o projeto identifica quando e onde ela está sendo
aplicada no sistema.

## O que tem aqui

- **`native/detector.cpp`**: versão em C++ puro (Win32), enumera todas as
  janelas visíveis e imprime o status de affinity de cada uma. Sem
  dependências externas.
- **`python/affinity_core.py`**: motor de monitoramento contínuo. Combina
  `SetWinEventHook` (reage rápido a janelas novas/em foco) com polling
  periódico (pega mudanças em janelas já abertas).
- **`python/server.py`**: API REST em cima do monitor, com FastAPI, incluindo
  um endpoint de streaming (SSE) para consumo em tempo real por um frontend.
- **`python/gui.py`**: janela nativa (Tkinter) mostrando o status ao vivo,
  sem depender de navegador nem do servidor. Tem botão de
  iniciar/parar monitoramento e exportação de snapshot (CSV/JSON).
- **`python/gerar_icone.py`**: utilitário para converter um PNG em `.ico`
  multi-resolução, recortando margem transparente automaticamente.
- **`docs/THREAT_MODEL.md`**: explicação teórica de por que a proteção tem
  limites e por que a ferramenta foca em detecção em vez de bypass.

## Como funciona

`GetWindowDisplayAffinity` é a contraparte de leitura de
`SetWindowDisplayAffinity`. Qualquer processo pode consultar o valor de
affinity de uma janela (desde que tenha o HWND e esteja no mesmo nível de
sessão/privilégio). Os valores possíveis:

| Valor | Constante | Significado |
|---|---|---|
| `0x00000000` | `WDA_NONE` | Sem proteção |
| `0x00000001` | `WDA_MONITOR` | Legado, exclui de captura |
| `0x00000011` | `WDA_EXCLUDEFROMCAPTURE` | Exclui de captura (Windows 10 2004+) |

Importante: **não existe um evento de sistema disparado quando a affinity
muda**. Não dá para "escutar" essa mudança diretamente. A abordagem usada
aqui é híbrida: hooks de eventos gerais de janela (`EVENT_OBJECT_SHOW`,
`EVENT_SYSTEM_FOREGROUND`, `EVENT_OBJECT_CREATE`) para reagir rápido a
janelas novas, combinados com polling leve de fallback para pegar mudanças
em janelas que já estavam abertas.

## Rodando a versão C++

Requer Windows e um compilador com suporte a `_WIN32_WINNT >= 0x0601`
(Windows 7+). Testado com MinGW-w64 via MSYS2.

```
g++ native/detector.cpp -o native/detector.exe -luser32
.\native\detector.exe
```

## Rodando a versão Python (API)

Requer Python 3.10+.

```
cd python
pip install -r requirements.txt
python server.py
```

Servidor sobe em `http://localhost:8000`. Endpoints:

- `GET /windows` — todas as janelas visíveis e seu status
- `GET /windows/protected` — só as marcadas com affinity
- `GET /windows/{hwnd}` — detalhe de uma janela específica
- `GET /events` — stream SSE de mudanças em tempo real
- `GET /health` — healthcheck

## Rodando a GUI nativa

Não depende do servidor nem de navegador, usa o monitor diretamente:

```
cd python
python gui.py
```

Abre uma janela com tabela ao vivo (título, PID, tipo de affinity, status),
botão de iniciar/parar monitoramento e exportação de snapshot.

## Empacotando como .exe standalone

Pra rodar em outra máquina Windows sem precisar de Python instalado:

```
cd python
pip install pyinstaller
pyinstaller --onefile --windowed --name AffinityDetector gui.py
```

O executável final fica em `python/dist/AffinityDetector.exe`. É
autocontido: não precisa do `.py`, do `affinity_core.py` nem de nada além
dele mesmo para rodar em outra máquina.

Requisitos da máquina de destino: Windows 64-bit, Windows 10 2004+ (para a
API de exclusão de captura funcionar), e aceitar o aviso do
SmartScreen/antivírus na primeira execução (comum em executáveis do
PyInstaller sem assinatura digital).

### Ícone customizado

```
python gerar_icone.py   # gera icone.ico a partir de icone.png na mesma pasta
pyinstaller --onefile --windowed --name AffinityDetector --icon=icone.ico gui.py
```

Se o ícone não atualizar visualmente após o build, é cache de ícones do
Windows, não um problema no `.exe`:

```
taskkill /IM explorer.exe /F
Remove-Item "$env:LOCALAPPDATA\IconCache.db" -Force -ErrorAction SilentlyContinue
Start-Process explorer.exe
```

## Limitações

- Só Windows, por depender de APIs Win32 (`user32.dll`).
- Só enxerga janelas na mesma sessão/nível de privilégio do processo que
  roda a ferramenta.
- Não detecta mudanças de affinity instantaneamente em todos os casos, por
  causa da ausência de evento nativo para isso (ver seção acima).

Para a discussão teórica de por que a própria proteção `WDA_EXCLUDEFROMCAPTURE`
tem limites, ver [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## Licença

MIT. Ver [`LICENSE`](LICENSE).
