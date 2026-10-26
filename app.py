# Python 3.12 recomendado.
# python -m pip install -r requirements.txt
# python -m streamlit run app.py
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

st.set_page_config(page_title="Observador Brasil", page_icon="🇧🇷", layout="wide")
TZ = ZoneInfo("America/Sao_Paulo")
st.title("🇧🇷 Observador Brasil")
st.caption("Fontes públicas • referência identificada • acesso pelo celular")
anos = st.sidebar.slider("Histórico em anos", 1, 9, 3)
automatico = st.sidebar.toggle("Atualizar a cada 5 minutos", value=True)
st.sidebar.button("Consultar novamente", type="primary")
st.sidebar.info("Cada consulta busca o último dado publicado. IPCA e dívida não são indicadores instantâneos.")


def json_api(url, params=None):
    # Sem cache local: cada execução faz uma nova requisição HTTP.
    with requests.Session() as session:
        retry = Retry(total=1, backoff_factor=0.5,
                      status_forcelist=[429, 500, 502, 503, 504],
                      respect_retry_after_header=False)
        session.mount("https://", HTTPAdapter(max_retries=retry))
        response = session.get(url, params=params, timeout=(15, 30),
                               headers={"Accept": "application/json", "Cache-Control": "no-cache"})
        response.raise_for_status()
        return response.json()


def obter_sgs(codigo, inicio, fim):
    raw = json_api(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados", {
        "formato": "json", "dataInicial": inicio.strftime("%d/%m/%Y"),
        "dataFinal": fim.strftime("%d/%m/%Y")})
    df = pd.DataFrame(raw)
    if df.empty or not {"data", "valor"}.issubset(df.columns):
        raise ValueError("Resposta SGS vazia ou fora do formato esperado")
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y", errors="raise")
    df["valor"] = pd.to_numeric(df["valor"].astype(str).str.replace(",", ".", regex=False), errors="raise")
    df = df[df.data <= pd.Timestamp(fim)].dropna().drop_duplicates("data").sort_values("data")
    if df.empty:
        raise ValueError("Nenhuma observação válida no intervalo")
    return df


def obter_mapa():
    estados = json_api("https://servicodados.ibge.gov.br/api/v1/localidades/estados")
    nomes = {str(e["id"]): (e["nome"], e["sigla"]) for e in estados}
    # 'last' solicita o último período disponível na série de estimativas.
    raw = json_api("https://apisidra.ibge.gov.br/values/t/6579/n3/all/v/9324/p/last")
    if not isinstance(raw, list) or len(raw) < 2:
        raise ValueError("SIDRA sem dados populacionais")
    registros = []
    for item in raw[1:]:
        codigo = str(item["D1C"])
        if codigo in nomes:
            nome, uf = nomes[codigo]
            registros.append({"codigo": codigo, "Estado": nome, "UF": uf,
                              "População": pd.to_numeric(item["V"], errors="coerce"),
                              "Referência": item["D3N"]})
    df = pd.DataFrame(registros)
    if len(df) != 27 or df.codigo.duplicated().any() or df["População"].isna().any():
        raise ValueError("População incompleta ou estrutura SIDRA alterada")
    geo = json_api("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR", {
        "formato": "application/vnd.geo+json", "qualidade": "minima", "intrarregiao": "UF"})
    codigos = set()
    for feature in geo["features"]:
        feature["properties"]["codarea"] = str(feature["properties"]["codarea"])
        codigos.add(feature["properties"]["codarea"])
    if codigos != set(df.codigo):
        raise ValueError("Malha geográfica incompatível com as UFs")
    return df, geo


def obter_agenda(hoje):
    itens = []
    # Paginação limitada para manter o site responsivo mesmo em agendas extensas.
    for pagina in range(1, 6):
        raw = json_api("https://dadosabertos.camara.leg.br/api/v2/eventos", {
            "dataInicio": hoje.isoformat(), "dataFim": (hoje + timedelta(days=6)).isoformat(),
            "ordem": "ASC", "ordenarPor": "dataHoraInicio", "itens": 100, "pagina": pagina})
        if not isinstance(raw.get("dados"), list):
            raise ValueError("Formato da agenda não reconhecido")
        itens.extend(raw["dados"])
        mais = any(link.get("rel") == "next" for link in raw.get("links", []))
        if not mais:
            return pd.DataFrame(itens), False
    return pd.DataFrame(itens), True


@st.fragment(run_every="5m" if automatico else None)
def painel():
    agora = datetime.now(TZ)
    hoje = agora.date()
    inicio = hoje - timedelta(days=365 * anos)
    st.caption(f"Consulta iniciada em {agora:%d/%m/%Y às %H:%M:%S} — Brasília")
    configuracao = {
        "Dívida bruta / PIB": (13762, "% do PIB", 75),
        "Meta Selic": (432, "% a.a.", 10),
        "IPCA mensal": (433, "% no mês", 65),
        "IPCA em 12 meses": (13522, "% em 12 meses", 65),
    }
    resultados, erros = {}, {}
    with st.spinner("Consultando BCB, IBGE e Câmara…"):
        with ThreadPoolExecutor(max_workers=6) as pool:
            tarefas = {pool.submit(obter_sgs, codigo, inicio, hoje): nome
                       for nome, (codigo, _, _) in configuracao.items()}
            tarefas[pool.submit(obter_mapa)] = "mapa"
            tarefas[pool.submit(obter_agenda, hoje)] = "agenda"
            for tarefa in as_completed(tarefas):
                nome = tarefas[tarefa]
                try:
                    resultados[nome] = tarefa.result()
                except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                    erros[nome] = str(exc)
    st.caption(f"Consultas concluídas em {datetime.now(TZ):%H:%M:%S} — Brasília")
    # Duas colunas favorecem a leitura das métricas em telas pequenas.
    colunas = st.columns(2)
    for i, (nome, (codigo, unidade, limite)) in enumerate(configuracao.items()):
        with colunas[i % 2]:
            if nome not in resultados:
                st.metric(nome, "Indisponível")
                st.error("A API não respondeu com dados válidos nesta consulta.")
                continue
            df = resultados[nome]
            atual = df.iloc[-1]
            st.metric(nome, f"{atual.valor:.2f}".replace(".", ","), help=unidade)
            mensal = codigo != 432
            referencia = atual.data.strftime("%m/%Y" if mensal else "%d/%m/%Y")
            st.caption(f"{unidade} • referência {referencia} • SGS {codigo}")
            fim_referencia = atual.data + pd.offsets.MonthEnd(0) if mensal else atual.data
            if (pd.Timestamp(hoje) - fim_referencia).days > limite:
                st.warning("Referência antiga: confira o calendário de divulgação da fonte.")
    for nome in ("Dívida bruta / PIB", "IPCA em 12 meses", "Meta Selic"):
        if nome in resultados:
            fig = px.line(resultados[nome], x="data", y="valor", title=nome,
                          labels={"data": "Referência", "valor": configuracao[nome][1]})
            fig.update_layout(margin=dict(l=5, r=5, t=45, b=5), height=300)
            st.plotly_chart(fig, use_container_width=True)
    st.subheader("Brasil por estado")
    if "mapa" in resultados:
        df, geo = resultados["mapa"]
        fig = px.choropleth(df, geojson=geo, locations="codigo",
                            featureidkey="properties.codarea", color="População",
                            hover_name="Estado", hover_data={"codigo": False, "UF": True,
                            "Referência": True, "População": ":,.0f"},
                            color_continuous_scale="YlGnBu")
        fig.update_geos(fitbounds="locations", visible=False)
        fig.update_layout(height=480, margin=dict(l=0, r=0, t=0, b=0),
                          coloraxis_colorbar=dict(title="Habitantes", thickness=12))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("IBGE/SIDRA: última estimativa disponível na tabela 6579. No celular, toque no estado.")
        estado = st.selectbox("Detalhar estado", sorted(df.Estado))
        st.dataframe(df[df.Estado == estado].drop(columns="codigo"), hide_index=True,
                     use_container_width=True)
    else:
        st.warning("Mapa indisponível nesta consulta. Os indicadores econômicos permanecem independentes.")
    st.caption("Pobreza, violência e governadores não são inferidos de outras séries. Este mapa apresenta população.")
    st.subheader("Câmara — próximos sete dias")
    if "agenda" in resultados:
        agenda, truncada = resultados["agenda"]
        if agenda.empty:
            st.info("A API não retornou eventos neste intervalo. Isso não comprova ausência de atividade.")
        else:
            campos = [c for c in ["dataHoraInicio", "descricao", "situacao", "urlRegistro"] if c in agenda]
            st.dataframe(agenda[campos], hide_index=True, use_container_width=True)
        if truncada:
            st.warning("Limite de 500 eventos atingido. Consulte a agenda oficial para a relação completa.")
    else:
        st.warning("Agenda indisponível nesta consulta.")
    st.markdown("[STF — pautas](https://www.stf.jus.br/pauta/pesquisarCalendario.asp?aba=processo) · "
                "[Senado — atividade](https://www25.senado.leg.br/web/atividade) · "
                "[BCB — estatísticas](https://www.bcb.gov.br/estatisticas) · "
                "[IBGE — SIDRA](https://sidra.ibge.gov.br/)")
    st.caption("Agenda não confirma aprovação, resultado de julgamento ou vigência de lei.")
    if erros:
        with st.expander("Diagnóstico das fontes indisponíveis"):
            for fonte, erro in erros.items():
                st.text(f"{fonte}: {erro[:400]}")


painel()
