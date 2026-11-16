# hubcarros — terminal de mercado de carros usados (MVP)

Servidor MCP que funciona como um **terminal de mercado**: compradores (e, na próxima fase, vendedores) conectam o ChatGPT/Claude e acompanham o mercado de carros usados do Reino Unido como se fossem ações. Há tickers por modelo/ano, cotação e histórico, preço justo por comparáveis, watchlists e alertas. Tudo isso com **checagem de histórico** e **verificação automática de conformidade** dos anúncios.

Especificações: [terminal](../docs/modulo-conteudo/terminal-spec.md) · [MVP original](../docs/modulo-conteudo/mvp-spec.md).

> Textos voltados ao comprador e ao revendedor estão em inglês (usuários no Reino Unido). Documentação e CLI do operador em português.

## Rodar em 1 minuto

```bash
cd mvp
pip install -e ".[dev]"          # Python 3.11+
hubcarros demo                   # cria hubcarros.db com 2 revendedores fictícios e 12 carros
hubcarros report demo-northgate  # relatório de conformidade por anúncio
hubcarros search "automatic suv under £20k" --near LS6
pytest -q                        # 66 testes
```

Terminal com mercado sintético (30 revendedores fictícios, 60 dias de histórico, cerca de 10 s):

```bash
hubcarros --db mercado.db synthetic --dealers 30 --days 60
hubcarros --db mercado.db market                 # mais anunciados, mais vendidos, altas e quedas
hubcarros --db mercado.db ticker TOYOTA-YARIS-2018
hubcarros --db mercado.db watcher new            # devolve o token secreto
hubcarros --db mercado.db watcher add <TOKEN> search "tesla model 3 under £40k"
hubcarros --db mercado.db watcher alerts <TOKEN>
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
| `market_overview` | Painel: mais anunciados, mais vendidos, maiores altas/quedas em 30 dias |
| `get_ticker` | Cotação de um ticker (`MAKE-MODEL-YEAR`): mediana, mín/máx, variação 7d/30d, dias até vender, histórico diário |
| `create_watcher` | Cria watchlist e devolve **token secreto** (só o hash é guardado) |
| `add_watch` / `list_watches` / `remove_watch` | Busca salva, ticker ou carro específico |
| `get_alerts` | Alertas não lidos: `NEW_MATCH`, `PRICE_DROP`, `SOLD` |

`search_vehicles` aceita `sort` (`best_deal`, `price_asc`, `newest_listing`…) e cada resultado traz ticker e avaliação de preço justo (`great`/`good`/`fair`/`high`). `get_vehicle` inclui histórico de preço do anúncio e o preço justo.

As instruções do servidor proíbem o assistente de calcular ou sugerir financiamento (ver briefing jurídico).

## Fluxo do operador (piloto)

```bash
hubcarros dealer add ng01 "Nome do Revendedor" "LS6 1AA" --phone "0113 ..." --email "..."
hubcarros ingest ng01 estoque.csv     # snapshot completo; carros fora do arquivo = vendidos (gera alertas)
hubcarros ingest ng01 estoque.csv --date 2026-11-17   # data da observação (padrão: hoje)
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
  market.py      Tickers, cotações, liquidez, preço justo (regressão preço × km)
  watch.py       Watchlists, tokens, alertas
  synthetic.py   Mercado sintético determinístico (demo/carga)
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
- Alertas são lidos por *pull* (`get_alerts`); e-mail/push ainda não existem.
- A ingestão trata cada arquivo como **estoque completo** do revendedor. Coletores de sites/portais (próxima etapa) vão precisar de um modo incremental, com expiração por "não visto há N dias".
- Variação de preço por ticker mistura efeito de composição (quais carros estão anunciados) com tendência real; com poucos anúncios é ruído. Por isso exigimos ≥ 5 anúncios para aparecer em altas/quedas.
- Os dados de `synthetic` são inventados; servem só para demonstrar o terminal.
