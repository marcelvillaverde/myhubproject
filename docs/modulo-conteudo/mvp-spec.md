# Especificação do MVP — fase 1 (carros)

> Código em [`mvp/`](../../mvp). O objetivo do MVP é testar **H2** (compradores usam assistentes de IA para buscar carros), **H3** (o selo de verificação aumenta o contato) e **H5** (o verificador de conformidade encontra problemas reais) com **5 revendedores piloto**, sem depender de contrato pago com HPI/Experian no primeiro dia.

## 1. Escopo

| Dentro | Fora (por enquanto) |
|---|---|
| Ingestão de estoque via CSV (export do DMS ou planilha) | Leitura automática de sites (exige autorização escrita de cada revendedor) |
| Busca estruturada + interpretação simples de texto livre | App próprio, login de compradores |
| Ferramentas MCP para ChatGPT/Claude | Pagamentos, cobrança automática |
| Checagem de risco veicular por **interface de provedor** (simulado no MVP) | Contrato HPI/Experian, API DVSA (registro pendente) |
| Verificador de conformidade de anúncios (regras) | Classificador por IA (fase seguinte, treinado com as ocorrências reais) |
| Captura de lead com consentimento + *intent score* | Referral de financiamento/seguro (ver briefing jurídico) |
| Gerador de descrição a partir de **fatos estruturados** | Texto livre gerado por LLM sem revisão |
| CLI para o operador (ingestão, relatório, leads) | Painel web do revendedor |

## 2. Arquitetura

```
CSV do revendedor ──► ingest ──► SQLite ◄── risk provider (mock → HPI/Experian/DVSA)
                                   │
                    compliance (regras) ── define status: published / needs_review / blocked
                                   │
             ┌─────────────────────┴───────────────────┐
        servidor MCP (stdio/HTTP)                 CLI do operador
  search_vehicles · get_vehicle · request_contact   ingest · report · leads · demo
```

Princípios:
- **Núcleo sem dependência de MCP.** Toda a lógica está em módulos Python puros; o servidor MCP é uma camada fina. Isso facilita trocar de canal (site SEO, widget) sem reescrever nada.
- **Só aparece para o comprador o que passou na conformidade.** Anúncios `blocked` nunca são retornados; `needs_review` aparecem apenas com aviso interno ao revendedor (não ao comprador) — configurável.
- **A IA não fala de parcelas.** As instruções do servidor proíbem calcular/sugerir financiamento (ver briefing jurídico, CONC 3.5).

## 3. Modelo de dados (SQLite)

- `dealers(id, name, postcode, phone, email)`
- `vehicles(id, dealer_id, reg, make, model, variant, year, price_gbp, mileage, fuel, transmission, body, colour, doors, seats, description, features, status, compliance_json, risk_json, updated_at, removed_at)`
- `leads(id, vehicle_id, dealer_id, name, email, phone, message, budget_gbp, timeframe_days, wants_test_drive, has_part_exchange, finance_interest, consent_contact, consent_marketing, intent_score, intent_tier, created_at, retain_until)`

Ingestão é **idempotente** por `(dealer_id, reg)`: carros que somem do feed recebem `removed_at` (vendidos) e saem da busca.

## 4. Ferramentas MCP

| Ferramenta | Entrada | Saída |
|---|---|---|
| `search_vehicles` | `query` (texto livre, opcional) + filtros: `make`, `model`, `max_price`, `min_price`, `max_mileage`, `min_year`, `fuel`, `transmission`, `body`, `min_seats`, `near_postcode`, `limit` | Lista resumida com selo de verificação e motivos do ranking |
| `get_vehicle` | `vehicle_id` | Ficha completa, resumo de risco (fonte + data + avisos), revendedor |
| `request_contact` | `vehicle_id`, nome, e-mail/telefone, `consent_contact` (obrigatório = true), mensagem, orçamento, prazo em dias, test-drive, troca | Confirmação + o que acontece em seguida. O *intent score* **não** é mostrado ao comprador |

## 5. Regras de conformidade (v1)

| Código | Regra | Severidade |
|---|---|---|
| `PRICE_MISSING` | Preço ausente ou zero | block |
| `FINANCE_NO_REP_EXAMPLE` | Texto com parcela/APR/depósito sem "Representative example" + APR | block |
| `DRIP_PRICING` | Taxa obrigatória (admin/prep/documentation fee) cobrada à parte do preço | block |
| `PRICE_EX_VAT` | Preço "+VAT"/"ex VAT" em anúncio para consumidor | warn |
| `CONSUMER_RIGHTS_EXCLUSION` | "Sold as seen", "no warranty", "no returns" em venda a consumidor | block |
| `TRADE_SALE_CHECK` | Mesmas expressões, mas o anúncio se declara venda "trade" | warn |
| `MILEAGE_MISMATCH` | Quilometragem citada no texto difere da estruturada em > 1.000 milhas | block |
| `UNVERIFIED_HISTORY_CLAIM` | "Full service history", "one owner", "HPI clear", "accident free" sem verificação | warn |
| `HISTORY_CONTRADICTION` | Texto diz "one owner" e o histórico registra mais de um | block |
| `WRITE_OFF_NOT_DISCLOSED` | Checagem indica Cat S/N/C/D e o texto não declara | block |
| `FINANCE_OUTSTANDING` | Checagem indica financiamento em aberto | block |
| `STOLEN_MARKER` | Checagem indica marcador de roubo | block |
| `MOT_EXPIRED_NOT_DISCLOSED` | MOT vencido e o texto não declara | warn |
| `UNSUBSTANTIATED_SUPERLATIVE` | "Cheapest in the UK", "best price guaranteed" | warn |

Status do anúncio: qualquer `block` → `blocked`; só `warn` → `needs_review`; nenhum → `published`.

## 6. Intent score (0–100)

Pesos iniciais (serão recalibrados com o que os revendedores disserem nas entrevistas, pergunta 11):

| Sinal | Pontos |
|---|---|
| Quer test-drive/visita | 25 |
| Prazo ≤ 7 dias / ≤ 30 dias | 20 / 10 |
| Orçamento informado e ≥ 90% do preço | 20 (ou 8 se informado mas abaixo) |
| Telefone informado | 10 |
| Tem carro para troca | 10 |
| Mensagem específica (≥ 40 caracteres) | 10 |
| Lead repetido do mesmo contato no mesmo carro (7 dias) | rejeitado |

Faixas: **alta** ≥ 70, **média** 40–69, **baixa** < 40. Só leads de alta intenção entram na cobrança por lead.

## 7. Métricas instrumentadas
Buscas por dia, resultados por busca, `get_vehicle` por busca, pedidos de contato por `get_vehicle`, distribuição de faixas de intenção, % de anúncios por status de conformidade, ocorrências por regra.

## 8. Próximos incrementos
1. Provedor de risco real (DVSA MOT history — gratuito com registro; depois HPI ou Experian AutoCheck sob contrato).
2. Transporte HTTP + publicação do conector no ChatGPT/Claude.
3. Páginas estáticas por veículo para SEO local (mesmos dados).
4. Notificação de lead ao revendedor (e-mail/WhatsApp) e retorno "virou visita?" em um clique.
5. Classificador de conformidade com LLM, avaliado contra as regras v1.
