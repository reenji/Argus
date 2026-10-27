# POLÍTICA DE PRIVACIDADE — ARGUS

**Última atualização: 6 de outubro de 2026**

Esta Política de Privacidade descreve como o **Argus** ("Argus", "Aplicativo", "Sistema" ou "Serviço") trata dados pessoais quando o usuário utiliza suas funcionalidades, incluindo aplicativo desktop, aplicação web, serviços de inteligência artificial, pesquisa, comunicação por e-mail, voz, captura de tela, câmera, arquivos e demais recursos disponibilizados pelo sistema.

Esta Política foi elaborada considerando a **Lei nº 13.709/2018 — Lei Geral de Proteção de Dados Pessoais (LGPD)** e demais normas brasileiras aplicáveis à proteção de dados.

**Esta versão deve ser complementada com a identificação do controlador, canais oficiais de contato, informações do Encarregado pelo Tratamento de Dados Pessoais (quando aplicável) e procedimentos operacionais de atendimento aos titulares antes de sua publicação definitiva.**

---

## 1. Quem é responsável pelo tratamento dos dados

O responsável pelo tratamento dos dados pessoais realizados por meio do Argus será o **Controlador**, a ser identificado nas informações oficiais do Serviço.

**Controlador:** [RAZÃO SOCIAL / NOME DO RESPONSÁVEL]

**CNPJ/CPF:** [INFORMAR]

**Endereço:** [INFORMAR]

**E-mail para assuntos de privacidade:** [INFORMAR]

**Encarregado de Dados (DPO), quando aplicável:** [INFORMAR]

Enquanto essas informações não forem preenchidas, este documento deve ser considerado uma **versão preparatória**, e não uma política definitiva para publicação comercial.

---

# 2. Princípios de tratamento

O Argus busca realizar o tratamento de dados pessoais de acordo com os princípios previstos na LGPD, especialmente:

- finalidade;
- adequação;
- necessidade;
- livre acesso;
- qualidade dos dados;
- transparência;
- segurança;
- prevenção;
- não discriminação; e
- responsabilização e prestação de contas.

O Argus procura limitar o tratamento aos dados necessários para disponibilizar, manter, proteger e aprimorar suas funcionalidades.

---

# 3. Dados que podem ser tratados

Os dados tratados dependem das funcionalidades utilizadas pelo usuário.

## 3.1. Dados fornecidos diretamente pelo usuário

Podem ser tratados, conforme a utilização do Serviço:

- nome;
- endereço de e-mail;
- credenciais de acesso;
- conteúdo de mensagens;
- comandos enviados ao assistente;
- arquivos selecionados pelo usuário;
- imagens;
- capturas de tela;
- conteúdo de câmera;
- áudio;
- transcrições;
- informações inseridas na memória do assistente;
- informações relacionadas a tarefas;
- conteúdo de pesquisas;
- mensagens de e-mail utilizadas pelas funcionalidades de integração;
- configurações do aplicativo;
- outras informações voluntariamente fornecidas pelo usuário.

O Argus não considera que todo dado disponível no dispositivo seja automaticamente coletado. O tratamento ocorre de acordo com a funcionalidade acionada pelo usuário e com as permissões concedidas.

---

# 4. Dados tratados pelo aplicativo desktop

No aplicativo desktop, determinadas funcionalidades podem processar informações localmente ou encaminhá-las a serviços externos necessários à execução da funcionalidade.

## 4.1. Voz

Quando o usuário utiliza funcionalidades de voz ou uma sessão Live, o áudio necessário à execução da funcionalidade pode ser transmitido ao provedor de inteligência artificial correspondente.

No estado atual do código analisado, o áudio da sessão Live não é gravado pelo Argus em arquivo ou banco de dados próprio.

Isso não impede que o provedor externo eventualmente trate ou retenha os dados de acordo com seus próprios termos, políticas e configurações.

---

## 4.2. Texto e conversas

As mensagens digitadas pelo usuário podem ser processadas pelo modelo de inteligência artificial selecionado.

Quando a funcionalidade web estiver sendo utilizada, determinadas conversas podem ser armazenadas no banco de dados do Serviço para permitir o funcionamento do histórico e de recursos relacionados.

---

## 4.3. Captura de tela e câmera

Quando o usuário aciona funcionalidades que utilizam captura de tela ou câmera, o conteúdo necessário à execução da ação pode ser processado e transmitido ao provedor externo correspondente.

O Argus não considera imagens ou conteúdo de câmera como dados coletados continuamente sem que a funcionalidade correspondente esteja ativa.

O usuário deve utilizar essas funcionalidades de acordo com a legislação aplicável e evitar compartilhar dados de terceiros sem autorização ou outra base legal adequada.

---

## 4.4. Arquivos

Arquivos selecionados pelo usuário podem ser lidos ou processados pelo Argus para execução da funcionalidade solicitada.

Quando necessário, partes ou a totalidade do conteúdo podem ser enviadas a provedores externos utilizados pela funcionalidade.

Arquivos gerados ou baixados pelo usuário são armazenados no local selecionado ou definido pela aplicação.

---

# 5. Memória e armazenamento local

O aplicativo desktop possui mecanismos de memória local.

Quando o usuário solicita que determinada informação seja armazenada em memória, o Argus pode salvar essas informações no diretório local de dados da aplicação.

Atualmente, o mecanismo inclui, entre outros:

- `memory/long_term.json`;
- `memory/task_history.json`;
- `memory/answer_cache.json`.

A memória de longo prazo possui limitação aproximada de conteúdo de acordo com a implementação atual.

O histórico de tarefas é limitado às **100 entradas mais recentes** e o cache de respostas é limitado a aproximadamente **200 itens**, conforme a implementação atual.

Esses limites são técnicos e **não devem ser interpretados como prazos legais de retenção**.

O usuário é responsável por proteger o dispositivo e sua conta de sistema contra acesso não autorizado aos arquivos locais.

---

# 6. Configurações e credenciais

Determinadas configurações podem ser armazenadas localmente.

A chave de API do Gemini, quando configurada pela interface, utiliza o mecanismo de armazenamento seguro do sistema operacional quando disponível.

Caso o usuário configure uma chave por meio da variável de ambiente `GEMINI_API_KEY`, essa informação poderá permanecer em arquivo `.env` local, sujeita às permissões do sistema operacional, backups, sincronização e demais mecanismos existentes no dispositivo do usuário.

O código contém ainda uma função legada que pode armazenar chaves em:

`config/api_keys.json`

Essa função não é acionada pela interface atual conforme a implementação analisada.

O usuário deve evitar compartilhar arquivos de configuração contendo credenciais ou chaves secretas.

---

# 7. Integração com Gmail

Quando o usuário habilita a integração com Gmail, o Argus utiliza autenticação OAuth para acessar as funcionalidades autorizadas.

Tokens OAuth são armazenados no mecanismo de credenciais do sistema quando suportado.

Dependendo da funcionalidade utilizada, o Argus poderá acessar informações necessárias para leitura, elaboração ou envio de mensagens.

Antes do envio de uma mensagem preparada pelo assistente, o sistema possui etapa de revisão e confirmação pelo usuário.

O Argus não é responsável pelas políticas de privacidade, segurança, retenção ou tratamento de dados realizados pelo Google.

---

# 8. Aplicação web

Quando o serviço web é disponibilizado e utilizado, determinados dados podem ser armazenados em infraestrutura de servidor.

De acordo com a implementação atualmente analisada, podem ser armazenados:

- endereço de e-mail;
- nome de exibição;
- hash da senha;
- configurações do usuário;
- memória associada à conta;
- chaves de API protegidas/cifradas;
- conversas;
- transcrições de texto de sessões Live;
- histórico de tarefas;
- cache de respostas;
- informações técnicas necessárias à operação do serviço.

As senhas não devem ser armazenadas em texto puro. A implementação utiliza **scrypt para geração do hash de senha**.

---

# 9. Tokens de autenticação

A aplicação web utiliza tokens de acesso para autenticação.

Na configuração analisada, o token possui validade padrão de aproximadamente **1.440 minutos**, salvo alteração da configuração do ambiente.

O cliente web armazena o token em `localStorage`.

O armazenamento de tokens em `localStorage` apresenta riscos específicos, especialmente em caso de comprometimento por código JavaScript malicioso ou vulnerabilidade de XSS. A implementação deverá ser avaliada e, quando possível, devem ser consideradas alternativas de armazenamento mais seguras, como cookies com atributos `HttpOnly`, `Secure` e `SameSite`.

Ao sair (logout), o servidor invalida todos os tokens já emitidos para a conta e encerra a sessão de voz em andamento.

---

# 10. Inteligência artificial e provedores externos

O Argus pode utilizar provedores externos de inteligência artificial e outros serviços para executar funcionalidades solicitadas pelo usuário.

Dependendo da configuração e da ação executada, dados podem ser enviados para:

- Google Gemini;
- Google Search;
- DuckDuckGo;
- OpenAI;
- ElevenLabs;
- Edge TTS;
- Gmail/Google;
- outros serviços eventualmente integrados ao Argus.

O conteúdo enviado depende da funcionalidade utilizada.

Por exemplo, uma solicitação de geração de resposta pode envolver o envio da mensagem do usuário ao provedor de inteligência artificial selecionado.

Uma funcionalidade de pesquisa pode enviar termos de pesquisa ao mecanismo de pesquisa correspondente.

Uma funcionalidade de voz pode transmitir áudio ou texto ao provedor de voz correspondente.

O Argus não controla as práticas de privacidade, segurança, retenção ou utilização de dados desses terceiros.

O usuário deve consultar as respectivas políticas e termos dos provedores antes de utilizar funcionalidades que envolvam o compartilhamento de dados.

---

# 11. Transferência internacional de dados

Alguns provedores utilizados pelo Argus podem estar localizados fora do Brasil ou utilizar infraestrutura localizada em outros países.

Consequentemente, determinados dados pessoais podem ser tratados ou armazenados internacionalmente.

Essas transferências deverão observar os requisitos da LGPD e as regulamentações aplicáveis da Autoridade Nacional de Proteção de Dados — ANPD.

O Controlador deverá manter registro dos países, provedores, categorias de dados e mecanismos jurídicos utilizados para as transferências internacionais aplicáveis à versão efetivamente disponibilizada do Argus.

---

# 12. Finalidades do tratamento

Os dados podem ser tratados para as seguintes finalidades:

1. fornecer as funcionalidades solicitadas pelo usuário;
2. autenticar usuários;
3. manter sessões e contas;
4. processar comandos e conversas;
5. executar funcionalidades de inteligência artificial;
6. realizar pesquisas;
7. executar funcionalidades de voz;
8. processar arquivos, imagens e capturas fornecidas pelo usuário;
9. executar integrações autorizadas;
10. enviar e-mails mediante autorização;
11. manter histórico e memória;
12. armazenar configurações;
13. garantir segurança e prevenir abusos;
14. aplicar limites de utilização;
15. diagnosticar falhas e problemas técnicos;
16. cumprir obrigações legais e regulatórias;
17. exercer regularmente direitos em processos judiciais, administrativos ou arbitrais; e
18. executar outras finalidades informadas ao usuário no momento da coleta.

O Argus não deverá utilizar dados pessoais para finalidade incompatível com aquela informada ao usuário sem fundamento jurídico adequado.

---

# 13. Bases legais

O tratamento de dados pessoais deverá ocorrer com fundamento em uma ou mais hipóteses legais previstas na LGPD, conforme a finalidade e o contexto do tratamento.

Entre as possíveis bases legais estão:

- execução de contrato ou de procedimentos preliminares relacionados ao contrato;
- cumprimento de obrigação legal ou regulatória;
- exercício regular de direitos;
- legítimo interesse, quando aplicável e após a realização da análise necessária;
- consentimento, quando exigido ou adotado;
- proteção do crédito, quando aplicável; e
- demais hipóteses previstas nos artigos 7º e 11 da LGPD.

A base legal específica poderá variar de acordo com a finalidade e com a natureza dos dados tratados.

---

# 14. Dados pessoais sensíveis

O Argus não tem como finalidade principal coletar dados pessoais sensíveis.

Entretanto, o usuário poderá inserir voluntariamente informações que sejam consideradas sensíveis pela LGPD em mensagens, arquivos, imagens, gravações ou outros conteúdos enviados ao sistema.

O usuário deve evitar inserir dados pessoais sensíveis quando eles não forem necessários para a funcionalidade utilizada.

Quando houver tratamento de dados pessoais sensíveis, deverão ser observadas as hipóteses legais específicas previstas na LGPD.

---

# 15. Dados de terceiros

O usuário poderá enviar ao Argus informações pertencentes a terceiros, incluindo nomes, endereços de e-mail, mensagens, documentos, imagens ou outras informações pessoais.

Ao fornecer dados de terceiros, o usuário deve possuir autorização, legitimidade ou outra base jurídica aplicável para realizar esse compartilhamento.

O Argus não recomenda o envio de informações pessoais de terceiros quando elas não forem necessárias para a finalidade pretendida.

---

# 16. Telemetria e analytics

De acordo com o código analisado em **2 de outubro de 2026**, o repositório não contém SDK identificado de analytics de produto, sistema próprio de telemetria periódica ou mecanismo próprio de coleta contínua de métricas de utilização.

As chamadas realizadas a serviços externos de inteligência artificial, pesquisa, e-mail ou voz são realizadas para executar funcionalidades solicitadas e **não devem ser consideradas, por si só, como analytics do Argus**.

Entretanto, serviços de terceiros podem possuir seus próprios mecanismos de logs, métricas, segurança, prevenção contra abuso ou análise de utilização, sujeitos às respectivas políticas.

---

# 17. Logs e informações técnicas

Durante a execução, o Argus pode apresentar informações de diagnóstico no terminal ou na interface.

Os logs de ferramentas podem incluir:

- nome da ferramenta;
- parâmetros da operação;
- trechos limitados do resultado;
- informações de erro;
- informações técnicas necessárias ao diagnóstico.

O código analisado limita determinados trechos de resultados exibidos nos logs a aproximadamente 80 caracteres.

No serviço web, os logs HTTP padrão do servidor podem incluir informações como endereço remoto, rota acessada e código de status.

No serviço web, os logs de diagnóstico registram o identificador interno do usuário e detalhes técnicos de erros (incluindo stack traces), mas não os parâmetros das ferramentas, como perguntas ou textos de mensagens.

Esses logs podem ser coletados pelo servidor, container, sistema operacional, hospedagem ou provedor de infraestrutura utilizado na implantação.

A retenção desses logs depende da infraestrutura efetivamente utilizada e não é integralmente controlada pelo código do Argus.

---

# 18. Redis, quotas e armazenamento temporário

O serviço web pode utilizar Redis para controle de quotas e mecanismos relacionados à operação.

As chaves de quota possuem expiração.

Quando Redis não está disponível e a configuração permite, determinados mecanismos de limitação podem utilizar memória do próprio processo.

Esses dados temporários não devem ser considerados como histórico permanente da conta.

---

# 19. Política de retenção

A configuração padrão atualmente identificada é:

`ARGUS_DATA_RETENTION_DAYS=90`

Quando habilitada, a rotina de retenção remove, durante a inicialização e posteriormente em periodicidade diária, determinados:

- registros de conversa;
- registros de tarefas; e
- entradas de cache web

que ultrapassem o período configurado.

O valor deve ser um número inteiro positivo.

**A retenção de 90 dias não significa que todos os dados pessoais sejam automaticamente eliminados após 90 dias.**

De acordo com a implementação atualmente analisada, a rotina não remove automaticamente:

- contas;
- hashes de senha;
- memória;
- configurações;
- segredos cifrados;
- outros registros não abrangidos pela rotina.

Esses dados permanecem armazenados até que sejam excluídos por procedimento específico ou pela administração da infraestrutura.

**Recomenda-se implementar mecanismos completos de exclusão de conta e dados antes da disponibilização comercial.**

---

# 20. Segurança

O Argus adota medidas técnicas compatíveis com sua arquitetura para reduzir riscos de acesso, alteração, perda ou divulgação indevida de dados.

Entre os mecanismos utilizados estão, conforme aplicável:

- hash de senhas utilizando scrypt;
- armazenamento de credenciais no chaveiro do sistema;
- cifragem de determinadas chaves armazenadas no servidor;
- autenticação;
- controle de acesso;
- limitação de utilização;
- expiração de dados temporários;
- separação entre componentes do sistema.

Nenhum sistema eletrônico pode garantir segurança absoluta.

O usuário também possui responsabilidade pela segurança de seu dispositivo, credenciais, arquivos de configuração, chaves de API e demais mecanismos de acesso.

---

# 21. Incidentes de segurança

Na hipótese de incidente de segurança envolvendo dados pessoais, o Controlador deverá avaliar a natureza, extensão, consequências e riscos do incidente e adotar as medidas exigidas pela legislação aplicável.

Quando necessário, poderão ser realizadas comunicações à ANPD e aos titulares afetados, observados os requisitos e prazos estabelecidos pela legislação e regulamentação aplicáveis.

---

# 22. Direitos dos titulares

Nos termos da LGPD, o titular poderá exercer, observadas as hipóteses e limitações legais, direitos como:

- confirmação da existência de tratamento;
- acesso aos dados;
- correção de dados incompletos, inexatos ou desatualizados;
- anonimização, bloqueio ou eliminação de dados desnecessários, excessivos ou tratados em desconformidade;
- portabilidade, quando regulamentada e aplicável;
- eliminação dos dados tratados com base no consentimento, ressalvadas as hipóteses legais de conservação;
- informação sobre entidades públicas e privadas com as quais os dados foram compartilhados;
- informação sobre a possibilidade de não fornecer consentimento e sobre as consequências da negativa;
- revogação do consentimento;
- revisão de decisões tomadas unicamente com base em tratamento automatizado, quando aplicável; e
- demais direitos previstos na LGPD.

O exercício de determinados direitos poderá estar sujeito às limitações previstas na própria legislação.

---

# 23. Como solicitar acesso, correção ou exclusão

Solicitações relacionadas à privacidade deverão ser encaminhadas para:

**E-mail:** [E-MAIL DE PRIVACIDADE]

O pedido deverá conter informações suficientes para permitir a identificação do titular e a análise da solicitação.

Por razões de segurança, o Controlador poderá solicitar informações adicionais para confirmar a identidade do solicitante.

O Controlador responderá às solicitações dentro dos prazos estabelecidos pela legislação aplicável.

---

# 24. Exclusão de conta e dados

Na versão do código analisada, **não existe atualmente uma rota web completa para exclusão integral da conta do usuário**.

Consequentemente, antes da disponibilização comercial, o sistema deverá possuir procedimento documentado para:

1. solicitação de exclusão;
2. identificação do titular;
3. exclusão ou anonimização dos dados aplicáveis;
4. tratamento dos dados que precisem ser mantidos por obrigação legal;
5. exclusão de dados em sistemas auxiliares;
6. tratamento de backups;
7. registro da solicitação e respectiva conclusão.

Enquanto esse mecanismo não estiver implementado, esta Política não deve afirmar que o usuário consegue excluir sua conta diretamente pela aplicação.

---

# 25. Cookies e armazenamento no navegador

A aplicação web pode utilizar mecanismos de armazenamento do navegador, incluindo `localStorage`, para manter informações necessárias à autenticação e funcionamento da aplicação.

O `localStorage` não é equivalente a um cookie `HttpOnly` e possui riscos próprios de segurança.

A versão efetivamente publicada do sistema deverá informar de maneira específica quaisquer cookies ou tecnologias semelhantes utilizadas para:

- autenticação;
- segurança;
- preferências;
- análise;
- publicidade;
- outras finalidades.

Caso sejam utilizados cookies não estritamente necessários, deverá ser avaliada a necessidade de consentimento ou outro fundamento jurídico adequado, conforme a legislação aplicável.

---

# 26. Menores de idade

O Argus não é destinado, de forma específica, a crianças.

Quando o tratamento envolver dados de crianças ou adolescentes, deverão ser observadas as disposições aplicáveis da LGPD, do Estatuto da Criança e do Adolescente e demais normas pertinentes.

Não deverão ser solicitados dados pessoais de crianças de forma incompatível com sua proteção e com seu melhor interesse.

---

# 27. Serviços de terceiros

O Argus pode depender de serviços de terceiros para fornecer determinadas funcionalidades.

Esses serviços podem possuir regras próprias de:

- privacidade;
- segurança;
- retenção;
- armazenamento;
- processamento;
- transferência internacional;
- utilização de dados.

O usuário deve consultar as políticas dos respectivos fornecedores.

A contratação ou utilização de um terceiro pelo Argus não significa que o Controlador deixe de ser responsável pelas obrigações que lhe forem atribuídas pela legislação aplicável.

---

# 28. Alterações desta Política

Esta Política poderá ser atualizada para refletir:

- alterações no sistema;
- novas funcionalidades;
- alterações legais ou regulatórias;
- mudanças nos provedores utilizados;
- mudanças nas práticas de tratamento;
- melhorias de segurança;
- alterações na infraestrutura.

Quando houver alterações relevantes, o usuário poderá ser informado por meios adequados, especialmente quando a alteração modificar de maneira significativa as finalidades ou condições do tratamento.

A data da última atualização será indicada no início deste documento.

---

# 29. Configuração do domínio e infraestrutura

O domínio público utilizado pelo Argus deverá ser configurado por meio da variável:

`PUBLIC_ARGUS_SITE_URL`

A URL do repositório é definida por:

`PUBLIC_ARGUS_REPOSITORY_URL`

A aplicação web utiliza:

`NEXT_PUBLIC_API_BASE_URL`

como endereço-base da API.

A URL WebSocket é derivada da configuração correspondente.

Essas configurações são técnicas e não substituem as informações oficiais de identificação do Controlador ou os canais de privacidade previstos nesta Política.

---

# 30. Ausência de garantia sobre serviços externos

Embora o Argus adote medidas para integrar serviços externos de maneira adequada, o funcionamento, disponibilidade, segurança e políticas desses serviços dependem de seus respectivos fornecedores.

O Argus não controla:

- alterações nas APIs de terceiros;
- indisponibilidade dos serviços externos;
- políticas internas de retenção desses fornecedores;
- alterações em seus modelos de inteligência artificial;
- práticas de segurança de infraestrutura de terceiros;
- mudanças em seus termos de uso.

O tratamento realizado por terceiros continuará sujeito às políticas e condições aplicáveis de cada fornecedor.

---

# 31. Contato

Para questões relacionadas a esta Política ou ao tratamento de dados pessoais, entre em contato:

**Controlador:** [RAZÃO SOCIAL / NOME]

**CNPJ/CPF:** [INFORMAR]

**E-mail:** [E-MAIL DE PRIVACIDADE]

**Endereço:** [ENDEREÇO]

**Encarregado/DPO:** [INFORMAR, SE APLICÁVEL]

---

# 32. Disposições finais

Esta Política deve ser interpretada em conjunto com os Termos de Uso do Argus e demais documentos jurídicos aplicáveis ao Serviço.

A presente Política descreve o funcionamento identificado na versão do código analisada em **2 de outubro de 2026** e não deve ser interpretada como garantia de que todas as futuras versões do software possuirão exatamente o mesmo comportamento.

Caso o Argus seja alterado para incluir novas formas de coleta, tratamento, armazenamento, compartilhamento, publicidade, análise comportamental ou monetização, esta Política deverá ser revisada antes da disponibilização dessas funcionalidades.

**Versão:** 1.0  
**Data de atualização:** 6 de outubro de 2026
