"""Referências monetárias e simulações transparentes do Observador Brasil."""
import math
import pandas as pd
import streamlit as st


def numero(valor, casas=2):
    return f'{float(valor):,.{casas}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def reais(valor):
    return 'R$ '+numero(valor)


def converter_divida_milhoes(valor):
    """SGS 13761: saldo publicado em milhões de reais."""
    return float(valor)*1_000_000


def juros_compostos(capital, anual_pct, meses):
    if not all(math.isfinite(float(v)) for v in [capital, anual_pct, meses]):
        raise ValueError('Informe números finitos')
    if capital < 0 or meses < 0 or anual_pct <= -100:
        raise ValueError('Capital, prazo ou taxa inválidos')
    saldo = float(capital)*(1+float(anual_pct)/100)**(float(meses)/12)
    return {'saldo':saldo,'juros':saldo-float(capital),
            'mensal_pct':((1+float(anual_pct)/100)**(1/12)-1)*100}


def mensal(serie):
    dados = serie[['data','valor']].copy().sort_values('data')
    dados['periodo'] = dados.data.dt.to_period('M')
    return dados.drop_duplicates('periodo',keep='last').set_index('periodo').sort_index()


def fator_inflacao(serie, inicio, fim):
    dados = mensal(serie)
    esperados = pd.period_range(inicio, fim, freq='M')
    if len(esperados)==0 or not set(esperados).issubset(set(dados.index)):
        raise ValueError('Faltam meses para calcular este período completo')
    taxas = dados.loc[esperados,'valor'].astype(float)
    if taxas.isna().any() or (taxas<=-100).any():
        raise ValueError('Taxa mensal inválida')
    return float((1+taxas/100).prod())


def comparar_salario(salarios, inflacao):
    sm, indice = mensal(salarios), mensal(inflacao)
    comuns = sm.index.intersection(indice.index)
    if len(comuns)==0:
        raise ValueError('Sem mês comum entre salário mínimo e índice')
    fim = comuns.max()
    inicio = fim-12
    if inicio not in sm.index:
        raise ValueError('Falta o salário mínimo do mesmo mês do ano anterior')
    fator = fator_inflacao(inflacao, inicio+1, fim)
    anterior, atual = float(sm.loc[inicio,'valor']), float(sm.loc[fim,'valor'])
    if anterior<=0 or atual<=0:
        raise ValueError('Salário mínimo inválido')
    recomposto = anterior*fator
    return {'inicio':inicio,'fim':fim,'anterior':anterior,'atual':atual,'fator':fator,
            'reajuste_pct':(atual/anterior-1)*100,'inflacao_pct':(fator-1)*100,
            'ganho_real_pct':(atual/anterior/fator-1)*100,'recomposto':recomposto,
            'diferenca':atual-recomposto}


def exibir_divida_reais(resultados):
    st.subheader('Quanto é a dívida em dinheiro?')
    serie = resultados.get('Dívida em reais')
    if serie is None:
        st.info('O saldo da dívida em reais não respondeu nesta consulta. Não estimamos o total multiplicando percentuais arredondados.')
        return
    dados = serie.sort_values('data')
    atual = dados.iloc[-1]
    total = converter_divida_milhoes(atual.valor)
    with st.container(border=True):
        st.metric('Dívida bruta total', 'R$ '+numero(total/1e12,3)+' trilhões')
        st.write('**'+reais(total/1e9)+' bilhões**')
        st.caption(f'Saldo oficial de {atual.data:%m/%Y}. Governo federal, INSS, estados e municípios; não apenas o governo federal.')
    linhas = [{'Informação':'Saldo em reais','Valor':reais(total),'Referência':atual.data.strftime('%m/%Y')}]
    if len(dados)>=2:
        anterior = dados.iloc[-2]
        delta = total-converter_divida_milhoes(anterior.valor)
        linhas.append({'Informação':'Variação desde '+anterior.data.strftime('%m/%Y'),
                       'Valor':('+' if delta>0 else '')+reais(delta),'Referência':atual.data.strftime('%m/%Y')})
    if 'Dívida bruta' in resultados:
        pct = mensal(resultados['Dívida bruta'])
        periodo = atual.data.to_period('M')
        if periodo in pct.index:
            linhas.append({'Informação':'Dívida / PIB no mesmo mês','Valor':numero(pct.loc[periodo,'valor'])+'%','Referência':str(periodo)})
    st.table(pd.DataFrame(linhas).drop(columns='Referência').set_index('Informação'))
    st.caption('Estoque de dívida: não é despesa de um único ano nem a conta anual de juros. A variação do saldo também reflete emissões, resgates, câmbio e outros ajustes.')
    st.markdown('[Fonte: BCB — dívida bruta em reais, SGS 13761](https://www3.bcb.gov.br/sgspub/consultarvalores/consultarValoresSeries.do?method=consultarSeries&series=13761)')


def exibir_selic(resultados):
    serie = resultados.get('Taxa Selic')
    if serie is None:
        st.info('A Selic não respondeu nesta consulta.')
        return
    atual = serie.iloc[-1]
    taxa = float(atual.valor)
    st.write(f'**Selic consultada: {numero(taxa)}% ao ano**, referência {atual.data:%d/%m/%Y}.')
    capital = st.number_input('Valor para simular juros (R$)',min_value=0.0,max_value=1_000_000_000_000.0,value=1000.0,step=100.0,format='%.2f',key='capital_selic')
    meses = st.selectbox('Prazo da simulação',[1,3,6,12,24],index=3,format_func=lambda m:f'{m} '+('mês' if m==1 else 'meses'),key='prazo_selic')
    conta = juros_compostos(capital,taxa,meses)
    st.table(pd.DataFrame([
        {'Informação':'Valor inicial','Em reais':reais(capital)},
        {'Informação':'Juros teóricos no prazo','Em reais':reais(conta['juros'])},
        {'Informação':'Saldo ao final','Em reais':reais(conta['saldo'])},
    ]).set_index('Informação'))
    st.caption(f'Taxa mensal matematicamente equivalente: {numero(conta["mensal_pct"],4)}%. Calculamos (1 + taxa anual) elevado a meses/12; não dividimos a taxa anual por 12.')
    with st.expander('E se a Selic subir ou cair?'):
        mudanca = st.number_input('Mudança hipotética (pontos percentuais)',min_value=-50.0,max_value=50.0,value=1.0,step=.25,format='%.2f',key='choque_selic')
        nova = taxa+mudanca
        if nova<0:
            st.info('Escolha uma mudança que mantenha a taxa simulada em zero ou acima.')
        else:
            alternativa = juros_compostos(capital,nova,meses)
            st.write(f'Com **{numero(nova)}% ao ano**, os juros seriam **{reais(alternativa["juros"])}** no mesmo prazo.')
            st.write(f'Diferença de juros em relação à taxa atual: **{reais(alternativa["juros"]-conta["juros"])}**.')
    st.caption('Simulação matemática à meta Selic constante, sem impostos, tarifas ou inflação. A remuneração de aplicações e o CET de empréstimos dependem do produto. Esta conta não mede o custo da dívida pública inteira, que possui diferentes indexadores e prazos.')


def escolher_indice(resultados, chave, padrao=0):
    opcoes = [nome for nome,fonte in [('IPCA','Inflação no mês'),('INPC','INPC mensal')] if fonte in resultados]
    if not opcoes:
        return None,None
    nome = st.selectbox('Índice de inflação',opcoes,index=min(padrao,len(opcoes)-1),key=chave)
    serie = resultados['Inflação no mês' if nome=='IPCA' else 'INPC mensal']
    st.caption('IPCA: inflação geral. INPC: famílias de 1 a 5 salários mínimos com pessoa de referência assalariada, na cobertura geográfica do índice.')
    return nome,serie


def exibir_precos(resultados):
    nome,serie = escolher_indice(resultados,'indice_precos')
    if serie is None:
        st.info('Nenhum índice mensal disponível para calcular a inflação em reais.')
        return
    fim = mensal(serie).index.max()
    periodo = st.selectbox('Período dos preços',['Último mês publicado','Últimos 12 meses','No ano da referência'],index=1,key='periodo_precos')
    inicio = fim if periodo=='Último mês publicado' else fim-11 if periodo=='Últimos 12 meses' else pd.Period(f'{fim.year}-01',freq='M')
    try:
        fator = fator_inflacao(serie,inicio,fim)
    except ValueError as exc:
        st.info(str(exc)+'. Selecione outro período ou atualize a consulta.')
        return
    valor = st.number_input('Quanto a compra custava no início? (R$)',min_value=0.0,max_value=1_000_000_000.0,value=1000.0,step=100.0,format='%.2f',key='cesta_inflacao')
    st.write(f'**{nome}: {numero((fator-1)*100)}%**, meses de {inicio.strftime("%m/%Y")} a {fim.strftime("%m/%Y")}.')
    st.table(pd.DataFrame([
        {'Informação':'A compra custava','Em reais':reais(valor)},
        {'Informação':'A mesma compra passaria a custar','Em reais':reais(valor*fator)},
        {'Informação':'Diferença no custo','Em reais':reais(valor*(fator-1))},
        {'Informação':'Poder de compra do mesmo dinheiro, a preços do início','Em reais':reais(valor/fator)},
    ]).set_index('Informação'))
    st.caption('Estimativa pela cesta média do índice, desde o início do primeiro mês até o fim do último mês indicado. A inflação do seu orçamento pode ser diferente. O fator acumula as taxas mensais por multiplicação.')


def exibir_salario(resultados):
    salarios = resultados.get('Salário mínimo')
    if salarios is None:
        st.info('O salário mínimo não respondeu nesta consulta.')
        return
    atual = salarios.iloc[-1]
    st.metric('Salário mínimo nominal',reais(atual.valor))
    st.caption(f'Referência {atual.data:%m/%Y} · SGS 1619. Valor bruto mensal nacional.')
    nome,serie = escolher_indice(resultados,'indice_salario',padrao=1)
    if serie is None:
        st.info('Falta a inflação mensal para calcular a comparação.')
        return
    try:
        c = comparar_salario(salarios,serie)
    except ValueError as exc:
        st.info(str(exc)+'. A comparação exige 12 meses completos e salário nas duas pontas.')
        return
    st.write(f'**Comparação no mesmo período: {c["inicio"].strftime("%m/%Y")} → {c["fim"].strftime("%m/%Y")}.**')
    leitura = 'superou a inflação' if c['ganho_real_pct']>0.005 else 'ficou abaixo da inflação' if c['ganho_real_pct']<-.005 else 'acompanhou a inflação'
    st.write(f'O aumento do salário mínimo **{leitura} pelo {nome}** neste período.')
    linhas = [
        ('Salário no início',reais(c['anterior'])),('Salário no fim',reais(c['atual'])),
        ('Aumento em reais',reais(c['atual']-c['anterior'])),
        ('Aumento percentual',numero(c['reajuste_pct'])+'%'),
        ('Inflação no período',numero(c['inflacao_pct'])+'%'),
        ('Salário que reporia a inflação',reais(c['recomposto'])),
        ('Acima/abaixo da reposição',reais(c['diferenca'])),
        ('Ganho/perda real',numero(c['ganho_real_pct'])+'%'),
    ]
    st.table(pd.DataFrame(linhas,columns=['Comparação','Resultado']).set_index('Comparação'))
    st.caption(f'Inflação acumulada de {(c["inicio"]+1).strftime("%m/%Y")} a {c["fim"].strftime("%m/%Y")}. A diferença em reais está a preços do fim do período.')
    with st.expander('Fórmulas e critérios da comparação'):
        st.write('Ganho real = (salário final / salário inicial) / fator de inflação − 1. Salário que reporia a inflação = salário inicial × fator acumulado.')
        st.caption('Comparamos o salário no mesmo mês de anos consecutivos e acumulamos os 12 meses intermediários de inflação. É uma comparação estatística de poder de compra; a regra legal de reajuste do salário mínimo possui critérios próprios.')
    st.markdown('[Salário mínimo — SGS 1619](https://www3.bcb.gov.br/sgspub/consultarvalores/consultarValoresSeries.do?method=consultarSeries&series=1619) · [INPC — IBGE](https://www.ibge.gov.br/estatisticas/economicas/precos-e-custos/9258-indice-nacional-de-precos-ao-consumidor.html)')


def exibir_monetario(resultados):
    st.subheader('Traduza os percentuais para reais')
    juros,precos,salario = st.tabs(['Selic em R$','Inflação em R$','Salário mínimo'])
    with juros:
        exibir_selic(resultados)
    with precos:
        exibir_precos(resultados)
    with salario:
        exibir_salario(resultados)
