# Compact mono AWC layout and loading geometry (proposal)

## Scope

`build_awc_bytes(awc, compact_streams=True)` places each mono stream's
chunks together. The logical chunk table order, stream IDs, payloads and
metadata are preserved. The default remains unchanged for compatibility.
Multichannel banks are deliberately rejected by this option: their shared
streaming blocks require a different loading model.

Global chunk-type sorting can place one stream's small metadata far away
from its DATA. A loader reading the complete interval between those chunks
then needs much more space than the payload size suggests. Compact layout
removes intervening streams but does not guarantee that every individual
stream fits the application's buffer.

`fivefury.awc.loading_geometry.inspect_loading_geometry` accepts an AWC
header/table, full file size, an explicit alignment and an optional buffer
budget. It checks table bounds and reports per-stream spans and the model
`aligned_header + stream_span`. A missing budget means unknown, not pass.
Multichannel streams do not receive mono-budget verdicts. Whole-file
encrypted headers must be decrypted before inspection.

The caller must qualify this loading model, alignment and budget for its
application. This API does not discover runtime buffer allocation, promise
compatibility with every game version, or measure total process memory.
It never changes bitrate, pitch, channels, duration or audio content.

## Evidence and limitations

A private GTA V Enhanced 1.0.1158.16 test reproduced dialogue stutters and
crashes with a modified bank. Compact placement alone did not fix it. A
CodeWalker-built compact bank with two oversized entries recoded to 160
kbit/s reduced the measured maximum requirement from 187,216 to 163,890
bytes. The user completed the tested dialogue with all audio/subtitles,
without crash or stutter. The 175,136-byte conservative budget used there
is **not** a universal AWC limit or proof of the exact pool assigned to it.

The Python compact writer subsequently rebuilt the approved M AWC byte for
byte (30,742,718 bytes), including all 788 entries. This establishes exact
artifact equivalence for that bank, not a new independent in-game test or
approval of other banks. Synthetic tests also exercise the geometry API.
The unchanged default writer also produces the same approved M bytes: this
bank's encrypted single-channel DATA already selects per-stream ordering.
Consequently, this experiment does not establish a default FiveFury ordering
bug as the crash cause. The explicit compact option additionally covers other
mono layouts; callers must inspect the final serialized artifact, including
any later incremental replacement, rather than infer safety from the writer.
No game assets, executables, dumps or encryption keys accompany this proposal.

The production consumer subsequently qualified named wave-slot capacities
from the game's active DAT4 configuration against a private runtime capture.
It uses the conservative minimum for the supported speech family and the
smallest original-compatible scanner slot, not a global 175,136-byte rule.
Multichannel blocks are checked against their corresponding originals instead.
These application-specific policies belong in the consumer, not this API.
The cumulative 0.9.47 delivery structurally reviewed 1,587 banks and changed
23; that inventory is not evidence of an in-game playthrough of all banks.

## Tests

`python -m pytest tests/audio/awc/test_loading_geometry.py -q`

Fixtures are synthesized PCM, not copied game content. Tests cover physical
span reduction, logical payload preservation, unknown budgets, exact budget
boundaries and malformed tables. The existing AWC unit suite must also pass.

---

# Layout mono compacto e geometria de carregamento (proposta)

A opção `compact_streams=True` reúne fisicamente os chunks de cada entrada
mono sem trocar o conteúdo lógico. A ordenação global por tipo pode separar
metadados e áudio por muitos bytes pertencentes a outras entradas, aumentando
o intervalo que o carregador precisa ler. Compactar elimina essa dispersão,
mas uma entrada individual ainda pode ultrapassar o orçamento disponível.

O medidor recebe alinhamento e orçamento explícitos. Orçamento ausente é
desconhecido, não aprovação. Bancos multicanal não herdam o cálculo mono.
Não há redução automática de bitrate nem constante universal de memória.
A política de recodificação permanece no consumidor, com validação própria.

O teste privado M passou no diálogo testado em GTA Enhanced 1.0.1158.16,
usando CodeWalker e duas recodificações para 160 kbit/s. O requisito máximo
medido caiu de 187.216 para 163.890 bytes. Isso não comprova o funcionamento
no jogo da nova opção Python, nem aprova todo o acervo. O orçamento de
175.136 bytes não deve ser generalizado. Posteriormente, o escritor Python
reproduziu o AWC M byte a byte (30.742.718 bytes, 788 entradas). Essa equivalência
é específica do M e não aprova automaticamente outros bancos. A contribuição usa somente fixtures
sintéticas e não distribui arquivos protegidos do jogo.

O escritor padrão, sem a nova opção, também reproduz exatamente o M: a flag
de DATA cifrado mono desse banco já seleciona a ordenação por entrada.
Portanto, o teste não demonstra que a ordenação padrão do FiveFury causou
o crash. A opção explícita amplia a compactação para outros layouts mono;
é necessário medir o artefato final, inclusive depois de substituições
incrementais, em vez de presumir segurança pelo nome do empacotador.

O envio upstream é restrito à API de geometria, compactação mono, documentação
e testes sintéticos; adaptações exclusivas do projeto ficam no fork.

O consumidor de produção qualificou depois os slots nomeados da configuração
DAT4 ativa comparando-os à captura privada de execução. Usa o menor orçamento
da família Speech e o menor slot Scanner compatível com o original, não um
limite global de 175.136 bytes. Bancos multicanal são comparados aos blocos de
seus próprios originais. Essas políticas pertencem ao consumidor, não à API.
A entrega cumulativa 0.9.47 revisou estruturalmente 1.587 bancos e alterou 23;
isso não equivale a jogar e testar todas as suas falas.
