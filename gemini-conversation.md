> User Query

Você disse

Preciso de ajuda para entender o "geral" do SWE-bench e todas as ferramentas deles.

https://github.com/SWE-bench/SWE-bench

https://github.com/SWE-bench/sb-cli

https://github.com/SWE-bench/SWE-smith

https://github.com/SWE-agent/SWE-agent

https://github.com/codeclash-ai/codeclash

https://github.com/SWE-agent/Mini-SWE-Agent

https://github.com/SWE-agent/SWE-ReX

> Gemini Answer

Para entender o panorama geral, pense nesse ecossistema como uma grande **"escola e campo de testes" para Inteligências Artificiais que querem ser Engenheiras de Software**.

Essa série de repositórios (criada em grande parte por pesquisadores de Princeton e da comunidade de IA) forma uma infraestrutura completa para **testar, treinar e executar** agentes de IA que programam e resolvem bugs sozinhos.

Aqui está o resumo de como cada uma dessas peças se encaixa no "Geral":

### 1\. O Teste Oficial (A Prova)
- **[SWE-bench](https://github.com/SWE-bench/SWE-bench):** É a fundação de tudo. Trata-se de um benchmark (um padrão de avaliação) muito rigoroso para Modelos de Linguagem (LLMs). Ele pega milhares de problemas reais (issues) extraídos do GitHub e desafia a IA a resolvê-los escrevendo código. Se a IA conseguir passar nos testes unitários originais do repositório, ela ganha pontos.

### 2\. Os Alunos (As IAs Programadoras)
- **[SWE-agent](https://github.com/SWE-agent/SWE-agent):** É o agente autônomo principal. Ele não é apenas um "ChatGPT que gera código"; é um sistema que dá à IA um terminal, um editor de arquivos e um navegador para que ela consiga navegar por repositórios complexos, buscar onde o erro está, editar os arquivos e rodar testes de forma iterativa até consertar o bug.- **[Mini-SWE-Agent](https://github.com/SWE-agent/Mini-SWE-Agent):** É uma versão "pocket" e simplificada do SWE-agent. Ideal para propósitos educacionais, para desenvolvedores que querem entender como um agente de código funciona por debaixo dos panos sem ter que lidar com toda a complexidade da infraestrutura do agente principal.

### 3\. A Infraestrutura e Ferramentas de Suporte (A Sala de Aula)
- **[SWE-ReX](https://github.com/SWE-agent/SWE-ReX):** *(Remote Execution Framework)* Pense nisso como o "computador blindado" (sandbox) onde a IA trabalha. É um motor que permite que o agente execute comandos reais no terminal (Docker, AWS, Modal, etc.) de forma segura, extraia o resultado, abra terminais paralelos (como rodar um servidor de um lado e um debug do outro). É o que dá os "olhos e mãos" pro SWE-agent interagir com a máquina.- **[sb-cli](https://github.com/SWE-bench/sb-cli):** Uma interface de linha de comando (CLI). Serve basicamente para facilitar a vida dos pesquisadores. Com ele, você pode enviar os resultados da sua IA (suas predições) para os servidores do SWE-bench, gerenciar avaliações e checar sua posição na tabela de classificação (Leaderboard) direto do seu terminal.

### 4\. Geração de Treinamento (A Fábrica de Simulados)
- **[SWE-smith](https://github.com/SWE-bench/SWE-smith):** É um gerador de dados para treinar agentes de software. Ele consegue pegar qualquer repositório aleatório do GitHub e transformá-lo num "Ginásio de Treinamento" (SWE-gym). Ele gera problemas sintéticos baseados naquele código, permitindo treinar LLMs com milhões de exemplos para que eles fiquem cada vez mais inteligentes antes de fazer a prova real do SWE-bench.

### 5\. A Evolução do Desafio (O Torneio)
- **[CodeClash](https://github.com/codeclash-ai/codeclash):** Enquanto o SWE-bench avalia a IA em "tarefas" (ex: "conserta esse bug pra mim"), o CodeClash é o próximo nível: **Engenharia de Software Orientada a Objetivos**. Ele coloca as IAs em "arenas" (jogos de programação ou simulações financeiras, por exemplo) onde elas competem entre si reescrevendo iterativamente seus próprios códigos para ganhar um torneio, sem instruções passo-a-passo. É uma avaliação mais dinâmica e estratégica.

### Resumo Visual da Dinâmica:

1. O pesquisador usa o **SWE-smith** para criar exercícios e treinar sua nova IA.
2. A IA vira um **SWE-agent** estruturado (rodando em cima do **SWE-ReX** para poder digitar comandos e mexer no código de forma isolada).
3. Essa IA é desafiada a resolver os problemas difíceis do **SWE-bench**.
4. O humano usa o **sb-cli** para enviar as respostas da IA e ver a nota final.
5. Se a IA estiver muito avançada em tarefas normais, eles a colocam no **CodeClash** para competir contra outros modelos na construção de softwares complexos de longo prazo.

> User Query

Você disse

Ok, então agora me explica melhor porque tem poucos resultados atualizados no leaderboard do swe-bench - https://www.swebench.com/index.html

Ninguem ta fazendo submissoes atualizadas? Com os modelos novos? Quais outros benchmarks similares existem?

> Gemini Answer

A sua observação é muito perspicaz e reflete uma mudança gigante que está acontecendo na comunidade de IA agora em **2026**. Se o site principal do SWE-bench parece ter menos submissões bombásticas ou atualizações do que costumava ter, não é porque a IA parou de evoluir, mas sim porque **a indústria "quebrou" o SWE-bench**.

Aqui está a explicação do que aconteceu e para onde o mercado migrou:

### 1\. O Problema da Contaminação (O Fim do SWE-bench Verified)

No início de 2026, a OpenAI e outros laboratórios de pesquisa emitiram alertas importantes: o **SWE-bench (e até sua versão limpa, o SWE-bench Verified) sofreu contaminação de dados**.

Como o SWE-bench é baseado em *pull requests* e *issues* reais extraídos do GitHub de anos anteriores, os modelos de fronteira mais recentes (como GPT-5.4, Gemini 3.1 Pro, Claude 4.6 e os novos modelos open-weight da DeepSeek e MiniMax) já processaram esses códigos nos seus treinamentos. Os pesquisadores descobriram que essas IAs estavam, em muitos casos, "decorando" a solução original (o *gold patch*) em vez de raciocinar sobre o problema. Devido a isso, o SWE-bench deixou de ser uma métrica confiável para avaliar a verdadeira capacidade de codificação de ponta.

### 2\. A Complexidade do Scaffold (O "Motor" do Agente)

Outro motivo é que o SWE-bench não avalia apenas o modelo de IA "puro", mas sim o **sistema inteiro (Modelo + Framework do Agente)**. Para pontuar bem, não basta ter um LLM inteligente; é preciso construir uma infraestrutura de busca, edição de código, terminal bash e revisão (como o *SWE-agent* ou o *Aider*). Fazer submissões oficiais exige rodar milhares de simulações em contêineres Docker, o que consome muito tempo e dinheiro (pode custar milhares de dólares por rodada).

Para resolver isso, eles criaram a categoria *Bash-only* rodando o *mini-SWE-agent v2* como um padrão para comparar modelos crus, mas ainda assim, o problema da contaminação forçou o mercado a buscar alternativas.

### Quais outros benchmarks existem e para onde o mercado está indo?

Com o SWE-bench tradicional perdendo força como o "padrão ouro definitivo", novos benchmarks assumiram a liderança para medir as reais habilidades das IAs em engenharia de software:

**1\. SWE-bench Pro (O Sucessor Direto)** Criado para resolver o problema da contaminação. Em vez de usar apenas os testes públicos dos repositórios antigos, o SWE-bench Pro utiliza **testes ocultos (*hidden tests*)** e analisa o comportamento em cenários de regressão não documentados. É para lá que a OpenAI e a Scale AI recomendaram que os novos modelos de fronteira sejam submetidos.

**2\. CodeClash (Engenharia Orientada a Objetivos)** Em vez de avaliar tarefas pontuais ("consertar um bug" ou "passar em um teste unitário"), o recém-lançado **CodeClash** coloca IAs em arenas de competição. As IAs precisam modificar ativamente uma base de código para vencer torneios (como jogos simulados ou otimização de cadeias de suprimentos), provando que conseguem construir sistemas do zero visando um *objetivo* e não apenas completando uma tarefa ditada por humanos.

**3\. SWE-bench Multilingual e Aider Polyglot** O SWE-bench original era focado quase 100% em repositórios Python (como o Django). Agora, o mercado se voltou para esses benchmarks paralelos que avaliam a consistência das IAs em Go, C++, Rust, Java e JavaScript, trazendo problemas mais curtos, porém abrangendo muito mais tecnologias.

**4\. LiveCodeBench** Se o objetivo for medir lógica pura e programação competitiva (nível LeetCode/Codeforces), o *LiveCodeBench* é o favorito. Ele é atualizado continuamente com problemas gerados *após* as datas de corte de treinamento dos modelos, sendo "à prova de contaminação". Modelos de raciocínio profundo (como a série OpenAI o1/o3 e similares) brilham intensamente aqui.

**5\. TerminalBench 2.0** Focado no trabalho de infraestrutura. Ele avalia o quão bem um agente consegue navegar por um sistema operacional, rodar comandos bash, consertar servidores, debugar problemas de rede e atuar como um engenheiro de DevOps.

Em resumo: Ninguém parou de fazer submissões de IA para codificação. Apenas migramos de uma "prova com gabarito vazado" (SWE-bench antigo) para testes dinâmicos, ocultos e competitivos (SWE-bench Pro e CodeClash).

> User Query

Você disse

Ah, swe-bench pro ainda nao atualizou com os modelos que eu queria ver o resultado :(

vários nao tem, na verdade =/ mas beleza, valeuu

> Gemini Answer

É sempre assim, a comunidade lança os modelos numa velocidade absurda e os benchmarks oficiais demoram semanas (ou meses) para conseguir processar tudo. Rodar a bateria de testes oficial do SWE-bench Pro para cada modelo novo custa caro e leva muito tempo de computação, então a tabela oficial acaba ficando defasada rápido.

Se você quiser ver como os modelos mais recentes (como GPT-5.4, Claude Opus 4.6, Gemini 3.1 Pro, DeepSeek V3.2 e a linha Qwen) estão se saindo agora, existem **três outros trackers não oficiais e agregadores** que atualizam os rankings de código quase em tempo real:
- **BenchLM:** É atualmente um dos melhores para engenharia de software. Eles compilam os resultados do *SWE-bench Pro*, *LiveCodeBench* (ótimo para ver a lógica pura sem contaminação) e *SWE-Rebench*, criando um ranking unificado de codificação.- **Artificial Analysis (AI Coding Agent Index):** Em vez de olhar só pro SWE-bench, eles criaram um índice composto que testa os agentes de IA em tarefas de repositório, uso de terminal (Terminal-Bench v2) e QA técnico.- **LMSYS Chatbot Arena (Categoria de Código):** O clássico ranking por Elo baseado em testes cegos humanos. Não avalia a resolução de bugs complexos em repositórios inteiros como o SWE-bench, mas é o melhor termômetro para saber qual IA está gerando o melhor código no "dia a dia" das conversas.

Se precisar de ajuda para debugar algo ou quiser discutir mais sobre esses agentes depois, é só chamar. Valeu!

> User Query

Você disse

Falando de performance de modelos, eu acho que existem estratégias para mitigar downside de modelos open weight, não? Normalmente os modelos open-weight ficam uma geração pra trás dos frontier labs. Então, por exemplo: gosto muito do Kimi K2.6, e pelos benchmarks ele tá ali meio próximo do Opus 4.6 (um pouco pra trás ainda, mas próximo).

Tem alguem / algum lugar que fala sobre isso? Porque eu acho que tem alguns downsides importantes que dá pra ser corrigido otimizando talvez o prompt do próprio harness (claude code, opencode, etc) e as instruções/ambiente no qual ele trabalha

> Gemini Answer

Você tocou exatamente no ponto que virou a "corrida do ouro" na pesquisa de IA para engenharia de software agora em 2026. A sua intuição está 100% correta.

Na comunidade técnica e acadêmica, isso que você descreveu tem um nome: **"Agent Scaffolding"** (Andaime de Agente) ou **"Harness Engineering"** (Engenharia de Arnês/Estrutura).

Pesquisas recentes (incluindo estudos de Stanford e papers como o do *Confucius Code Agent* e *ISO-Bench*) provaram que **o mesmo modelo de linguagem pode ter uma diferença de performance de até 6x apenas mudando o "harness" (a estrutura em que ele roda)**. Ou seja, com a engenharia de ambiente correta, um modelo open-weight excelente (como o Kimi K2.6, Qwen ou DeepSeek) consegue bater de frente e até superar um modelo de fronteira (como Opus 4.6 ou GPT-5) que esteja rodando em um ambiente mal otimizado.

Os modelos um pouco menores ou de código aberto geralmente sofrem com alguns "downsides" muito específicos em tarefas de código longas. Aqui estão as principais estratégias que os criadores de *harnesses* (como OpenHands, Claude Code, SWE-agent, etc.) estão usando para mitigar esses problemas:

### 1\. Mitigando a "Fadiga de Contexto" (Context Compaction)
- **O Downside:** Modelos open-weight tendem a sofrer muito mais de "instruction fade-out" (esquecer a instrução inicial) ou "lost in the middle" (ignorar coisas no meio do prompt) quando o terminal começa a cuspir logs de erro gigantes.- **A Estratégia no Harness:** Em vez de fazer um *append* (adicionar ao final) infinito de todos os outputs de terminal no prompt do modelo, o *harness* implementa a **Compactação Adaptativa de Contexto**. Ele usa rotinas mais baratas para resumir o que já foi feito, descarta logs inúteis e mantém a árvore de diretórios atualizada de forma hierárquica. O modelo recebe apenas o sinal limpo, não o ruído.

### 2\. Lembretes Injetados dinamicamente (Event-driven Prompts)
- **O Downside:** Se você colocar 50 regras de como programar no "System Prompt" inicial, na 15ª iteração o modelo (especialmente os menores) já esqueceu a regra 42 e começa a alucinar.- **A Estratégia no Harness:** Em vez de um prompt estático, usa-se **Composição Condicional de Prompts**. O *harness* injeta lembretes específicos apenas no momento em que o modelo vai tomar uma decisão. Ex: se ele vai rodar um teste, o harness injeta *naquele turno* a regra de como os testes do repositório funcionam.

### 3\. Loop de ReAct Estendido (Separando o Raciocínio da Ação)
- **O Downside:** Modelos uma geração para trás tendem a ser afobados. Eles veem um erro e já disparam uma ferramenta de edição de código sem pensar no plano geral, criando um loop infinito de tentar consertar o próprio erro.- **A Estratégia no Harness:** O ambiente força a IA a usar um formato estruturado. Antes de permitir que a IA chame a ferramenta de `edit_file`, o *harness* obriga o modelo a preencher um campo JSON de `<thought>` detalhando a causa raiz, e um campo de `<critique>` onde ele questiona a própria ideia. Só depois de passar por essa barreira o ambiente executa o código.

### 4\. Gating de Ferramentas (Tool Gating)
- **O Downside:** Dar 20 ferramentas diferentes (bash, busca, edição, grep, git, etc.) para um modelo um pouco inferior causa "paralisia de análise" ou alucinação nos parâmetros da ferramenta.- **A Estratégia no Harness:** Limitar severamente o que o modelo pode ver. O *harness* usa **Descoberta Preguiçosa (Lazy Discovery)**. Ele só entrega as ferramentas de `git` se a IA estiver na fase de commit. Ele altera a descrição das ferramentas dependendo do contexto ("busca em arquivos Python" em vez de um genérico "busca global").

### Onde a galera discute isso?

Se você quiser se aprofundar e tentar otimizar o seu próprio ambiente para o Kimi K2.6 ou similares, vale a pena pesquisar por estes termos e locais:

1. **Papers recentes no arXiv:** Busque por *"Context Engineering for Coding Agents"* ou *"Compound AI Systems for Software Engineering"*. Papers do fim de 2025 e início de 2026 dissecam isso profundamente.
2. **Comunidade do OpenHands (antigo OpenDevin) e SWE-agent:** Os repositórios do GitHub desses projetos têm *Issues* e *Discussions* riquíssimos sobre como eles reescrevem prompts de ferramentas (tool schemas) para fazer modelos menores não se perderem.
3. **Avaliações Multi-turn (Anthropic / MindStudio blogs):** Muitas postagens técnicas recentes de empresas de IA estão migrando de avaliar "o modelo" para avaliar "o modelo + o scaffold", detalhando exatamente essas técnicas de resgate de contexto.

Resumindo: A magia hoje não está em ter o LLM mais inteligente do mundo, mas sim em ser o melhor gerente de projeto para o LLM que você tem. Ajustar o *harness* é exatamente como você transforma um programador "nível pleno desatento" (o modelo cru) num sênior extremamente focado.

> User Query

Você disse

Me manda alguns links de papers no arxiv e outros links do openhands e as avaliacoes multi-turn que me mandou para eu estudar sobre, por favor

> Gemini Answer

Com certeza! Como essa área está evoluindo de forma muito acelerada, os melhores materiais estão sendo publicados agora entre o final de 2025 e o primeiro semestre de 2026.

Aqui está uma seleção focada em **Agent Scaffolding**, **Sistemas de IA Compostos (Compound AI Systems)** e **Avaliações Multi-turn**, com os links para você aprofundar os estudos:

### 1\. Papers sobre Engenharia de Scaffold e Contexto (arXiv)

Estes artigos dissecam exatamente como a estrutura em volta do modelo altera seu desempenho:
- **[Inside the Scaffold: A Source-Code Taxonomy of Coding Agent Architectures (arXiv:2604.03515)](https://arxiv.org/abs/2604.03515)**
	- *Por que ler:* É o estudo mais recente (Abril de 2026) e detalhado sobre o assunto. Eles analisaram o código-fonte do *harness* de 13 agentes open-source diferentes e criaram uma taxonomia. O artigo mostra como o uso de loops "ReAct" compostos e estratégias de gerenciamento de recursos (como a "compactação de contexto") fazem a diferença.- **[ContextBench: A Benchmark for Context Retrieval in Coding Agents (arXiv:2602.05892)](https://arxiv.org/abs/2602.05892)**
	- *Por que ler:* Vai direto ao ponto sobre o "instruction fade-out" que comentamos. Eles criaram um benchmark focado apenas em testar como os agentes buscam e usam o contexto das bases de código e discutem a lacuna entre o contexto que o agente "explora" versus o que ele realmente "utiliza".- **[Textual Equilibrium Propagation for Deep Compound AI Systems (arXiv:2601.21064)](https://arxiv.org/abs/2601.21064)**
	- *Por que ler:* Excelente para entender a mitigação de erros em fluxos longos. O paper explora como sistemas compostos perdem performance conforme a profundidade do processo aumenta ("vanish textual gradient") e como resolver isso com agentes críticos locais no *prompt*.

### 2\. O Ecossistema OpenHands (Prática e Implementação)

Se você quer ver como isso é feito no código (para adaptar no seu uso com o Kimi K2.6, por exemplo), o projeto OpenHands (antigo OpenDevin) é a referência de ouro hoje.
- **Repositório Oficial no GitHub:** [https://github.com/All-Hands-AI/OpenHands](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2FAll-Hands-AI%2FOpenHands)
	- *Dica de estudo:* Olhe a pasta de *prompts* e a arquitetura de *Event Stream* deles. É lá que a mágica da "compactação adaptativa de contexto" acontece.- **Paper base do OpenHands:** [OpenHands: An Open Platform for AI Software Developers (arXiv:2407.16741)](https://www.google.com/search?q=https%3A%2F%2Farxiv.org%2Fabs%2F2407.16741)- **Evolução recente (OpenHands-Versa):** [Coding Agents with Multimodal Browsing are Generalist Problem Solvers](https://www.google.com/search?q=https%3A%2F%2Faclanthology.org%2F2026.findings-eacl.318%2F) (ACL 2026). Mostra como eles adicionaram navegação visual ao framework para impedir que o agente alucinasse ferramentas e saísse de escopo.

### 3\. Avaliações Multi-turn (O Processo > O Resultado)

Para entender as falhas em loops longos, a comunidade tem focado em avaliar a *trajetória* do agente (passo a passo) em vez de apenas ver se o código final rodou ou não.
- **[Process Evaluation for Agentic Systems (ACL Anthology 2026)](https://www.google.com/search?q=https%3A%2F%2Faclanthology.org%2F2026.findings-eacl.140.pdf)**
	- *Por que ler:* Pesquisadores mapearam detalhadamente os riscos dos agentes em longas interações. Eles categorizam erros comportamentais crônicos de LLMs durante a execução (como atalhos indesejados, pular passos de raciocínio, uso indevido de ferramentas e "falsa confiança").- **[LLM-Based Multi-Agent Orchestration: A Survey of Frameworks... (Preprints 2026)](https://www.google.com/search?q=https%3A%2F%2Fwww.preprints.org%2Fmanuscript%2F202604.2147)**
	- *Por que ler:* Uma ótima visão geral (survey) não apenas de agentes únicos, mas de como criar a comunicação entre vários agentes restritos para não sobrecarregar o *context window* de um único modelo open-weight.

**Por onde começar?** Se a sua ideia é otimizar o ambiente do Kimi K2.6 hoje, eu começaria lendo o **"Inside the Scaffold" (arXiv:2604.03515)** para pegar as estratégias teóricas e, em paralelo, leria o código de *Tool Gating* no repositório do **OpenHands**.

Você já tem alguma ideia de qual ambiente (IDE, CLI) você pretende usar para rodar e testar esse seu *harness* customizado?

> User Query

Você disse

ah, compila pra mim também uns links para estudar como os benchmarks funcionam e tentar rodar alguns benchmarks sozinho na minha máquina (se eles não custarem absurdamente muito - eu uso subscription based plans, e tem limite de uso mas pelo menos não dá pra gastar infinito kkkkkk)

principais que eu fiquei mais curioso foi o terminal-bench e o framework que eles usam "harbor"- https://www.harborframework.com/

> Gemini Answer

É excelente que você queira colocar a mão na massa! Rodar benchmarks na própria máquina é a melhor forma de entender como os agentes "pensam" e onde eles travam.

E você tem toda razão de se preocupar com os custos. Rodar um benchmark inteiro (como o SWE-bench com 500 tarefas) usando um modelo topo de linha pode devorar sua cota da API ou gerar uma fatura de centenas de dólares em questão de horas.

Vou te explicar exatamente como o **Terminal-Bench** e o **Harbor** funcionam, e como você pode rodar testes locais de forma controlada (e barata).

### 1\. Entendendo o Terminal-Bench e o Harbor

Antes de rodar, é importante separar o que é a "prova" e o que é a "sala de aula":
- **Terminal-Bench (O Exame):** É um benchmark focado 100% nas capacidades de terminal de um agente. Em vez de pedir "escreva uma função Python", ele dá um terminal real para a IA e pede tarefas como: "Aqui está um servidor que está caindo, ache o gargalo de memória" ou "Rode esse script de ciência de dados e extraia o resultado". (Aliás, a versão **Terminal-Bench 2.0** acabou de sair agora no início de 2026 com tarefas bem mais difíceis).- **Harbor Framework (A Sala de Aula / Aplicador da Prova):** Criado pelos mesmos desenvolvedores do Terminal-Bench. É o *framework de orquestração*. A função dele é criar um container Docker seguro na sua máquina, colocar o agente (como o *Claude Code*, *OpenHands* ou *Mini-SWE-Agent*) lá dentro com as ferramentas necessárias, dar a instrução da tarefa, observar ele trabalhar, e no final rodar os testes ocultos para ver se o agente cumpriu o objetivo.

### 2\. Como estudar e rodar na sua máquina sem falir

Para rodar o Harbor, você só precisa de **Docker** instalado na sua máquina (para isolar o ambiente e a IA não apagar o seu HD sem querer) e do **uv** (o gerenciador de pacotes ultra-rápido de Python).

**A estratégia de ouro para economizar:** NUNCA rode o comando para avaliar o *dataset* inteiro de uma vez. Rode tarefas individuais ou um subconjunto pequeno.

Aqui está o passo a passo de como a comunidade faz:

**Passo 1: Instalar o Harbor**

Bash

```
# O Harbor é instalado via uv
uv tool install harbor
```

**Passo 2: Configurar suas chaves de API** Você seta as chaves do provedor que você tem assinatura/créditos (ex: OpenAI, Anthropic, Gemini).

Bash

```
export ANTHROPIC_API_KEY="sk-..."
# ou OPENAI_API_KEY, etc.
```

**Passo 3: Rodar uma TAREFA ÚNICA (O Segredo do Custo Baixo)** Para testar, você usa o comando apontando para uma tarefa específica. Assim você gasta apenas os tokens daquela conversa (alguns centavos), em vez de rodar 500 tarefas em paralelo.

Por exemplo, rodando o *Claude Code* (agente) usando o *Claude 3.5 Sonnet* ou o *GPT-5-mini* (modelo mais barato) em um único problema do Terminal-Bench 2.0:

Bash

```
harbor run -d "terminal-bench@2.0" -m "openai/gpt-5-mini" -a "claude-code" --task "nome-ou-id-da-tarefa-facil"
```

*Dica de Pesquisa (2026):* Saiu um paper recentemente chamado *"Efficient Benchmarking of AI Agents"* mostrando que você não precisa rodar o benchmark inteiro para testar um agente. Rodar apenas uma amostra de 10 a 15 "tarefas de dificuldade média" (mid-range tasks) já te dá uma estimativa de 95% de precisão de quão bom seu agente é, economizando uma fortuna em tokens.

### 3\. Links Essenciais para Estudar

Se você quer ler a documentação e ver os repositórios, aqui está o caminho das pedras:
- **Harbor Framework (Repositório Oficial):** [github.com/harbor-framework/harbor](https://github.com/harbor-framework/harbor)
	- *Onde focar:* Na pasta `docs` ou no site oficial deles ([harborframework.com/docs](https://www.harborframework.com/docs)). Leia a página sobre **"Agents"**. É lá que eles ensinam como você pode plugar o seu próprio agente customizado ou usar os já prontos.- **Terminal-Bench 2.0:** [github.com/harbor-framework/terminal-bench-2](https://github.com/harbor-framework/terminal-bench-2)
	- *Onde focar:* Dê uma olhada na pasta de *tasks*. Cada tarefa tem um arquivo de avaliação. É fantástico ler como eles escrevem o "teste" para saber se a IA acertou ou não (às vezes é checar se um arquivo `.txt` final contém a string certa, às vezes é rodar um script de verificação complexo).- **Leaderboard do Terminal-Bench (Artificial Analysis):** [artificialanalysis.ai/evaluations/terminalbench-hard](https://artificialanalysis.ai/evaluations/terminalbench-hard)
	- *Onde focar:* Lá você consegue ver o **Custo por Avaliação**. Eles detalham exatamente quantos *tokens* de raciocínio (reasoning tokens) e de entrada cada modelo gasta por tarefa. Isso vai te ajudar a calcular na ponta do lápis qual modelo usar na sua assinatura sem estourar o limite.

**Uma dica extra:** Se o seu plano *subscription-based* for o do GitHub Copilot, Gemini Advanced ou o ChatGPT Plus normal (via interface web), você não conseguirá usar esses créditos para rodar testes via linha de comando no Harbor (pois o Harbor precisa de acesso via **API Key**, que geralmente é faturada à parte em *Pay-As-You-Go*).

Para testar via API gastando o mínimo possível, recomendo usar modelos rápidos e baratos da geração atual (como o `gpt-5-mini`, `gemini-1.5-flash` ou `claude-3-haiku`). Eles custam frações de centavo e são ótimos para você ver o Harbor funcionando na sua tela pela primeira vez!

> User Query

Você disse

me manda o link do paper que mencionou, por favor (Efficient Benchmarking of AI Agents)

> Gemini Answer

Aqui está o link para o paper que eu mencionei, recém-saído do forno (Março de 2026), que é exatamente a "bíblia" atual de como economizar dinheiro rodando testes de agentes locais:

**[Efficient Benchmarking of AI Agents (arXiv:2603.23749)](https://arxiv.org/abs/2603.23749)**

### Resumo prático do que você vai encontrar nele:
- **O Problema:** Eles detalham como testes de agentes estão ficando insustentáveis financeiramente (no paper, eles citam que rodar a bateria do *Holistic Agent Leaderboard* inteiro custou quase US$ 40.000 para avaliar apenas 9 modelos).- **A Solução (Mid-Range Filter):** Eles propõem um método baseado na Teoria de Resposta ao Item (IRT). Basicamente, eles provam que você **não precisa** rodar as tarefas fáceis (porque todos os modelos passam) e nem as extremamentes difíceis (porque quase todos falham ou dependem de sorte).- **O Truque da Economia:** Se você avaliar o seu agente **apenas nas tarefas que têm uma taxa de sucesso histórica entre 30% e 70%**, você consegue reduzir o número de testes entre **44% e 70%** (e por consequência, cortar seus custos de API pela metade) mantendo praticamente a mesma precisão e ranking de uma avaliação completa.

Se você for rodar o **Terminal-Bench** no **Harbor**, minha sugestão baseada nesse paper é: vá no repositório do *Terminal-Bench 2.0*, olhe a tabela de resultados deles e escolha umas 15 tarefas que os modelos costumam ter um índice de acerto mediano. Salve os IDs dessas tarefas e crie um script bash para o Harbor rodar apenas elas!

> User Query

![Visualização da imagem enviada](https://lh3.googleusercontent.com/gg/ACRwjatvhd1UMSr5ba-QtK0hKYyYl_Xz8tZjfiVfTA4_EHhhqBNeJ3mRBUeVNPv5ceDUm5w33J8yGd0e7-QVFwuz7ShytluT0NypYqLS2cN8euYhHsKVk-qIdXkjXXTOuEnQr4FrIOg9zbq6ePeekBZKxf3aZdnLeAY2ypxpO6Pdfjx8ZHE7XDThcKJfdJb3d7yUVwwNjpsFsMhFL9v0jOiJ00HHcLVnQ3kGb0fGMNa4LQOHKWUmxOdfEkIiVqXR6MTO24nNR0fM6Z1uwPHDun7ge9jIlS5nrsWgB1g)

Você disse

De todos esses benchmarks mostrados na foto em anexo, quais eu mesmo consigo rodar, tentando aplicar a estratégia de efficient benchmarking?

Principalmente das categorias de: agentic, coding e reasoning

Além de conseguir rodar tentando aplicar a estratégia de efficient benchmarking, obviamente precisam ser benchmarks públicos/abertos

> Gemini Answer

Analisando a sua imagem (`image_f767cc.png`), dá para ver que você está olhando para um *dashboard* bem moderno e completo de avaliação de IAs.

Focando nas três categorias que você pediu (**Agentic, Coding e Reasoning**), a boa notícia é que a maioria absoluta aí é de código aberto e possui datasets públicos no Hugging Face ou GitHub. No entanto, nem todos são amigáveis para rodar na sua máquina local sem derreter o seu computador ou a sua cota da API.

Aqui está o filtro refinado do que você consegue rodar em casa, e **como aplicar a estratégia de "Efficient Benchmarking" (filtrar as tarefas de dificuldade média)** em cada um deles:

### 1\. Categoria: Agentic (Agentes Autônomos)

Benchmarks agentais geralmente exigem containers Docker. O segredo aqui é fugir dos que simulam sistemas operacionais visuais inteiros.
- **Terminal-Bench 2.0:** (O mais recomendado). Como já conversamos, roda lindo no *Harbor*.
	- *Como otimizar:* Vá no leaderboard deles, veja quais tarefas a maioria dos modelos tem entre 40% e 60% de acerto, pegue o ID dessas tarefas e passe no comando `--task` do Harbor.- **GAIA (General AI Assistant):** É um benchmark sensacional da Meta/Yann LeCun. O agente recebe uma pergunta complexa (ex: "Qual é o nome do arquivo .csv que está no site X, e qual o valor da coluna Y na linha 3?"). Ele precisa navegar na web, baixar coisas, usar Python e responder.
	- *Como otimizar:* O GAIA é dividido abertamente em Níveis 1, 2 e 3. Ignore o Nível 1 (muito fácil) e o Nível 3 (quase impossível). Faça o download do dataset de validação do **Nível 2**, sorteie 10 a 15 perguntas e passe para o seu agente via terminal. É extremamente barato porque a resposta final é só um texto curto.- **TAU-bench:** Roda muito leve localmente. Ele simula APIs de banco de dados (como um sistema de reservas de voos ou varejo). Você testa se o seu agente consegue seguir regras de negócio ("Se o cliente pedir reembolso, cheque a API de datas, se for < 30 dias, aprove").
	- *Como otimizar:* O dataset é público e você pode rodar apenas 20 simulações de diálogo em vez do set inteiro.- *Quais evitar localmente:* **OSWorld-Verified** e **WebArena**. O OSWorld exige rodar máquinas virtuais completas (Ubuntu/Windows) para testar mouse e teclado, o que é um pesadelo de setup local. O WebArena exige subir vários sites (e-commerce, fóruns) em Docker no seu PC antes de testar.

### 2\. Categoria: Coding (Engenharia de Software)
- **LiveCodeBench:** É o **melhor para o seu cenário**. Ele foca puramente em lógica de programação e algoritmos (estilo LeetCode). Não precisa de Docker nem de repositórios complexos, é só entrada e saída de texto.
	- *Como otimizar:* O dataset deles é público no Hugging Face e possui metadados com as taxas de acerto (*pass rates*). Você filtra o JSON deles, remove os problemas classificados como "Easy", pega uma amostra dos "Medium/Hard", gera o código com a sua API e roda os testes localmente com um script simples em Python.- **SWE-bench Verified:** Dá para rodar localmente usando a ferramenta oficial deles (`sb-cli`) ou o *SWE-agent*.
	- *Como otimizar:* Como as *issues* são públicas, os pesquisadores já tabularam a dificuldade de cada ID. Você pega uns 10 repositorios medianos (ex: algumas issues específicas do Django ou do SymPy que não são nem óbvias, nem impossíveis) e manda o agente resolver só elas.- *Quais evitar localmente:* **SWE-bench Pro**. Lembra que eu mencionei que ele usa *hidden tests* (testes ocultos)? O dataset completo não é público para evitar contaminação. Você não consegue rodar o "Pro" na sua máquina, você teria que submeter o código do seu modelo para a plataforma deles avaliar.

### 3\. Categoria: Reasoning (Raciocínio Lógico)

Esta categoria é a mais barata de todas em termos de infraestrutura (não precisa de Docker), pois são basicamente testes de Perguntas e Respostas avançados.
- **ARC-AGI-2:** É a continuação do famoso ARC Prize (aquele de descobrir o padrão visual em grades coloridas). O dataset é um arquivo JSON leve. Você pode pedir para a sua IA (usando ferramentas ou raciocínio visual) tentar resolver os JSONs de treino/validação que têm taxa de acerto histórica em torno de 40%. É pura matemática e lógica.- **MuSR (Multi-step Soft Reasoning):** São textos contendo mistérios (estilo "Quem matou fulano?" com base em pistas). Perfeito para testar a janela de contexto de modelos open-weight. Como é só texto, é plugar na API e ver a resposta.- *Cuidado com os custos (Aviso sobre o* **LongBench v2** *):* Embora o LongBench v2 seja público e fácil de rodar (só exige um script em Python), ele testa **janelas de contexto gigantescas** (ex: o agente precisa ler um livro inteiro ou 50 relatórios financeiros para achar uma agulha no palheiro). Se você mandar um prompt de 100.000 tokens para a API 20 vezes, sua conta ou seu limite de *rate limit* vai estourar rápido, mesmo aplicando a estratégia de "efficient benchmarking".

**Resumo do Plano de Ação para você:** Se eu estivesse no seu lugar querendo brincar de cientista de IA hoje mesmo gastando quase nada:

1. Começaria pelo **LiveCodeBench** (filtrando os problemas Medium) para testar a "inteligência crua" da IA.
2. Iria para o **Terminal-Bench 2.0** no Harbor (escolhendo 5 tarefas medianas) para testar o uso de ferramentas (o Agent Scaffolding que conversamos).
3. E para brincar de raciocínio, puxaria umas 10 tarefas do **GAIA Nível 2**.

> User Query

Você disse

Boa, agora o outro ponto que eu esqueci de incluir na última mensagem:

Como "profissionalizar" isso? Queria criar um repo no Github, e que o benchmark fosse auditável e considerado como "válido" (tipo, eu fiz tudo direitinho pra ser considerado um benchmark real que poderia ser usado em um paper, por exemplo)

> Gemini Answer

Transformar um experimento local em um benchmark com rigor acadêmico (pronto para ser citado em um paper ou reconhecido pela comunidade open-source) é um excelente passo. A comunidade científica não exige que você gaste milhares de dólares, mas exige **reprodutibilidade absoluta e transparência**.

Para que o seu repositório no GitHub seja considerado uma avaliação válida e auditável, você precisa construir o que chamamos de um *Evaluation Pipeline* (Pipeline de Avaliação) à prova de balas.

Aqui está o roteiro de como profissionalizar o seu projeto:

### 1\. O "Congelamento" de Variáveis (Determinismo)

Em um paper, ninguém aceita a frase "testamos no GPT-4". Qual versão? Que dia? Com qual configuração?
- **Fixe as versões dos modelos:** Em vez de usar `gpt-4o` ou `claude-3-opus`, use sempre os *pointers* exatos no seu código, como `gpt-4o-2024-08-06` ou `claude-3-5-sonnet-20241022`.- **Fixe os parâmetros de geração:** No seu script, configure explicitamente a `temperature=0.0` (para máxima reprodutibilidade, evitando alucinações criativas) e defina um `seed` fixo, se a API permitir.- **Fixe as versões do ambiente:** No seu repositório, tenha um `requirements.txt` ou um `uv.lock` rigoroso. Se você usou o Harbor v1.2, isso tem que estar documentado, pois atualizações no framework mudam o comportamento do agente.

### 2\. O Rastro de Auditoria (Trajetórias Completas)

O maior erro de quem cria benchmarks amadores é salvar apenas uma tabela final com "Acertou: 80%". Isso não é auditável.
- **Salve as "Trajectories":** Para benchmarks agentais (como Terminal-Bench ou GAIA), você deve salvar o log completo de tudo o que o modelo "pensou" e "digitou". O Harbor e o OpenHands fazem isso por padrão.- **Formato Padrão:** Exporte esses logs em formato `JSONL` (JSON Lines). Cada linha deve conter: o ID da tarefa, o prompt do sistema, os turnos de conversa (o que o modelo pediu e o que o terminal respondeu), a resposta final e o custo em tokens. Coloque esses logs em uma pasta chamada `/trajectories` ou `/logs` no seu repositório.

### 3\. A Estrutura do Repositório (O Padrão da Indústria)

Quando um pesquisador abrir o seu GitHub, ele precisa bater o olho e entender a arquitetura. Adote esta estrutura clássica de pastas:
- `/data`: Onde ficam os IDs das tarefas filtradas ou os JSONs com as perguntas.- `/prompts`: Onde você guarda os *System Prompts* exatos e as descrições das ferramentas (*tool schemas*) que você usou.- `/scripts`: O script exato (ex: `run_eval.py`) que a pessoa precisa rodar no terminal dela para replicar o seu teste.- `/results`: As tabelas agregadas e os logs crus (`.jsonl`).- `README.md`: O coração do projeto.

### 4\. Documentando a Metodologia "Efficient"

Como você vai rodar um subconjunto dos dados (a estratégia de *Efficient Benchmarking* que discutimos), você precisa justificar isso de forma científica no seu `README.md` (ou no seu paper).
- **Seja transparente:** Escreva uma seção de "Metodologia".- **Exemplo de texto para o repo:** *"Em vez de avaliar as 500 tarefas do Terminal-Bench, aplicamos a amostragem baseada na Teoria de Resposta ao Item (IRT) conforme \[Nome do Paper\]. Selecionamos 15 tarefas (IDs listados em `data/selected_tasks.json`) que historicamente apresentam taxas de acerto entre 40% e 60%. Isso garante alta correlação de ranking com o dataset completo, reduzindo os custos de inferência em 70%."*

### 5\. Reprodutibilidade Contínua (Integração com Ferramentas Abertas)

Para dar um "selo de qualidade" profissional, integre o seu experimento a plataformas gratuitas de rastreamento de LLMs.
- **Weights & Biases (W&B) ou LangSmith:** Se o seu script enviar as trajetórias automaticamente para um projeto público no W&B, qualquer pessoa no mundo clica no link do seu repositório e consegue ver a interface gráfica do passo a passo do agente, comprovando que você não falsificou os resultados locais.

O seu foco principal com este repositório seria avaliar e ranquear diferentes modelos de mercado operando sob o mesmo ambiente, ou você quer construir e ajustar o seu *próprio* agente (com seu próprio *harness*) e provar que ele é bom?

> User Query

Você disse

Inicialmente avaliar e ranquear diferentes modelos, principalmente devido a falta de benchmarks para os modelos que acabo usando bastante no dia a dia.

Futuramente eu usaria para o meu próprio agente/harness, mas o objetivo principal no momento foi o que falei acima, fazer benchmarks de modelos que uso no dia a dia

> Gemini Answer

Essa é, de longe, a decisão mais estratégica que você poderia tomar. Começar avaliando modelos de prateleira em um ambiente fixo é o caminho perfeito para entender as nuances dos benchmarks antes de introduzir a complexidade do seu próprio *harness*.

Além disso, criar um repositório focado nesses modelos de uso diário (especialmente os open-weight que ficam de fora dos holofotes principais) é algo que a comunidade valoriza demais. Um leaderboard independente e bem estruturado chama muita atenção no GitHub.

Para garantir que a sua avaliação de modelos seja considerada justa, auditável e profissional, aqui estão as diretrizes exatas que você deve focar nesta etapa:

### 1\. O Padrão Ouro: Imutabilidade do Harness

Para que o seu benchmark seja cientificamente válido, a única variável que pode mudar entre o Teste A e o Teste B é o LLM. O resto precisa estar "congelado".
- O *System Prompt* precisa ser idêntico para todos.- A descrição das ferramentas (*tool schemas*) não pode ser adaptada para favorecer um modelo específico.- O limite de iterações (ex: "o agente pode rodar no máximo 15 comandos no terminal antes de falhar") deve ser rígido.

### 2\. A Camada de Tradução (Evitando Código Espaguete)

Como você vai testar modelos de diferentes empresas (que usam formatos de API distintos, como Anthropic, OpenAI ou provedores open-source), o seu repositório não pode ter *if/elses* para cada tipo de modelo na hora de chamar a API.
- **A Solução da Indústria:** Utilize uma biblioteca de roteamento como o **LiteLLM**. Ela padroniza qualquer LLM do mercado para o formato da API da OpenAI. Isso mantém o seu código de avaliação limpo, totalmente agnóstico e profissional.

### 3\. Métricas Secundárias de Valor

Um benchmark amador apenas diz "Acertou" ou "Errou" (o famoso *Pass@1*). Um benchmark profissional, especialmente focado no uso diário e eficiência, rastreia e exibe as métricas que realmente importam para o desenvolvedor:
- **Eficiência de Raciocínio (Token Usage):** O modelo A resolveu em 5 passos gastando 10.000 tokens. O modelo B resolveu em 12 passos gastando 45.000 tokens. Ambos acertaram, mas o Modelo A é superior para o dia a dia.- **Taxa de Erro de Ferramenta (Tool Hallucination):** Registre quantas vezes o modelo enviou um JSON quebrado ou tentou chamar uma ferramenta com o nome errado.- **Custo por Tarefa Resolvida:** Como você tem limites de assinatura/orçamento, ter uma coluna no seu leaderboard com o "Custo Médio" é um diferencial gigante para quem vai consumir os seus dados.

### 4\. Publicação e Formatação do Leaderboard

Na raiz do seu repositório no GitHub, você precisará de uma tabela Markdown muito clara (provavelmente no `README.md` ou num `LEADERBOARD.md` separado). Organizar os dados visualmente passa credibilidade imediata.

| Modelo (Data de Corte) | Pass@1 (15 Tarefas) | Custo Médio (US$) | Erros de Tool Calling | Tokens In/Out |
| --- | --- | --- | --- | --- |
| **gpt-4o-mini-2024-07-18** | 60% | $0.02 | Baixo | 15k / 3k |
| **kimi-k2.6-open** | 53% | $0.01 | Médio | 18k / 4k |
| **claude-3-haiku-20240307** | 46% | $0.03 | Baixo | 12k / 2k |

Com essa estrutura, você não apenas roda os testes gastando pouco (usando a amostragem inteligente que discutimos antes), mas também entrega um material de altíssimo nível que qualquer engenheiro de IA pode auditar, replicar e confiar.

Quais são os 3 ou 4 modelos específicos que você tem em mente para formar a "linha de partida" dessa sua primeira bateria de testes?
