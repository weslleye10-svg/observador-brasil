"""Orçamento federal: SIOP/SPARQL e benefícios agregados do Ipeadata.

Sem dados pessoais e sem chaves. Não confundir aportes a fundos com saques.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo
import math
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from dossie import exibir_noticias

TZ=ZoneInfo('America/Sao_Paulo')
SIOP='https://www1.siop.planejamento.gov.br/sparql/'
IPEA='https://www.ipeadata.gov.br/api/odata4/'
PREFIX='PREFIX loa: <http://vocab.e.gov.br/2013/09/loa#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> '
PROGRAMAS={
 'Bolsa Família': {'acoes':['8442'],'nota':'Transferência direta; despesas de gestão não incluídas. Quantidade Ipeadata: posição de dezembro; não representa o mês corrente.','contagem':'FAM_PBF','valor':'VAL_PBF12','unidade':'benefícios/famílias em dezembro','fonte':'https://www.gov.br/mds/pt-br/acoes-e-programas/bolsa-familia'},
 'BPC': {'acoes':['00H5','00IN'],'nota':'O recorte orçamentário inclui BPC e RMV; a série de beneficiários é de BPC. Não dividir essa despesa orçamentária pelo público do BPC.','contagem':'PES_BPC','valor':'VAL_BPC','unidade':'benefícios na posição mensal','fonte':'https://www.gov.br/mds/pt-br/acoes-e-programas/suas/beneficios-assistenciais/beneficio-assistencial-ao-idoso-e-a-pessoa-com-deficiencia-bpc'},
 'Pé-de-Meia': {'acoes':['00W2'],'nota':'Aporte da União ao fundo de incentivo escolar. Pago no SIOP não significa valor sacado pelos estudantes.','fonte':'https://www.gov.br/mec/pt-br/pe-de-meia'},
 'Seguro-Desemprego': {'acoes':['00H4'],'nota':'Recorte da ação Seguro Desemprego, sem incluir automaticamente Seguro-Defeso.','fonte':'https://portalfat.trabalho.gov.br/programas-e-acoes-2/seguro-desemprego-2/'},
 'Auxílio-Gás': {'acoes':['21DV'],'nota':'Ação Auxílio Gás dos Brasileiros. Mudanças de desenho ou novas ações não são somadas automaticamente a este recorte.','fonte':'https://www.gov.br/mds/pt-br/acoes-e-programas/auxilio-gas'},
 'Minha Casa Minha Vida': {'acoes':['00AF','00CY','00CW','00VM'],'nota':'Recorte FAR, FDS e subvenções identificadas. Não é o financiamento habitacional total; exclui FGTS e não mede unidades entregues.','fonte':'https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/habitacao/programa-minha-casa-minha-vida'},
}
FUNCOES={'Saúde':'10','Educação':'12','Segurança Pública':'06'}

def requisitar(url,params=None):
    r=requests.get(url,params=params,timeout=(5,25),headers={'User-Agent':'ObservadorBrasil/4.0','Cache-Control':'no-cache','Accept':'*/*'})
    r.raise_for_status()
    if len(r.content)>20_000_000:raise ValueError('Resposta maior que o limite de 20 MB')
    return r.json()

def numero(v):
    x=float(v)
    if not math.isfinite(x):raise ValueError('Valor numérico inválido')
    return x

def br(v,casas=2):
    return 'Não disponível' if v is None else f'{v:,.{casas}f}'.replace(',','X').replace('.',',').replace('X','.')

def reais(v):
    if v is None:return 'Não disponível'
    return 'R$ '+br(v/1e9)+' bi' if abs(v)>=1e9 else 'R$ '+br(v/1e6)+' mi' if abs(v)>=1e6 else 'R$ '+br(v)

def variacao(atual,anterior):
    return None if atual is None or anterior is None or anterior<=0 else (atual/anterior-1)*100

def query_orcamento(ano):
    ano=int(ano)
    if not 2023<=ano<=datetime.now(TZ).year:raise ValueError('Exercício inválido')
    acoes=sorted({x for p in PROGRAMAS.values() for x in p['acoes']})
    valores='|'.join(acoes)
    return PREFIX+f'''SELECT ?rel ?codigo ?nome ?data (COUNT(?i) AS ?linhas)
      (SUM(?v1) AS ?inicial) (SUM(?v2) AS ?autorizado) (SUM(?v3) AS ?empenhado)
      (SUM(?v4) AS ?liquidado) (SUM(?v5) AS ?pago)
    WHERE {{ GRAPH <http://orcamento.dados.gov.br/{ano}/> {{
      ?i ?rel ?obj .
      ?obj loa:codigo ?codigo; rdfs:label ?nome .
      FILTER((?rel=loa:temFuncao && REGEX(STR(?codigo),"^(06|10|12)$")) || (?rel=loa:temAcao && REGEX(STR(?codigo),"^({valores})$")))
      ?i a loa:ItemDespesa; loa:temExercicio ?ex;
        loa:valorDotacaoInicial ?v1; loa:valorLeiMaisCredito ?v2;
        loa:valorEmpenhado ?v3; loa:valorLiquidado ?v4; loa:valorPago ?v5 .
      ?ex loa:dataUltimaAtualizacao ?data .
    }} }} GROUP BY ?rel ?codigo ?nome ?data ORDER BY ?rel ?codigo'''

def obter_orcamento(ano):
    raw=requisitar(SIOP,{'query':query_orcamento(ano),'format':'application/sparql-results+json'})
    rows=[]
    for r in raw['results']['bindings']:
        d={k:v['value'] for k,v in r.items()}
        d['tipo']='funcao' if d.pop('rel').endswith('temFuncao') else 'acao'
        for k in ['inicial','autorizado','empenhado','liquidado','pago','linhas']:d[k]=numero(d[k])
        rows.append(d)
    if not rows:raise ValueError('O SIOP não retornou dados para este exercício')
    df=pd.DataFrame(rows)
    if df.duplicated(['tipo','codigo']).any():raise ValueError('SIOP retornou múltiplas versões do mesmo código; total não calculado')
    return df

def serie_ipea(codigo):
    permitidos={'FAM_PBF','VAL_PBF12','PES_BPC','VAL_BPC'}
    if codigo not in permitidos:raise ValueError('Série não permitida')
    raw=requisitar(IPEA+f"ValoresSerie(SERCODIGO='{codigo}')")
    if raw.get('@odata.nextLink'):raise ValueError('Série paginada: resposta incompleta, total não utilizado')
    df=pd.DataFrame([{'mes':str(x['VALDATA'])[:7],'valor':numero(x['VALVALOR'])} for x in raw['value']
        if x.get('NIVNOME')=='Brasil' and str(x.get('TERCODIGO'))=='0' and x.get('VALVALOR') is not None])
    if df.empty or df.mes.duplicated().any():raise ValueError('Série nacional ausente ou duplicada')
    # Séries anuais são carimbadas em 1º de janeiro, mas FAM_PBF descreve dezembro.
    if codigo=='FAM_PBF':df['mes']=df.mes.str[:4]+'-12'
    return df[df.mes<=datetime.now(TZ).strftime('%Y-%m')].sort_values('mes')

def combinar_beneficios(qtd,valores):
    # Valores das quatro séries financeiras Ipeadata selecionadas são R$ mil.
    df=qtd.rename(columns={'valor':'quantidade'}).merge(valores.rename(columns={'valor':'mil_reais'}),on='mes',validate='one_to_one')
    df=df[df.quantidade>0].copy()
    df['valor_reais']=df.mil_reais*1000
    df['medio']=df.valor_reais/df.quantidade
    return df.sort_values('mes')

def exibir_evolucao_beneficios(hist,programa):
    st.subheader('Evolução dos benefícios — '+programa)
    anual=programa=='Bolsa Família'
    periodo=st.selectbox('Período para analisar',['Últimos 5 anos','Últimos 10 anos','Série completa'],key='janela_evolucao_beneficios')
    indicador=st.selectbox('Qual informação mostrar no gráfico?',['Quantidade de benefícios','Valor médio por benefício','Valor total da competência'],key='metrica_evolucao_beneficios')
    st.write('Cada ponto mostra **'+indicador.lower()+'**'+(' em **dezembro de cada ano**.' if anual else ' na **competência mensal**.'))
    st.caption('Quantidade mede atendimento, não dinheiro. Média e total são valores em reais. Benefícios não são necessariamente pessoas únicas. Mudanças de desenho e nome do programa podem limitar a comparação histórica.')
    dados=hist.copy().sort_values('mes')
    if periodo!='Série completa':
        anos=5 if periodo=='Últimos 5 anos' else 10
        dados=dados[dados.mes.str[:4].astype(int)>=int(dados.iloc[-1].mes[:4])-anos+1]
    campo={'Quantidade de benefícios':'quantidade','Valor médio por benefício':'medio','Valor total da competência':'valor_reais'}[indicador]
    inicial=dados.iloc[0];final=dados.iloc[-1];diferenca=float(final[campo]-inicial[campo]);pct=variacao(final[campo],inicial[campo])
    fmt=(lambda v:br(v,0)+' benefícios') if campo=='quantidade' else (lambda v:'R$ '+br(v))
    def rotulo(m):return m[:4]+' (dezembro)' if anual else m[5:]+'/'+m[:4]
    with st.container(border=True):
        st.write('**Comparação do período selecionado**')
        st.write('Início · '+rotulo(inicial.mes)+': **'+fmt(inicial[campo])+'**')
        st.write('Último dado · '+rotulo(final.mes)+': **'+fmt(final[campo])+'**')
        sinal='+' if diferenca>=0 else ''
        st.write('Diferença: **'+sinal+fmt(diferenca)+'**'+(' · **'+('+' if pct>=0 else '')+br(pct)+'%**' if pct is not None else ''))
        st.caption('Comparação entre o primeiro e o último ponto exibidos; não é variação anual nem prova de corte, fraude ou revisão cadastral.')
    escala=1e6 if campo=='quantidade' else 1e9 if campo=='valor_reais' else 1
    unidade='Milhões de benefícios' if campo=='quantidade' else 'R$ bilhões na competência' if campo=='valor_reais' else 'R$ por benefício'
    dados['Data']=pd.to_datetime(dados.mes+'-01')
    dados['Valor no eixo']=dados[campo]/escala
    dados['Leitura exata']=dados[campo].map(fmt)
    dados['Referência']=dados.mes.map(rotulo)
    fig=px.line(dados,x='Data',y='Valor no eixo',markers=True,custom_data=['Referência','Leitura exata'])
    fig.update_traces(line=dict(color='#38bdf8',width=3),marker=dict(size=7),hovertemplate='%{customdata[0]}<br><b>%{customdata[1]}</b><extra></extra>')
    datas=dados.iloc[::max(1,len(dados)//4)]
    if datas.iloc[-1].mes!=dados.iloc[-1].mes:datas=pd.concat([datas,dados.tail(1)])
    fig.update_xaxes(title='Ano — posição de dezembro' if anual else 'Mês de referência',tickvals=datas.Data,ticktext=datas.mes.map(lambda m:m[:4] if anual else m[5:]+'/'+m[:4]),tickangle=0,fixedrange=True)
    ajustar=st.toggle('Destacar variações com escala ajustada',False,key='escala_evolucao_beneficios')
    fig.update_yaxes(title=unidade,rangemode='normal' if ajustar else 'tozero',tickformat=',.1f' if escala>1 else ',.0f',fixedrange=True,automargin=True)
    fig.update_layout(height=330,separators=',.',margin=dict(l=15,r=15,t=15,b=20),showlegend=False,dragmode=False)
    st.plotly_chart(fig,width='stretch',config={'displayModeBar':False,'scrollZoom':False})
    st.caption('Escala ajustada: o eixo vertical pode não começar em zero; isso amplia visualmente as diferenças.' if ajustar else 'Eixo vertical começa em zero. Valores em milhões/bilhões conforme a unidade indicada. Não é necessário ampliar o gráfico para consultar os números abaixo.')
    st.write('**Valores exatos — últimos pontos do período**')
    tabela=dados.tail(12).iloc[::-1].copy()
    tabela['Quantidade']=tabela.quantidade.map(lambda x:br(x,0))
    tabela['Média (R$)']=tabela.medio.map(lambda x:'R$ '+br(x))
    tabela['Total (R$ bilhões)']=tabela.valor_reais.map(lambda x:br(x/1e9,3))
    st.dataframe(tabela[['Referência','Quantidade','Média (R$)','Total (R$ bilhões)']],hide_index=True,width='stretch')
    st.caption('Total e média são nominais, sem descontar inflação. Fonte: Ipeadata/MDS, séries nacionais; referência indicada em cada linha.')

def sgs(codigo):
    if codigo not in (1207,433,1619):raise ValueError('Série não permitida')
    quantidade=40 if codigo==1207 else 36 if codigo==1619 else 500
    raw=requisitar(f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/{quantidade}',{'formato':'json'})
    df=pd.DataFrame(raw); df['data']=pd.to_datetime(df['data'],format='%d/%m/%Y');df['valor']=pd.to_numeric(df['valor'])
    return df[df.data<=pd.Timestamp(datetime.now(TZ).date())].sort_values('data')

def pib_anual():
    raw=requisitar('https://apisidra.ibge.gov.br/values/t/6784/n1/1/v/9808/p/all')
    rows=[]
    for r in raw[1:]:
        if str(r['MC'])!='1550':raise ValueError('Unidade do PIB mudou; esperado milhões de reais')
        rows.append({'data':pd.Timestamp(int(r['D3C']),1,1),'valor':numero(r['V'])})
    if not rows:raise ValueError('PIB anual ausente')
    return pd.DataFrame(rows).sort_values('data')

def total_recorte(df,tipo,codigos):
    if df is None:return None
    parte=df[(df.tipo==tipo)&df.codigo.isin(codigos)]
    # Ação ausente não vira gasto zero. Exibir o recorte completo apenas se todos vieram.
    if set(parte.codigo)!=set(codigos):return None
    return {k:float(parte[k].sum()) for k in ['inicial','autorizado','empenhado','liquidado','pago']}|{'data':', '.join(sorted(set(parte.data)))}

def carregar_financas(ano):
    tarefas={'atual':lambda:obter_orcamento(ano),'anterior':lambda:obter_orcamento(ano-1),'pib':pib_anual,'ipca':lambda:sgs(433),'minimo':lambda:sgs(1619)}
    for c in ['FAM_PBF','VAL_PBF12','PES_BPC','VAL_BPC']:tarefas[c]=lambda c=c:serie_ipea(c)
    dados={};erros={}
    with ThreadPoolExecutor(max_workers=9) as pool:
        futuros={pool.submit(fn):nome for nome,fn in tarefas.items()}
        for f in as_completed(futuros):
            nome=futuros[f]
            try:dados[nome]=f.result()
            except (requests.RequestException,ValueError,KeyError,TypeError) as e:erros[nome]=type(e).__name__+': '+str(e)[:180]
    return {'dados':dados,'erros':erros,'hora':datetime.now(TZ)}

def card_orcamento(nome,atual,anterior,ano):
    with st.container(border=True):
        st.subheader(nome)
        if atual is None:
            st.warning('Recorte não disponível integralmente no SIOP. Não é gasto zero.')
            return
        delta=variacao(atual['inicial'],anterior['inicial'] if anterior else None)
        st.metric(f'LOA inicial de {ano}',reais(atual['inicial']),None if delta is None else ('+' if delta>=0 else '')+br(delta)+f'% vs LOA inicial {ano-1}',delta_color='off')
        if delta is not None:
            st.badge('Expansão nominal da LOA' if delta>0 else 'Redução nominal da LOA' if delta<0 else 'LOA nominal estável',color='green' if delta>0 else 'orange' if delta<0 else 'gray')
        st.metric('Autorizado — lei + créditos',reais(atual['autorizado']))
        st.metric('Pago no exercício',reais(atual['pago']))
        if atual['autorizado']>0:
            fracao=atual['pago']/atual['autorizado']
            st.progress(max(0.,min(1.,fracao)),text=br(fracao*100)+'% do autorizado pago')
        mudanca=variacao(atual['autorizado'],atual['inicial'])
        if mudanca is not None:st.caption('Créditos/alterações sobre a LOA inicial: '+('+' if mudanca>=0 else '')+br(mudanca)+'%. Não mede contingenciamento.')
        try:data_fonte=datetime.fromisoformat(atual['data']).astimezone(TZ).strftime('%d/%m/%Y às %H:%M')
        except ValueError:data_fonte=atual['data']
        st.caption('Base SIOP atualizada em: '+data_fonte+' (Brasília)')

@st.fragment(run_every='5m')
def exibir_orcamento():
    st.header('Economia, Orçamento e Benefícios Sociais')
    st.caption('União • valores nominais em reais • despesas do exercício, sem restos a pagar de exercícios anteriores')
    ano=st.selectbox('Exercício orçamentário',list(range(datetime.now(TZ).year,2023,-1)),key='ano_orcamento')
    cache=st.session_state.setdefault('financas_cache',{})
    refresh=st.button('Atualizar orçamento e benefícios',key='refresh_orcamento')
    if refresh or ano not in cache or (datetime.now(TZ)-cache[ano]['hora']).total_seconds()>=300:
        with st.spinner('Consultando SIOP, Ipeadata e Banco Central…'):cache[ano]=carregar_financas(ano)
    pacote=cache[ano];d=pacote['dados']
    st.caption(f'Consulta: {pacote["hora"]:%d/%m/%Y às %H:%M} (Brasília). Cada indicador tem sua própria referência.')
    st.subheader('Saúde, Educação e Segurança Pública')
    st.caption('Compare quanto foi previsto, autorizado e pago. Os valores abaixo são da União.')
    with st.expander('Como ler o orçamento e as comparações'):
        st.write('LOA inicial é a previsão anual. Autorizado inclui alterações legais. Empenhado é compromisso; liquidado reconhece a entrega; pago é desembolso. A execução parcial do ano não é comparada ao total pago no ano anterior.')
    resumo=[]
    for nome,c in FUNCOES.items():
        atual=total_recorte(d.get('atual'),'funcao',[c]);anterior=total_recorte(d.get('anterior'),'funcao',[c])
        card_orcamento(nome,atual,anterior,ano)
        if atual:resumo.append({'Área':nome,**{k:atual[k] for k in ['inicial','autorizado','empenhado','liquidado','pago']}})
    if resumo:
        df=pd.DataFrame(resumo)
        st.subheader('Orçamento previsto, autorizado e pago')
        st.caption(f'União · exercício {ano} · colunas em R$ bilhões. Previsto = LOA inicial; autorizado = lei + créditos; pago = desembolso no exercício.')
        long=df.melt(id_vars='Área',value_vars=['inicial','autorizado','pago'],var_name='Estágio',value_name='Reais')
        long['Estágio']=long['Estágio'].map({'inicial':'Previsto','autorizado':'Autorizado','pago':'Pago'})
        long['R$ bilhões']=long.Reais/1e9
        long['Valor resumido']=long.Reais.map(lambda v:'R$ '+br(v/1e9)+' bilhões')
        long['Valor exato']=long.Reais.map(lambda v:'R$ '+br(v))
        fig=px.bar(long,x='Área',y='R$ bilhões',color='Estágio',barmode='group',
            category_orders={'Estágio':['Previsto','Autorizado','Pago']},
            color_discrete_map={'Previsto':'#87cefa','Autorizado':'#0070c9','Pago':'#ffaaaa'},
            custom_data=['Área','Estágio','Valor resumido','Valor exato'])
        fig.update_traces(hovertemplate='<b>%{customdata[0]} · %{customdata[1]}</b><br>%{customdata[2]}<br><br>Valor exato: %{customdata[3]}<extra></extra>')
        fig.update_layout(separators=',.',hoverlabel=dict(font_size=14,align='left'),legend=dict(title_text='',orientation='h',y=1.16),margin=dict(l=10,r=10,t=70,b=10))
        fig.update_xaxes(title=None,fixedrange=True)
        fig.update_yaxes(title='R$ bilhões',rangemode='tozero',fixedrange=True)
        st.plotly_chart(fig,width='stretch',config={'displayModeBar':False,'scrollZoom':False})
        st.write('**Leitura rápida — valores em R$ bilhões**')
        leitura=df[['Área','inicial','autorizado','pago']].rename(columns={'inicial':'Previsto','autorizado':'Autorizado','pago':'Pago'}).copy()
        for coluna in ['Previsto','Autorizado','Pago']:leitura[coluna]=leitura[coluna].map(lambda v:br(v/1e9))
        st.table(leitura.set_index('Área'))
        st.caption('Exemplo de leitura: 251,84 significa R$ 251,84 bilhões. Passe o mouse ou toque numa coluna para ver também o valor completo em reais.')
        with st.expander('Valores exatos e download do orçamento'):
            st.dataframe(df,width='stretch',hide_index=True)
            st.download_button('Baixar orçamento em CSV',df.to_csv(index=False,sep=';',decimal=','),'orcamento.csv','text/csv')
    st.link_button('Fonte e documentação: SIOP', 'https://www1.siop.planejamento.gov.br/siopdoc/doku.php?id=acesso_publico:dados_abertos')
    st.subheader('Benefícios e habitação')
    colunas=st.columns(2)
    for i,nome in enumerate(list(PROGRAMAS)[:4]):
        with colunas[i%2]:
            with st.container(border=True):
                st.write('**'+nome+'**')
                rec=total_recorte(d.get('atual'),'acao',PROGRAMAS[nome]['acoes'])
                st.metric('Autorizado no exercício',reais(rec['autorizado']) if rec else 'Não disponível')
                if st.button('Abrir detalhes de '+nome,key='abrir_'+str(i)):
                    st.session_state['programa_social']=nome
    programa=st.selectbox('Programa social',list(PROGRAMAS),key='programa_social')
    p=PROGRAMAS[programa];atual=total_recorte(d.get('atual'),'acao',p['acoes']);anterior=total_recorte(d.get('anterior'),'acao',p['acoes'])
    card_orcamento(programa,atual,anterior,ano)
    st.caption('Ações orçamentárias: '+', '.join(p['acoes'])+'. '+p['nota'])
    if atual and 'pib' in d:
        # SIDRA 6784/9808, unidade validada em milhões de reais; mesmo exercício.
        pib=d['pib'];pib=pib[pib.data.dt.year==ano]
        if len(pib)==1 and pib.iloc[0].valor>0:st.metric(f'Pago em {ano} / PIB anual de {ano}',br(atual['pago']/(pib.iloc[0].valor*1e6)*100,3)+'%')
        else:st.caption(f'Pago/PIB de {ano}: não calculado enquanto o PIB anual desse exercício não estiver publicado. Não usamos PIB de outro ano.')
        st.link_button('PIB anual — IBGE/SIDRA 6784','https://sidra.ibge.gov.br/tabela/6784')
    if p.get('contagem') in d and p.get('valor') in d:
        hist=combinar_beneficios(d[p['contagem']],d[p['valor']])
        if not hist.empty:
            r=hist.iloc[-1];ant=hist[hist.mes==f'{int(r.mes[:4])-1}{r.mes[4:]}'];a=ant.iloc[-1] if not ant.empty else None
            with st.container(border=True):
                st.write('**Público e valor médio — mesma competência**')
                st.metric('Quantidade de benefícios',br(r.quantidade,0),None if a is None else br(variacao(r.quantidade,a.quantidade))+'% em 12 meses',delta_color='off')
                st.metric('Média por benefício',reais(r.medio),None if a is None else br(variacao(r.medio,a.medio))+'% nominal em 12 meses',delta_color='off')
                st.caption('Referência: '+r.mes+' · '+p['unidade']+'. Média = valor da competência / benefícios da mesma competência. Fontes: Ipeadata/MDS/Portal da Transparência, valores monetários convertidos de R$ mil.')
                st.write('Valor total da competência: **'+reais(r.valor_reais)+'**')
                if a is not None and 'ipca' in d:
                    ipca=d['ipca'].copy();ipca['mes']=ipca.data.dt.strftime('%Y-%m');jan=ipca[(ipca.mes>a.mes)&(ipca.mes<=r.mes)]
                    if len(jan)==12 and jan.mes.nunique()==12:
                        fator=float((1+jan.valor/100).prod());ganho=(r.medio/a.medio/fator-1)*100
                        st.write('Variação real da média, descontado o IPCA desses 12 meses: **'+br(ganho)+'%**.')
                if 'minimo' in d:
                    sm=d['minimo'];sm=sm[sm.data.dt.strftime('%Y-%m')==r.mes]
                    if not sm.empty:st.write('Média / salário mínimo da competência: **'+br(r.medio/sm.iloc[-1].valor*100)+'%**.')
            exibir_evolucao_beneficios(hist,programa)
            with st.expander('Série de beneficiários e valores'):
                st.dataframe(hist[['mes','quantidade','valor_reais','medio']],hide_index=True,width='stretch')
                st.download_button('Baixar benefícios em CSV',hist.to_csv(index=False,sep=';',decimal=','),'beneficios.csv','text/csv')
    else:
        st.metric('Público atendido','Não disponível via integração')
        st.metric('Ticket médio','Não disponível via integração')
        st.caption('As fontes públicas integradas não fornecem uma série nacional compatível para estes campos. Não dividimos orçamento anual pelo número de pessoas de outro período.')
    st.write('**Fila, bloqueios, cancelamentos e reajustes:** consulte os registros oficiais e o radar abaixo. Esses eventos não são inferidos da variação de despesa ou do número de benefícios.')
    st.table(pd.DataFrame([
        {'Campo':'Fila de espera','Situação':'Sem série nacional compatível na integração; não significa fila zero.'},
        {'Campo':'Bloqueios e cancelamentos','Situação':'Não inferidos da queda do público; consultar registros administrativos.'},
        {'Campo':'Contingenciamento','Situação':'Não equivale à diferença entre autorizado e pago; consultar decreto/relatório fiscal.'}
    ]).set_index('Campo'))
    if programa=='BPC':st.caption('Referência de valor: o BPC é vinculado ao salário mínimo. A média observada na folha pode diferir; não substitui análise individual de concessão.')
    if programa=='Seguro-Desemprego':
        st.link_button('MTE — painel oficial de público, parcelas e valores','https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/estatisticas-trabalho/seguro-desemprego/seguro-desemprego')
    if programa=='Pé-de-Meia':
        st.caption('Referência documental (não automática): CAIXA, 21/09/2026, cerca de 4 milhões de estudantes no calendário; parcela de frequência de R$ 200 no ensino regular ou R$ 225 na EJA. Não é ticket médio calculado.')
        st.link_button('CAIXA — calendário e público informado','https://caixanoticias.caixa.gov.br/Paginas/Not%C3%ADcias/2026/09-SETEMBRO/CAIXA-inicia-pagamento-de-nova-parcela-do-programa-pe-de-meia-nesta-segunda-feira%2821%29.aspx')
    st.link_button('Portal oficial do programa',p['fonte'])
    with st.expander('Base constitucional e limites da análise fiscal'):
        st.write('CF/88: arts. 6º (direitos sociais), 165–169 (orçamento), 196 e 198 (saúde), 203, V (assistência/BPC), 205 e 212 (educação) e 144 (segurança). O cumprimento de pisos não é calculado apenas pela função orçamentária.')
        st.write('Tese favorável: controle de elegibilidade e autorização legislativa permitem focalização e prestação de contas. Limites: devido processo, defesa e proteção social impedem tratar uma oscilação de gasto como autorização para supressão de direitos.')
        st.write('Precedente: RE 567.985, Tema 27, STF — critério econômico do BPC. Não estabelece resultado automático para cada requerimento. O painel não julga elegibilidade individual.')
        st.link_button('STF — Tema 27','https://portal.stf.jus.br/jurisprudenciaRepercussao/verAndamentoProcesso.asp?incidente=2569060&numeroProcesso=567985&classeProcesso=RE&numeroTema=27')
    st.subheader('Radar de notícias orçamentárias')
    termo=st.selectbox('Assunto do radar',['corte de gastos','pente-fino bolsa família','reajuste BPC','déficit fiscal','contingenciamento de verbas',programa],key='radar_orcamento')
    exibir_noticias(termo,prefixo='orcamento')
    if pacote['erros']:
        with st.expander('Disponibilidade e falhas das fontes'):
            for nome,erro in pacote['erros'].items():st.text(nome+': '+erro)
