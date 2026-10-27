"""Consulta anual ao Excel oficial do FBSP, com validação de estrutura e fallback datado."""
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import json,re,zipfile,xml.etree.ElementTree as ET
import pandas as pd
import requests
import streamlit as st

PAGINA='https://forumseguranca.org.br/publicacoes/anuario-brasileiro-de-seguranca-publica/'
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
TABELAS={'T01':('mvi','Mortes violentas intencionais','M','O','por 100 mil habitantes'),
 'T03':('homicidios','Homicídios dolosos','C','E','por 100 mil habitantes'),
 'T11':('roubo_veiculos','Crimes contra o patrimônio','C','E','por 100 mil veículos'),
 'T15':('roubo_carga','Roubo a instituição','H','J','por 100 mil habitantes'),
 'T21':('feminicidios','Homicídios de mulheres','H','J','por 100 mil mulheres')}

def ler_excel(conteudo):
    with zipfile.ZipFile(BytesIO(conteudo)) as z:
        if sum(i.file_size for i in z.infolist())>100_000_000:raise ValueError('Planilha descompactada excede limite')
        strings=[''.join(x.itertext()) for x in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        rel={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        abas={s.get('name'):'xl/'+rel[s.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')].lstrip('/') for s in ET.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',NS)}
        saida={};notas=[]
        for aba,(chave,titulo,cont,taxa,unidade) in TABELAS.items():
            path=abas[aba].replace('xl/xl/','xl/')
            rows=[]
            for row in ET.fromstring(z.read(path)).findall('m:sheetData/m:row',NS):
                d={}
                for c in row:
                    v=c.find('m:v',NS)
                    if v is not None:d[re.sub(r'\d','',c.get('r'))]=strings[int(v.text)] if c.get('t')=='s' else v.text
                rows.append(d)
            cab=' '.join(str(v) for r in rows[:9] for v in r.values())
            if titulo.casefold() not in cab.casefold() or '2025' not in cab:raise ValueError('Estrutura do anuário mudou; requer revisão da tabela '+aba)
            registros=[]
            for r in rows:
                nome=re.sub(r'\s*\(\d+\)','',r.get('A','')).strip()
                if nome=='Brasil' or nome in ESTADOS:
                    try:n=float(r[cont]);t=float(r[taxa])
                    except (KeyError,ValueError):n=None;t=None
                    registros.append({'Estado':nome,'total':n,'taxa':t})
            if len(registros)!=28:raise ValueError('Não foram validadas 27 UFs e Brasil na tabela '+aba)
            saida[chave]={'dados':registros,'unidade':unidade,'tabela':aba,'ano':2025}
            notas.extend({'tabela':aba,'nota':r['A']} for r in rows if r.get('A','').startswith(('(1)','(2)','(3)','(4)','(5)','(6)')))
        return {'indicadores':saida,'notas':notas,'ano':2025,'edicao':2026}

BASE=json.loads(Path(__file__).with_name('dados_estaduais.json').read_text(encoding='utf8'))
ESTADOS={x['Estado'] for x in BASE['dados']}

def obter_seguranca():
    hora=datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    try:
        r=requests.get(PAGINA,timeout=(5,15));r.raise_for_status()
        links=re.findall(r'href=["\']([^"\']+anuario-(\d{4})\.xlsx)["\']',r.text)
        if not links:raise ValueError('Link oficial do Excel não localizado')
        url,edicao=max(links,key=lambda a:int(a[1]))
        if urlparse(url).hostname!='forumseguranca.org.br':raise ValueError('Arquivo fora do domínio oficial')
        if edicao!='2026':raise ValueError('Nova edição '+edicao+' disponível: estrutura precisa ser conferida antes de substituir os dados')
        r=requests.get(url,timeout=(5,20));r.raise_for_status()
        if len(r.content)>15_000_000:raise ValueError('Arquivo maior que limite')
        dados=ler_excel(r.content)
        return dict(dados,fonte=url,consulta=hora,ao_vivo=True,erro=None)
    except (requests.RequestException,ValueError,KeyError,ET.ParseError,zipfile.BadZipFile) as e:
        dados=json.loads(Path(__file__).with_name('seguranca_referencia.json').read_text(encoding='utf8'))
        return dict(dados,consulta=hora,ao_vivo=False,erro=str(e)[:220])

def consulta_seguranca():
    salvo=st.session_state.get('seguranca_consulta')
    if salvo is None or (datetime.now(ZoneInfo('America/Sao_Paulo'))-datetime.fromisoformat(salvo['consulta'])).total_seconds()>300:
        salvo=obter_seguranca();st.session_state['seguranca_consulta']=salvo
    return salvo

def metrica_nacional():
    s=consulta_seguranca();r=next(x for x in s['indicadores']['homicidios']['dados'] if x['Estado']=='Brasil')
    st.metric('Homicídios dolosos — Brasil',f'{r["taxa"]:.1f}'.replace('.',','))
    st.caption(f'Por 100 mil habitantes · {s["ano"]} · {int(r["total"]):,} vítimas. FBSP, T03. Não é MVI nem dado de hoje.')

def exibir_seguranca():
    st.subheader('Segurança — homicídios, feminicídios e roubos')
    s=consulta_seguranca()
    st.caption('Consulta: '+s['consulta'][:19].replace('T',' ')+' (Brasília) · edição '+str(s['edicao'])+' · dados '+str(s['ano']))
    if not s['ao_vivo']:st.info('Consulta ao anuário indisponível ou estrutura alterada. Base de referência verificada em '+s['verificado_em']+'. '+s['erro'])
    chave=st.selectbox('Indicador de segurança',['mvi','homicidios','feminicidios','roubo_veiculos','roubo_carga'],format_func=lambda x:{'mvi':'Mortes violentas intencionais','homicidios':'Homicídios dolosos','feminicidios':'Feminicídios','roubo_veiculos':'Roubo de veículos','roubo_carga':'Roubo de carga'}[x],key='indicador_seguranca')
    c=s['indicadores'][chave];df=pd.DataFrame(c['dados']);br=df[df.Estado=='Brasil'].iloc[0];uf=df[df.Estado!='Brasil'].copy()
    st.metric('Taxa nacional',f'{br.taxa:.2f}'.replace('.',','));st.caption(c['unidade']+f' · {int(br.total):,} registros/vítimas · {s["ano"]}')
    top=uf.dropna(subset=['taxa']).nlargest(5,'taxa').copy();top['Taxa']=top.taxa.map(lambda v:f'{v:.2f}'.replace('.',','));top['Total']=top.total.astype('Int64')
    st.write('**Cinco maiores taxas estaduais**');st.table(top[['Estado','Taxa','Total']].set_index('Estado'))
    regioes={'Norte':['AC','AP','AM','PA','RO','RR','TO'],'Nordeste':['AL','BA','CE','MA','PB','PE','PI','RN','SE'],'Centro-Oeste':['DF','GO','MS','MT'],'Sudeste':['ES','MG','RJ','SP'],'Sul':['PR','RS','SC']}
    por_estado={r['Estado']:r['UF'] for r in BASE['dados']};por_uf={u:r for r,lista in regioes.items() for u in lista}
    uf['Região']=uf.Estado.map(por_estado).map(por_uf)
    grupos=uf.groupby('Região',as_index=False).agg(total=('total',lambda x:x.sum() if x.notna().all() else float('nan')));grupos['Parcela do total nacional (%)']=grupos.total/br.total*100
    if uf.total.isna().any():st.info('Sinais de ausência/traço na fonte foram preservados como não disponíveis; não são convertidos automaticamente em zero. Agregados regionais incompletos ficam vazios.')
    st.write('**Distribuição regional — números absolutos**');st.dataframe(grupos.rename(columns={'total':'Total de registros/vítimas'}),hide_index=True,width='stretch')
    st.caption('Participação no total não é taxa de risco. Não somar feminicídios a homicídios, nem subtotais que já integrem outras categorias. A taxa de roubo de veículos usa a frota como denominador; feminicídio usa a população feminina. Notas e cobertura podem limitar comparações estaduais.')
    with st.expander('Notas metodológicas da publicação'):
        for n in s['notas']:
            if n['tabela']==c['tabela']:st.caption(n['nota'])
    st.link_button('Fonte: publicação e dados do FBSP',PAGINA)
    st.download_button('Baixar indicadores de segurança',df.to_csv(index=False,sep=';',decimal=','),'seguranca.csv','text/csv')
