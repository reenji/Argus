# Benchmark do Argus Desktop

Dados brutos: [JSON](desktop-0.1.0-20261002T234224Z.json) e
[CSV](desktop-0.1.0-20261002T234224Z.csv). O executável foi produzido localmente
por PyInstaller com `ARGUS.spec`.

## Execução reproduzível

Na raiz do repositório, depois de instalar dependências e compilar:

```bash
python -m PyInstaller --noconfirm --clean ARGUS.spec
python scripts/benchmark_desktop.py --scenario all
```

Por padrão, mede 60 segundos ocioso, 180 segundos de uso típico e 300 segundos
de uso intenso, coletando CPU e RSS a cada segundo. Os dois últimos cenários são
guiados e pedem Enter antes da amostragem; use um terminal interativo. Adicione
`--live-api` somente se quiser autorizar chamadas do Gemini durante os
cenários. Sem essa opção, a chave é removida do ambiente, o chaveiro é
desativado para o processo de medição e os dados usam um diretório temporário.

A rodada mais recente, feita no GitHub Actions em 2026-10-20, está em [ci-2026-10-20.md](ci-2026-10-20.md).

## Execução registrada

- Versão: 0.1.0; coletada às 23:41:24 UTC em 2026-10-02, Linux CachyOS x86_64,
  kernel 7.2.7-1-cachyos, Python 3.14.7.
- Hardware reportado pelo sistema: Intel Core i5-13450HX (10 núcleos físicos,
  16 lógicos), 7,44 GiB de memória visível.
- Ocioso: 60 amostras por 60 segundos. CPU média 17,236% e máxima 21,828% de
  um núcleo lógico; RSS médio 172,859 MiB e máximo 173,082 MiB.
- A janela permaneceu na configuração inicial, sem chave Gemini e sem chamadas
  de rede. Portanto, esta medição cobre apenas esse estado ocioso.
- Uso típico e intenso: não executados nesta coleta; exigem interação e, para
  testar conversação e ferramentas Gemini, uma chave configurada e autorização
  explícita por `--live-api`.

## Requisitos

O host medido acima é um ambiente em que o executável abriu e permaneceu
ocioso. Uma única máquina e apenas o estado de configuração não determinam um
mínimo ou um recomendado oficial. Esses requisitos continuam sem validação até
medir os cenários típico e intenso e repetir a coleta em máquinas com hardware
inferior e superior. A distribuição também requer espaço para o pacote e os
arquivos do usuário; este ensaio não mediu disco.

CPU é percentual de um núcleo lógico (100% equivale a um núcleo totalmente
ocupado), não percentual total dos 16 núcleos. RAM é RSS do processo Argus, não
memória total do computador. Outros sistemas e uso conectado podem divergir.
