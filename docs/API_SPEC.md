# API 명세 작성 기준

각자 자기 API의 명세를 이 기준에 맞춰 씁니다. API 목록과 담당은 [ARCHITECTURE 5장](ARCHITECTURE.md#5-api와-담당)을 따르고, 필드와 규칙은 [BACKEND_PLAN 4장](BACKEND_PLAN.md#4-담당별-상세)과 [TEAM_CONVENTIONS 3장](TEAM_CONVENTIONS.md#3-api-약속)을 따릅니다.

명세는 **구현 전에** 씁니다. 성공 예시 1개와 실패 예시 1개를 먼저 정하고, 그 예시가 그대로 첫 테스트가 됩니다.

## 1. 작성 원칙

| 원칙 | 이유 |
| --- | --- |
| **API 하나 = 명세 하나** (경우마다 나누지 않음) | 같은 경로·메서드가 여러 번 나오지 않게 합니다 |
| **요청 상세는 한 가지 형식만** | 잘못된 값은 "다른 요청"이 아니라 "실패 응답을 받는 경우"입니다 |
| **응답 상세는 상태 코드별로 나눔** | 성공 1개와 실패 여러 개를 코드로 구분합니다 |
| **실패 응답 본문은 공통 형식을 따름** | 경우마다 다른 건 `error.code`뿐입니다. 형식을 매번 다시 쓰지 않습니다 |
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

### 목록 응답 `Page[T]`

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 0
}
```

`page` 기본 1, `page_size` 기본 20·최대 100. 정렬 순서는 항상 같게 합니다.

### 실패 응답 공통 형식

```json
{
  "error": {
    "code": "SLOT_SOLD_OUT",
    "message": "남은 자리가 부족합니다.",
    "details": {},
    "request_id": "req_8f2c1a"
  }
}
```

클라이언트는 `message` 문구가 아니라 `code`로 분기합니다.

### 에러 코드

| 상태 | code | 뜻 |
| --- | --- | --- |
| 401 | `UNAUTHORIZED` | 토큰 없음·만료·로그아웃한 토큰, 로그인 실패 |
| 403 | `FORBIDDEN` | 운영자가 아님(역할), 남의 식당(소유) |
| 404 | `NOT_FOUND` | 없는 리소스, 관련 없는 사람에게 숨긴 리소스 (예: 남의 예약) |
| 409 | `SLOT_SOLD_OUT` | 남은 자리 부족 |
| 409 | `PARTY_SIZE_EXCEEDED` | 슬롯의 1회 최대 인원 초과 |
| 409 | `SLOT_ALREADY_STARTED` | 이미 시작한 시간대 |
| 409 | `DUPLICATE_RESERVATION` | 같은 시간대에 이미 `CONFIRMED` 예약이 있음 |
| 409 | `ALREADY_CANCELLED` | 이미 취소한 예약 |
| 409 | `CANCELLATION_NOT_ALLOWED` | 시작 시각이 지나 취소할 수 없음 |
| 422 | `VALIDATION_ERROR` | 형식이 잘못된 입력 (필드 누락, 타입·범위 위반) |
| 503 | `SERVICE_UNAVAILABLE` | DB 연결 실패 |

401·403·404·422·503 코드 이름은 담당 2(김태양)의 초안이고 팀이 확정합니다 ([BACKEND_PLAN 7장](BACKEND_PLAN.md#7-팀이-확인할-것)). 새 코드가 필요하면 이 표에 먼저 추가하고 공유합니다.

### 예시 데이터

모든 명세가 같은 시드 데이터를 가정하면 예시끼리 맞물립니다.

| id | 대상 | 설명 |
| --- | --- | --- |
| 사용자 1 · 2 | 고객 A · 고객 B | `role: CUSTOMER` |
| 사용자 3 · 4 | 운영자 A · 운영자 B | `role: OWNER` |
| 식당 1 · 2 | 운영자 A 소유 | `owner_id: 3` |
| 식당 3 | 운영자 B 소유 | `owner_id: 4` |
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
| 200 | — | 성공 |
| 4xx | `...` | |

성공 응답 예시:

```json
{ }
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
  "party_size": 2
}
```

| 필드 | 위치 | 타입 | 필수 | 규칙 |
| --- | --- | --- | --- | --- |
| `slot_id` | body | 정수 | O | 존재하는 슬롯 id |
| `party_size` | body | 정수 | O | 1 이상 (상한은 슬롯의 `max_party_size`로 409에서 판단) |

**응답 상세**

| 상태 | code | 언제 |
| --- | --- | --- |
| 201 | — | 예약 성공 |
| 401 | `UNAUTHORIZED` | 토큰 없음·만료·로그아웃한 토큰 |
| 404 | `NOT_FOUND` | 없는 `slot_id` |
| 409 | `SLOT_ALREADY_STARTED` | 시작 시각이 지난 슬롯 |
| 409 | `PARTY_SIZE_EXCEEDED` | `party_size`가 슬롯의 `max_party_size`보다 큼 |
| 409 | `SLOT_SOLD_OUT` | 남은 자리(`capacity − reserved_guests`)보다 많음 |
| 409 | `DUPLICATE_RESERVATION` | 같은 슬롯에 이미 `CONFIRMED` 예약이 있음 |
| 422 | `VALIDATION_ERROR` | 필드 누락, `party_size`가 0 이하 |

성공 응답 예시 (`ReservationOut`):

```json
{
  "id": 15,
  "user_id": 1,
  "slot_id": 7,
  "restaurant_id": 1,
  "starts_at": "2026-10-30T18:00:00+09:00",
  "ends_at": "2026-10-30T19:00:00+09:00",
  "party_size": 2,
  "status": "CONFIRMED",
  "created_at": "2026-10-28T15:20:00+09:00",
  "cancelled_at": null,
  "can_cancel": true
}
```

**실패 예시**

```text
[409 SLOT_SOLD_OUT]
요청: POST /api/v1/reservations  {"slot_id": 9, "party_size": 3}   (고객 A, 남은 자리 2)
응답: 409
{
  "error": {
    "code": "SLOT_SOLD_OUT",
    "message": "남은 자리가 부족합니다.",
    "details": {"remaining": 2, "requested": 3},
    "request_id": "req_8f2c1a"
  }
}
```

```text
[422 VALIDATION_ERROR]
요청: POST /api/v1/reservations  {"slot_id": 7, "party_size": 0}
응답: 422
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "입력값이 올바르지 않습니다.",
    "details": {"party_size": "1 이상이어야 합니다."},
    "request_id": "req_3b9d70"
  }
}
```
