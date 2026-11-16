# Briefing jurídico — Módulo Conteúdo (fase 1: carros)

> **Não é aconselhamento jurídico.** Este documento organiza o que levantamos em fontes públicas (pesquisadas em 16/11/2026) e as perguntas que você precisa levar a um advogado ou consultor de compliance regulatório no Reino Unido **antes** de cobrar por leads ou oferecer referral de financiamento/seguro.
> Objetivo: transformar uma consulta de 1 hora em respostas objetivas, em vez de uma conversa exploratória cara.

## 1. Resumo para o advogado (cole no e-mail)

> Estamos criando um serviço B2B para pequenos revendedores de carros usados no Reino Unido. Compradores buscam carros em linguagem natural via assistentes de IA (ChatGPT/Claude, por meio de um servidor MCP) e páginas web indexáveis. O comprador pode pedir contato; repassamos o lead ao revendedor. Receita: assinatura SaaS do revendedor e/ou taxa por lead. Fase 2: encaminhar compradores a parceiros de financiamento automotivo e seguro mediante comissão, e expandir para imóveis (agências locais). Também oferecemos uma checagem automática de conformidade dos anúncios dos revendedores. Precisamos saber quais autorizações/registros são necessários em cada fase e como estruturar contratos e textos.

## 2. Mapa de riscos regulatórios

| Tema | Por que importa | Fase | Situação |
|---|---|---|---|
| **Credit broking (FCA)** | Apresentar compradores a credores (ou a corretores de crédito) é atividade regulada. O FCA trata repasse de contatos a credores/corretores como atividade de *lead generator* reportável. Uma alternativa é ser **Introducer Appointed Representative (IAR)** de uma empresa autorizada — o IAR só pode apresentar clientes ao principal e divulgar promoções *não* em tempo real. | 2 (referral financiamento) | Não lançar até parecer |
| **Promoções financeiras (CONC 3.5)** | Se um anúncio mostrar parcela mensal, taxa de juros ou qualquer valor de custo do crédito, exige **exemplo representativo** (APR representativa, valor total do crédito, total a pagar etc.) com destaque não inferior. Um chat de IA que "conversa" sobre parcelas pode ser visto como promoção **em tempo real**. O FCA anunciou revisão de CONC 3 em abril de 2026 — confirmar texto vigente. | 1 (anúncios dos revendedores) e 2 | Mitigado no MVP: a IA não calcula nem sugere parcelas |
| **Seguro (FCA – distribuição)** | Encaminhar a seguradoras/corretores pode ser *insurance distribution*. Introducer puro costuma ter tratamento mais simples. | 2 | Não lançar até parecer |
| **Estate Agents Act 1979** | Um negócio que apresenta compradores a vendedores de imóveis faz *estate agency work*, mesmo 100% online. Obrigatório aderir a esquema de redress aprovado (The Property Ombudsman ou Property Redress) para imóveis residenciais; supervisão AML pela HMRC. | 2 (imóveis) | Bloqueia taxa por lead em imóveis |
| **DMCC Act 2024** (em vigor desde 06/04/2025) | Práticas comerciais desleais com aplicação direta pela CMA, multas até o maior entre £300 mil ou 10% do faturamento global. Proíbe **drip pricing** (taxas escondidas) e **avaliações falsas**. Como a plataforma publica os anúncios, precisa de política clara de responsabilidade e remoção. | 1 | Coberto pelo verificador de conformidade + termos |
| **CAP Code (ASA)** | Preço deve incluir taxas obrigatórias (ex.: "admin fee") e IVA quando o público é consumidor. A ASA já condenou anúncios de carros com taxa de admin não informada. | 1 | Coberto pelo verificador de conformidade |
| **UK GDPR + PECR** | Lead = dado pessoal. Base legal para repasse ao revendedor, aviso de privacidade, retenção, e consentimento separado para marketing. | 1 | MVP grava consentimento explícito e finalidade |
| **Dados veiculares** | API de histórico de MOT da DVSA exige registro (nova versão desde 01/09/2025; chave revogada após 90 dias sem uso). HPI/Experian exigem contrato comercial e têm termos sobre exibição/revenda dos dados. | 1 | MVP usa interface de provedor + simulação |
| **Responsabilidade por conteúdo gerado por IA** | Textos gerados pela IA para o revendedor podem conter afirmações falsas (ex.: "1 dono", "FSH"). Quem responde? | 1 | Revendedor aprova texto antes de publicar |

## 3. Perguntas objetivas para a consulta

### Fase 1 (lançar com isso respondido)
1. Cobrar do revendedor **por lead** (contato de comprador interessado) de carro, sem nenhum envolvimento com financiamento, exige alguma autorização? E se o lead mencionar que o comprador quer financiar?
2. Se o anúncio do revendedor contiver informação de financiamento (ex.: "a partir de £199/mês"), qual é a nossa responsabilidade como plataforma de publicação? Basta bloquear/sinalizar anúncios sem exemplo representativo?
3. Nosso assistente pode **responder perguntas** sobre um anúncio que já contém promoção de crédito? Onde fica a linha entre "exibir o anúncio" e "promoção em tempo real"?
4. Que cláusulas precisamos no contrato com o revendedor: garantia de exatidão do anúncio, indenização, direito de remover anúncios, base legal para compartilhar leads (controlador independente vs. operador)?
5. Que texto mínimo de aviso de privacidade/consentimento colocar no fluxo de pedido de contato feito **dentro de um chat de IA de terceiros**?
6. Podemos exibir, ao comprador, resultados de checagem de histórico (HPI/Experian/DVSA)? Que avisos de limitação usar ("verificação baseada em dados de terceiros na data X")?

### Fase 2 (antes de ativar)
7. Para referral de financiamento: IAR de um corretor/credor autorizado é suficiente para um site que gera leads via IA? Quanto custa e quanto demora conseguir um principal?
8. Para seguro: modelo de introducer — o que podemos e não podemos dizer ao comprador?
9. Imóveis: o simples fato de cobrar por lead da agência nos torna *estate agent*? E se cobrarmos só assinatura SaaS, sem taxa por lead? Quais obrigações de *material information* (Partes A/B/C) recaem sobre nós vs. a agência?
10. **Agregador/terminal:** agregar anúncios de portais (AutoTrader, Motors, eBay) e de sites de revendedores num terminal com histórico de preços. Em que condições isso infringe o *database right* (Copyright and Rights in Databases Regulations 1997; caso *Innoweb*, C-202/12, sobre anúncios de carros)? Existe estrutura viável (licença, extração não substancial, só link de saída)? E para sites de revendedores sem contrato?

## 4. Decisões já tomadas no MVP para reduzir risco
- O assistente **não calcula, sugere ou compara parcelas** de financiamento. Se o comprador perguntar, a resposta é: "fale com o revendedor".
- Nenhum referral de financiamento/seguro na fase 1.
- O verificador de conformidade bloqueia publicação de anúncios com promoção de crédito sem exemplo representativo, com taxa de admin não incluída no preço, ou com alegações de histórico não verificadas.
- Lead só é criado com consentimento explícito, finalidade gravada e retenção definida (padrão: 180 dias).
- Resultado de checagem de risco sempre exibido com fonte, data e aviso de limitação.

## Fontes
- [FCA — Regulatory guide for credit brokers](https://www.fca.org.uk/firms/regulatory-guide-credit-brokers) e [Glossário](https://www.fca.org.uk/firms/regulatory-guide-credit-brokers/glossary)
- [FCA Handbook — CONC 3.5](https://handbook.fca.org.uk/handbook/CONC/3/5.html)
- [FCA — Section 2: Promoting your business and finding customers](https://www.fca.org.uk/firms/regulatory-guide-credit-brokers/section-2)
- [Business Companion — Estate agency work](https://www.businesscompanion.info/focus/ntseat-advice-for-estate-agents/information-for-people-who-are-working-as-an-estate-agent)
- [Estate Agents Act 1979 — Redress schemes](https://www.legislation.gov.uk/ukpga/1979/38/crossheading/redress-schemes)
- [Cooley — New UK consumer law regime comes into force (DMCC)](https://www.cooley.com/news/insight/2025/2025-04-14-new-uk-consumer-law-regime-comes-into-force)
- [HCR Law — 10% turnover penalties](https://www.hcrlaw.com/news-and-insights/new-consumer-protection-laws-10-turnover-penalties-and-how-to-avoid-them/)
- [ASA — Prices: General](https://www.asa.org.uk/advice-online/prices-general.html) e [Motoring](https://www.asa.org.uk/advice-online/motoring.html)
- [ASA — Compulsory costs and charges](https://www.asa.org.uk/Advice-Training-on-the-rules/Advice-Online-Database/Compulsory-costs-and-charges-General.aspx)
- [ASA — To include or not to include VAT in stated prices](https://www.asa.org.uk/news/to-include-or-not-to-include-vat-in-stated-prices.html)
- [DVSA — MOT history API documentation](https://documentation.history.mot.api.gov.uk/mot-history-api/register)
