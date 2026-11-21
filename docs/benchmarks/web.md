# Benchmark de carga do serviço web

O coletor cria contas sintéticas, autentica sessões concorrentes e consulta
`/auth/me`, `/actions` e `/status`. Registra cada latência e status HTTP, mais
CPU e RSS do processo API (ou do container API quando executado com Compose).
Não envia conteúdo real ao Gemini e não abre WebSockets de voz.

## Execução reproduzível

Medição nativa isolada com SQLite temporário:

```bash
python scripts/benchmark_web.py --concurrency 1,5,10,20,40 --duration-seconds 20
```

Deploy de referência com PostgreSQL e Redis via Docker Compose:

```bash
python scripts/benchmark_web.py --compose --concurrency 1,5,10,20,40 --duration-seconds 20
```

O segundo modo cria um projeto Compose temporário com nome único e remove os
serviços e volumes desse projeto ao terminar. A regra registrada pelo coletor
define saturação como o primeiro estágio com p95 acima de 1.000 ms ou mais de
1% de erros. Isso é um limiar operacional do script, não uma meta de produto.

A rodada mais recente, feita no GitHub Actions em 2026-10-20, está em [ci-2026-10-20.md](ci-2026-10-20.md).

## Medição local executada

Em 2026-10-02, Linux CachyOS x86_64, kernel 7.2.7-1-cachyos, Python 3.14.7,
Intel Core i5-13450HX (10 núcleos físicos, 16 lógicos) e 7,44 GiB visíveis,
foi executado o modo nativo/API com SQLite temporário. Cada estágio durou 20 s;
foram consultados três endpoints autenticados em loop por sessão.

| Sessões HTTP virtuais | Requisições | Erros | p95 | CPU média por sessão* | RSS total do serviço | RSS do serviço / sessão** |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 939 | 0% | 7,251 ms | 18,715% | 154,252 MiB | 154,252 MiB |
| 5 | 3.572 | 0% | 20,142 ms | 12,530% | 155,728 MiB | 31,146 MiB |
| 10 | 5.678 | 0% | 35,180 ms | 10,084% | 161,226 MiB | 16,123 MiB |
| 20 | 6.216 | 0% | 75,555 ms | 5,625% | 164,330 MiB | 8,217 MiB |
| 40 | 6.172 | 0% | 204,024 ms | 2,787% | 166,359 MiB | 4,159 MiB |

\* Percentual de um núcleo lógico, dividido pelo número de sessões. 100% é um
núcleo lógico ocupado.
\** Divide o RSS médio total da API pelo número de sessões e inclui a memória
base do processo; não é uma medição da memória incremental privada por sessão.

Brutos: [resumo JSON](web-0.1.0-native-api-sqlite-20261002T233159Z.json),
[latências e erros CSV](web-0.1.0-native-api-sqlite-20261002T233159Z-requests.csv)
e [CPU/RAM por amostra CSV](web-0.1.0-native-api-sqlite-20261002T233159Z-resources.csv).

Os cinco níveis medidos ficaram abaixo do limiar definido, então não foi
observado ponto de saturação até 40 sessões HTTP neste perfil. O ponto exato e
a capacidade máxima não foram determinados, e outro tipo de tráfego pode mudar
o resultado. Docker não está instalado neste
ambiente; portanto, o Compose com PostgreSQL/Redis, limites de container e
sessões de áudio/WebSocket não foram executados. Nenhum limite de CPU ou RAM de
deploy foi inferido ou alterado com base nessa medição. O hardware, SQLite,
duração, endpoints e ausência de tráfego Gemini afetam os resultados; não
extrapole para outro deploy.
