# Observador Brasil

Aplicativo: https://observador-brasil-weslley.streamlit.app/

## Instalação

Python 3.11 ou posterior. Mantenha no mesmo diretório app.py, monetario.py,
dossie.py, dossie_casos.json, orcamento.py, seguranca.py, seguranca_referencia.json,
dados_estaduais.json e brasil_uf.geojson.

```sh
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Streamlit Community Cloud: repositório weslleye10-svg/observador-brasil,
branch main, arquivo principal app.py. Atualizações do código no GitHub são
implantadas pelo serviço. Nenhuma chave é necessária nas integrações atuais.

## Três abas

- Visão Geral e Macroeconomia: dívida, Selic, IPCA, referências em reais,
  salário mínimo, homicídios nacionais, estados, rankings, mapa e agenda.
- Dossiê de Corrupção: oito fichas documentadas, busca por pessoa/empresa,
  natureza dos valores, registro processual, fontes e notícias 24h/7d.
- Economia, Orçamento e Benefícios Sociais: Saúde, Educação, Segurança,
  seis programas, orçamento inicial/autorizado, execução, comparações,
  público e média onde há séries compatíveis, radar fiscal e CSV.

As abas principais têm execução sob demanda: apenas a aba aberta consulta
suas fontes. Os fragmentos atualizam em cinco minutos na sessão ativa;
macroeconomia também tem controle específico na lateral. Atualização manual
limpa os caches da sessão. Não há serviço de coleta enquanto o site está dormindo.

## Fontes e limites

BCB/SGS: 13762 dívida/PIB; 13761 saldo em milhões de reais, multiplicado por
1.000.000; 432 meta Selic; 433 IPCA mensal; 13522 IPCA 12m; 1619 salário mínimo;
188 INPC. Exibir data medida e horário da consulta; não anualizar o último IPCA.
Juros teóricos compostos, sem tarifas ou impostos; não representam CET nem o
custo da dívida pública inteira. Ganho real salarial usa meses equivalentes.

IBGE/SIDRA: população 6579, pobreza 5877, analfabetismo 7113. Bases anuais/mensais
mantêm periodicidade própria. PIB fiscal: tabela 6784, variável 9808, unidade
1550 validada (milhões de reais). Só calcular pago/PIB se houver o mesmo ano;
PIB anual definitivo pode ter defasagem. Nunca usar denominador de outro ano.

SIOP/SPARQL: consulta pública por função (06, 10, 12) e ação. Mostra data de
atualização da base. LOA inicial comparada à LOA inicial anterior (nominal).
Autorizado = lei + créditos; diferença para inicial não mede contingenciamento.
Execução exclui restos a pagar de exercícios anteriores e não mede pisos legais.
Função federal não é gasto consolidado de União, estados e municípios.
Ações e abrangência estão explícitas: BPC inclui RMV no orçamento; Pé-de-Meia
mostra aporte ao fundo, não saques; MCMV é recorte FAR/FDS/subvenções, sem FGTS.
Ação ausente não é gasto zero. O servidor usa sintaxe SPARQL compatível com sua
versão, formato JSON específico e validação contra códigos duplicados.

Ipeadata/MDS: FAM_PBF (quantidade anual de dezembro), VAL_PBF12 (valor mensal),
PES_BPC e VAL_BPC (mensais). Filtrar exclusivamente Brasil/território 0;
valores financeiros dessas séries são R$ mil. FAM_PBF tem carimbo de janeiro
para a posição de dezembro daquele ano: converter referência para dezembro
antes de combinar com o valor mensal. Médias exigem mesma competência.
Não confundir benefícios, pessoas únicas, parcelas e famílias.

Público, ticket, fila, bloqueios e cancelamentos dos demais programas não têm
série nacional compatível nas integrações atuais. A tela mostra indisponibilidade
e links oficiais, sem números inventados. Há referência documental datada da
CAIXA para o Pé-de-Meia, distinguindo parcela regulamentar de média observada.
O Portal da Transparência exige chave; não incluímos credencial no código nem
raspagem de dados pessoais. Painéis oficiais do MTE continuam acessíveis por link.

Segurança: consulta o Excel oficial do FBSP, edição 2026, dados 2025, com
validação de cinco tabelas e 27 UFs + Brasil: T01 MVI, T03 homicídios dolosos,
T11 roubo de veículos, T15 carga, T21 feminicídios. Fonte e notas exibidas.
Taxa de veículo por 100 mil veículos; feminicídio por 100 mil mulheres;
demais por 100 mil habitantes. Distribuição regional usa absolutos/participações,
não taxa de risco. Traços não viram zero; agregados incompletos ficam vazios.
Se fonte falhar ou surgir edição com estrutura diferente, usa referência datada
e avisa; nova edição exige validar o formato antes de migrar. Não soma categorias
sobrepostas. Mapa/ranking de MVI recebem a consulta validada.

Governadores: cadastro editorial de 26/10/2026, com fonte secundária e
filiações a confirmar. Não há integração oficial de mandatos nesta versão.
Governador eleito não substitui ocupante em exercício; revisar antes de uso
institucional. População anual não recalcula taxa criminal de outro período.

Dossiê: Mensalão, Sanguessugas, Cartões, Lava Jato/Petrolão, Pasadena, Banco
Master, Aloprados, Emendas/Operação Make Up. Investigação, condenação,
arquivamento e anulação são situações distintas. Atuação de ministro/órgão
de controle fica separada de pessoas investigadas. Ocorrer numa gestão não
prova envolvimento do presidente ou partido. As fichas têm revisão editorial,
com data do registro jurídico; notícias não alteram conclusões judiciais.

Correção: ferramenta IPCA para cifras em reais com mês-base definido, sem juros
ou câmbio, por produto dos fatores mensais após o mês-base. Exige todos os meses.
Não é ressarcimento judicial. Cifras sem base adequada e dólares não são
corrigidos automaticamente. Bloqueio continua bloqueio após a correção.

Notícias: GDELT DOC 2.0, alternativa Google News RSS, sem chave. Filtros 24h/7d,
deduplicação e rejeição de datas futuras/ausentes. GDELT usa indexação, RSS
publicação informada pelo veículo. Provedores podem limitar consultas e jornais
podem cobrar pelo artigo. Radar fiscal tem cinco assuntos e o programa escolhido.

## Validação e diretrizes

Testes de unidades monetárias, referência anual, combinação de competências,
correção IPCA com mês ausente, fallback de fonte e interface Streamlit: três
abas, seis programas, oito fichas e cinco indicadores. SIOP, Ipeadata e PIB/IBGE
consultados ao vivo em 27/10/2026. BCB apresentou timeouts/502/503 durante testes;
essa falha é sinalizada no aplicativo. Testes de UI precisam permitir sockets
locais; o ambiente restrito do Windows pode bloquear o próprio AppTest.

Os requisitos estão em REQUISITOS_PROJETO.md; a entrada original foi preservada
em DIRETRIZES_FORNECIDAS.md. Funcionalidade disponível não implica que todos os
campos tenham API pública, periodicidade diária ou dados publicados até hoje.
