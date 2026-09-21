"""Engine e sessao SQLAlchemy. Banco proprio do servico (SQLite por padrao)."""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

_url = settings.database_url
if _url.startswith("sqlite:///") and ":memory:" not in _url:
    _caminho = _url.replace("sqlite:///", "", 1)
    os.makedirs(os.path.dirname(_caminho) or ".", exist_ok=True)

engine = create_engine(
    _url,
    connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {},
)


def ativar_chaves_estrangeiras(engine_):
    """SQLite nao aplica FOREIGN KEY por padrao; ligamos por conexao."""
    if engine_.dialect.name == "sqlite":

        @event.listens_for(engine_, "connect")
        def _pragma(conexao, _):
            conexao.execute("PRAGMA foreign_keys=ON")


ativar_chaves_estrangeiras(engine)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependencia FastAPI: uma sessao por requisicao."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
