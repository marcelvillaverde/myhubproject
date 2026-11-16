# Terminal de mercado de carros — visão e especificação (v0.2)

> Atualização de 17/11/2026. Substitui o foco "SaaS para 50 revendedores" por: **agregador nacional + terminal de mercado**, acessado via MCP por compradores e vendedores.

## 1. Visão

1. **Agregar** o estoque de montadoras e revendedores de todo o Reino Unido numa base única.
2. **Monitorar** a web continuamente em busca de anúncios novos, quedas de preço e carros vendidos.
3. **Terminal:** compradores e vendedores se conectam ao nosso MCP (ChatGPT, Claude ou outro cliente) e acompanham o mercado como num terminal de ações:

| Conceito de bolsa | No terminal de carros |
|---|---|
| Ativo / ticker | Modelo + ano, ex.: `TOYOTA-RAV4-2020` |
| Cotação | Preço mediano dos anúncios ativos |
| Histórico de cotação | Snapshots diários da mediana, mínimo, máximo e volume |
| Volume | Anúncios ativos, novos e vendidos no período |
| Liquidez | Dias médios até vender |
| Variação | % da mediana vs. 7/30 dias atrás |
| Watchlist | Buscas salvas, tickers e carros específicos |
| Alertas | Novo anúncio compatível, queda de preço, carro vendido |
| Valuation | **Preço justo** por comparáveis (ajustado por quilometragem) |
| Livro de ofertas (fase seguinte) | Intenções de compra publicadas pelos compradores × anúncios |

## 2. Fontes de dados

| Fonte | Decisão | Status |
|---|---|---|
| CSV / feeds enviados por revendedores | Sim | Pronto (`ingest`) |
| Sites próprios dos revendedores | Sim, com robots.txt e opção de sair | Próxima etapa (conector) |
| Feeds de montadoras (seminovos certificados) | Sim, via parceria | Depende de negociação |
| **Portais (AutoTrader, Motors, eBay, etc.)** | **Decisão do fundador: incluir** | Conector plugável; **ativar só após parecer jurídico** |

### Ressalva jurídica sobre portais (registrada a pedido do fundador)
- No Reino Unido, bases de dados têm o **direito sui generis** (Copyright and Rights in Databases Regulations 1997, reg. 16): extrair ou reutilizar **parte substancial** sem consentimento é infração, inclusive pela **soma repetida de partes pequenas**.
- O precedente mais próximo é exatamente sobre **anúncios de carros**: *Innoweb v Wegener* (TJUE, C-202/12, 2013). Um metabuscador (GasPedaal) que consultava em tempo real o banco de anúncios de carros AutoTrack foi considerado infrator. É jurisprudência europeia anterior ao Brexit; seu peso atual nos tribunais britânicos precisa ser confirmado pelo advogado.
- Além disso há os termos de uso dos portais, bloqueios técnicos e possível responsabilidade por dados pessoais de vendedores particulares (UK GDPR).
- **Mitigações técnicas previstas no conector:** respeitar robots.txt, limitar a taxa de acesso, identificar o robô, armazenar só os campos necessários, guardar o link de origem e remover sob demanda. Isso reduz o risco, mas **não resolve a questão do database right**.

Pergunta adicionada ao briefing jurídico: *"Agregar anúncios de portais (AutoTrader etc.) num terminal com histórico de preços: em que condições isso infringe o database right (Innoweb), e existe estrutura viável (licença, extração não substancial, link-out)?"*

## 3. Terminal do comprador (implementado nesta versão)

### Dados de mercado
- Cada anúncio guarda `first_seen`, `removed_at` (vendido/retirado) e **histórico de preço** (uma linha por mudança).
- **Snapshot diário por ticker:** ativos, novos, removidos, mediana, mínimo, máximo, quilometragem mediana.
- **Estatísticas do ticker:** cotação atual, variação em 7 e 30 dias, dias médios no mercado (vendidos), volume.
- **Preço justo:** regressão linear preço × quilometragem dentro do ticker quando há ≥ 5 comparáveis; senão, mediana. Classificação: `great` (≤ −10%), `good` (≤ −3%), `fair` (±3%), `high` (> +3%).

### Watchlist e alertas
- O comprador cria um **watcher** e recebe um **token secreto** (o MCP não tem login neste estágio; quem tiver o token lê os alertas).
- Tipos de watch: `search` (filtros), `ticker`, `vehicle`.
- Alertas gerados a cada ingestão: `NEW_MATCH`, `PRICE_DROP` (com valor e %), `SOLD`.
- Entrega por *pull* via MCP (`get_alerts`). E-mail/push ficam para a próxima fase (exigem consentimento separado).

### Ferramentas MCP novas
| Ferramenta | Função |
|---|---|
| `market_overview` | Tickers mais negociados, maiores altas e quedas, contagem do mercado |
| `get_ticker` | Cotação, variação, liquidez e histórico diário de um ticker |
| `get_vehicle` (ampliado) | Inclui preço justo e histórico de preço do anúncio |
| `create_watcher` / `add_watch` / `list_watches` / `remove_watch` | Watchlist |
| `get_alerts` | Alertas não lidos (marca como lidos) |

## 4. Próximas etapas
1. **Conector de fontes** (interface comum + conector de sites de revendedores com robots.txt e limite de taxa). Conectores de portal desligados por padrão até o parecer.
2. **Livro de ofertas:** intenções de compra visíveis aos vendedores e *matching* automático.
3. **Terminal do vendedor:** demanda por ticker, preço sugerido de compra/venda, tempo estimado de venda.
4. **Entrega de alertas** por e-mail/push e autenticação de usuários.

## Fontes
- [Two Birds — Database right: infringement by re-utilisation and extraction](https://www.twobirds.com/en/insights/2021/uk/database-right-infringement-by-reutilisation-and-extraction)
- [EU Law Radar — Case C-202/12, Innoweb](https://eulawradar.com/case-c-20212-innoweb-search-engines-copying-insubstantial-parts-of-a-website/)
- [Mondaq — When is web scraping of a database unlawful](https://mondaq.com/uk/advertising-marketing-branding/285352/when-is-web-scraping-of-a-database-unlawful)
- [Copyright User — Data scraping or mining and protected databases](https://copyrightuser.org/?p=6180)
- [Auto Trader — resultados anuais FY25 (≈14 mil pátios)](https://plc.autotrader.co.uk/media/umddcnxx/full-year-press-release-fy25.pdf)
