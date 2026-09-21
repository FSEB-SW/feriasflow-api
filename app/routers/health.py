"""Observabilidade minima: estado do servico e das dependencias."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..calendario import ClienteCalendario, get_cliente_calendario
from ..config import settings
from ..database import get_db
from ..schemas import HealthResposta

router = APIRouter(tags=["Operacao"])


@router.get("/health", response_model=HealthResposta, summary="Saude do servico")
def health(
    db: Session = Depends(get_db), calendario: ClienteCalendario = Depends(get_cliente_calendario)
):
    try:
        db.execute(text("SELECT 1"))
        banco = "ok"
    except Exception:  # noqa: BLE001
        banco = "erro"
    calendario_api = "ok" if calendario.disponivel() else "indisponivel"
    estado = "ok" if banco == "ok" and calendario_api == "ok" else "degradado"
    return HealthResposta(
        status=estado,
        servico="feriasflow-api",
        versao=settings.versao,
        banco=banco,
        calendario_api=calendario_api,
    )
