# Módulo Conteúdo — Carros & Imóveis (Business Model Canvas)

> Status: rascunho v0.1 · Mercado-alvo: Reino Unido · Data: 2026-11-16

## 1. Canvas

| Bloco | Conteúdo |
|---|---|
| **Proposta de Valor** | **Compradores:** encontrar carros/imóveis em linguagem natural, com verificação automática de riscos. **Vendedores:** leads com intenção real de compra, não cliques casuais. |
| **Segmentos de Clientes** | Fase inicial: 20–50 pequenos/médios revendedores de carros usados (insatisfeitos com o custo da AutoTrader) + 10–20 pequenas agências imobiliárias locais (querendo reduzir dependência de portais). |
| **Canais** | Integração MCP com ChatGPT/Claude (sem app próprio); SEO local; comunidades locais. |
| **Relacionamento** | Autoatendimento para vendedores (upload de inventário, IA gera os textos); verificação de conformidade incluída no serviço. |
| **Fontes de Receita** | Assinatura SaaS (£49–£199/mês) + taxa por lead de alta intenção + comissão de referral (seguro/financiamento). |
| **Recursos Principais** | Dados de inventário em tempo real (o mais crítico); modelo de IA de conformidade (riscos legais em anúncios). |
| **Atividades Principais** | Aquisição presencial de inventário (o trabalho mais árduo); limpeza de dados e verificação em tempo real. |
| **Parceiros** | Fornecedores de histórico veicular (HPI/Experian); pequenos vendedores (primeiro inventário e primeiros pagantes). |
| **Estrutura de Custos** | Desenvolvimento (integração de IA + crawlers), equipe de vendas, conformidade jurídica. |

## 2. Análise crítica

### 2.1 O que está forte
- **Dor real e mensurável.** A receita média da AutoTrader por revendedor está na casa de £2.800+/mês, e a da Rightmove por agência acima de £1.500/mês. Um preço de £49–£199 é uma ancoragem muito agressiva.
- **Canal sem custo de aquisição de comprador.** Usar ChatGPT/Claude via MCP evita competir em Google Ads/SEO nacional com portais gigantes.
- **Conformidade como diferencial.** Pequenos vendedores raramente têm alguém revisando anúncios; isso é vendável como "seguro" e não só como "tráfego".

### 2.2 Riscos principais (por ordem de gravidade)

1. **O vendedor paga por audiência, não por ferramenta.** A AutoTrader cobra caro porque entrega compradores. Se no início o volume de buscas via MCP for baixo, o SaaS vira "gerador de textos" — e isso tem concorrentes baratos. **Mitigação:** cobrar no início *só por lead* (ou assinatura com garantia de N leads) até provar volume.
2. **Dependência de plataforma (MCP/ChatGPT/Claude).** Descoberta, ranking e regras de apps nessas plataformas não são controladas por você. **Mitigação:** manter páginas indexáveis por SEO local para cada item de inventário desde o dia 1 — o mesmo dado serve aos dois canais.
3. **Regulação dos serviços de referral (crítico, verificar com advogado):**
   - **Financiamento de veículos:** apresentar compradores a credores é *credit broking*, atividade regulada pela **FCA**. Exige autorização própria ou atuar como *Appointed Representative/introducer* de uma empresa autorizada.
   - **Seguro:** distribuição de seguros também é regulada pela FCA; um modelo de *introducer* puro (apenas encaminhar) costuma ser o caminho mais simples.
   - **Imóveis:** cobrar por apresentar compradores a vendedores pode configurar *estate agency work* (Estate Agents Act 1979) → obrigatoriedade de esquema de *redress* (TPO/PRS) e supervisão AML pela HMRC.
   - **Anúncios imobiliários:** exigência de *material information* (Trading Standards, Partes A/B/C) — uma boa oportunidade para o modelo de conformidade.
   - **Proteção ao consumidor:** DMCC Act 2024 (práticas comerciais desleais), Consumer Rights Act 2015, normas da ASA/CAP.
   - **Dados:** leads são dados pessoais → UK GDPR + PECR (consentimento para contato de marketing).
4. **Dois verticais ao mesmo tempo.** Carros e imóveis têm dados, parceiros, regulação e ciclos de venda totalmente diferentes. Dividir 1 equipe pequena entre os dois atrasa a liquidez de ambos.
5. **Definição de "lead de alta intenção".** Sem uma definição objetiva, a taxa por lead gera disputa com o vendedor. Exemplos: comprador confirmou orçamento + data de visita/test-drive; ou passou pela verificação de risco e pediu contato.
6. **"Aquisição presencial de inventário" não escala.** Boa para os primeiros 20 clientes; depois precisa ser substituída por integração com feeds.

### 2.3 Recomendações
- **Começar só com carros.** Motivos: dor de preço mais aguda (AutoTrader), parceiro de dados claro (HPI/Experian) e "verificação de risco" fácil de demonstrar (finance outstanding, write-off, quilometragem). Imóveis entram na fase 2.
- **Inventário via feed, não digitação.** A maioria dos revendedores já exporta estoque a partir do seu DMS/site; integrar esses feeds (ou ler o site do próprio revendedor, com permissão por escrito) reduz o trabalho presencial à assinatura do contrato.
- **Referral via parceiro autorizado.** Lançar financiamento/seguro como *introducer* de uma empresa já autorizada pela FCA, em vez de buscar autorização própria no início.
- **Preço de entrada:** piloto gratuito por 60 dias → depois £X por lead qualificado, com teto mensal; assinatura só quando o volume de leads estiver comprovado.

## 3. Hipóteses a validar (antes de escrever código)

| # | Hipótese | Teste | Critério de sucesso |
|---|---|---|---|
| H1 | Revendedores pagariam por leads vindos de assistentes de IA | 15 entrevistas presenciais com revendedores | ≥ 8 aceitam piloto com compromisso de feedback |
| H2 | Compradores usam ChatGPT/Claude para buscar carro | Servidor MCP mínimo com inventário de 5 revendedores | ≥ 100 buscas e ≥ 10 pedidos de contato em 30 dias |
| H3 | A verificação de risco aumenta a confiança do comprador | Comparar taxa de contato com/sem selo de verificação | Aumento ≥ 20% |
| H4 | O inventário pode ser obtido sem digitação manual | Ingestão de feed/site para os 5 revendedores do piloto | ≥ 90% dos anúncios atualizados em < 24h |
| H5 | O modelo de conformidade encontra problemas reais | Rodar sobre 200 anúncios públicos | ≥ 1 problema relevante a cada 10 anúncios, com baixa taxa de falso positivo |

## 4. Métricas-chave (North Star e apoio)
- **North Star:** leads qualificados entregues por revendedor/mês.
- Apoio: % de inventário atualizado < 24h; taxa busca→contato; taxa lead→visita/test-drive (reportada pelo revendedor); churn mensal de vendedores; custo de aquisição por revendedor.

## 5. Próximos passos sugeridos
1. Consulta jurídica curta (FCA/credit broking + estate agency) antes de prometer referral ou taxa por lead em imóveis.
2. Roteiro de entrevista com revendedores e lista de 30 revendedores locais.
3. Especificação do MVP: servidor MCP (busca + detalhe + pedido de contato) + ingestão de feed + checagem HPI.
