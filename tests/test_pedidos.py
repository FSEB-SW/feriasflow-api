"""Pedido de ferias: regras de negocio, integracao com o calendario e maquina de estados."""
from datetime import timedelta

from conftest import FIM, SEG, pedido_padrao


# ----- criacao e regras --------------------------------------------------------


def test_solicitar_ferias(client, carla_id, calendario):
    r = client.post("/pedidos", json=pedido_padrao(carla_id, observacao="Viagem"))
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["status"] == "solicitado"
    assert corpo["dias_corridos"] == 12
    assert corpo["dias_uteis"] == 10
    assert corpo["colaborador"] == {"id": carla_id, "nome": "Carla Souza", "equipe": "Engenharia"}
    assert calendario.chamadas == 1, "a API de calendario foi consultada uma vez"

    c = client.get(f"/colaboradores/{carla_id}").json()
    assert (c["saldo_dias"], c["dias_reservados"], c["saldo_disponivel"]) == (30, 12, 18)


def test_feriado_desconta_dias_uteis(client, carla_id, calendario):
    calendario.feriados = [(SEG + timedelta(days=3), "Feriado de teste")]
    corpo = client.post("/pedidos", json=pedido_padrao(carla_id)).json()
    assert corpo["dias_uteis"] == 9


def test_regras_de_periodo(client, carla_id):
    def tentar(inicio, fim):
        return client.post(
            "/pedidos",
            json={"colaborador_id": carla_id, "inicio": inicio.isoformat(), "fim": fim.isoformat()},
        )

    assert tentar(FIM, SEG).status_code == 422, "fim antes do inicio"
    assert tentar(SEG - timedelta(days=60), SEG).status_code == 422, "no passado"
    assert tentar(SEG, SEG + timedelta(days=3)).status_code == 422, "menos de 5 dias corridos"
    r = tentar(SEG + timedelta(days=4), SEG + timedelta(days=10))
    assert r.status_code == 422 and "sexta" in r.json()["detail"], "inicio na sexta"
    assert tentar(SEG + timedelta(days=5), SEG + timedelta(days=10)).status_code == 422, "sabado"


def test_inicio_nos_dois_dias_antes_de_feriado(client, carla_id, calendario):
    calendario.feriados = [(SEG + timedelta(days=2), "Feriado na quarta")]
    r = client.post("/pedidos", json=pedido_padrao(carla_id))
    assert r.status_code == 422
    assert "antecedem feriado" in r.json()["detail"]


def test_saldo_insuficiente(client, carla_id):
    client.put(f"/colaboradores/{carla_id}", json={"saldo_dias": 10})
    r = client.post("/pedidos", json=pedido_padrao(carla_id))
    assert r.status_code == 422
    assert "saldo insuficiente" in r.json()["detail"]


def test_saldo_considera_reserva_de_pedidos_em_analise(client, carla_id):
    assert client.post("/pedidos", json=pedido_padrao(carla_id)).status_code == 201  # 12 dias
    seg2 = SEG + timedelta(days=14)
    r = client.post(
        "/pedidos",
        json={"colaborador_id": carla_id, "inicio": seg2.isoformat(), "fim": (seg2 + timedelta(days=20)).isoformat()},
    )
    assert r.status_code == 422, "21 dias > 18 disponiveis"


def test_sobreposicao_409(client, carla_id):
    client.post("/pedidos", json=pedido_padrao(carla_id))
    seg2 = SEG + timedelta(days=7)
    r = client.post(
        "/pedidos",
        json={"colaborador_id": carla_id, "inicio": seg2.isoformat(), "fim": (seg2 + timedelta(days=6)).isoformat()},
    )
    assert r.status_code == 409
    assert "sobrepoe" in r.json()["detail"]


def test_colaborador_inexistente_ou_inativo(client, carla_id):
    assert client.post("/pedidos", json=pedido_padrao(99)).status_code == 404
    client.put(f"/colaboradores/{carla_id}", json={"ativo": False})
    assert client.post("/pedidos", json=pedido_padrao(carla_id)).status_code == 422


# ----- integracao com a API secundaria --------------------------------------------


def test_calendario_fora_do_ar_503(client, carla_id, calendario):
    calendario.modo = "fora"
    r = client.post("/pedidos", json=pedido_padrao(carla_id))
    assert r.status_code == 503
    assert "calendario indisponivel" in r.json()["detail"]
    assert client.get("/pedidos").json()["total"] == 0, "nada foi persistido"


def test_calendario_fora_do_contrato_502(client, carla_id, calendario):
    calendario.modo = "invalido"
    assert client.post("/pedidos", json=pedido_padrao(carla_id)).status_code == 502


def test_calendario_degradado_registra_aviso(client, carla_id, calendario):
    calendario.modo = "degradado"
    corpo = client.post("/pedidos", json=pedido_padrao(carla_id)).json()
    assert corpo["aviso_calendario"] == "BrasilAPI indisponivel (simulado)"


# ----- maquina de estados ---------------------------------------------------------


def test_aprovar_debita_saldo_e_cancelar_devolve(client, carla_id):
    pid = client.post("/pedidos", json=pedido_padrao(carla_id)).json()["id"]

    r = client.post(f"/pedidos/{pid}/aprovar")
    assert r.status_code == 200 and r.json()["status"] == "aprovado"
    c = client.get(f"/colaboradores/{carla_id}").json()
    assert (c["saldo_dias"], c["dias_reservados"], c["saldo_disponivel"]) == (18, 0, 18)

    assert client.post(f"/pedidos/{pid}/aprovar").status_code == 409, "ja aprovado"
    assert client.post(f"/pedidos/{pid}/recusar", json={"motivo": "tarde"}).status_code == 409

    r = client.post(f"/pedidos/{pid}/cancelar")
    assert r.json()["status"] == "cancelado"
    assert client.get(f"/colaboradores/{carla_id}").json()["saldo_dias"] == 30
    assert client.post(f"/pedidos/{pid}/cancelar").status_code == 409, "ja cancelado"


def test_recusar_exige_motivo(client, carla_id):
    pid = client.post("/pedidos", json=pedido_padrao(carla_id)).json()["id"]
    assert client.post(f"/pedidos/{pid}/recusar", json={}).status_code == 422
    r = client.post(f"/pedidos/{pid}/recusar", json={"motivo": "Parada da unidade"})
    assert r.json()["status"] == "recusado"
    assert r.json()["motivo_recusa"] == "Parada da unidade"
    assert client.get(f"/colaboradores/{carla_id}").json()["saldo_disponivel"] == 30
    assert client.post(f"/pedidos/{pid}/cancelar").status_code == 409, "recusado nao cancela"


# ----- alterar / excluir ----------------------------------------------------------


def test_alterar_periodo_revalida(client, carla_id, calendario):
    pid = client.post("/pedidos", json=pedido_padrao(carla_id)).json()["id"]
    novo_fim = SEG + timedelta(days=4)
    r = client.put(f"/pedidos/{pid}", json={"fim": novo_fim.isoformat(), "observacao": "curtas"})
    assert r.status_code == 200
    assert r.json()["dias_corridos"] == 5
    assert r.json()["observacao"] == "curtas"
    assert calendario.chamadas == 2

    assert client.put(f"/pedidos/{pid}", json={}).status_code == 422
    client.post(f"/pedidos/{pid}/aprovar")
    assert client.put(f"/pedidos/{pid}", json={"observacao": "x"}).status_code == 409


def test_excluir(client, carla_id):
    pid = client.post("/pedidos", json=pedido_padrao(carla_id)).json()["id"]
    client.post(f"/pedidos/{pid}/aprovar")
    assert client.delete(f"/pedidos/{pid}").status_code == 409, "aprovado: cancele antes"
    client.post(f"/pedidos/{pid}/cancelar")
    assert client.delete(f"/pedidos/{pid}").status_code == 204
    assert client.get(f"/pedidos/{pid}").status_code == 404


# ----- listagem -----------------------------------------------------------------


def test_listar_filtros_e_paginacao(client, carla_id):
    bruno = client.post(
        "/colaboradores", json={"nome": "Bruno Lima", "email": "bruno@empresa.com"}
    ).json()["id"]
    p1 = client.post("/pedidos", json=pedido_padrao(carla_id)).json()["id"]
    p2 = client.post("/pedidos", json=pedido_padrao(bruno)).json()["id"]
    seg2 = SEG + timedelta(days=14)
    client.post(
        "/pedidos",
        json={"colaborador_id": bruno, "inicio": seg2.isoformat(), "fim": (seg2 + timedelta(days=4)).isoformat()},
    )
    client.post(f"/pedidos/{p1}/aprovar")

    tudo = client.get("/pedidos").json()
    assert (tudo["total"], tudo["paginas"], len(tudo["itens"])) == (3, 1, 3)

    pagina = client.get("/pedidos", params={"tamanho": 2, "pagina": 2}).json()
    assert (pagina["total"], pagina["paginas"], len(pagina["itens"])) == (3, 2, 1)

    assert client.get("/pedidos", params={"status": "aprovado"}).json()["itens"][0]["id"] == p1
    assert client.get("/pedidos", params={"colaborador_id": bruno}).json()["total"] == 2
    assert client.get("/pedidos", params={"ano": SEG.year}).json()["total"] >= 2
    assert client.get("/pedidos", params={"ano": 1999}).json()["total"] == 0
    assert client.get("/pedidos", params={"status": "invalido"}).status_code == 422
    assert p2 in [i["id"] for i in tudo["itens"]]


def test_health(client, calendario):
    assert client.get("/health").json()["status"] == "ok"
    calendario.modo = "fora"
    corpo = client.get("/health").json()
    assert corpo["status"] == "degradado"
    assert corpo["calendario_api"] == "indisponivel"
