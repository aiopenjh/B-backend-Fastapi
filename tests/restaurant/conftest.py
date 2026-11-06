import os

# 라우터 -> container -> common.database 를 불러올 때 POSTGRES_URL 이 필요함.
# API 테스트는 가짜 서비스를 쓰므로 실제 DB에 연결하지 않음 (주소 형식만 맞추면 됨)
os.environ.setdefault(
    "POSTGRES_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)
