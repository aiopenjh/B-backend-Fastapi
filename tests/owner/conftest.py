# [담당 5 최지훈] 창구->container->common.database를 불러올 때 POSTGRES_URL이 필요함.
# API 테스트는 가짜 매니저를 쓰므로 실제 DB에 연결하지 않음 (주소 모양만 맞추면 됨)
import os

os.environ.setdefault(
    "POSTGRES_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)
