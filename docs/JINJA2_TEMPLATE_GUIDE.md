# Jinja2 화면 구현 현황과 연결 가이드

갱신: 2026-11-04  
작업 저장소: `C:\B-backend-Fastapi`  
기준 브랜치: `feat/owner-reservations` (`55da514`에서 작업)

## 현재 결과

수업 방식에 맞춰 **FastAPI → 조회 서비스 → Jinja2 → HTML**로 구성했다.
프런트엔드 프레임워크나 브라우저의 fetch 호출 없이 서버에서 화면을 렌더링한다.

- 로그인 화면: 입력 틀과 미리보기 이동. 실제 로그인 구현 전이므로 입력·제출 비활성.
- 운영 식당: 식당별 카드, 실제 목록/0건/미연결 상태 구분.
- 식당 예약: 방문 날짜, 표시 개수(20/50/100), 예약 표, 상태 배지.
- 조회 조건: 날짜와 페이지 번호를 서버가 검증. 날짜를 비우면 전체 기간.
- 페이지 이동: 실제 결과의 전체 건수로 이전/다음 표시. 식당·날짜·표시 개수 유지.
- 방문 일시: 오프셋이 있는 datetime을 한국 시간으로 표시.
- 공통 UI: 사이드 메뉴, 모바일 메뉴, 카드·표·입력 스타일.
- 식당과 예약 조회 서비스 호출 및 반환값 변환 어댑터 작성.

**실제 인증과 DB 조회는 아직 미연결이다.** 기본 조회 의존성이 `None`을 반환하므로 실제 목록이나 0건으로 표시하지 않는다. 식당 카드 구성 예시는 실제 데이터가 아니다.

기존 API·도메인·ERD·DB에는 변경을 가하지 않았다. 예약 생성/취소, 고객 예약 화면도 추가하지 않았다.

## 실행

```powershell
cd C:\B-backend-Fastapi
uv sync --no-install-project
uv run --no-sync uvicorn main:app --app-dir src --reload
```

- 로그인: <http://127.0.0.1:8000/ui>
- 식당 목록: <http://127.0.0.1:8000/ui/owner/restaurants>
- 예약 화면: <http://127.0.0.1:8000/ui/owner/restaurants/1/reservations>
- 조건 예시: `/ui/owner/restaurants/1/reservations?date=2026-11-04&page=2&page_size=20`

작업 중 실행한 미리보기 서버는 <http://127.0.0.1:8015/ui>다.
예시 ID 1은 실제 식당 존재를 뜻하지 않는다.
HTML 파일을 직접 열지 말고 FastAPI 서버 주소로 접속한다.

Jinja2 3.1.6과 MarkupSafe 3.0.4를 프로젝트 가상환경에 설치했고 의존성 파일에도 기록했다. 기존 패키지 버전은 변경하지 않았다.
`--no-install-project`로 의존성만 설치하고 `--no-sync`로 해당 환경에서 소스를 실행한다.

## 파일과 연결 흐름

| 파일 | 역할 |
| --- | --- |
| `src/main.py` | HTML 라우터와 StaticFiles 등록 |
| `src/web.py` | GET 입력 검증, 조회 호출, Jinja2 context 전달, 한국 시간 출력 |
| `src/web_data.py` | 기존 OwnerService 호출 및 화면용 결과 변환 |
| `src/templates/base.html` | 공통 레이아웃과 메뉴 |
| `src/templates/login.html` | 로그인 화면 |
| `src/templates/owner/restaurants.html` | 식당 카드와 상태별 화면 |
| `src/templates/owner/reservations.html` | 조건 입력, 예약 표, 상태 배지 |
| `src/templates/components/pagination.html` | 공용 이전/다음 페이지 |
| `src/static/styles.css` | 반응형 스타일 |

```text
GET /ui/owner/restaurants
  → get_owner_ui_queries()에서 조회 객체 주입
  → OwnerUIQueries.restaurants(page, page_size)
  → OwnerService.list_my_restaurants(owner, PageParams)
  → PageResult(items, total, page, page_size)
  → restaurants.html에서 반복 렌더링

GET /ui/owner/restaurants/{id}/reservations
  → 날짜·페이지 입력 검증
  → OwnerUIQueries.reservations(id, date, page, page_size)
  → OwnerService.list_restaurant_reservations(owner, id, date, PageParams)
  → (Reservation, TimeSlot) 결과를 표에 필요한 값으로 변환
  → reservations.html에서 반복 렌더링
```

API와 HTML 라우터가 동일 application 서비스를 재사용한다. HTML 라우터에서 SQL을 작성하거나 같은 서버의 JSON API로 HTTP 요청을 보내지 않는다.

## 연결할 위치는 한 곳

`src/web_data.py`의 `get_owner_ui_queries()`가 연결 지점이다.
현재는 인증과 조회 모듈이 미완성이라 `None`을 반환한다.

다음은 **미완성 모듈과 HTML 인증 전달 방식을 완성한 뒤 적용할 연결 예시**다. 지금 붙이면 누락된 import 또는 미구현 인증으로 실패하므로 활성화하지 않았다.

```python
from fastapi import Depends
from container import create_owner_service
from owner.presentation.dependencies import require_owner

def get_owner_ui_queries(
    owner=Depends(require_owner),
    service=Depends(create_owner_service),
) -> OwnerUIQueries:
    return OwnerUIQueries(owner, service)
```

이 의존성을 연결하면 기존 어댑터가 서비스를 호출하고, 반환된 목록·전체 건수·페이지를 현재 템플릿이 표시한다. 서비스의 없는 식당/타인 식당 검사를 재사용한다. 인증을 건너뛰거나 임의 운영자 ID를 넣지 않는다.

현재 어댑터는 서비스 예외를 삼키거나 빈 목록으로 바꾸지 않는다. 오류 응답은 기존 앱 공통 핸들러를 따른다. HTML 전용 오류 화면은 후속 작업이다.

## 화면 데이터 계약

| 대상 | 값 |
| --- | --- |
| 식당 카드 | `id, name, address` |
| 예약 표 | `id, starts_at, party_size, contact_phone, status` |
| 페이지 | `items, total, page, page_size` |
| 날짜 | `YYYY-MM-DD`, 빈 값/생략은 전체 기간 |
| 페이지 입력 | `page >= 1`, `1 <= page_size <= 100` |

- `None`: 미연결. `[]`: 조회 성공 후 0건. 오류는 이 둘로 바꾸지 않는다.
- 상태는 현재 도메인의 `CONFIRMED` / `CANCELLED`를 표시한다.
- 값은 Jinja2의 기본 HTML 이스케이프를 유지한다. `|safe`는 쓰지 않는다.
- 토큰·비밀번호·해시를 context에 전달하지 않는다.
- 시간대가 없는 datetime은 임의로 한국 시간이라고 해석하지 않는다. 실제 데이터는 오프셋이 있는 값을 반환해야 한다.

## 앞으로 해야 할 일

### 1. 팀 모듈 통합

- [ ] `common.pagination.PageParams`의 `page/page_size` 생성 규격과 `offset` 확인.
- [ ] restaurant 도메인·출력 스키마·ORM·repository 통합.
- [ ] slot ORM/repository 및 reservation repository 통합.
- [ ] 사용자 ID UUID와 예약 user_id int 차이 합의.
- [ ] JSON owner 라우터를 `/api/v1`에 등록. 현재 main은 auth/user 라우터만 등록한다.
- [ ] JSON API에서 사용하는 `ReservationOut.from_domain()` 구현. HTML 어댑터는 현재 예약·슬롯 쌍에서 표에 필요한 필드를 직접 꺼낸다.

### 2. 인증 연결

- [ ] `auth/presentation/routers/v1/router.py`의 `login()` 구현. 현재 `pass`.
- [ ] `auth/presentation/dependencies.py`의 `get_authenticated_user()` 구현 (#14에서 이름이 바뀜, `AuthenticatedUser`를 돌려줌). 현재 `NotImplementedError`.
- [ ] 문서 계약인 OAuth2 `username=이메일/password`와 토큰 응답 확인.
- [ ] 일반 HTML 링크/폼 이동에서 인증을 유지할 방식을 확정하고 구현. Bearer 헤더는 링크 이동에 자동 첨부되지 않는다.
- [ ] `require_owner`와 요청별 서비스를 위 연결 함수에 주입.
- [ ] 실제 로그인 동작 이후 로그인 폼 활성화, 미리보기 안내 정리.

### 3. 실제 데이터와 권한 검증

- [ ] 실제 PostgreSQL 결과로 카드·예약 표·페이지 이동 확인.
- [ ] 본인 식당만 조회되고 다른 식당 ID로 우회할 수 없는지 확인.
- [ ] 날짜 필터와 한국 시간 경계 확인.
- [ ] 인증 없음/고객 역할/타인 식당/없는 식당/DB 장애 응답 확인.
- [ ] 로그아웃 및 만료된 토큰 접근 거절 확인.
- [ ] 연결 완료 화면을 발표 자료에 기록.

기존 팀 문서의 Jinja2 제외 문구는 과거 방침이다. 이번 요청에 따른 템플릿 작업을 README와 이 문서에 기록했으며, 다른 팀 설계 문서를 임의로 재작성하지 않았다.

## 확인한 범위

- 로컬 ASGI 요청으로 화면 3개와 CSS 정상 응답.
- 빈 날짜/잘못된 날짜/페이지 범위 및 표시 개수 검증.
- 테스트에서만 조회 의존성을 대체하여 목록 렌더링, HTML 이스케이프, 한국 시간 표시, 날짜를 유지하는 다음 페이지 링크 확인.
- 브라우저에서 좁은 화면의 로그인·식당 카드·예약 표, 날짜/표시 개수 제출 확인.

위 테스트용 데이터는 앱 또는 DB에 저장하지 않았다. 실제 OwnerService와 DB를 연결한 통합 테스트, 인증·권한 테스트는 아직 수행하지 않았다.

## 참고

- [FastAPI Jinja2](https://fastapi.tiangolo.com/advanced/templates/)
- [FastAPI StaticFiles](https://fastapi.tiangolo.com/tutorial/static-files/)
- [API 명세](API_SPEC.md)
- [담당별 계획](BACKEND_PLAN.md)
