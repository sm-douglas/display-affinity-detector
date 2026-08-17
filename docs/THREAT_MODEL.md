# Threat model e limitações teóricas

Este documento explica, em nível conceitual, por que `WDA_EXCLUDEFROMCAPTURE`
tem limites, e por que este projeto foca em **detecção** da proteção em vez
de tentar ser uma garantia absoluta de confidencialidade.

## Como a proteção funciona

`WDA_EXCLUDEFROMCAPTURE` atua no nível do compositor de janelas (DWM). Quando
uma janela recebe essa flag, o Windows instrui o compositor a omitir aquele
buffer específico sempre que outro processo solicita uma captura através das
APIs padrão (`BitBlt`, `PrintWindow`, Windows Graphics Capture API).

Ou seja: é um controle de política do sistema operacional sobre uma via
específica de captura, não uma barreira física entre o conteúdo renderizado
e a tela.

## Categorias de limitação

**1. Vias de captura alternativas**
A proteção cobre as APIs de captura de tela do Windows. Qualquer mecanismo
que obtenha os pixels por um caminho diferente do compositor (nível de
driver de vídeo, ou hardware externo apontado para a tela) não passa pelo
DWM e portanto não está sujeito a essa política.

**2. Escopo de sessão e privilégio**
A affinity é aplicada por processo/janela dentro de uma sessão. Ferramentas
rodando com privilégio mais alto que o processo protegido, ou fora do
escopo de usuário padrão, têm historicamente superfícies de acesso
diferentes ao conteúdo renderizado.

**3. Timing da aplicação da flag**
A proteção só existe a partir do momento em que `SetWindowDisplayAffinity`
é chamada. Qualquer captura que ocorra antes dessa chamada (por exemplo,
durante a inicialização da janela) não é coberta retroativamente.

**4. Captura fora do sistema operacional**
Sendo um controle de software, não cobre captura física (uma câmera
apontada para o monitor, por exemplo). Esse é o limite teórico de qualquer
proteção desse tipo, independente de implementação.

## Por que o foco é detecção

Dado que nenhuma dessas proteções é absoluta, saber **quando e onde** a
proteção está sendo aplicada tem valor prático mesmo sem cobrir 100% dos
vetores teóricos acima. É essa a proposta deste projeto: observabilidade
sobre o uso da API, não uma ferramenta de evasão.
