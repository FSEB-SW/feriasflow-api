"""Pedidos de ferias: CRUD com filtros/paginacao e as transicoes da maquina de estados."""
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..calendario import (
    CalendarioContratoInvalido,
    CalendarioIndisponivel,
    ClienteCalendario,
    get_cliente_calendario,
)
from ..database import get_db
from ..models import Colaborador, PedidoFerias
from ..regras import RegraViolada, transicionar, validar_periodo
from ..schemas import Pagina, PedidoAtualizar, PedidoCriar, PedidoResposta, Recusa, StatusPedido

router = APIRouter(prefix="/pedidos", tags=["Pedidos de ferias"])

MSG_CALENDARIO_FORA = (
    "Servico de calendario indisponivel; nao foi possivel validar o periodo. Tente novamente."
)


def _obter(db: Session, pedido_id: int) -> PedidoFerias:
    pedido = db.scalar(
        select(PedidoFerias)
        .options(selectinload(PedidoFerias.colaborador))
        .where(PedidoFerias.id == pedido_id)
    )
    if not pedido:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido nao encontrado")
    return pedido


def _validar(db, calendario, colaborador, inicio, fim, ignorar_id=None):
    """Traduz excecoes de dominio e de integracao em respostas HTTP."""
    try:
        return validar_periodo(db, calendario, colaborador, inicio, fim, ignorar_pedido_id=ignorar_id)
    except RegraViolada as exc:
        raise HTTPException(exc.status_http, exc.mensagem) from exc
    except CalendarioIndisponivel as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MSG_CALENDARIO_FORA) from exc
    except CalendarioContratoInvalido as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Resposta invalida do servico de calendario: {exc}"
        ) from exc


@router.get("", response_model=Pagina[PedidoResposta], summary="Listar pedidos (filtros + paginacao)")
def listar(
    colaborador_id: int | None = Query(default=None),
    status_: StatusPedido | None = Query(default=None, alias="status"),
    ano: int | None = Query(default=None, ge=1900, le=2200, description="Ano do inicio"),
    pagina: int = Query(default=1, ge=1),
    tamanho: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filtros = []
    if colaborador_id is not None:
        filtros.append(PedidoFerias.colaborador_id == colaborador_id)
    if status_ is not None:
        filtros.append(PedidoFerias.status == status_.value)
    if ano is not None:
        from datetime import date

        filtros.append(PedidoFerias.inicio >= date(ano, 1, 1))
        filtros.append(PedidoFerias.inicio <= date(ano, 12, 31))

    total = db.scalar(select(func.count()).select_from(PedidoFerias).where(*filtros)) or 0
    itens = db.scalars(
        select(PedidoFerias)
        .options(selectinload(PedidoFerias.colaborador))
        .where(*filtros)
        .order_by(PedidoFerias.inicio.desc(), PedidoFerias.id.desc())
        .offset((pagina - 1) * tamanho)
        .limit(tamanho)
    ).all()
    return Pagina(
        itens=itens, total=total, pagina=pagina, tamanho=tamanho, paginas=max(1, ceil(total / tamanho))
    )


@router.get("/{pedido_id}", response_model=PedidoResposta, summary="Obter pedido")
def obter(pedido_id: int, db: Session = Depends(get_db)):
    return _obter(db, pedido_id)


@router.post(
    "",
    response_model=PedidoResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar ferias",
    description=(
        "Valida o periodo com a API de calendario (dias uteis, feriados) e as regras da CLT, "
        "e cria o pedido em status `solicitado`. 422 regra violada, 409 sobreposicao, "
        "503 calendario fora do ar."
    ),
)
def criar(
    dados: PedidoCriar,
    db: Session = Depends(get_db),
    calendario: ClienteCalendario = Depends(get_cliente_calendario),
):
    colaborador = db.get(Colaborador, dados.colaborador_id)
    if not colaborador:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Colaborador nao encontrado")
    periodo = _validar(db, calendario, colaborador, dados.inicio, dados.fim)
    pedido = PedidoFerias(
        colaborador_id=colaborador.id,
        inicio=dados.inicio,
        fim=dados.fim,
        dias_corridos=periodo.dias_corridos,
        dias_uteis=periodo.dias_uteis,
        observacao=dados.observacao,
        aviso_calendario=periodo.aviso_calendario,
    )
    db.add(pedido)
    db.commit()
    return _obter(db, pedido.id)


@router.put("/{pedido_id}", response_model=PedidoResposta, summary="Alterar pedido (so em analise)")
def atualizar(
    pedido_id: int,
    dados: PedidoAtualizar,
    db: Session = Depends(get_db),
    calendario: ClienteCalendario = Depends(get_cliente_calendario),
):
    pedido = _obter(db, pedido_id)
    if pedido.status != "solicitado":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Pedido {pedido.status} nao pode ser alterado"
        )
    alteracoes = dados.model_dump(exclude_unset=True)
    if not alteracoes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nenhum campo informado")
    inicio = alteracoes.get("inicio", pedido.inicio)
    fim = alteracoes.get("fim", pedido.fim)
    if inicio != pedido.inicio or fim != pedido.fim:
        periodo = _validar(db, calendario, pedido.colaborador, inicio, fim, ignorar_id=pedido.id)
        pedido.inicio, pedido.fim = inicio, fim
        pedido.dias_corridos, pedido.dias_uteis = periodo.dias_corridos, periodo.dias_uteis
        pedido.aviso_calendario = periodo.aviso_calendario
    if "observacao" in alteracoes:
        pedido.observacao = alteracoes["observacao"]
    db.commit()
    return _obter(db, pedido.id)


@router.delete("/{pedido_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir pedido")
def remover(pedido_id: int, db: Session = Depends(get_db)):
    pedido = _obter(db, pedido_id)
    if pedido.status == "aprovado":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Pedido aprovado nao pode ser excluido; cancele antes"
        )
    db.delete(pedido)
    db.commit()


def _transicao(db: Session, pedido_id: int, acao: str, motivo: str | None = None) -> PedidoFerias:
    pedido = _obter(db, pedido_id)
    try:
        transicionar(pedido, acao, motivo)
    except RegraViolada as exc:
        raise HTTPException(exc.status_http, exc.mensagem) from exc
    db.commit()
    return _obter(db, pedido.id)


@router.post("/{pedido_id}/aprovar", response_model=PedidoResposta, summary="Aprovar (gestor)")
def aprovar(pedido_id: int, db: Session = Depends(get_db)):
    return _transicao(db, pedido_id, "aprovar")


@router.post("/{pedido_id}/recusar", response_model=PedidoResposta, summary="Recusar (gestor)")
def recusar(pedido_id: int, dados: Recusa, db: Session = Depends(get_db)):
    return _transicao(db, pedido_id, "recusar", dados.motivo)


@router.post("/{pedido_id}/cancelar", response_model=PedidoResposta, summary="Cancelar")
def cancelar(pedido_id: int, db: Session = Depends(get_db)):
    return _transicao(db, pedido_id, "cancelar")
