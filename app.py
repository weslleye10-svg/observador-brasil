# Instalar: python -m pip install -r requirements.txt
# Executar: python -m streamlit run app.py
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).parent
TZ = ZoneInfo('America/Sao_Paulo')
BASE = json.loads((ROOT / 'dados_estaduais.json').read_text(encoding='utf8'))
UF_BASE = pd.DataFrame(BASE['dados'])
CONFIG = {
    'Dívida bruta': (13762, '% do PIB', 'Parcela da produção anual equivalente à dívida do governo.', 75),
    'Taxa Selic': (432, '% ao ano', 'Meta da taxa básica de juros definida pelo Banco Central.', 10),
    'Inflação no mês': (433, '% no mês', 'Variação dos preços medida pelo IPCA naquele mês.', 65),
    'Inflação em 12 meses': (13522, '% em 12 meses', 'Variação acumulada do IPCA nos últimos 12 meses.', 65),
}
INDICADORES = {
    'População': ('pop_ref', 'habitantes', 'populacao'),
    'Pobreza (%)': ('pobreza_ref', '% da população', 'pobreza'),
    'Analfabetismo (%)': ('educacao_ref', '% das pessoas de 15 anos ou mais', 'educacao'),
    'Violência (por 100 mil)': ('violencia_ref', 'mortes violentas intencionais por 100 mil habitantes', 'violencia'),
}

st.set_page_config(page_title='Observador Brasil', page_icon='🇧🇷', layout='wide', initial_sidebar_state='collapsed')
st.markdown('''<style>
.block-container{max-width:1120px;padding-top:2rem;padding-bottom:3rem}
[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums}
[data-testid="stMetricLabel"] p{font-weight:600}
@media(max-width:640px){.block-container{padding:1rem .85rem 3rem}h1{font-size:1.7rem!important}h2{font-size:1.35rem!important}h3{font-size:1.15rem!important}[data-testid="stMetricValue"]{font-size:2rem!important}}
</style>''', unsafe_allow_html=True)
st.title('Observador Brasil')
st.caption('Economia e estados • valores exatos, fontes e datas em cada consulta')
with st.sidebar:
    st.header('Consulta')
    anos = st.slider('Histórico econômico (anos)', 1, 9, 3)
    automatico = st.toggle('Atualizar a cada 5 minutos', True)
    if st.button('Atualizar dados agora', type='primary'):
        st.session_state.pop('consulta', None)
    st.caption('Cada nova sessão consulta as APIs. Os valores publicados pelas fontes têm periodicidades diferentes.')


def br(valor, casas=2):
    if valor is None or pd.isna(valor):
        return 'Não disponível'
    return f'{float(valor):,.{casas}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def resposta_api(url, params=None):
    with requests.Session() as session:
        retry = Retry(total=1, backoff_factor=.3, status_forcelist=[429, 500, 502, 503, 504], respect_retry_after_header=False)
        session.mount('https://', HTTPAdapter(max_retries=retry))
        r = session.get(url, params=params, timeout=(5, 20), headers={'Cache-Control':'no-cache', 'User-Agent':'ObservadorBrasil/2.0'})
        r.raise_for_status()
        return r


def obter_sgs(codigo, inicio, fim):
    limitado = False
    try:
        raw = resposta_api(f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados', {
            'formato':'json', 'dataInicial':inicio.strftime('%d/%m/%Y'), 'dataFinal':fim.strftime('%d/%m/%Y')}).json()
    except (requests.RequestException, ValueError):
        # Uma falha no histórico não impede consultar as últimas observações.
        raw = resposta_api(f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/20', {'formato':'json'}).json()
        limitado = True
    df = pd.DataFrame(raw)
    if df.empty or not {'data', 'valor'}.issubset(df.columns):
        raise ValueError('Série SGS sem observações válidas')
    df['data'] = pd.to_datetime(df.data, format='%d/%m/%Y', errors='raise')
    df['valor'] = pd.to_numeric(df.valor.astype(str).str.replace(',', '.', regex=False), errors='raise')
    df = df[df.data <= pd.Timestamp(fim)].dropna().drop_duplicates('data').sort_values('data')
    if df.empty:
        raise ValueError('Série sem observações no período')
    df = df.reset_index(drop=True)
    df.attrs['historico_limitado'] = limitado
    return df


def obter_sidra(tabela, variavel, filtros=''):
    url = f'https://apisidra.ibge.gov.br/values/t/{tabela}/n3/all/v/{variavel}/p/last{filtros}'
    raw = resposta_api(url).json()
    if not isinstance(raw, list) or len(raw) != 28:
        raise ValueError('Esperadas 27 UFs no SIDRA')
    registros = [{'codigo':str(r['D1C']), 'valor':pd.to_numeric(r['V'], errors='raise'), 'ano':str(r['D3N'])} for r in raw[1:]]
    df = pd.DataFrame(registros)
    if df.codigo.duplicated().any() or set(df.codigo) != set(UF_BASE.codigo):
        raise ValueError('Códigos estaduais inválidos')
    if df.valor.isna().any() or (df.valor < 0).any() or (tabela != 6579 and (df.valor > 100).any()):
        raise ValueError('Valores estaduais inválidos')
    return df


def obter_agenda(hoje):
    itens, mais = [], False
    for pagina in range(1, 6):
        raw = resposta_api('https://dadosabertos.camara.leg.br/api/v2/eventos', {
            'dataInicio':hoje.isoformat(), 'dataFim':(hoje+timedelta(days=6)).isoformat(),
            'ordem':'ASC', 'ordenarPor':'dataHoraInicio', 'itens':100, 'pagina':pagina}).json()
        if not isinstance(raw.get('dados'), list):
            raise ValueError('Formato de agenda inválido')
        itens.extend(raw['dados'])
        mais = any(link.get('rel') == 'next' for link in raw.get('links', []))
        if not mais:
            break
    df = pd.DataFrame(itens)
    if not df.empty:
        df = df.drop_duplicates('id').sort_values('dataHoraInicio')
    return df, mais


def consultar(agora):
    inicio = agora.date() - timedelta(days=365*anos)
    resultados, erros = {}, {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        tarefas = {pool.submit(obter_sgs, c[0], inicio, agora.date()): nome for nome,c in CONFIG.items()}
        tarefas[pool.submit(obter_sidra, 6579, 9324)] = 'populacao'
        tarefas[pool.submit(obter_sidra, 5877, 9948)] = 'pobreza'
        tarefas[pool.submit(obter_sidra, 7113, 10267, '/c2/6794/c58/2795')] = 'educacao'
        tarefas[pool.submit(obter_agenda, agora.date())] = 'agenda'
        for tarefa in as_completed(tarefas):
            nome = tarefas[tarefa]
            try:
                resultados[nome] = tarefa.result()
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                erros[nome] = str(exc)
    return {'resultados':resultados, 'erros':erros, 'hora':datetime.now(TZ), 'anos':anos}


def tabela_economica(df, codigo):
    # Selic: última meta observada em cada mês; demais séries já são mensais.
    dados = df.groupby(df.data.dt.to_period('M'), sort=True).tail(1).copy()
    dados['Referência'] = dados.data.dt.strftime('%m/%Y')
    dados['Valor exato'] = dados.valor.map(lambda v: br(v)+'%')
    dados['Variação (p.p.)'] = dados.valor.diff().map(lambda v: '—' if pd.isna(v) else br(v)+' p.p.')
    return dados[['Referência', 'Valor exato', 'Variação (p.p.)']].iloc[::-1].reset_index(drop=True)


def exibir_economia(resultados, hora):
    st.header('Economia')
    st.caption(f'Última consulta: {hora:%d/%m/%Y às %H:%M} • horário de Brasília')
    cols = st.columns(2)
    for i,(nome,(codigo, unidade, explicacao, limite)) in enumerate(CONFIG.items()):
        with cols[i%2]:
            with st.container(border=True):
                if nome not in resultados:
                    st.metric(nome, 'Indisponível')
                    st.caption('Não foi possível consultar a fonte agora.')
                    continue
                atual = resultados[nome].iloc[-1]
                st.metric(nome, br(atual.valor)+'%')
                ref = atual.data.strftime('%d/%m/%Y' if codigo == 432 else '%m/%Y')
                st.caption(f'{unidade} · referência {ref}')
                fim_ref = atual.data if codigo == 432 else atual.data + pd.offsets.MonthEnd(0)
                if (pd.Timestamp(hora.date())-fim_ref).days > limite:
                    st.warning('Referência antiga. Consulte o calendário da fonte.')
    disponiveis = [nome for nome in CONFIG if nome in resultados]
    if not disponiveis:
        return
    nome = st.selectbox('Qual indicador você quer acompanhar?', disponiveis, key='grafico_indicador')
    codigo, unidade, explicacao, _ = CONFIG[nome]
    df = resultados[nome].copy()
    st.write(explicacao)
    if df.attrs.get('historico_limitado'):
        st.info('O histórico completo não respondeu. Exibindo as últimas observações obtidas diretamente no BCB nesta consulta.')
    zoom = st.toggle('Habilitar zoom no gráfico', value=False, key='zoom_grafico')
    df['referencia'] = df.data.dt.strftime('%d/%m/%Y' if codigo == 432 else '%m/%Y')
    df['exato'] = df.valor.map(lambda v: br(v)+'%')
    fig = go.Figure(go.Scatter(x=df.data, y=df.valor, mode='lines', line=dict(color='#38bdf8',width=3),
        customdata=df[['referencia','exato']], hovertemplate='<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>'))
    fig.update_layout(height=320, margin=dict(l=10,r=15,t=15,b=20), separators=',.', hovermode='x unified',
        dragmode='zoom' if zoom else False, showlegend=False,
        xaxis=dict(title='Data',tickformat='%m/%Y',nticks=4,fixedrange=not zoom),
        yaxis=dict(title=unidade,ticksuffix='%',tickformat='.2f',nticks=5,fixedrange=not zoom))
    st.plotly_chart(fig, width='stretch', config={'displayModeBar':zoom,'scrollZoom':False,'displaylogo':False})
    st.caption('Eixo horizontal: data. Eixo vertical: percentual. Toque na linha para consultar o valor. A escala vertical acompanha o intervalo selecionado; não representa proporção de uma área.')
    tab = tabela_economica(df, codigo)
    st.subheader('Valores exatos — sem precisar ampliar')
    st.caption('Últimas observações mensais. Na Selic, usamos a última meta registrada em cada mês. Variação em pontos percentuais (p.p.) em relação à observação mensal anterior.')
    st.dataframe(tab.head(12), hide_index=True, width='stretch')
    with st.expander('Ver todo o histórico e baixar CSV'):
        st.dataframe(tab, hide_index=True, width='stretch')
        st.download_button('Baixar histórico deste indicador', df[['data','valor']].to_csv(index=False,decimal=',',sep=';').encode('utf-8-sig'), f'sgs_{codigo}.csv', mime='text/csv')
    with st.expander('Como interpretar estes números?'):
        st.write('**Dívida bruta:** percentual do PIB devido pelo governo geral. Não é uma porcentagem do orçamento.')
        st.write('**Selic:** meta anual da taxa básica de juros. Não é rendimento mensal de uma aplicação.')
        st.write('**IPCA no mês:** mudança dos preços naquele mês. **IPCA em 12 meses:** inflação acumulada ao longo de 12 meses.')
        st.write('**Pontos percentuais:** passar de 10% para 11% é aumentar 1 p.p. O gráfico pode começar acima de zero; consulte os valores exatos para comparar.')
    st.markdown('[Fonte: Banco Central — SGS](https://www3.bcb.gov.br/sgspub/) · [IPCA: IBGE](https://www.ibge.gov.br/indicadores/inflacao)')


def montar_estados(resultados):
    dados = UF_BASE.copy()
    avisos = []
    for chave,coluna,ref in [('populacao','População','pop_ref'),('pobreza','Pobreza (%)','pobreza_ref'),('educacao','Analfabetismo (%)','educacao_ref')]:
        if chave in resultados:
            novo = resultados[chave].set_index('codigo')
            dados[coluna] = dados.codigo.map(novo.valor)
            dados[ref] = dados.codigo.map(novo.ano)
        else:
            avisos.append(chave)
    return dados, avisos


def exibir_estados(resultados):
    st.header('Brasil por estado')
    st.write('Escolha um estado para ver os dados completos. A tabela continua disponível mesmo sem o mapa.')
    dados, avisos = montar_estados(resultados)
    if avisos:
        st.info('IBGE indisponível para '+', '.join(avisos)+f'. Exibindo a base verificada em {BASE["verificado_em"]}, com o ano de cada indicador abaixo. Não é uma consulta ao vivo desses campos.')
    estado = st.selectbox('Estado', sorted(dados.Estado), key='estado_escolhido')
    row = dados[dados.Estado == estado].iloc[0]
    detalhes = []
    for indicador,(ref,unidade,fonte) in INDICADORES.items():
        exato = br(row[indicador],0 if indicador=='População' else 1)
        if '(%)' in indicador:
            exato += '%'
        detalhes.append({'Indicador':indicador, 'Valor':exato, 'Referência':str(row[ref])})
    st.subheader(estado)
    st.table(pd.DataFrame(detalhes).set_index('Indicador'))
    st.caption('População em habitantes. Pobreza e analfabetismo em %. Violência em mortes violentas intencionais por 100 mil habitantes — não é porcentagem.')
    st.write(f'**Governador registrado:** {row["Governador registrado"]} · **Partido na fonte:** {row["Partido na fonte"]}')
    st.caption('Cadastro nominal de referência consultado em 26/10/2026, sem atualização automática de mandatos. Fonte secundária; não confundir com governador eleito para 2027.')
    with st.expander('Fontes e definições deste estado'):
        for indicador,(ref,unidade,fonte) in INDICADORES.items():
            st.markdown(f'**{indicador} ({row[ref]}):** [{unidade}]({BASE["fontes"][fonte]})')
        st.write('Pobreza: indicador ODS 1.2.1 da tabela SIDRA 5877, conforme a linha e a metodologia publicadas pelo IBGE. Analfabetismo: pessoas de 15 anos ou mais, sexo total, PNAD Contínua.')
        st.write('Violência: Anuário Brasileiro de Segurança Pública 2026, tabela 01, dados de 2025. Base anual consolidada; não representa ocorrências de hoje.')
        for nota in BASE['notas_mvi']:
            st.caption(nota)
        st.markdown(f'[Cadastro de governadores — fonte consultada]({BASE["fontes"]["governos"]})')
        st.caption(BASE['nota_governos'])
    indicador = st.selectbox('O que comparar entre os estados?', list(INDICADORES), key='mapa_indicador')
    ref,unidade,fonte = INDICADORES[indicador]
    ordenados = dados.sort_values(indicador,ascending=False).copy()
    ordenados['Valor exato'] = ordenados[indicador].map(lambda v: br(v,0 if indicador=='População' else 1)+('%' if '(%)' in indicador else ''))
    ordenados['Ano'] = ordenados[ref]
    st.subheader('Comparação em tabela')
    st.caption(f'{indicador} · {unidade}. Ordenação do maior para o menor; comparação descritiva, sem atribuição de responsabilidade ao governante atual.')
    st.dataframe(ordenados[['Estado','Valor exato','Ano']], hide_index=True, width='stretch', height=330)
    st.download_button('Baixar dados das 27 UFs',dados.to_csv(index=False,sep=';',decimal=',').encode('utf-8-sig'),'estados.csv',mime='text/csv')
    with st.expander('Abrir mapa interativo', expanded=False):
        geo = json.loads((ROOT/'brasil_uf.geojson').read_text(encoding='utf8'))
        for f in geo['features']:
            f['properties']['codarea'] = str(f['properties']['codarea'])
        ordenados['leitura'] = ordenados['Valor exato']+' · '+ordenados['Ano'].astype(str)
        # Desenha os polígonos locais diretamente: sem tiles ou TopoJSON externos.
        fig = go.Figure()
        baixo, alto = float(ordenados[indicador].min()), float(ordenados[indicador].max())
        por_codigo = ordenados.set_index('codigo')
        for feature in geo['features']:
            registro = por_codigo.loc[str(feature['properties']['codarea'])]
            t = (float(registro[indicador])-baixo)/(alto-baixo) if alto>baixo else .5
            cor = px.colors.sample_colorscale('Blues', [.2+.8*t])[0]
            geometria = feature['geometry']
            poligonos = [geometria['coordinates']] if geometria['type']=='Polygon' else geometria['coordinates']
            for poligono in poligonos:
                contorno = poligono[0]
                fig.add_trace(go.Scatter(x=[pt[0] for pt in contorno],y=[pt[1] for pt in contorno],
                    mode='lines',fill='toself',fillcolor=cor,legendgroup=registro['UF'],
                    line=dict(color='#38bdf8' if registro['Estado']==estado else '#64748b',
                              width=2 if registro['Estado']==estado else .7),
                    text=f"<b>{registro['Estado']}</b><br>{registro['leitura']}",
                    hoverinfo='text',hoveron='fills',showlegend=False))
        fig.update_layout(height=440,margin=dict(l=5,r=5,t=5,b=5),dragmode=False,
            paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(visible=False,fixedrange=True,range=[-75,-33]),
            yaxis=dict(visible=False,fixedrange=True,range=[-35,6],scaleanchor='x',scaleratio=1))
        st.plotly_chart(fig,width='stretch',config={'displayModeBar':False,'scrollZoom':False})
        st.caption(f'Tons mais escuros indicam valores maiores. Intervalo: {br(baixo,0 if indicador=="População" else 1)} a {br(alto,0 if indicador=="População" else 1)} {unidade}. Contorno azul: estado escolhido.')
        st.caption('Toque no estado para ver o valor. Para consultar todos os indicadores sem gestos de zoom, use o seletor Estado acima. Geometria oficial do IBGE incluída no projeto.')


def exibir_agenda(resultados):
    st.header('Câmara — próximos sete dias')
    if 'agenda' not in resultados:
        st.info('A agenda não respondeu nesta consulta. Acesse o portal oficial abaixo.')
    else:
        agenda,truncada = resultados['agenda']
        if agenda.empty:
            st.info('Nenhum evento retornado pela API neste intervalo.')
        else:
            resumo = agenda.copy()
            resumo['Data e hora'] = pd.to_datetime(resumo.dataHoraInicio).dt.strftime('%d/%m às %H:%M')
            resumo = resumo.rename(columns={'descricao':'Assunto','situacao':'Situação'})
            st.dataframe(resumo[['Data e hora','Assunto','Situação']],hide_index=True,width='stretch')
        if truncada:
            st.caption('Exibindo até 500 eventos. Confira a relação completa no portal.')
    st.caption('Evento na agenda não confirma votação, aprovação ou vigência de lei.')
    st.markdown('[Câmara — agenda](https://www.camara.leg.br/agenda) · [Senado — atividade](https://www25.senado.leg.br/web/atividade) · [STF — pautas](https://www.stf.jus.br/pauta/pesquisarCalendario.asp?aba=processo)')


@st.fragment(run_every='5m' if automatico else None)
def painel():
    agora = datetime.now(TZ)
    consulta = st.session_state.get('consulta')
    if consulta is None or consulta['anos'] != anos or (agora-consulta['hora']).total_seconds() >= 300:
        with st.spinner('Consultando fontes públicas…'):
            consulta = consultar(agora)
        st.session_state['consulta'] = consulta
    resultados = consulta['resultados']
    economia,estados,agenda = st.tabs(['Economia','Estados','Agenda'])
    with economia:
        exibir_economia(resultados,consulta['hora'])
    with estados:
        exibir_estados(resultados)
    with agenda:
        exibir_agenda(resultados)
    st.caption('Referência é o período medido. Consulta é o horário em que verificamos a fonte. Dados anuais e mensais não são medições em tempo real.')
    if consulta['erros']:
        with st.expander('Disponibilidade das fontes'):
            for fonte,erro in consulta['erros'].items():
                st.text(f'{fonte}: {erro[:300]}')


painel()
