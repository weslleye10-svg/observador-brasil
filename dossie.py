"""Dossiê histórico com fontes e monitor de mídia. Notícias não alteram status judicial."""
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
from zoneinfo import ZoneInfo
import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
import requests
import streamlit as st

TZ=ZoneInfo('America/Sao_Paulo')
UTC=timezone.utc
GDELT='https://api.gdeltproject.org/api/v2/doc/doc'
GOOGLE_RSS='https://news.google.com/rss/search'


def carregar_casos():
    return json.loads(Path(__file__).with_name('dossie_casos.json').read_text(encoding='utf8'))


def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFD',str(texto).casefold()) if unicodedata.category(c)!='Mn')


def filtrar_casos(casos,termo):
    termos=normalizar(termo).split()
    return [k for k,c in casos.items() if all(t in normalizar(json.dumps(c,ensure_ascii=False)) for t in termos)]


def url_segura(url):
    try:
        p=urlsplit(str(url))
        if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:
            return None
        return urlunsplit((p.scheme,p.netloc,p.path,p.query,''))
    except ValueError:
        return None


def data_gdelt(valor):
    try:
        return datetime.strptime(str(valor),'%Y%m%dT%H%M%SZ').replace(tzinfo=UTC)
    except ValueError:
        return None


def data_rss(valor):
    try:
        dt=parsedate_to_datetime(str(valor))
        return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)
    except (TypeError,ValueError,OverflowError):
        return None


def filtrar_artigos(itens,agora,horas,limite=12):
    corte=agora-timedelta(hours=horas)
    unicos={}
    for item in itens:
        dt=item.get('data')
        url=url_segura(item.get('url'))
        titulo=' '.join(str(item.get('titulo','')).split())[:500]
        if not titulo or not url or dt is None or not corte<=dt<=agora:
            continue
        chave=(normalizar(titulo),item.get('fonte','').casefold())
        novo=dict(item,url=url,titulo=titulo)
        if chave not in unicos or dt>unicos[chave]['data']:
            unicos[chave]=novo
    return sorted(unicos.values(),key=lambda a:a['data'],reverse=True)[:limite]


def buscar_noticias(termo,horas=168,tentar_gdelt=True,agora=None):
    """API gratuita GDELT; fallback RSS do Google News. Sem chave ou assinatura.

    GDELT fornece data de indexação; RSS fornece pubDate. Ambas são filtradas
    novamente no cliente. Falha de serviço não é confundida com zero notícias.
    """
    if horas not in (24,168):
        raise ValueError('Janela permitida: 24 ou 168 horas')
    agora=agora or datetime.now(UTC)
    if agora.tzinfo is None:
        raise ValueError('Horário da consulta deve ter fuso')
    # Apenas termos de texto: não aceitar operadores ou URLs vindos da pesquisa.
    termo=' '.join(re.findall(r'[\wÀ-ÿ]+',str(termo),flags=re.UNICODE))[:140]
    if not termo:
        raise ValueError('Termo de busca vazio')
    consulta='"'+termo+'"'
    erros=[]
    provedor_vazio=None
    headers={'User-Agent':'ObservadorBrasil/3.0','Cache-Control':'no-cache'}
    if tentar_gdelt:
        try:
            r=requests.get(GDELT,params={'query':consulta+' sourcelang:portuguese','mode':'artlist',
                'format':'json','timespan':'24h' if horas==24 else '7d','maxrecords':50,'sort':'datedesc'},
                timeout=(4,8),headers=headers)
            r.raise_for_status()
            raw=r.json()
            if not isinstance(raw,dict) or not isinstance(raw.get('articles'),list):
                raise ValueError('Resposta GDELT fora do formato esperado')
            itens=[]
            for a in raw['articles']:
                if not isinstance(a,dict):continue
                url=url_segura(a.get('url'))
                itens.append({'titulo':a.get('title',''),'url':url,'data':data_gdelt(a.get('seendate')),
                    'fonte':a.get('domain',''),'tipo_data':'Indexada em'})
            itens=filtrar_artigos(itens,agora,horas)
            if itens:return {'itens':itens,'provedor':'GDELT DOC 2.0','erros':erros,'hora':datetime.now(UTC)}
            provedor_vazio='GDELT DOC 2.0'
        except (requests.RequestException,ValueError) as exc:
            erros.append('GDELT: '+str(exc)[:220])
    try:
        r=requests.get(GOOGLE_RSS,params={'q':consulta+(' when:1d' if horas==24 else ' when:7d'),
            'hl':'pt-BR','gl':'BR','ceid':'BR:pt-419'},timeout=(4,8),headers=headers)
        r.raise_for_status()
        if len(r.content)>5_000_000:raise ValueError('Feed maior que o limite permitido')
        root=ET.fromstring(r.content)
        if root.tag!='rss' or root.find('channel') is None:raise ValueError('Resposta não é RSS de notícias')
        itens=[]
        for a in root.findall('./channel/item'):
            fonte=a.find('source')
            itens.append({'titulo':a.findtext('title',''),'url':a.findtext('link',''),
                'data':data_rss(a.findtext('pubDate','')),'fonte':fonte.text if fonte is not None and fonte.text else 'Google News',
                'tipo_data':'Publicada em'})
        return {'itens':filtrar_artigos(itens,agora,horas),'provedor':'Google News RSS (alternativa ao GDELT)',
                'erros':erros,'hora':datetime.now(UTC)}
    except (requests.RequestException,ET.ParseError,ValueError) as exc:
        erros.append('Google News RSS: '+str(exc)[:220])
    return {'itens':[],'provedor':provedor_vazio,'erros':erros,'hora':datetime.now(UTC)}


def exibir_pessoas(pessoas):
    if pessoas:
        for pessoa in pessoas:
            with st.container(border=True):
                st.write('**'+pessoa['Nome']+'**')
                st.caption(pessoa['Papel documentado'])
                st.write(pessoa['Situação no registro'])
                st.link_button('Fonte deste registro',pessoa['Fonte'])
    else:
        st.caption('Nenhum nome adicional é atribuído sem fonte nesta ficha.')


def corrigir_ipca(valor,base,fim,serie):
    """Corrige do fim do mês base ao fim do mês final; exige todos os meses."""
    import pandas as pd
    import math
    b=pd.Period(base,freq='M');f=pd.Period(fim,freq='M')
    if f<b or not math.isfinite(float(valor)) or valor<0:raise ValueError('Período ou valor inválido')
    esperados=pd.period_range(b+1,f,freq='M')
    por_mes=serie.copy();por_mes['mes']=pd.to_datetime(por_mes.data).dt.to_period('M')
    janela=por_mes[por_mes.mes.isin(esperados)]
    if len(janela)!=len(esperados) or janela.mes.duplicated().any():raise ValueError('IPCA sem todos os meses do intervalo')
    if not all(math.isfinite(float(x)) and float(x)>-100 for x in janela.valor):raise ValueError('Taxas inválidas')
    return float(valor)*float((1+janela.valor/100).prod())


def exibir_correcao(c):
    with st.expander('Valor nominal e equivalência pelo IPCA'):
        st.caption('Simulação de poder de compra; não é cálculo de ressarcimento judicial. Não inclui juros, câmbio ou multa. Bloqueios e baixas contábeis conservam sua natureza após a correção.')
        referencia=c.get('correcao')
        if not referencia:
            st.info('Esta ficha não tem valor em reais com mês-base suficientemente definido para correção automática. Valores em dólares não são convertidos sem metodologia cambial.')
            return
        st.write('Base utilizada: **'+referencia['base']+'** · '+referencia['nota'])
        if st.button('Consultar IPCA e calcular equivalência',key='corrigir_'+c['nome']):
            try:
                from orcamento import sgs,reais
                import pandas as pd
                serie=sgs(433);fim=serie.iloc[-1].data.strftime('%Y-%m')
                valor=corrigir_ipca(referencia['valor'],referencia['base'],fim,serie)
                st.metric('Valor nominal em reais',reais(referencia['valor']))
                st.metric('Equivalente ao fim de '+fim,reais(valor))
                st.caption('Produto dos fatores mensais do IPCA, a partir do mês seguinte à base. SGS 433/IBGE; consulta '+datetime.now(TZ).strftime('%d/%m/%Y %H:%M')+'.')
            except (requests.RequestException,ValueError,KeyError,IndexError) as e:st.warning('Não foi possível calcular com o intervalo completo: '+str(e)[:150])


def exibir_noticias(termo,prefixo='dossie'):
    st.subheader('Últimas Notícias e Atualizações')
    janela=st.radio('Período das notícias',['Últimas 24 horas','Últimos 7 dias'],index=1,horizontal=True,key='janela_'+prefixo)
    horas=24 if janela=='Últimas 24 horas' else 168
    st.caption('Busca por: '+termo+'. Manchetes são cobertura de mídia; decisões devem ser confirmadas na fonte oficial.')
    chave=(termo,horas)
    cache=st.session_state.setdefault('dossie_noticias',{})
    refazer=st.button('Atualizar notícias agora',key='atualizar_noticias_'+prefixo)
    salvo=cache.get(chave)
    agora=datetime.now(UTC)
    if refazer or salvo is None or (agora-salvo['hora']).total_seconds()>=300:
        # GDELT solicita espaçamento entre consultas. Não bloquear a UI com sleep.
        ultima=st.session_state.get('dossie_ultima_gdelt',0)
        tentar=time.monotonic()-ultima>=5
        if tentar:st.session_state['dossie_ultima_gdelt']=time.monotonic()
        with st.spinner('Consultando notícias recentes…'):
            salvo=buscar_noticias(termo,horas,tentar_gdelt=tentar)
        if len(cache)>=24:cache.pop(next(iter(cache)))
        cache[chave]=salvo
    st.caption(f'Consulta: {salvo["hora"].astimezone(TZ):%d/%m/%Y às %H:%M} (Brasília) · '+(salvo['provedor'] or 'provedores indisponíveis'))
    if salvo['provedor'] is None:
        st.warning('Não foi possível consultar o monitor agora. A ficha histórica permanece disponível.')
    elif not salvo['itens']:
        st.info('Nenhuma notícia com data válida foi retornada na janela escolhida. A cobertura depende dos provedores.')
    for item in salvo['itens']:
        with st.container(border=True):
            st.link_button(item['titulo'],item['url'],width='stretch')
            st.caption(f'{item["fonte"]} · {item["tipo_data"]} {item["data"].astimezone(TZ):%d/%m/%Y às %H:%M}')
    st.caption('Atualização automática a cada cinco minutos enquanto esta sessão estiver ativa. No GDELT, a data é de indexação; no RSS, a data é a de publicação informada pelo veículo. Links podem exigir assinatura do jornal.')
    if salvo['erros']:
        with st.expander('Disponibilidade dos provedores de notícias'):
            for erro in salvo['erros']:st.text(erro)


@st.fragment(run_every='5m')
def exibir_dossie(casos):
    st.header('Dossiê de Corrupção (2002 - Presente)')
    st.caption('Casos selecionados • documentos identificados • cobertura de mídia recente')
    termo=st.text_input('Pesquisar escândalo, político, operador financeiro ou empresa',
        placeholder='Ex.: Mensalão, Alberto Youssef, Petrobras, Banco Master',key='busca_dossie',max_chars=120)
    encontrados=filtrar_casos(casos,termo)
    if not encontrados:
        st.info('Nenhuma ficha histórica corresponde a esse termo.')
        if st.checkbox('Consultar notícias sobre este termo',key='noticias_busca_livre'):
            exibir_noticias(termo)
        return
    st.caption(f'{len(encontrados)} caso(s) encontrado(s). A pesquisa também encontra autoridades de controle; ser citado não indica culpa.')
    # O caso mais recente abre inicialmente, mantendo os demais disponíveis.
    ordem=['banco-master','mensalao','sanguessugas','cartoes','lava-jato','pasadena','aloprados','emendas-make-up']
    opcoes=[k for k in ordem if k in encontrados]
    escolhido=st.selectbox('Selecione o caso',opcoes,format_func=lambda k:casos[k]['nome'],key='caso_dossie')
    c=casos[escolhido]
    st.subheader(c['nome'])
    st.caption(c['periodo'])
    st.subheader('O Esquema')
    st.write(c['esquema'])
    st.subheader('Impacto Financeiro')
    st.metric(c['impacto']['rotulo'],c['impacto']['valor'])
    st.caption(c['impacto']['data']+' · '+c['impacto']['nota'])
    st.write(c['efeito'])
    exibir_correcao(c)
    st.subheader('Status Atual')
    st.write('**'+c['status_tipo']+'**')
    st.write(c['status'])
    st.caption(f'Último registro processual usado: {c["status_data"]}. Ficha revisada em {c["verificado_em"]}. A revisão da ficha não significa consulta automática a todos os processos.')
    st.subheader('Rede de Envolvidos — papéis documentados')
    st.caption('Pessoas, empresas e instituições citadas nas fontes. A situação descrita é individual e tem o alcance indicado no registro.')
    exibir_pessoas(c['pessoas'])
    if c['autoridades']:
        with st.expander('Autoridades judiciais e de controle — atuação institucional'):
            exibir_pessoas(c['autoridades'])
    with st.expander('Base constitucional, argumentos e jurisprudência'):
        st.write('**Base constitucional:** '+c['constitucional'])
        st.write('**Fundamentos da responsabilização:** '+c['argumento'])
        st.write('**Limites e garantias jurídicas:** '+c['limite'])
        st.write('**Jurisprudência e alcance:** '+c['precedente'])
        st.link_button('Constituição Federal — texto oficial','https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm')
    with st.expander('Documentos e fontes da ficha'):
        for f in c['fontes']:
            st.link_button(f['titulo'],f['url'],width='stretch')
            st.caption(f'{f["tipo"]} · {f["data"]}')
    st.caption('Valores são nominais, na moeda e no ano da fonte. Não somar estimativas, bloqueios, baixas contábeis, multas e devoluções. As fichas têm atualização editorial; o monitor de notícias tem consulta automática e não altera conclusões judiciais.')
    exibir_noticias(c['consulta'])
