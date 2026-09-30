# VISION — SuperAgent

> Por que este sistema existe, o que ele é de verdade e até onde pode ir.
> Documento vivo — se a estratégia mudar, este arquivo muda primeiro.

---

## 1. Teoria: em que espaço das LLMs isso se situa

LLM pura é um preditor de tokens: sem memória, sem planejamento, com alucinação
estatística. O SuperAgent materializa a **malha agêntica** consolidada na
literatura (ReAct → Plan-and-Execute → LLM-as-Judge):

```
Perceber → Planejar → Agir (ferramenta) → Observar → Verificar → Replanejar
```

| Corrente teórica | Como o SuperAgent aplica |
|---|---|
| **Plan-and-Execute** (planejar ≠ executar) | Planner gera plano JSON estruturado; executor nunca decide o roteiro |
| **LLM-as-Judge / Reflexion** | Critic avalia cada step (APPROVE/REJECT) antes de avançar |
| **Tool use** | Ferramentas explícitas via allowlist; o modelo nunca "toca" o sistema |
| **Capability-based security** | Poder do agente = menor conjunto possível: poucas ferramentas, limites duros em código |
| **Bounded autonomy** | Supervisor com steps/replans/tempo/profundidade — o loop não pode divergir infinitamente |

**Princípio central:** separar o que o LLM decide (conteúdo) do que o código
decide (confinamento, limites, política). O modelo sugere; Python autoriza.
System prompt pode ser burlado por injeção — `if/else` não.

## 2. Finalidade: o problema real que resolve

O SuperAgent ocupa o espaço entre dois extremos do mercado:

```
Chatbot (não executa) ──── SuperAgent ──── Agente nu (executa qualquer coisa)
   seguro, inútil             │              poderoso, perigoso
                              │
              executar tarefas estruturadas em máquina local,
              auditável, com custo de LLM = zero e dados que
              nunca saem do servidor
```

**Casos de uso alvo:** automatizar tarefas repetíveis de escritório/dev
(gerar arquivos, resumir documentos, escrever e validar código) onde **dados
não podem sair da máquina** — LGPD, compliance, propriedade intelectual,
ambiente air-gapped, orçamento sem API cloud.

## 3. Diferenciais — com honestidade sobre o que NÃO é

A arquitetura em si (planner/executor/critic) **não é inédita** — LangGraph,
CrewAI e AutoGen fazem igual ou mais. O diferencial está na **escolha de
projeto**, não no padrão de topo:

1. **Segurança independente de prompt** — política e limites vivem em
   `core/supervisor.py` e `core/policy.py`, não no system prompt. Um agente
   comprometido por prompt injection continua travado em N steps / M replans /
   workspace confinado.
2. **Escrita transacional com rollback** (`FilesystemTool.write_many`) — raro
   em frameworks agênticos; quase todos deixam o workspace meio-escrito.
3. **Auditoria em ~2500 linhas** — sem LangChain: só requests + pydantic +
   yaml + dotenv. Dá para ler tudo numa sentada. `audit.sh` + testes de
   regressão de segurança (travessia, prefixo, symlink) são first-class.
4. **Custo marginal zero** — Ollama local: sem token billing, sem telemetria,
   funciona offline.
5. **Rejeição deliberada de poder** — web/sandbox só existem se ativados
   explicitamente e com isolamento. Enquanto o mercado corre para "agente que
   faz tudo", a tese aqui é "agente que faz o suficiente, de forma verificável".
6. **Decision layer com confidence ≠ autorização** (`core/decisions.py`) —
   o Critic delega a um motor de decisão pluggable (LLM, regras offline ou
   endpoint tipado no padrão Jev/Laya), mas `confidence < limiar` vira
   `ESCALATE` e **para o run**: a probabilidade nunca autoriza efeito
   colateral sozinha. AutORIZação continua 100% no Supervisor/Policy.
   É a metade que os decision layers puros não vendem — um runtime confinado
   onde decidir é seguro.

**Posicionamento:**
> Não é o agente mais poderoso — é o único que você audita em uma tarde
> antes de dar acesso ao seu servidor.
> *Jev decide. SuperAgent autoriza. O LLM explica.*

**Janela de nicho:** enquanto os grandes otimizam *capability*, o gargalo
crescente em produção é **confiança e conformidade** (LGPD, EU AI Act,
ISO 42001). Existe demanda por "agente certificável".

## 4. Prospecção de crescimento

### Roadmap-resumo (detalhe em `ROADMAP.md`)

| Versão | Evolução | Por quê |
|---|---|---|
| **V0.6** | Sandbox de execução (bwrap → docker → limits) | O coder só *propõe* arquivos; executar é o próximo salto de utilidade — e o maior risco a conter |
| **V0.7** | RAG + memória vetorial local + sub-agentes paralelos | Contexto é o limite real hoje; memória por run_id é só o embrião |
| **V0.8** | Gateway MCP com allowlist por domínio | Conectar o ecossistema de ferramentas sem reescrever o core — maior acelerador de adoção |
| **V1.0** | Conformidade como produto: trilha de auditoria imutável, evals com tarefas-ouro, relatório de compliance | É aqui a tese de posicionamento vira produto vendável |

### Caminhos de crescimento (menor → maior ambição)

1. **Open-source do core** → métrica de adoção; `audit.sh` e os testes de
   segurança viram a marca registrada do repositório.
2. **Verticalização regulada** — saúde/financeiro/governo: é onde "local +
   auditável" vale prêmio, não desconto.
3. **Certificação como produto** — exportar trilha de auditoria + relatório
   em formato exigido por normas. Os dados já existem (logs JSON + memória
   SQLite); falta o relatório.

### Riscos a monitorar (não se autoengana)

- **A fronteira se move:** modelos locais melhoram rápido — bom para nós, mas
  modelos pequenos erram mais; o Critic existe por isso e precisa de evals.
- **Consolidação de frameworks:** se os grandes embutirem "sandbox auditável"
  como feature, o diferencial esvazia — daí a importância do estágio 3
  (compliance como produto, não como código).
- **A regex de política nunca é o walled garden:** o valor real é o
  confinamento de filesystem + limites do Supervisor; a política de conteúdo
  é só a camada mais visível (defense-in-depth, não fronteira).

### Tese de crescimento em uma frase

O mercado está saturado de agentes potentes; a escassez é de agentes
**confiáveis**. O SuperAgent é a semente verificável (testes provando o
confinamento) sobre a qual se constrói automação em ambiente regulado.
