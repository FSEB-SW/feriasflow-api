"""CRUD de colaboradores e saldo."""
from conftest import CARLA, pedido_padrao


def test_criar_e_obter(client):
    r = client.post("/colaboradores", json=CARLA)
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["saldo_dias"] == 30
    assert corpo["saldo_disponivel"] == 30
    assert corpo["ativo"] is True
    assert client.get(f"/colaboradores/{corpo['id']}").json()["nome"] == "Carla Souza"


def test_email_duplicado_409_e_invalido_422(client):
    client.post("/colaboradores", json=CARLA)
    assert client.post("/colaboradores", json=CARLA).status_code == 409
    assert client.post("/colaboradores", json={**CARLA, "email": "sem-arroba"}).status_code == 422
    assert client.post("/colaboradores", json={**CARLA, "saldo_dias": 99}).status_code == 422


def test_listar_com_filtros(client):
    client.post("/colaboradores", json=CARLA)
    client.post("/colaboradores", json={"nome": "Bruno Lima", "email": "bruno@empresa.com", "equipe": "BIM"})
    assert len(client.get("/colaboradores").json()) == 2
    assert [c["nome"] for c in client.get("/colaboradores", params={"equipe": "BIM"}).json()] == ["Bruno Lima"]
    client.put("/colaboradores/2", json={"ativo": False})
    assert len(client.get("/colaboradores", params={"ativo": True}).json()) == 1


def test_atualizar(client, carla_id):
    r = client.put(f"/colaboradores/{carla_id}", json={"saldo_dias": 20, "equipe": "BIM"})
    assert r.status_code == 200
    assert r.json()["saldo_dias"] == 20
    assert client.put(f"/colaboradores/{carla_id}", json={}).status_code == 422
    assert client.put("/colaboradores/99", json={"nome": "Ninguem"}).status_code == 404


def test_remover_bloqueado_com_pedido_ativo(client, carla_id):
    pedido = client.post("/pedidos", json=pedido_padrao(carla_id)).json()
    r = client.delete(f"/colaboradores/{carla_id}")
    assert r.status_code == 409
    client.post(f"/pedidos/{pedido['id']}/cancelar")
    assert client.delete(f"/colaboradores/{carla_id}").status_code == 204
    assert client.get(f"/pedidos/{pedido['id']}").status_code == 404, "pedido removido em cascata"
