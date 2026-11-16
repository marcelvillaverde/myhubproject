# hubcarros — MVP (fase 1: carros usados)

Servidor MCP que deixa compradores buscarem carros de revendedores locais pelo ChatGPT/Claude, com **checagem de histórico** e **verificação automática de conformidade** dos anúncios. Especificação: [`docs/modulo-conteudo/mvp-spec.md`](../docs/modulo-conteudo/mvp-spec.md).

> Textos voltados ao comprador e ao revendedor estão em inglês (usuários no Reino Unido). Documentação e CLI do operador em português.

## Rodar em 1 minuto

```bash
cd mvp
pip install -e ".[dev]"          # Python 3.11+
hubcarros demo                   # cria hubcarros.db com 2 revendedores fictícios e 12 carros
hubcarros report demo-northgate  # relatório de conformidade por anúncio
hubcarros search "automatic suv under £20k" --near LS6
pytest -q                        # 48 testes
```

Servidor MCP:

```bash
export HUBCARROS_DB=hubcarros.db
export HUBCARROS_RISK_FIXTURE=data/demo/risk_fixture.json   # checagens simuladas
hubcarros-mcp            # stdio (Claude Desktop / Claude Code)
hubcarros-mcp --http     # streamable HTTP (para conector remoto)
```

Exemplo de configuração no Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "hubcarros": {
      "command": "hubcarros-mcp",
      "env": {
        "HUBCARROS_DB": "/caminho/para/hubcarros.db",
        "HUBCARROS_RISK_FIXTURE": "/caminho/para/mvp/data/demo/risk_fixture.json"
      }
    }
  }
}
```

## Ferramentas MCP

| Ferramenta | O que faz |
|---|---|
| `search_vehicles` | Texto livre + filtros estruturados; só retorna anúncios aprovados e sem alerta bloqueante no histórico |
| `get_vehicle` | Ficha completa com resumo do histórico (fonte, data, aviso) |
| `request_contact` | Cria lead **somente** com `consent_contact=true`; calcula *intent score* (não exibido ao comprador) |

As instruções do servidor proíbem o assistente de calcular ou sugerir financiamento (ver briefing jurídico).

## Fluxo do operador (piloto)

```bash
hubcarros dealer add ng01 "Nome do Revendedor" "LS6 1AA" --phone "0113 ..." --email "..."
hubcarros ingest ng01 estoque.csv     # idempotente; carros fora do arquivo saem da busca
hubcarros report ng01                 # mostrar ao revendedor o que corrigir
hubcarros draft 12                    # rascunho de descrição só com fatos do cadastro
hubcarros leads ng01                  # leads com faixa de intenção
hubcarros metrics                     # buscas, visualizações, leads
hubcarros purge-leads                 # apaga leads além do prazo de retenção (180 dias)
```

O CSV aceita cabeçalhos comuns de exports de DMS (`Registration`/`VRM`, `Derivative`, `Fuel Type`, `Advert text` …); veja `HEADER_ALIASES` em `src/hubcarros/ingest.py`. Obrigatórios: placa, marca, modelo, ano, quilometragem.

## Estrutura

```
src/hubcarros/
  ingest.py      CSV → Vehicle (aliases, normalização, erros por linha)
  compliance.py  14 regras (FCA CONC 3.5, DMCC/drip pricing, Consumer Rights Act, CAP, histórico)
  risk.py        Protocolo RiskProvider + provedor simulado; resumo para o comprador
  search.py      Filtros + interpretação de texto livre
  leads.py       Validação, consentimento, intent score
  copywriter.py  Rascunho de anúncio só com fatos verificados
  service.py     Camada de aplicação (usada por MCP e CLI)
  db.py          SQLite (stdlib)
  server.py      Servidor MCP
  cli.py         CLI do operador
data/demo/       Revendedores e estoque fictícios + checagens simuladas
```

## Limitações conhecidas
- **Checagem de histórico é simulada.** Para produção, implemente `RiskProvider` com a API de histórico de MOT da DVSA (registro gratuito) e, sob contrato, HPI ou Experian.
- Regras de conformidade são uma **triagem de risco**, não parecer jurídico; precisão por regra deve ser medida no piloto (H5).
- Proximidade por postcode compara apenas a área (ex.: `LS`), sem geocodificação.
- Sem autenticação no transporte HTTP: não exponha publicamente antes de adicionar auth.
- Notificação de leads ao revendedor ainda é manual (`hubcarros leads`).
