# 팀 컨벤션

아직 도구나 GitHub 설정으로 강제한 건 없습니다. 작업 진행 방식은 [WORKFLOW.md](WORKFLOW.md)를 따릅니다.

## 1. 이름 짓기와 소통

- 파일 이름과 코드 식별자는 영어로 씁니다. 문서 내용은 한국어로 써도 됩니다. 대화와 사용자에게 보이는 메시지도 한국어로 써도 됩니다.
- Python 파일/함수/JSON 필드는 `snake_case`, 클래스는 `PascalCase`
- 모듈 폴더 이름은 단수 소문자: `user`, `restaurant`, `slot`, `reservation`, `owner`
- 같은 대상의 클래스는 계층별로 이름을 구분: 도메인 `Reservation`, ORM 모델 `ReservationModel`, 입출력 스키마 `ReservationCreate` · `ReservationOut`, 레포지토리 `ReservationRepository`, 서비스 `ReservationService`
- `party_size`, `reserved_guests`처럼 도메인 이름을 쓰고, 설명 없는 줄임말은 피함
- 질문할 땐 구체적인 요청과 결과를 같이 공유. "안 돼요"만 쓰지 말고 뭘 해 봤는지, 에러 내용(민감 정보 제거)을 같이 적기

## 2. 코드 구조

모듈·계층 구분과 모듈 사이 참조 규칙은 [ARCHITECTURE.md](ARCHITECTURE.md) 1~2장을 따릅니다.

- 코드는 `src/<모듈>/{presentation, application, domain, infrastructure}/`에 둠. 폴더 구조는 사람마다 새로 만들지 말고 기준 예제(`src/restaurant/`)를 따름
- 단순 조회도 라우터 → 서비스 → 레포지토리 순서로 통일. 서비스가 얇아도 괜찮음
- 라우터에 SQL이나 업무 규칙을 쓰지 않음. 규칙은 도메인 객체 메서드에 둠
- `domain`은 순수 파이썬(`dataclass`, 표준 라이브러리)만 사용. FastAPI · SQLAlchemy · Pydantic import 금지
- 레포지토리는 ORM 모델을 도메인 객체로 바꿔서 돌려줌. 추상 리포지토리 인터페이스나 제네릭 베이스 클래스는 만들지 않음 (구체 클래스 하나면 충분)
- 서비스가 자기 트랜잭션을 책임지고 `commit()`. 레포지토리·헬퍼는 커밋하지 않음 (`flush()`까지만)
- DB 코드는 모두 `async`/`await`. 세션은 요청 하나당 하나. 한 세션을 동시에 실행되는 작업끼리 공유하지 않음
- 다른 모듈의 `presentation`은 import하지 않음 (예외: `get_current_user`, `require_owner`)

## 3. API 약속

- 비즈니스 경로는 `/api/v1`로 시작
- 구현 전에 성공 요청/응답 예시 1개, 실패 예시 1개를 먼저 정함
- 입력 스키마와 출력 스키마는 따로 만듦. 비밀번호 해시는 절대 응답에 넣지 않고, 클라이언트가 소유자·권한·예약 상태·예약된 인원을 직접 정하게 두지 않음
- 로그인은 OAuth2 폼(`username`=이메일, `password`). 보호된 API는 `Authorization: Bearer <token>`
- 목록 응답은 `items`, `page`, `page_size`, `total`. 기본 20개, 최대 100개, 정렬 순서는 항상 같게
- 타임스탬프는 오프셋 포함 ISO 형식, 가격은 원 단위 정수. 날짜 필터는 Asia/Seoul 기준
- 상태 코드:
  - 200: 조회, 수정, 취소
  - 201: 새 예약
  - 204: 로그아웃
  - 401: 로그인 안 됨/만료/로그아웃한 토큰
  - 403: 운영자가 아님(역할), 남의 식당(소유)
  - 404: 없는 리소스, 또는 관련 없는 사람에게 숨긴 리소스 (예: 남의 예약)
  - 409: 예약 규칙 위반·상태 충돌 (`SLOT_SOLD_OUT`, `PARTY_SIZE_EXCEEDED`, `SLOT_ALREADY_STARTED`, `DUPLICATE_RESERVATION`, `ALREADY_CANCELLED`, `CANCELLATION_NOT_ALLOWED`)
  - 422: 잘못된 입력
  - 503: DB 연결 실패
- 에러 응답 형식은 하나로 통일: `error.code`, `error.message`, `error.details`, `error.request_id`. 클라이언트는 메시지 문구가 아니라 code로 분기
- 도메인 규칙 위반은 `AppError`를 상속한 도메인 예외로 던지고, 공통 핸들러가 HTTP 응답으로 바꿈. 도메인에서 `HTTPException`을 쓰지 않음
- OpenAPI 문서는 실제 구현된 API 기준

## 4. 인증과 소유권

제공된 `get_current_user`·`require_owner` 의존성과 `Restaurant.is_owned_by`를 쓰고, 각각 뭘 돌려주는지, 어디서 요청을 거절하는지 설명할 수 있어야 합니다. 로그인만으로는 부족하고, 운영자 역할만으로도 부족합니다. 개인 리소스마다 소유자 확인(예약의 `user_id`, 식당의 `owner_id`)이 따로 있어야 합니다. 관련 없는 고객, 다른 식당 운영자로 API를 직접 호출해서 테스트합니다.

운영자 권한과 식당 소유(`owner_id`)는 시드로만 줍니다. 로그아웃한 토큰은 `token_blacklist`(PostgreSQL, Redis 없음)로 차단합니다. 비밀값(`POSTGRES_URL`, JWT 서명 키 등)은 각자 `.env`에 넣고, 커밋하지 않습니다. 외부에 배포한다면 HTTPS와 허용 origin을 명시합니다.

## 5. DB 변경

각자 자기 필드, 관계, 제약 조건을 설명할 수 있어야 합니다. 테이블 기준은 [ARCHITECTURE 3장 ERD](ARCHITECTURE.md#3-데이터-모델-erd)입니다.

- ORM 모델은 자기 모듈 `infrastructure/models.py`에 두고, 공용 `Base`(`common/database.py`)를 상속
- 테이블은 앱 시작 시 lifespan `create_all`로 생성. 마이그레이션 도구(Alembic)는 쓰지 않음
- `create_all`은 없는 테이블만 만들고 **이미 있는 테이블의 컬럼 변경은 반영하지 않음**. 모델을 바꾸면 로컬 DB를 다시 만들고(`docker compose down -v`), PR에 그 사실을 적음
- ERD에 없는 컬럼·테이블을 추가하려면 먼저 팀과 합의하고 ARCHITECTURE 3장을 함께 고침
- 모델, 도메인 객체, 스키마, 시드, 쿼리, 그걸 쓰는 쪽을 함께 바꿈
- 데이터는 가짜 데이터만 쓰고, 로컬/테스트용 DB에서만 작업
- 예약 가능 조회 결과는 그 시점 스냅샷일 뿐이고, 실제 예약할 때 DB에서 남은 자리를 다시 확인

## 6. 범위에서 뺀 것

UI 연결(Jinja2 포함), CI, Redis 캐시는 범위에서 뺐습니다 (2026-10-28). API는 FastAPI의 API 문서 화면(`/docs`)과 pytest로 확인합니다. 자세한 목록은 [ARCHITECTURE.md](ARCHITECTURE.md) 7장을 봅니다.

- DB 장애를 "결과 없음"으로 성공 처리하면 안 됨
- 예약 완료는 서버가 성공(201)을 돌려준 뒤에만 완료로 봄

## 7. 테스트

기능마다 테스트 2개로 시작합니다: API 정상 1개, 실패 1개. 업무 규칙이 있는 모듈(`slot`, `reservation`)은 도메인 단위 테스트도 둡니다. 그 뒤로는 실제로 위험한 지점이 보일 때 추가합니다. 테스트 개수나 커버리지 목표는 정하지 않습니다.

- 도메인 규칙: DB 없이 도메인 객체만 만들어서 pytest (가장 빠르고 먼저 씀)
- API 검증/출력: pytest + `httpx.AsyncClient`(`ASGITransport`) 비동기 테스트
- 저장/소유권: 실제 PostgreSQL 테스트 DB로 통합 테스트
- 예약 취소: 실제 DB로 두 번째 취소가 409이고 좌석이 한 번만 복구되는지
- 로그아웃: 로그아웃한 토큰으로 `GET /users/me` → 401
- (선택) 예약 경합/재시도: 독립된 PostgreSQL 세션 두 개로 일부러 겹치게 실행

순차 호출이나 목으로는 DB 동시성을 검증할 수 없습니다. 포매터/린터는 하나만 정해서 씁니다.

## 8. 로컬 검증과 AI 사용

CI는 만들지 않습니다. PR을 올리기 전에 각자 로컬에서 테스트와 린터를 돌리고, 실제로 돌린 명령과 결과를 PR에 남깁니다. 테스트가 없는 건 통과한 게 아닙니다. 실행 환경 문제는 정해진 질문 시간에 함께 보고, 기능 동작 문제는 해당 모듈 담당자에게 넘깁니다.

AI가 만든 코드는 초안입니다. 받아들이기 전에 요청이 4계층을 지나는 흐름을 따라가 보고, 작은 동작 하나를 직접 바꿔 보고, 관련 테스트를 돌리고, 실패 케이스 하나를 설명할 수 있어야 합니다. 설명이 안 되면 모듈을 통째로 받지 말고 작업을 더 작게 나눕니다.

로그에는 request ID와 에러 내용을 남기되, 토큰·비밀번호·접속 비밀값·개인 정보는 남기지 않습니다.
