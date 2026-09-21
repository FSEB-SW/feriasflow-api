"""CRUD de colaboradores (cadastro da equipe e saldo de ferias - persona Gustavo, gestor)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Colaborador, PedidoFerias
from ..regras import STATUS_ATIVOS, dias_reservados
from ..schemas import ColaboradorAtualizar, ColaboradorCriar, ColaboradorResposta

router = APIRouter(prefix="/colaboradores", tags=["Colaboradores"])


def _obter(db: Session, colaborador_id: int) -> Colaborador:
    colaborador = db.get(Colaborador, colaborador_id)
    if not colaborador:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Colaborador nao encontrado")
    return colaborador


def _garantir_email_livre(db: Session, email: str, ignorar_id: int | None = None) -> None:
    existente = db.scalar(select(Colaborador).where(Colaborador.email == email))
    if existente and existente.id != ignorar_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"E-mail ja cadastrado: {email}")


def montar_resposta(db: Session, c: Colaborador) -> ColaboradorResposta:
    reservados = dias_reservados(db, c.id)
    return ColaboradorResposta(
        id=c.id,
        nome=c.nome,
        email=c.email,
        equipe=c.equipe,
        saldo_dias=c.saldo_dias,
        dias_reservados=reservados,
        saldo_disponivel=c.saldo_dias - reservados,
        ativo=c.ativo,
    )


@router.get("", response_model=list[ColaboradorResposta], summary="Listar colaboradores")
def listar(
    equipe: str | None = Query(default=None),
    ativo: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    consulta = select(Colaborador).order_by(Colaborador.nome)
    if equipe is not None:
        consulta = consulta.where(Colaborador.equipe == equipe)
    if ativo is not None:
        consulta = consulta.where(Colaborador.ativo == ativo)
    return [montar_resposta(db, c) for c in db.scalars(consulta).all()]


@router.get("/{colaborador_id}", response_model=ColaboradorResposta, summary="Obter colaborador")
def obter(colaborador_id: int, db: Session = Depends(get_db)):
    return montar_resposta(db, _obter(db, colaborador_id))


@router.post(
    "",
    response_model=ColaboradorResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar colaborador",
)
def criar(dados: ColaboradorCriar, db: Session = Depends(get_db)):
    _garantir_email_livre(db, dados.email)
    colaborador = Colaborador(**dados.model_dump())
    db.add(colaborador)
    db.commit()
    db.refresh(colaborador)
    return montar_resposta(db, colaborador)


@router.put("/{colaborador_id}", response_model=ColaboradorResposta, summary="Atualizar colaborador")
def atualizar(colaborador_id: int, dados: ColaboradorAtualizar, db: Session = Depends(get_db)):
    colaborador = _obter(db, colaborador_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    if not alteracoes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nenhum campo informado")
    if "email" in alteracoes:
        _garantir_email_livre(db, alteracoes["email"], ignorar_id=colaborador.id)
    for campo, valor in alteracoes.items():
        setattr(colaborador, campo, valor)
    db.commit()
    db.refresh(colaborador)
    return montar_resposta(db, colaborador)


@router.delete(
    "/{colaborador_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remover colaborador"
)
def remover(colaborador_id: int, db: Session = Depends(get_db)):
    colaborador = _obter(db, colaborador_id)
    pendente = db.scalar(
        select(PedidoFerias).where(
            PedidoFerias.colaborador_id == colaborador.id,
            PedidoFerias.status.in_(STATUS_ATIVOS),
        )
    )
    if pendente:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Colaborador tem pedido #{pendente.id} {pendente.status}; cancele antes de remover",
        )
    db.delete(colaborador)
    db.commit()
