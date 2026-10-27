# Observador Brasil — requisitos do projeto

Atualizado em 27/10/2026 a partir das orientações fornecidas pelo usuário.
O texto original está em [DIRETRIZES_FORNECIDAS.md](DIRETRIZES_FORNECIDAS.md).
Este documento registra requisitos; não declara funcionalidades futuras como implementadas.

## Finalidade e análise

Análise política, constitucional, fiscal e social do Brasil nos níveis federal,
estadual e municipal, com linguagem direta, isenção e fontes identificáveis.
Consultar fontes oficiais ou APIs ao analisar economia, orçamento, segurança,
tramitação legislativa e processos judiciais. Exibir data da consulta, período
medido, unidade, fonte e indisponibilidade. Dados mensais/anuais não se tornam
medições em tempo real por serem consultados hoje.

Para leis, PECs e processos: resumo, enquadramento constitucional e normas,
argumentos jurídicos favoráveis e contrários, impacto orçamentário pertinente
e precedentes do STF com identificação e alcance. Não inventar precedentes.

## Estrutura prevista da interface

1. Visão Geral e Macroeconomia: dívida/PIB e saldo em reais, Selic, IPCA,
   taxa nacional de homicídios devidamente definida, séries históricas e mapa
   estadual com população, pobreza, analfabetismo, criminalidade e governador.
2. Dossiê de Corrupção (2002 - Presente): pesquisa, seleção, mecanismo,
   pessoas e papéis documentados, cifras, situação processual e notícias.
3. Economia, Orçamento e Benefícios Sociais: orçamento e execução de Saúde,
   Educação e Segurança Pública; benefícios; radar de notícias orçamentárias.

Manter boa leitura no celular: valores explícitos em reais, percentuais com
base e período, tabelas/cartões legíveis e gráficos sem depender de hover.
Usar Streamlit e requests; Plotly/Folium conforme necessidade do mapa.
A entrega de código completo para cópia deve vir acompanhada das dependências
necessárias; a implementação atual possui módulos auxiliares.

## Orçamento e benefícios sociais — requisitos novos

Programas: Bolsa Família, BPC, Pé-de-Meia, Auxílio-Gás, Seguro-Desemprego e
Minha Casa Minha Vida. Priorizar cartões para os quatro primeiros exigidos
na interface: Bolsa Família, BPC, Pé-de-Meia e Seguro-Desemprego.

Para cada programa, quando houver dados comparáveis:
- Orçamento autorizado, execução, custo relativo ao PIB e contexto fiscal.
- Valor médio recebido, reajustes e comparação com inflação/salário mínimo.
- Quantidade atendida, unidade (pessoa/família), competência e fila de espera.
- Cancelamentos, bloqueios, revisão cadastral e mudanças de elegibilidade.
- Variação anual com períodos equivalentes, base explícita e distinção entre
  variação nominal e real. Queda de despesa não prova pente-fino ou corte.

Saúde, Educação e Segurança: comparar previsto/autorizado e executado,
identificando exercício, abrangência federativa e estágio da despesa
(empenhada, liquidada ou paga). Não comparar execução parcial com ano completo
sem aviso nem misturar transferências e gasto direto de modo a duplicar valores.
Não calcular ticket dividindo despesa anual por beneficiários de um único mês.
Minha Casa Minha Vida exige métricas próprias de habitação, não ticket de renda.

Fontes a avaliar: Portal da Transparência, dados orçamentários federais,
MDS, Planejamento, ministérios gestores e APIs legislativas. Registrar necessidade
de chave, limites e disponibilidade antes de prometer integração sem credenciais.

Radar: buscas por “corte de gastos”, “pente-fino bolsa família”, “reajuste BPC”,
“déficit fiscal” e “contingenciamento de verbas”, com fonte, data, links,
janela temporal e tratamento de falhas. Notícias não substituem execução oficial.

## Dossiê — ampliação e rigor

Além dos seis casos existentes, incluir Dossiê dos Aloprados e investigações
recentes de emendas/contratos após pesquisa documental. O recorte solicitado
é 2002–presente, com interesse nas gestões federais do PT; isso não atribui
um caso, pessoa ou instituição automaticamente a um partido ou governo.

Distinguir investigado, denunciado, condenado, absolvido, decisão anulada,
prisão cautelar e situação de custódia na data documentada. Autoridades de
julgamento/controle ficam separadas das pessoas investigadas. Notícia não
atualiza automaticamente o status judicial.

Valores nominais e corrigidos exigem fonte, moeda, data-base, índice e fórmula;
correção monetária não equivale a atualização judicial com juros. Não somar
bloqueio, baixa contábil, estimativa, multa e ressarcimento como um mesmo rombo.
Não corrigir cifras em dólares sem metodologia cambial e monetária explícita.

## Indicadores estaduais e apresentação

Os rankings de violência, pobreza e analfabetismo do texto original são referências
fornecidas, não resultados atuais validados. Recalcular a ordenação com a edição,
indicador e população-alvo pertinentes. Distinguir MVI de homicídio e taxa por
100 mil habitantes de porcentagem. Incluir feminicídio, roubos de carga/veículos
e violência patrimonial quando existirem fontes comparáveis; números absolutos
não demonstram maior risco regional.

No chat: ir direto aos fatos, tabelas e barras textuais quando úteis, sempre
com escala e base. Evitar transformar diferenças estatísticas em causalidade.

## Situação após registro destes requisitos

Já existente: duas abas principais; macroeconomia e referências monetárias;
mapa/tabela estadual; agenda da Câmara; seis fichas do dossiê e monitor de notícias.
Parte dos dados estaduais e processuais exige revisão editorial, conforme LEIA-ME.

Pendente de implementação e validação:
- Terceira aba de orçamento e benefícios, fontes, cartões e radar específico.
- Taxa nacional de homicídios como métrica principal e indicadores complementares.
- Ficha dos Aloprados, investigações adicionais e valores corrigidos documentados.
- Atualização dinâmica das bases anuais e do cadastro de governantes onde disponível.

Este registro não altera app.py nem publica funcionalidades pendentes.
## Implementação em 27/10/2026

A estrutura de três abas, orçamento SIOP, seis programas, radar fiscal, oito fichas, correção IPCA condicionada e cinco indicadores de segurança foi implementada. A seção anterior descreve o estado antes desta implementação. Permanecem limitações de disponibilidade: fila/bloqueios/cancelamentos, público e ticket de parte dos programas, cadastro oficial automático de governadores e atualização editorial do status jurídico. Consulte LEIA-ME.md para a cobertura exata e as validações.
