# RAG Pipeline — Extração e Estruturação de Taxas de Intercâmbio

> Pipeline de IA para extração automática de taxas de intercâmbio Visa & Mastercard a partir de PDFs técnicos.
> **Bolsista Doutor Bandeiras** · Dr. Ademir Batista dos Santos Neto · Junho 2026

---

## Visão Geral

Este projeto implementa um pipeline **RAG (Retrieval-Augmented Generation)** para extrair, estruturar e consultar as regras de intercâmbio publicadas periodicamente pela Visa e Mastercard em formato PDF. O pipeline transforma documentos com centenas de tabelas hierárquicas em um banco de dados relacional consultável e em um índice vetorial para respostas semânticas.

### Problema Central

Os manuais de intercâmbio Visa e Mastercard contêm:
- 20–35 tabelas por documento com cabeçalhos multi-nível
- Notas de rodapé que modificam as regras principais
- Caps, floors e tiers volumétricos embutidos nas células
- Layout variável entre versões semestrais

### Solução: Pipeline em 5 Estágios

```
[PDF Bandeira] → [Ingestão & OCR] → [Chunking Estrutural]
                                            ↓
                              [Extração Semântica via LLM]
                                            ↓
                              [Validação & Reconciliação]
                                            ↓
                         [PostgreSQL + Qdrant (Vector Store)]
                                            ↓
                    [Agente de Consulta RAG / Dashboard Metabase]
```

---

## Estrutura do Repositório

```
ademirneto/
├── src/
│   ├── ingestion/        # Leitura de PDF, OCR fallback
│   ├── chunking/         # Chunking estrutural por entidade de regra
│   ├── embedding/        # Geração de vetores e indexação no Qdrant
│   ├── extraction/       # Agente LLM para extração JSON estruturada
│   ├── validation/       # Great Expectations + regras de negócio
│   └── retrieval/        # Pipeline RAG + Cross-Encoder re-ranking
├── data/
│   ├── raw/              # PDFs originais das bandeiras
│   └── processed/        # JSONs extraídos e validados
├── docs/
│   ├── proposta_tecnica_pipeline_intercambio.md
│   ├── proposta_tecnica.pdf
│   ├── arquitetura_db.png
│   └── comparativo_pipeline.svg
├── notebooks/            # Exploração e prototipagem
├── infra/                # Docker Compose, DDL PostgreSQL, config Qdrant
├── scripts/              # Scripts de automação e setup
├── tests/                # Testes unitários e de integração
├── requirements.txt
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Stack Tecnológica

| Camada | Tecnologia | Finalidade |
|---|---|---|
| Extração de PDF | `pdfplumber` + `unstructured` | Tabelas hierárquicas + classificação de blocos |
| OCR Fallback | `pytesseract` + `OpenCV` | PDFs não-digitais ou com artefatos |
| Processamento | `Polars` + `PyArrow` | Performance em datasets tabulares grandes |
| LLM de Extração | `Ollama` (llama3.1:70b / qwen2.5:72b) | Structured output JSON nativo |
| Embedding | `text-embedding-3-large` / `BGE-M3` | Qualidade semântica no domínio financeiro |
| Vector Store | `Qdrant` | Payload filtering + HNSW + hybrid search |
| Banco Relacional | `PostgreSQL` + `TimescaleDB` | Série temporal + analytics SQL |
| Orquestração | `Apache Airflow` | DAGs de re-ingestão automática |
| Monitoramento | `Evidently AI` + `MLflow` | Drift detection + versionamento de modelos |
| Dashboard | `Metabase` | Open-source, SQL-native |
| Re-ranking | `Cross-Encoder MiniLM-L-6-v2` | Precisão pós-busca vetorial |
| Validação de Dados | `Great Expectations` | Qualidade automatizada com alertas |

---

## Modelo de Dados

A camada relacional contém 6 tabelas principais:

- **`bandeiras`** — documentos de origem (Visa, Mastercard) com versionamento por data
- **`tipos_cartao`** — produtos (Infinite, Signature, World Elite, Core…) com flag Durbin
- **`segmentos`** — MCCs agrupados por categoria (Supermarket, Petroleum, Utilities…)
- **`regras_intercambio`** — tabela central: `rate_pct`, `rate_fixed_usd`, `cap_usd`, `floor_usd`, `tier_label`
- **`ajustes`** — bonificações e penalidades condicionais por nota de rodapé
- **`footnotes_resolvidas`** — texto original + paráfrase estruturada pelo LLM

Cada regra tem metadados completos: `modalidade` (CP/CNP), `vigencia_inicio/fim`, `fonte_pagina`.

---

## Instalação

```bash
# 1. Clonar e entrar no diretório
git clone git@github.com:ademirNeto/rag.git
cd rag/ademirneto

# 2. Ambiente virtual
python -m venv .venv && source .venv/bin/activate

# 3. Dependências
pip install -r requirements.txt

# 4. Variáveis de ambiente
cp .env.example .env
# edite .env com suas credenciais

# 5. Infraestrutura (PostgreSQL + Qdrant)
docker compose -f infra/docker-compose.yml up -d

# 6. Inicializar banco de dados
python scripts/init_db.py
```

---

## Uso Rápido

```python
from src.ingestion.pdf_loader import PDFLoader
from src.chunking.rule_chunker import RuleChunker
from src.extraction.llm_extractor import LLMExtractor
from src.validation.rate_validator import RateValidator

# 1. Ingerir PDF
loader = PDFLoader("data/raw/visa-usa-interchange-reimbursement-fees.pdf")
page_blocks = loader.extract_blocks()

# 2. Chunking estrutural
chunker = RuleChunker(page_blocks)
rule_chunks = chunker.build_rule_chunks()

# 3. Extração via LLM
extractor = LLMExtractor(model="qwen2.5:72b")
raw_rules = extractor.extract(rule_chunks)

# 4. Validação
validator = RateValidator()
validated_rules = validator.validate(raw_rules)
```

---

## Ordem de Execução dos Milestones

O projeto é dividido em 11 milestones que devem ser executados na sequência abaixo. Cada milestone é pré-requisito do seguinte — não avance sem concluir as issues do milestone anterior.

```
M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10 → M11
```

| Ordem | Milestone | Dependência | Por quê antes |
|---|---|---|---|
| **M1** | Fundamentos RAG e Ambiente | — | Base conceitual e infraestrutura mínima (Python, Docker) |
| **M2** | Ingestão de PDFs | M1 | Sem extração de dados não há nada para processar |
| **M3** | Chunking Estrutural | M2 | Chunking opera sobre os blocos extraídos em M2 |
| **M4** | Embedding e Qdrant | M3 | Vetoriza os chunks gerados em M3 e os indexa no Qdrant |
| **M5** | Extração LLM com Ollama | M3 | O LLM refina a extração estruturada dos chunks de M3 |
| **M6** | Banco de Dados Relacional | M5 | Persiste as regras validadas produzidas em M5 |
| **M7** | Validação de Dados | M5, M6 | Valida as regras antes e depois da persistência no banco |
| **M8** | Pipeline RAG e Retrieval | M4, M6 | Une Qdrant (M4) e PostgreSQL (M6) no agente de consulta |
| **M9** | Orquestração com Airflow | M8 | Automatiza o pipeline completo já validado em M8 |
| **M10** | Monitoramento e Drift Detection | M8, M9 | Monitora a qualidade do pipeline em operação contínua |
| **M11** | Dashboard com Metabase | M6 | Consome o banco relacional (M6) para visualizações finais |

### Visão de Dependências

```
M1 (Ambiente)
 └─► M2 (Ingestão)
      └─► M3 (Chunking)
           ├─► M4 (Embedding + Qdrant)
           │    └─► M8 (RAG + Retrieval) ◄─────────────┐
           └─► M5 (LLM Extração)                        │
                ├─► M6 (PostgreSQL) ──────────────────► M8
                │    ├─► M7 (Validação)                 │
                │    └─► M11 (Metabase)                 │
                └─► M7 (Validação)          M9 (Airflow) ──► M10 (Monitoramento)
```

> **Dica de estudo:** M4 e M5 podem ser estudados em paralelo após concluir M3, pois são independentes entre si. Da mesma forma, M9 e M11 podem ser abordados em paralelo após M8 e M6, respectivamente.

---

## Documentação Técnica

- [Proposta Técnica Completa](docs/proposta_tecnica_pipeline_intercambio.md)
- [Arquitetura do Banco de Dados](docs/arquitetura_db.png)
- [Comparativo do Pipeline](docs/comparativo_pipeline.svg)

---

## Testes

```bash
pytest tests/ -v
```

---

**Dr. Ademir Batista dos Santos Neto** · *Cientista de Dados Sênior* · Junho 2026
