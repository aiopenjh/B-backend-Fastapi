# API 명세 작성 기준

각자 자기 API의 명세를 이 기준에 맞춰 씁니다. API 목록과 담당은 [ARCHITECTURE 5장](ARCHITECTURE.md#5-api와-담당)을 따르고, 필드와 규칙은 [BACKEND_PLAN 4장](BACKEND_PLAN.md#4-담당별-상세)과 [TEAM_CONVENTIONS 3장](TEAM_CONVENTIONS.md#3-api-약속)을 따릅니다.

명세는 **구현 전에** 씁니다. 성공 예시 1개와 실패 예시 1개를 먼저 정하고, 그 예시가 그대로 첫 테스트가 됩니다.

## 1. 작성 원칙

| 원칙 | 이유 |
| --- | --- |
| **API 하나 = 명세 하나** (경우마다 나누지 않음) | 같은 경로·메서드가 여러 번 나오지 않게 합니다 |
| **요청 상세는 한 가지 형식만** | 잘못된 값은 "다른 요청"이 아니라 "실패 응답을 받는 경우"입니다 |
| **응답 상세는 상태 코드별로 나눔** | 성공 1개와 실패 여러 개를 코드로 구분합니다 |
| **성공·실패 응답 본문은 모두 공통 봉투(`APIResponse`)를 따름** | 성공이면 `data`만, 실패면 `code`·`message`·`errors`만 경우마다 다릅니다. 형식을 매번 다시 쓰지 않습니다 |
| **실패 예시는 "이 요청 → 이 응답"으로 짝지음** | 그대로 실패 테스트 케이스가 됩니다 |
| **같은 200 안에서 값만 다른 경우는 실패가 아님** | 예: 예약 가능 조회의 `available: true/false`는 200 예시 하나에 둘 다 보이게 씁니다 |

## 2. 공통 규칙

### 기본 정보

| 항목 | 값 |
| --- | --- |
| Base URL | `http://localhost:8000/api/v1` |
| 인증 | `Authorization: Bearer <access_token>` (로그인 API로 발급) |
| 요청 본문 | `Content-Type: application/json` (로그인만 폼 `application/x-www-form-urlencoded`) |
| 시각 | 오프셋 포함 ISO 8601, Asia/Seoul 기준 (예: `2026-10-30T18:00:00+09:00`) |
| 가격 | 원 단위 정수 |

### 응답 봉투 `APIResponse[T]` (`common/schemas.py`)

모든 응답 본문은 아래 봉투 하나로 감쌉니다. 성공 여부는 `success`와 HTTP 상태 코드가 **항상 같이** 말합니다 (실패를 200으로 보내지 않습니다).

| 필드 | 타입 | 성공 | 실패 |
| --- | --- | --- | --- |
| `success` | 불리언 | `true` | `false` |
| `code` | 문자열 | `"OK"` | 에러 코드 표의 값 (예: `"SLOT_SOLD_OUT"`) |
| `message` | 문자열 | 처리 결과 메시지 | 사람이 읽을 실패 이유 |
| `errors` | 객체 또는 `null` | `null` | 필드 이름 → 메시지 목록 (예: `{"party_size": ["1 이상이어야 합니다."]}`), 특정 필드가 없으면 `{}` |
| `data` | `T` 또는 `null` | 출력 스키마 (`UserResponse`, `ReservationOut`, `Page[T]` …) | `null` |
| `request_id` | 문자열 | 요청 로그 미들웨어가 만든 id (응답 헤더 `X-Request-ID`와 같은 값) | 같음 |
| `responded_at` | 시각 | 응답 시각 | 같음 |

성공:

```json
{
  "success": true,
  "code": "OK",
  "message": "요청이 성공적으로 처리되었습니다.",
  "errors": null,
  "data": { "id": "00000000-0000-4000-8000-000000000001", "email": "customer-a@example.com" },
  "request_id": "req_8f2c1a",
  "responded_at": "2026-10-28T15:20:00+09:00"
}
```

실패:

```json
{
  "success": false,
  "code": "SLOT_SOLD_OUT",
  "message": "남은 자리가 부족합니다.",
  "errors": {},
  "data": null,
  "request_id": "req_8f2c1a",
  "responded_at": "2026-10-28T15:20:00+09:00"
}
```

클라이언트는 `message` 문구가 아니라 `code`로 분기합니다. 실패 봉투는 라우터에서 직접 만들지 않습니다. 서비스·도메인이 `AppError` 계열 예외를 던지면 공통 핸들러(`common/error_handlers.py`)가 실패 봉투로 바꿉니다. FastAPI 기본 422(`RequestValidationError`)도 같은 핸들러가 `VALIDATION_ERROR` 봉투로 바꿉니다.

**봉투를 쓰지 않는 예외 (2개)**

| API | 이유 | 응답 |
| --- | --- | --- |
| `POST /auth/login` 성공 | OAuth2 표준 토큰 응답이어야 `/docs`의 Authorize 버튼이 동작함 | 200 `{access_token, token_type, expires_in}` (최상위) |
| `POST /auth/logout` 성공 | 204는 본문이 없음 | 204, 본문 없음 |

두 API도 **실패 응답은 봉투**를 씁니다 (예: 로그인 실패 401).

### 목록 응답 `Page[T]`

목록은 `data` 안에 `Page[T]`를 넣습니다.

```json
{
  "success": true,
  "code": "OK",
  "message": "요청이 성공적으로 처리되었습니다.",
  "errors": null,
  "data": {
    "items": [],
    "page": 1,
    "page_size": 20,
    "total": 0
  },
  "request_id": "req_8f2c1a",
  "responded_at": "2026-10-28T15:20:00+09:00"
}
```

`page` 기본 1, `page_size` 기본 20·최대 100. 정렬 순서는 항상 같게 합니다.

### 에러 코드

| 상태 | code | 뜻 |
| --- | --- | --- |
| 401 | `UNAUTHORIZED` | 토큰 없음·만료·로그아웃한 토큰, 로그인 실패 |
| 400 | `DUPLICATED_USER_ERROR` | 이미 가입된 이메일 (대소문자·앞뒤 공백 무시, 동시 가입으로 commit에서 걸린 경우 포함) |
| 400 | `INVALID_ROLE_CHANGE` | `ADMIN` 부여, `ADMIN` 계정의 역할 변경 |
| 403 | `FORBIDDEN` | 운영자가 아님(역할), 남의 식당(소유), 관리자가 아님(`require_admin`) |
| 404 | `NOT_FOUND` | 없는 리소스, 관련 없는 사람에게 숨긴 리소스 (예: 남의 예약) |
| 404 | `USER_NOT_FOUND` | 없거나 탈퇴한 사용자 (역할 변경) |
| 409 | `SLOT_SOLD_OUT` | 남은 자리 부족 |
| 409 | `PARTY_SIZE_EXCEEDED` | 슬롯의 1회 최대 인원 초과 |
| 409 | `SLOT_ALREADY_STARTED` | 이미 시작한 시간대 |
| 409 | `DUPLICATE_RESERVATION` | 같은 시간대에 이미 `CONFIRMED` 예약이 있음 |
| 409 | `ALREADY_CANCELLED` | 이미 취소한 예약 |
| 409 | `CANCELLATION_NOT_ALLOWED` | 시작 시각이 지나 취소할 수 없음 |
| 422 | `VALIDATION_ERROR` | 형식이 잘못된 입력 (필드 누락, 타입·범위 위반) |
| 500 | `INTERNAL_SERVER_ERROR` | 처리하지 못한 예외. 요청 로그 미들웨어가 잡아 `request_id`가 든 실패 봉투로 응답하고 스택을 로그에 남김 |
| 503 | `SERVICE_UNAVAILABLE` | DB 연결 실패 |

401·403·404·422·500·503 코드는 `common/errors.py`의 `CommonErrorCode`에 들어 있습니다 (HTTP 상태와 기본 메시지를 함께 가짐). 모듈 전용 코드는 각 모듈의 `domain/exceptions.py`에 있습니다: 사용자 400·404(`user`), `SLOT_SOLD_OUT`·`PARTY_SIZE_EXCEEDED`·`SLOT_ALREADY_STARTED`(`slot`), `ALREADY_CANCELLED`(`reservation`). `DUPLICATE_RESERVATION`·`CANCELLATION_NOT_ALLOWED`는 아직 코드에 없고, 쓰는 담당이 추가합니다. 새 코드가 필요하면 이 표에 먼저 추가하고 공유합니다.

### 예시 데이터

모든 명세가 같은 시드 데이터를 가정하면 예시끼리 맞물립니다.

사용자 id는 UUID입니다(2026-11-04, [ARCHITECTURE 3장](ARCHITECTURE.md#3-데이터-모델-erd)). 예시에서는 읽기 쉽게 `00000000-0000-4000-8000-00000000000N` 형식을 쓰고, 아래 표에서는 끝자리만 `…0001`처럼 줄여 씁니다. 실제 값은 저장할 때 정해집니다. 식당·슬롯·예약 id는 정수 그대로입니다.

| id | 대상 | 설명 |
| --- | --- | --- |
| 사용자 `…0001` · `…0002` | 고객 A · 고객 B | `role: CUSTOMER` |
| 사용자 `…0003` · `…0004` | 운영자 A · 운영자 B | `role: OWNER` |
| 식당 1 · 2 | 운영자 A 소유 | `owner_id: "…0003"` |
| 식당 3 | 운영자 B 소유 | `owner_id: "…0004"` |
| 슬롯 7 | 식당 1, 열린 슬롯 | `capacity: 10`, `reserved_guests: 2`, `max_party_size: 4` |
| 슬롯 9 | 식당 1, 거의 찬 슬롯 | `capacity: 10`, `reserved_guests: 8`, `max_party_size: 4` |

## 3. 템플릿

아래 블록을 복사해서 `## 4. API 명세` 아래에 자기 API를 추가합니다. 쓰지 않는 칸(예: 인증 없는 API의 `Authorization`)은 지웁니다.

````md
### <기능명>

| 항목 | 값 |
| --- | --- |
| 기능 분류 | <user / restaurant / slot / reservation / owner> |
| API Path | `/api/v1/...` |
| http method | `GET` / `POST` / `PATCH` |
| 담당자 | <이름> (담당 N) |
| 인증 | 필요 없음 / 로그인 / 운영자 |
| 명세 작성 현황 | 시작 전 / 작성 중 / 완료 |
| 테스트 여부 | ☐ 정상 · ☐ 실패 |

**요청 상세**

```http
<METHOD> /api/v1/...
Content-Type: application/json
Authorization: Bearer <access_token>

{ }
```

| 필드 | 위치 | 타입 | 필수 | 규칙 |
| --- | --- | --- | --- | --- |
| | path / query / body | | O / X | |

**응답 상세**

| 상태 | code | 언제 |
| --- | --- | --- |
| 200 | `OK` | 성공 |
| 4xx | `...` | |

성공 응답 예시 (봉투의 `data` 부분만 쓰고, 나머지 필드는 공통 형식을 따름):

```json
{
  "success": true,
  "code": "OK",
  "data": { }
}
```

**실패 예시** (요청 → 응답, 최소 1개)

```text
[<상태> <code>]
요청: ...
응답: ...
```
````

## 4. API 명세

API 목록은 [ARCHITECTURE 5장](ARCHITECTURE.md#5-api와-담당)에 있습니다. 각자 템플릿으로 자기 API를 이 아래에 추가합니다. 아래 예약 생성은 작성 예시입니다.

### 예약 생성 (작성 예시)

| 항목 | 값 |
| --- | --- |
| 기능 분류 | reservation |
| API Path | `/api/v1/reservations` |
| http method | `POST` |
| 담당자 | 김민지 (담당 4) |
| 인증 | 로그인 |
| 명세 작성 현황 | 작성 중 |
| 테스트 여부 | ☐ 정상 · ☐ 실패 |

**요청 상세**

```http
POST /api/v1/reservations
Content-Type: application/json
Authorization: Bearer <access_token>

{
  "slot_id": 7,
  "party_size": 2,
  "contact_phone": "010-1234-5678"
}
```

| 필드 | 위치 | 타입 | 필수 | 규칙 |
| --- | --- | --- | --- | --- |
| `slot_id` | body | 정수 | O | 존재하는 슬롯 id |
| `party_size` | body | 정수 | O | 1 이상 (상한은 슬롯의 `max_party_size`로 409에서 판단) |
| `contact_phone` | body | 문자열 | X | 연락처, 20자 이하 |

**응답 상세**

| 상태 | code | 언제 |
| --- | --- | --- |
| 201 | `OK` | 예약 성공 |
| 401 | `UNAUTHORIZED` | 토큰 없음·만료·로그아웃한 토큰 |
| 404 | `NOT_FOUND` | 없는 `slot_id` |
| 409 | `SLOT_ALREADY_STARTED` | 시작 시각이 지난 슬롯 |
| 409 | `PARTY_SIZE_EXCEEDED` | `party_size`가 슬롯의 `max_party_size`보다 큼 |
| 409 | `SLOT_SOLD_OUT` | 남은 자리(`capacity − reserved_guests`)보다 많음 |
| 409 | `DUPLICATE_RESERVATION` | 같은 슬롯에 이미 `CONFIRMED` 예약이 있음 |
| 422 | `VALIDATION_ERROR` | 필드 누락, `party_size`가 0 이하 |

성공 응답 예시 (`APIResponse[ReservationOut]`):

```json
{
  "success": true,
  "code": "OK",
  "message": "예약이 완료되었습니다.",
  "errors": null,
  "data": {
    "id": 15,
    "user_id": "00000000-0000-4000-8000-000000000001",
    "slot_id": 7,
    "restaurant_id": 1,
    "starts_at": "2026-10-30T18:00:00+09:00",
    "ends_at": "2026-10-30T19:00:00+09:00",
    "party_size": 2,
    "contact_phone": "010-1234-5678",
    "status": "CONFIRMED",
    "created_at": "2026-10-28T15:20:00+09:00",
    "cancelled_at": null,
    "can_cancel": true
  },
  "request_id": "req_5d1e42",
  "responded_at": "2026-10-28T15:20:00+09:00"
}
```

**실패 예시**

```text
[409 SLOT_SOLD_OUT]
요청: POST /api/v1/reservations  {"slot_id": 9, "party_size": 3}   (고객 A, 남은 자리 2)
응답: 409
{
  "success": false,
  "code": "SLOT_SOLD_OUT",
  "message": "남은 자리가 부족합니다.",
  "errors": {"party_size": ["남은 자리(2명)보다 많습니다. 요청: 3명"]},
  "data": null,
  "request_id": "req_8f2c1a",
  "responded_at": "2026-10-28T15:20:00+09:00"
}
```

```text
[422 VALIDATION_ERROR]
요청: POST /api/v1/reservations  {"slot_id": 7, "party_size": 0}
응답: 422
{
  "success": false,
  "code": "VALIDATION_ERROR",
  "message": "입력값이 올바르지 않습니다.",
  "errors": {"party_size": ["1 이상이어야 합니다."]},
  "data": null,
  "request_id": "req_3b9d70",
  "responded_at": "2026-10-28T15:20:01+09:00"
}
```

### 회원가입

| 항목 | 값 |
| --- | --- |
| 기능 분류 | user |
| API Path | `/api/v1/users` |
| http method | `POST` |
| 담당자 | 강성수 (담당 1) |
| 인증 | 필요 없음 |
| 명세 작성 현황 | 완료 (코드 #18·#25. `main.py`의 `wire_dependencies(app)` 연결 전이라 지금은 500) |
| 테스트 여부 | ☐ 정상 · ☐ 실패 (API 테스트 없음. 서비스 단위 테스트 6개만 있음) |

**요청 상세**

```http
POST /api/v1/users
Content-Type: application/json

{
  "name": "고객A",
  "email": "customer-a@example.com",
  "password": "pass1234!",
  "phone": "010-1234-5678"
}
```

| 필드 | 위치 | 타입 | 필수 | 규칙 |
| --- | --- | --- | --- | --- |
| `name` | body | 문자열 | O | 2~20자 |
| `email` | body | 문자열 | O | 이메일 형식. 앞뒤 공백을 지우고 소문자로 바꿔 저장 (`Email` 값 객체) |
| `password` | body | 문자열 | O | 8자 이상, 영문·숫자·특수문자(`@$!%*#?&`)를 각각 1개 이상. 이 밖의 문자(공백, `^` 등)는 쓸 수 없음 |
| `phone` | body | 문자열 | O | 휴대폰 번호 `01[016789]-?\d{3,4}-?\d{4}` |

**응답 상세**

| 상태 | code | 언제 |
| --- | --- | --- |
| 201 | `OK` | 가입 성공 (역할은 항상 `CUSTOMER`) |
| 400 | `DUPLICATED_USER_ERROR` | 이미 가입된 이메일 |
| 422 | `VALIDATION_ERROR` | 필드 누락·형식 위반, 비밀번호 규칙 위반 (`errors.password`) |

성공 응답 예시 (`APIResponse[UserResponse]`, `password_hash`는 나가지 않음):

```json
{
  "success": true,
  "code": "OK",
  "message": "회원가입이 완료되었습니다.",
  "data": {
    "id": "6f1c2a4e-8b3d-4f5a-9c7e-1d2b3a4c5e6f",
    "email": "customer-a@example.com",
    "name": "고객A",
    "phone": "010-1234-5678",
    "role": "CUSTOMER"
  }
}
```

**실패 예시**

```text
[400 DUPLICATED_USER_ERROR]
요청: POST /api/v1/users  {"name": "고객A", "email": " Customer-A@Example.com ", "password": "pass1234!", "phone": "010-1234-5678"}   (customer-a@example.com 이미 가입)
응답: 400
{
  "success": false,
  "code": "DUPLICATED_USER_ERROR",
  "message": "중복된 회원이 등록되어 있습니다.",
  "errors": {},
  "data": null,
  ...
}
```

알려진 한계: 비밀번호 길이 상한이 없어 72바이트를 넘으면 bcrypt가 오류를 냅니다(500). `Email` 정규식이 `+`가 들어간 주소(예: `a+b@x.com`)를 422로 거부합니다.
