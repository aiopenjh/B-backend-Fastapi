# Jinja2 화면과 예약 흐름

프로젝트 루트에서 PostgreSQL과 FastAPI를 켠 뒤 브라우저로 접속합니다. [기본 실행](../README.md#실행-안내) · [로그 창이 있는 시연 앱](../demo/README.md)

## 역할별 진입점

| 화면 | 주소 | 할 수 있는 일 |
| --- | --- | --- |
| 로그인·회원가입 | `/ui`, `/ui/signup` | 손님 가입 후 바로 로그인. 기존 회원은 역할별 첫 화면으로 이동 |
| 손님 | `/ui/restaurants` → `/ui/restaurants/{id}` | 상호·메뉴·주소 검색, 구·동과 업종 선택, 사진·메뉴·잔여석 확인 후 예약 |
| 내 예약 | `/ui/my/reservations` | 내 예약 조회, 시작 전 확정 예약 취소 |
| 운영자 | `/ui/owner/restaurants` → `/ui/owner/restaurants/{id}/reservations` | 내 식당의 날짜별 예약과 예약자 조회, 입장·사유 있는 취소·노쇼 처리 |
| 관리자 | `/ui/admin/owners` | 상호 일부로 식당을 찾아 예약 열기, 운영자별 식당 조회, 사유와 메모를 남겨 취소 |

## 4명을 예약하면 10석이 6석이 되는 과정

1. 식당 상세를 열면 `src/web.py`가 날짜와 인원으로 `SlotService.get_availability()`를 호출합니다. 잔여석은 `capacity - reserved_guests`입니다.
2. 예약 폼을 `POST /ui/restaurants/{id}/reserve`로 제출합니다. 서버가 손님과 식당·날짜·시간대를 확인하고 `ReservationService.create()`를 호출합니다.
3. 서비스는 슬롯에 행 락을 걸고 중복과 잔여석을 확인합니다. 예약 한 건을 만들고 `reserved_guests`를 **예약 인원인 4**만큼 늘려 함께 커밋합니다.
4. 성공하면 HTTP 303으로 상세 화면을 다시 엽니다. 서버가 슬롯을 다시 조회해 완료 안내와 시간 버튼에 남은 6석을 표시합니다. [취소 시 좌석 복구 규칙](ARCHITECTURE.md#4-예약-규칙)

매진이면 일반 화면의 시간 버튼은 비활성이고 잔여석은 0입니다. 시연 앱에서는 잔여석을 그대로 표시하고 버튼을 열어 둡니다. 해당 시간에 예약이 없는 손님이 누르면 상세 화면에 실패 안내가, 로그 창에 `409 SLOT_SOLD_OUT`이 나옵니다.

## 화면과 코드 연결

| 코드 | 역할 |
| --- | --- |
| `src/main.py`, `src/web.py` | 화면 라우터·정적 파일 등록, 폼 처리, 서비스 호출, 템플릿 렌더링 |
| `src/web_auth.py` | `/ui` 전용 HttpOnly 쿠키에서 JWT를 읽어 사용자 확인. JSON API는 Bearer 헤더 사용 |
| `src/web_data.py` | 운영자와 조회 서비스를 `OwnerUIQueries`에 연결해 예약자와 입장·취소 버튼에 필요한 값 준비 |
| `src/browse/`, `src/admin/` | 손님 식당 검색과 관리자 식당·예약 조회 |
| `src/templates/restaurants/detail.html` | 시간대별 잔여석과 예약 결과 표시 |
| `src/templates/admin/` | 관리자 식당 검색 결과와 예약 목록 |
| `demo/log_panel_app.py` | 화면 로그와 시드 계정 전환 |

관리자 식당 표는 마지막 예약 **접수 시각** 순으로 정렬합니다. 검색어가 없으면 10곳을, 검색하면 상호가 부분 일치하는 식당을 보여 줍니다. 시연 앱에서는 관리자 창이 보이는 동안 3초마다 검색 조건을 유지한 채 결과 표만 다시 받아옵니다. 운영자 목록은 가입 순서를 유지합니다.

두 역할을 동시에 보여 줄 때는 다른 브라우저 프로필이나 일반 창·시크릿 창으로 엽니다. 같은 세션에서 계정을 바꾸면 두 탭의 로그인도 함께 바뀝니다. [발표 시나리오](../demo/SCENARIO.md)
