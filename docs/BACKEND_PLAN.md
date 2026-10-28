# 백엔드 구현 계획 (5인 · 도메인 모듈 · 학습 적용형)

FastAPI를 배우면서 배운 개념을 바로 자기 모듈에 적용하는 방식으로, 5명이 도메인 모듈 하나씩 맡아 백엔드를 구현하는 계획입니다.

- 기준 문서: [README](../README.md), [ARCHITECTURE](ARCHITECTURE.md), [TEAM_CONVENTIONS](TEAM_CONVENTIONS.md), [ROADMAP](ROADMAP.md), [WORKFLOW](WORKFLOW.md)
- 테이블 기준: [ARCHITECTURE 3장 ERD](ARCHITECTURE.md#3-데이터-모델-erd) (2026-10-28 확정)
- 상태: 2026-10-28 개정. 6인 역할(A~F) 분담을 담당 1~5로 정리하고, `src/<도메인>/` 4계층 구조와 확정 ERD를 반영함. UI · CI · Redis는 제외. ERD 수정 반영(운영자 소속 → `restaurants.owner_id`, 예약 요청 중복 방지 테이블 삭제, 로그아웃 필수)

## 1. 범위

### 하는 것

로그인 → 식당 목록·상세 → 예약 가능 시간 조회 → 예약 → 내 예약 목록·상세 → 취소 → 로그아웃(토큰 차단), 그리고 운영자의 자기 식당 예약 조회와 식당 정보 수정까지 **실제 PostgreSQL(비동기)로** 동작하게 만듭니다.

### 빼는 것

| 빼는 것 | 이유 | 대신 |
| --- | --- | --- |
| UI (Jinja2 화면, 프론트 연결) | 백엔드와 4계층 학습에 집중 | API 문서 화면(`/docs`)과 pytest로 확인 |
| CI | 설정 비용 대비 학습 효과 작음 | PR 전에 로컬에서 테스트 실행, 결과를 PR에 기록 |
| Redis 캐시 | 결정에 따라 제외 | 모든 조회를 DB에서 바로 읽음 |
| Alembic 마이그레이션 | 단순하게 가기 위해 | lifespan에서 `create_all` + 시드 |
| 회원가입 | 핵심 흐름 밖 | 시드 계정 로그인. **선택 과제** (담당 1) |
| 예약 요청 중복 방지 (`idempotency_records`) | 재시도·상태 관리 개념이 추가로 필요 | **ERD에서 삭제**. 같은 슬롯 중복 예약 규칙으로 일부 방어 |
| 운영자 소속 테이블 (`restaurant_members`) | 식당 하나에 운영자 한 명이면 충분 | **ERD에서 삭제**. `restaurants.owner_id`로 대체 |
| 독립 세션 동시성 테스트 | 테스트 환경 구성이 어려움 | 행 락 코드 + 순차 테스트. 재현 테스트는 **선택 과제** |
| 슬롯 겹침 DB 제약 (`EXCLUDE`) | PostgreSQL 확장 필요 | 시드 데이터로만 겹치지 않게 함 |
| 예약 오픈 시각, 결제, 알림 | ERD·과제 범위 밖 | — |

선택 과제는 "절대 안 하는 것"이 아니라 **필수 흐름이 다 돌아간 뒤 여유가 있으면 추가할 것**입니다.

> ⚠ 예약 요청 중복 방지 테이블이 없어서, 네트워크 오류 뒤 재시도하면 예약이 두 번 생길 수 있습니다. 단, 같은 슬롯 중복 예약 규칙 때문에 같은 사용자가 같은 슬롯에 두 번 예약되지는 않습니다. 남는 한계는 시연 때 설명합니다.

### 사용하는 테이블

6개, 모두 필수: `users`, `token_blacklist`, `restaurants`, `menus`, `reservation_slots`, `reservations`. `restaurant_members`와 `idempotency_records`는 2026-10-28 ERD 수정으로 삭제했습니다 ([ARCHITECTURE 3장](ARCHITECTURE.md#3-데이터-모델-erd)).

## 2. 한눈에 보는 역할

| 담당 | 모듈 | 맡는 테이블 | API | 공용 부품 |
| --- | --- | --- | --- | --- |
| **담당 1 · 강성수** | `src/user/` | `users` · `token_blacklist` | `POST /auth/login` · `GET /users/me` · `POST /auth/logout` | `get_current_user` · 요청 로그/CORS 미들웨어 |
| **담당 2 · 김태양** | `src/restaurant/` | `restaurants` · `menus` | `GET /restaurants` · `GET /restaurants/{id}` · `PATCH /owner/restaurants/{id}` | `Page[T]` · 공통 에러 형식 · `Restaurant.is_owned_by` |
| **담당 3 · 이영민** | `src/slot/` | `reservation_slots` | `GET /restaurants/{id}/availability` | `TimeSlot` 도메인 규칙 · lifespan 시드 |
| **담당 4 · 김민지** | `src/reservation/` (쓰기) | `reservations` | `POST /reservations` · `POST /reservations/{id}/cancel` | `ReservationOut` · `Reservation` 도메인 규칙 |
| **담당 5 · 최지훈** | `src/owner/` + `src/reservation/` (조회) | 없음 (다른 테이블을 JOIN해 조회) | `GET /users/me/reservations` · `GET /reservations/{id}` · `GET /owner/restaurants` · `GET /owner/restaurants/{id}/reservations` | `require_owner` (운영자 역할 검사) |

모든 경로 앞에는 `/api/v1`이 붙습니다. 담당 4는 트랜잭션이 들어가는 쓰기 2개에 집중하고, 예약 조회는 담당 5가 같은 모듈 안 별도 파일(`query_*.py`)로 만듭니다 ([ARCHITECTURE 2장](ARCHITECTURE.md#2-폴더-구조와-담당)).

`common/database.py`, `common/config.py`, `main.py` 뼈대는 지원 작업(에이전트 활용)으로 준비하고, 각자 자기 라우터와 ORM 모델을 `main.py`에 등록합니다.

### 서로 기다리는 공용 부품

| 부품 | 만드는 사람 | 쓰는 사람 | 필요한 날 | 기다리는 동안 |
| --- | --- | --- | --- | --- |
| `get_current_user` 의존성 | 담당 1 | 2 · 4 · 5 | D4 | `app.dependency_overrides`로 가짜 사용자 주입 |
| `Page[T]` 목록 응답 스키마 | 담당 2 | 2 · 5 | D4 | 합의한 필드(`items`·`page`·`page_size`·`total`)로 각자 임시 작성 |
| 공통 에러 형식 (`AppError` + 예외 핸들러 + 에러 코드 초안) | 담당 2 | 모두 | D4 | 각자 `AppError`를 상속한 예외를 던져 두면, 핸들러가 생긴 뒤 응답 형식만 바뀜 |
| `TimeSlot` 도메인 (`can_accept` · `reserve` · `release`) | 담당 3 | 3 · 4 | D4 | 담당 4는 인터페이스(메서드 이름·예외)만 합의하고 서비스부터 작성 |
| lifespan 테이블 생성 + 시드 | 담당 3 (각자 자기 테이블 행 제공) | 모두 | D4 | 테스트 안에서 직접 행 만들기 |
| 운영자 역할 검사 `require_owner` 의존성 | 담당 5 | 2 · 5 | D5 | `get_current_user` 결과의 `role`을 직접 확인하는 임시 코드 |
| 소유 확인 `Restaurant.is_owned_by(user_id)` | 담당 2 | 2 · 5 | D5 | `restaurant.owner_id == user.id`를 직접 비교 |
| `ReservationOut` 응답 스키마 + `Reservation.can_cancel()` | 담당 4 | 4 · 5 | D5 | 4장의 필드 표를 그대로 따름 |

## 3. 다 같이 배우는 공통 기초 (D1~D3)

ROADMAP 그대로, 처음 3일은 모두 같은 작은 기능을 4계층으로 만들며 아래 개념을 익힙니다. 이 개념은 이후 모든 담당이 그대로 씁니다.

| 개념 | 공식 자료 | 어디에 쓰나 |
| --- | --- | --- |
| 경로 · 쿼리 파라미터, 타입 검증 | [Path Parameters](https://fastapi.tiangolo.com/tutorial/path-params/), [Query Parameters](https://fastapi.tiangolo.com/tutorial/query-params/) | 모든 GET API |
| 요청 바디와 Pydantic 모델 | [Request Body](https://fastapi.tiangolo.com/tutorial/body/) | 예약 생성, 식당 수정 |
| 입력·출력 스키마 분리 | [Response Model](https://fastapi.tiangolo.com/tutorial/response-model/) | 모든 API (비밀번호 해시 제외) |
| 에러 응답 | [Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/) | 공통 에러 형식 `error.code` · `message` · `details` · `request_id` |
| 라우터로 파일 나누기 | [Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/) | `src/<모듈>/presentation/router.py` |
| 의존성 주입 | [Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) | DB 세션, 현재 사용자 |
| 비동기 DB 모델 · 세션 · 조회 | [SQLAlchemy 2.0 ORM 튜토리얼](https://docs.sqlalchemy.org/en/20/tutorial/), [asyncio 확장](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) | 모든 테이블, `AsyncSession` |
| 앱 시작 이벤트 | [Lifespan Events](https://fastapi.tiangolo.com/advanced/events/) | `create_all`, 시드 |
| 테스트 | [Testing](https://fastapi.tiangolo.com/tutorial/testing/), [Async Tests](https://fastapi.tiangolo.com/advanced/async-tests/) | 도메인 단위 테스트, API 테스트 |

FastAPI 공식 SQL 튜토리얼은 SQLModel을 쓰지만, 이 프로젝트는 **비동기 SQLAlchemy(`AsyncSession` + asyncpg)**를 씁니다. DB 부분은 SQLAlchemy 문서를 기준으로 봅니다.

**공통 실습 (D1~D3)**: `src/restaurant/`에 식당 상세 조회를 4계층으로 만듭니다. 도메인 `Restaurant` dataclass → 메모리 리스트 레포지토리 → 서비스 → 라우터(ID 검증 422, 없으면 404) → 레포지토리만 DB 조회로 교체 → 테스트 2개. 다섯 명이 만든 것 중 하나를 골라 기준 예제로 통합하고, 담당 2가 이어받습니다.

**모두가 지키는 것**

- 자기 테이블의 ORM 모델은 자기 모듈의 `infrastructure/models.py`에 두고, 공용 `Base`를 상속합니다. 컬럼·제약을 직접 설명할 수 있어야 합니다.
- 도메인 객체는 FastAPI·SQLAlchemy·Pydantic을 import하지 않습니다. 규칙 위반은 `AppError`를 상속한 도메인 예외로 던집니다.
- 커밋은 application 서비스에서 한 번만 합니다. 레포지토리와 헬퍼는 커밋하지 않습니다.
- 응답은 출력 스키마로만 내보냅니다. ORM 모델이나 도메인 객체를 그대로 반환하지 않습니다.
- 다른 모듈 코드는 [ARCHITECTURE 2장 참조 규칙](ARCHITECTURE.md#모듈-사이-참조-규칙) 안에서만 씁니다.

## 4. 담당별 상세

### 담당 1 (강성수) · 인증 · 사용자 (`src/user/`)

**도메인**: 시드로 넣은 고객·운영자 계정으로 로그인하고, 보호된 API가 "지금 요청한 사람이 누구인지" 알 수 있게 합니다. 로그아웃하면 그 토큰을 블랙리스트에 넣어 더 이상 쓰지 못하게 합니다. 모든 팀원이 이 결과를 씁니다. 앱 전체에 걸리는 미들웨어(요청 로그·처리 시간, CORS)도 맡습니다.

**테이블** — `users`: `id`, `email`(UQ), `password_hash`, `name`, `phone`, `role`(`CUSTOMER`·`OWNER`), `created_at`, `updated_at`, `deleted_at` / `token_blacklist`: `id`, `user_id`(FK), `token_jti`(UQ), `expires_at`, `created_at`

| API | 요청 | 성공 | 실패 |
| --- | --- | --- | --- |
| `POST /auth/login` | 폼 `username`(이메일) · `password` | 200 `{access_token, token_type: "bearer", expires_in}` | 422 형식 오류 · 401 이메일·비밀번호 불일치 |
| `GET /users/me` | `Authorization: Bearer …` | 200 `{id, email, name, phone, role}` | 401 토큰 없음·만료 |
| `get_current_user` (의존성) | 토큰 | 도메인 `User` | 401 (블랙리스트 토큰, 탈퇴 `deleted_at` 계정도 401) |
| `POST /auth/logout` | `Authorization: Bearer …` | 204 (이 토큰은 이후 401) | 401 토큰 없음·만료·이미 로그아웃 |

**계층별 파일**: `domain/user.py` · `application/service.py`(로그인·로그아웃) · `infrastructure/models.py`(`UserModel`, `TokenBlacklistModel`), `repository.py`, `security.py`(해시·JWT·`jti`) · `presentation/router.py`, `schemas.py`, `dependencies.py`(`get_current_user`) · `common/middleware.py`

**배우고 바로 적용하기**

| 배울 것 | 적용할 곳 |
| --- | --- |
| [OAuth2 + JWT 튜토리얼](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) | `OAuth2PasswordRequestForm` 로그인, 토큰 발급·검증 |
| 비밀번호 해시 (검증된 라이브러리 사용, 직접 만들지 않음) | 시드 비밀번호 저장, 로그인 비교 |
| `Depends`로 의존성 만들기 | `get_current_user` — 다른 4명이 그대로 씀 |
| `app.dependency_overrides` | 다른 팀원 테스트용 가짜 사용자 |
| JWT `jti` 클레임과 블랙리스트 조회 | 로그아웃한 토큰 차단 |
| [미들웨어](https://fastapi.tiangolo.com/tutorial/middleware/), [CORS](https://fastapi.tiangolo.com/tutorial/cors/) | 요청 로그 + `X-Process-Time`, 허용 origin 설정 |

**단계**

1. `users` 모델 + 시드 계정 4개 (고객 2 · 운영자 2) 행을 담당 3에게 전달
2. `POST /auth/login` — 사용자 없음과 비밀번호 틀림을 **같은 401**로 응답. 토큰에 처음부터 `jti` 포함
3. `get_current_user` → **D4까지 공유** (먼저 가짜 버전을 공유하고 나중에 진짜로 교체해도 됨)
4. `GET /users/me` — 응답에 `password_hash`가 없는지 테스트
5. 요청 로그·처리 시간 미들웨어, CORS (D5)
6. `POST /auth/logout` + `token_blacklist`, `get_current_user`에 블랙리스트 확인 추가, lifespan에서 만료된 행 정리 (D6)
7. **선택**: `POST /auth/signup`

**테스트**: 올바른 계정 로그인 → 200 / 틀린 비밀번호 → 401 / 로그아웃한 토큰으로 `GET /users/me` → 401

### 담당 2 (김태양) · 식당 · 메뉴 (`src/restaurant/`)

**도메인**: 누구나 보는 식당 목록·상세와 메뉴, 그리고 운영자만 쓰는 식당 정보 수정입니다. "이 식당의 주인인가"(`Restaurant.is_owned_by`)도 식당의 규칙이라 담당 2가 만듭니다. 팀 전체가 쓰는 **공통 응답 형식**(목록 `Page[T]`, 에러 응답)도 맡습니다. 공통 실습 기준 예제를 이어받습니다.

**테이블** — `restaurants`: `id`, `owner_id`(FK → `users.id`·IX·NOT NULL), `name`, `description`, `address`, `cuisine`, `image_url`, `status`, `phone`, `created_at`, `updated_at`, `deleted_at` / `menus`: `id`, `restaurant_id`(FK·IX), `name`, `description`, `price`, `created_at`, `updated_at`

| API | 요청 | 성공 | 실패 |
| --- | --- | --- | --- |
| `GET /restaurants` | `q`(이름 검색) · `cuisine` · `sort`(`id` 기본 · `name`) · `page`(기본 1) · `page_size`(기본 20, 최대 100) | 200 `Page[RestaurantSummary]` | 422 |
| `GET /restaurants/{id}` | 경로 id | 200 `RestaurantDetail` (메뉴 포함) | 422 · 404 |
| `PATCH /owner/restaurants/{id}` | 토큰 + `{name?, description?, address?, phone?, status?}` | 200 `RestaurantDetail` | 422 · 401 · 403 운영자 아님·남의 식당 · 404 없는 식당 |

`RestaurantSummary` = `id, name, cuisine, image_url, status` / `RestaurantDetail` = 여기에 `description, address, phone, menus[{id, name, description, price}]`. `deleted_at`이 있는 식당은 목록·상세에서 404로 숨깁니다.

**계층별 파일**: `domain/restaurant.py`(`Restaurant`, `Menu`, 수정 가능 필드 규칙, `is_owned_by`) · `application/service.py` · `infrastructure/models.py`, `repository.py` · `presentation/router.py`, `owner_router.py`, `schemas.py` · `common/pagination.py`, `common/errors.py`, `common/error_handlers.py`

**배우고 바로 적용하기**

| 배울 것 | 적용할 곳 |
| --- | --- |
| `Query(ge=1, le=100)`, `Literal` 검증 | `page`, `page_size`, `sort` |
| `where` · `ilike` · `offset` · `limit` · `count`, 고정 정렬 | 검색·필터·정렬·페이지 나누기 |
| 제네릭 `Page[T]` 스키마 | 공용 목록 응답 → **담당 5도 사용** |
| 예외 핸들러 `@app.exception_handler` | `AppError`·422·`HTTPException`을 `{"error": {code, message, details, request_id}}`로 → **모두 사용** |
| 비동기에서 관계 함께 불러오기 (`selectinload`) | 상세에 메뉴 포함 (비동기에선 지연 로딩이 안 됨) |
| `model_dump(exclude_unset=True)` 부분 수정 | PATCH — 보낸 필드만 바꾸기 |
| 권한 규칙을 도메인 메서드로 표현 | `Restaurant.is_owned_by()` → **담당 5도 사용** |

**단계**

1. 공통 실습 예제를 기준으로 두 모델(`owner_id` 포함) + 식당 3곳(운영자 A 2곳, 운영자 B 1곳)·메뉴 9개 시드 행을 담당 3에게 전달
2. `GET /restaurants/{id}` → `GET /restaurants` + `Page[T]` 공유 (D4)
3. `AppError`·에러 핸들러·에러 코드 초안 공유 (D4) — 처음엔 422·404만 바꿔 보고, 다른 담당의 코드를 받아 목록을 채움
4. `PATCH` — 담당 5의 `require_owner`로 역할 확인 → `is_owned_by`로 소유 확인. 입력 스키마에는 허용 필드만 둠 (`owner_id`는 수정 불가)

**테스트 2개**: 있는 식당 상세 → 200 + 메뉴 / 없는 id → 404

### 담당 3 (이영민) · 예약 가능 시간 · 시드 (`src/slot/`)

**도메인**: 날짜와 인원을 고르면 그 식당에서 예약할 수 있는 시간대를 보여 줍니다. "이 슬롯에 N명이 들어갈 수 있나" 규칙을 `TimeSlot`에 만들어 **담당 4의 예약 생성과 공유**합니다. 팀 전체가 쓰는 lifespan 테이블 생성과 시드도 관리합니다.

**테이블** — `reservation_slots`: `id`, `restaurant_id`(FK·IX), `starts_at`, `ends_at`, `capacity`, `reserved_guests`, `max_party_size`, `created_at`, `updated_at` · `CHECK (0 ≤ reserved_guests ≤ capacity)`, `CHECK (max_party_size ≥ 1)`, `CHECK (starts_at < ends_at)`

| API | 요청 | 성공 | 실패 |
| --- | --- | --- | --- |
| `GET /restaurants/{id}/availability` | `date`(YYYY-MM-DD) · `party_size`(1 이상) | 200 `{restaurant_id, date, slots[{id, starts_at, ends_at, remaining, max_party_size, available}]}` | 422 · 404 |

`available = TimeSlot.can_accept(party_size, now)` = 시작 전 AND `party_size ≤ max_party_size` AND `capacity − reserved_guests ≥ party_size`. 저장하지 않고 응답 때 계산합니다.

**계층별 파일**: `domain/time_slot.py`(`TimeSlot.can_accept/reserve/release`), `domain/exceptions.py` · `application/service.py` · `infrastructure/models.py`, `repository.py`(`get_for_update` 포함) · `presentation/router.py`, `schemas.py` · `src/main.py` lifespan, `src/seed.py`

**배우고 바로 적용하기**

| 배울 것 | 적용할 곳 |
| --- | --- |
| 쿼리 파라미터를 `date` 타입·범위로 검증 | 잘못된 날짜·인원 → 422 |
| 타임존 포함 시간(`timestamptz`)과 `zoneinfo` | 서울 기준 하루 = `[00:00, 다음 날 00:00)` 범위로 조회 |
| `CheckConstraint`, 복합 인덱스 | `reserved_guests` 범위, `(restaurant_id, starts_at)` |
| 순수 도메인 객체 단위 테스트 (DB 없이) | `can_accept` · `reserve` 규칙 |
| lifespan + `run_sync(Base.metadata.create_all)` | 앱 시작 시 테이블 생성, 시드 중복 방지 |
| `select(...).with_for_update()` 레포지토리 메서드 | 담당 4가 예약 트랜잭션에서 사용 |

**단계**

1. 모델 + `TimeSlot` 도메인과 단위 테스트 → 도메인 인터페이스를 **D4에 담당 4와 공유**
2. lifespan `create_all` + 시드 스크립트 (D4) — 각 담당이 넘겨준 행을 한 파일로 모음. 슬롯은 "오늘(서울) 기준 내일 이후"로 계산하고, 이미 시드가 있으면 건너뜀
3. availability API — 날짜 범위 계산을 작은 함수로 분리하고 그 함수부터 테스트
4. `get_for_update(session, slot_id)` 레포지토리 메서드 (D5, 담당 4 사용)

**테스트 2개**: 열린 슬롯 `available: true` · 꽉 찬 슬롯 `false` / `party_size=0` → 422 (+ `TimeSlot` 단위 테스트)

### 담당 4 (김민지) · 예약 생성 · 취소 (`src/reservation/` 쓰기)

**도메인**: 예약을 만들고 취소합니다. 슬롯 인원을 바꾸는 유일한 쓰기라서 **트랜잭션과 행 락**을 배우는 담당입니다. 취소 규칙은 `Reservation` 도메인 객체에 둡니다.

**테이블** — `reservations`: `id`, `user_id`(FK·IX), `slot_id`(FK·IX), `party_size`, `status`(`CONFIRMED` · `CANCELLED`), `created_at`, `updated_at`, `cancelled_at`

| API | 요청 | 성공 | 실패 |
| --- | --- | --- | --- |
| `POST /reservations` | 토큰 + `{slot_id, party_size}` | 201 `ReservationOut` | 422 · 401 · 404 슬롯 없음 · 409 `SLOT_SOLD_OUT` / `PARTY_SIZE_EXCEEDED` / `SLOT_ALREADY_STARTED` / `DUPLICATE_RESERVATION` |
| `POST /reservations/{id}/cancel` | 토큰 | 200 `ReservationOut` | 401 · 404 없음·남의 예약 · 409 `ALREADY_CANCELLED` / `CANCELLATION_NOT_ALLOWED` |

`ReservationOut` = `id, user_id, slot_id, restaurant_id, starts_at, ends_at, party_size, status, created_at, cancelled_at, can_cancel` — 예약 + 슬롯으로 만듭니다.

`can_cancel = 요청한 사람이 예약자 AND status = CONFIRMED AND 슬롯 시작 전` — `Reservation.can_cancel()` 하나로 계산하고 `cancel()`도 같은 판단을 씁니다. 운영자가 보면 항상 `false`입니다.

**예약 생성 순서 (한 트랜잭션)**: 슬롯 행 락(담당 3 레포지토리) → 같은 슬롯 `CONFIRMED` 예약 확인 → `TimeSlot.reserve()` → 예약 INSERT · 슬롯 저장 → 커밋. 어디서든 실패하면 전부 롤백.

**취소 순서 (한 트랜잭션)**: 예약 조회 → 본인인지 확인(아니면 404) → 슬롯 행 락 → 예약 행 락 → `Reservation.cancel()` → `TimeSlot.release()` → 커밋. 락 순서는 생성과 같게 **슬롯 → 예약**.

**계층별 파일**: [ARCHITECTURE 2장](ARCHITECTURE.md#2-폴더-구조와-담당) `reservation` 파일표의 담당 4 항목

**배우고 바로 적용하기**

| 배울 것 | 적용할 곳 |
| --- | --- |
| `AsyncSession` 트랜잭션 (`async with session.begin()` 또는 commit/rollback) | 예약 생성·취소를 한 묶음으로 |
| 행 락 `select(...).with_for_update()` | 두 요청이 같은 남은 자리를 보고 둘 다 성공하는 것 방지 |
| 도메인 예외 → 공통 핸들러 → 409 | `SLOT_SOLD_OUT`, `ALREADY_CANCELLED` … |
| `status_code=201` | 새 예약 |

**단계**

1. 모델 + `Reservation` 도메인과 단위 테스트, `ReservationOut` → **D5까지 담당 5와 공유**
2. `POST /reservations` — 처음엔 락 없이 만들고 테스트 → 그다음 `with_for_update()` 추가 (차이를 설명할 수 있게)
3. `POST /reservations/{id}/cancel` — 두 번째 취소가 409이고 좌석이 한 번만 복구되는지 테스트
4. **선택**: 독립 PostgreSQL 세션 두 개로 동시 예약 테스트

**테스트 2개**: 남은 자리 있는 슬롯 → 201 + `reserved_guests` 증가 / 꽉 찬 슬롯 → 409 (+ `Reservation` 단위 테스트)

### 담당 5 (최지훈) · 예약 조회 · 운영자 (`src/owner/` + `src/reservation/` 조회)

**도메인**: 고객은 자기 예약만, 운영자는 자기 식당 예약만 보게 합니다. **인증(누구인가)과 인가(볼 수 있는가)를 구분**하는 담당입니다. 운영자 역할 검사 `require_owner`를 만들어 모든 운영자 API에 공유합니다.

**테이블** — 자기 테이블 없음. `restaurants.owner_id`(담당 2)와 `reservations`·`reservation_slots`(담당 4·3)를 JOIN해 조회합니다.

| API | 요청 | 성공 | 실패 |
| --- | --- | --- | --- |
| `GET /users/me/reservations` | 토큰 · `page` · `status`(선택) | 200 `Page[ReservationOut]` (내 것만) | 422 · 401 |
| `GET /reservations/{id}` | 토큰 | 200 `ReservationOut` | 401 · 404 없음·관련 없음 |
| `GET /owner/restaurants` | 토큰 · `page` | 200 `Page[RestaurantSummary]` (내 식당만, `WHERE owner_id = 나`) | 401 · 403 고객 |
| `GET /owner/restaurants/{id}/reservations` | 토큰 · `date`(선택) · `page` | 200 `Page[ReservationOut]` | 422 · 401 · 403 고객·남의 식당 · 404 없는 식당 |
| `require_owner` (의존성) | 토큰 | 운영자 `User` | 401 · 403 고객 |

**계층별 파일**: `owner/presentation/dependencies.py`(`require_owner`)·`router.py` · `owner/application/service.py` · `owner/infrastructure/query_repository.py` (`domain`은 비워 둠) + `reservation/`의 `query_service.py` · `query_repository.py` · `query_router.py`

**배우고 바로 적용하기**

| 배울 것 | 적용할 곳 |
| --- | --- |
| `select(...).join(...)` 여러 테이블 (다른 모듈 ORM 모델은 JOIN에만) | 예약 + 슬롯 + 식당(`owner_id`) |
| 의존성 위에 의존성 쌓기 (`Depends(get_current_user)` → 역할 검사) | `require_owner` |
| 인증(401) vs 권한 없음(403) vs 숨김(404) | 예약 상세, 운영자 API |
| 요청한 사람에 따라 달라지는 계산 필드 | `can_cancel` (담당 4의 `Reservation.can_cancel()` 재사용) |
| `Page[T]` 재사용 (담당 2) | 목록 API 3개 |

**단계**

1. `require_owner` 의존성 → **D5까지 공유** (담당 2의 PATCH가 사용)
2. `GET /owner/restaurants` (`WHERE owner_id = 나`) → `GET /owner/restaurants/{id}/reservations` (담당 2의 `is_owned_by`로 소유 확인)
3. `GET /users/me/reservations` → `GET /reservations/{id}`

**테스트 2개**: 운영자 A가 자기 식당 예약 조회 → 200 / 운영자 A가 운영자 B 식당 예약 조회 → 403 (+ 고객이 운영자 API 호출 → 403)

## 5. 일정 (ROADMAP 기준)

| 일차 | 담당 1 강성수 | 담당 2 김태양 | 담당 3 이영민 | 담당 4 김민지 | 담당 5 최지훈 |
| --- | --- | --- | --- | --- | --- |
| D1~D3 (10.26~28) | 공통 실습: 식당 상세 4계층 → 404/422 → DB → 테스트 2개 · **G1** 후 모듈 배정 | ← | ← | ← | ← |
| D4 (10.29) | users · 로그인(`jti` 포함) · `get_current_user` 공유 | 식당 상세·목록 · `Page[T]`·에러 형식 공유 | 슬롯 모델 · `TimeSlot` 공유 · **lifespan 시드 공유** | reservations 모델 · `Reservation` 도메인 · 생성 서비스 뼈대 | `require_owner` · 운영자 조회 레포지토리 뼈대 |
| D5 (10.30) | `/users/me` · 미들웨어 | PATCH (역할·소유 확인) · `is_owned_by` 공유 | availability API · `get_for_update` | 생성 트랜잭션 + 행 락 · `ReservationOut` 공유 | 운영자 식당 목록 · `require_owner` 공유 |
| D6 (10.31) | 로그아웃 · 블랙리스트 · 다른 팀원 인증 연동 지원 | 검색·필터·정렬 · 404/422 정리 | 잘못된 입력 처리 | 취소 API | 내 예약 목록·상세 · 운영자 예약 목록 · **G2** |
| D7 (11.1) | 테스트 2개 + 로그아웃 차단 테스트 (+선택) | 테스트 2개 | 테스트 2개 + 도메인 단위 | 테스트 2개 + 도메인 단위 (+선택) | 테스트 2개 + 다른 식당 접근 거부 |
| D8 (11.2) | 통합 버그 수정 · **G3** | ← | ← | ← | ← |
| D9~D12 | 새 기능 중단 → 다른 팀원 환경에서 재현(**G4**) → 성공·실패·테스트 1개씩 설명(**G5**) | ← | ← | ← | ← |

**G2 확인 흐름** (D6): 고객 A 로그인(`/docs` Authorize) → 식당 목록 → 상세 → 예약 가능 조회 → 예약 → 내 예약 목록·상세 → 취소 → 로그아웃 → 같은 토큰으로 `/users/me` 401 / 운영자 A 로그인 → 운영 식당 → 그 식당 예약 목록 → 운영자 B 식당 예약 목록 403. API 문서 화면(`/docs`)에서 실제 API로 확인합니다.

## 6. 담당별로 시연 때 설명할 것 (G5)

| 담당 | 성공 요청 1개 | 실패 요청 1개 | 설명할 개념 |
| --- | --- | --- | --- |
| 1 | 로그인 → 토큰 | 로그아웃한 토큰 → 401 | 토큰이 어떻게 "현재 사용자"가 되는지, JWT를 회수하려면 왜 블랙리스트가 필요한지 |
| 2 | 식당 상세 + 메뉴 | 없는 식당 → 404 | 레포지토리를 메모리 → DB로 바꿔도 다른 계층이 그대로인 이유 |
| 3 | 날짜·인원별 가능 시간 | 인원 0명 → 422 | 규칙을 `TimeSlot`에 두면 조회·예약이 같은 판단을 하는 이유 |
| 4 | 예약 → 201 | 꽉 찬 슬롯 → 409 | 트랜잭션과 행 락이 무엇을 막는지 |
| 5 | 운영자 자기 식당 예약 | 다른 식당 → 403 | 역할 검사와 소유 검사를 나누는 이유, 401 · 403 · 404의 차이 |

## 7. 팀이 확인할 것

- `restaurants.status` 값(예: `OPEN`·`CLOSED`)과, `CLOSED` 식당의 슬롯 예약을 막을지 (지금은 표시용)
- 에러 코드 이름 — 409 코드는 [ARCHITECTURE 4장](ARCHITECTURE.md#4-예약-규칙)에 있음. 나머지(`VALIDATION_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`)는 담당 2가 초안을 만들고 팀이 정함
- 모듈 골격 정리 (커밋 5fff636에서 시작) — 남은 것: `database.py`를 `src/restaurant/infrastructure/`에서 `src/common/`으로 이동, `reservation`·`common` 모듈과 빠진 `infrastructure/` 패키지 추가, `src/owner/`는 자기 테이블이 없으므로 `domain/`은 비워 둠. D4 시작 전에 지원 작업으로 정리
