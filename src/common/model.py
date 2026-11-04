from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

def init_models():
    """SQLAlchemy 모델 메타데이터 등록"""
