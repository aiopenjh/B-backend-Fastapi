# PR #8과 현재 슬롯 코드 비교·수동 검사 가이드

검증일: 2026-11-04 (Asia/Seoul). 원본 소스는 수정하지 않았다. 병합과 임시 수정은 `/tmp/pr8-compat-check` 복제본에서만 수행했다.

## 1. 결론과 비교 기준

**현재 작업 내용을 그대로 통합하면 Git 충돌과 실행 호환성 문제가 모두 있다.**

- [사용자가 지정한 화면](https://github.com/aiopenjh/B-backend-Fastapi/pull/8/changes/2fa81ee983f79dade5cbdb27bb25a543089441ab#top)은 PR 전체가 아니라 `2fa81ee` 커밋의 `time_slot.py` 수정이다.
- 이 커밋은 `self.ends_at.tzinfo`, 반환 타입 문법, `_violation(..., now)` 인자를 고친다. 현재 로컬에서도 이 세 가지는 수정되어 있다.
- PR 최신 head: `c63092c1d20cf53747841573a73af854559d565a`.
- 로컬: `feat/slot`, HEAD `581880e969940206ec24d9ad0937ab585f7f88b8` + 미커밋 수정 3개 + 새 `day_range.py`와 `tests/slot/`.
- 검증 시 원격 dev: `99308b16c0914747af917f6d87deeccac1cf1b9e`.

| 비교 | 결과 |
| --- | --- |
| 로컬 HEAD ↔ PR head | Git 자동 병합 가능 |
| 로컬 미커밋 작업 포함 ↔ 지정 커밋 `2fa81ee` | 아래 2개 파일 충돌 |
| 로컬 미커밋 작업 포함 ↔ PR head | 아래 2개 파일 충돌 |
| PR head ↔ 검증 시점 dev | Git 자동 병합 가능 |

충돌 파일은 `src/common/errors.py`, `src/slot/domain/time_slot.py`다. `git merge-tree --write-tree`로 실제 3-way 병합을 계산했다. 충돌이 없다는 결과는 실행 호환성을 보장하지 않는다.

## 2. 발견한 문제

### A. 임시 AppError와 PR의 정식 AppError 충돌

로컬 `src/common/errors.py` 끝에는 임시 `class AppError(Exception): pass`가 있다. PR은 같은 자리에 `error_code`, `message`, `errors`를 가진 정식 구현을 추가한다.

해결 방향: PR의 정식 구현을 채택하고 임시 클래스를 제거한다. 두 클래스를 동시에 남기거나 임시 클래스로 덮으면 안 된다.

### B. time_slot.py의 잔여석 분기 충돌

로컬은 잔여석 오류를 딕셔너리 한 개로 생성하고, `return None`을 분기 밖으로 옮겼다. PR은 기존 두 인자 호출을 포맷팅했고 `return None`도 기존 위치에 남아 있다. 같은 구간을 수정해서 충돌한다.

문법 수정은 양쪽이 같은 목적이다. 다만 잔여석 오류 생성 방식은 아래 C의 공통 예외 계약에 맞춰 다시 결정해야 한다. `return None`은 분기 밖에 명시하는 로컬 방향이 읽기 쉽다. PR의 현재 위치는 도달하지 않지만, 함수 끝의 암묵적 `None` 때문에 정상 예약 자체는 동작한다.

### C. 슬롯 예외가 공통 핸들러와 맞지 않아 HTTP 500 발생

`src/slot/domain/exceptions.py`는 `status_code = 409`, `code = "SLOT_..."`를 정의한다. PR의 핸들러는 이 속성들을 읽지 않고 **`exc.error_code.status`와 `exc.error_code.code`**를 읽는다. 그래서 기본 `INTERNAL_SERVER_ERROR`를 상속한다.

추가로:

- 시작한 슬롯: `errors={"starts_at": "시각 문자열"}`는 `dict[str, list[str]]` 계약 위반이다.
- 최대 인원 초과: `errors={"max_party_size": 4, "requested": 5}`도 계약 위반이다.
- 로컬 잔여석 부족: `SlotSoldOut({...})`는 딕셔너리를 첫 번째 인자 `message`에 넣는다. `errors`는 빈 딕셔너리가 되고 응답 스키마의 문자열 메시지 검증도 실패한다.

검증 시 PR의 공통 코드 + 로컬 슬롯 코드로 구성한 임시 앱에서 세 경우 모두 `500 / INTERNAL_SERVER_ERROR`를 재현했다. 원본 PR 자체도 세 경우 모두 500이었다.

수정 방향 예시(PR의 정식 공통 코드가 들어온 이후):

```python
from enum import unique
from http import HTTPStatus
from common.errors import AppError, ErrorCode

@unique
class SlotErrorCode(ErrorCode):
    SLOT_ALREADY_STARTED = (HTTPStatus.CONFLICT, "이미 시작한 시간대입니다.")
    PARTY_SIZE_EXCEEDED = (HTTPStatus.CONFLICT, "최대 인원을 초과했습니다.")
    SLOT_SOLD_OUT = (HTTPStatus.CONFLICT, "남은 자리가 부족합니다.")

class SlotRuleViolation(AppError):
    pass

class SlotAlreadyStarted(SlotRuleViolation):
    error_code = SlotErrorCode.SLOT_ALREADY_STARTED

class PartySizeExceeded(SlotRuleViolation):
    error_code = SlotErrorCode.PARTY_SIZE_EXCEEDED

class SlotSoldOut(SlotRuleViolation):
    error_code = SlotErrorCode.SLOT_SOLD_OUT
```

발생시키는 쪽도 키워드 인자를 사용한다:

```python
SlotAlreadyStarted(errors={"starts_at": ["이미 시작한 시간대입니다."]})
PartySizeExceeded(errors={"party_size": ["최대 예약 인원을 초과했습니다."]})
SlotSoldOut(errors={"party_size": ["남은 자리보다 요청 인원이 많습니다."]})
```

위 코드는 수정 제안이며 원본에 적용하지 않았다. 테스트는 예외와 `SlotErrorCode`를 정의한 `slot.domain.exceptions`에서 직접 가져오는 편이 명확하다.

### D. 현재 전체 테스트가 수집 단계에서 실패

`tests/slot/test_time_slot.py:10`에서 존재하지 않는 `SlotErrorCode`를 가져온다.

실행 결과:

| 대상 | 결과 |
| --- | --- |
| 현재 로컬 전체 pytest | ImportError로 수집 실패 |
| 현재 로컬 common + reservation | 13 passed |
| 원본 PR head 전체 pytest | 13 passed |
| PR 공통 코드 + 로컬 슬롯·테스트 | 동일 ImportError |
| 위 임시 복제본에서 해당 import 한 줄만 제거 | 15 passed |

15개 통과 상태에서도 HTTP 오류 3종은 모두 500이었다. 현재 슬롯 테스트 2개가 정상 판정과 시작 슬롯 예외만 검사하여, 공통 응답 변환 문제를 잡지 못하기 때문이다. 이 import 제거도 임시 복제본에서만 수행했다.

### E. UUID 변경은 예약 모듈과 아직 맞지 않음

PR의 User는 `UUID | None`, UserResponse는 `UUID`다. 현재 예약 코드는 다음 세 곳이 아직 정수다:

- `src/reservation/domain/reservation.py`: `user_id: int`
- `src/reservation/infrastructure/models.py`: `Mapped[int]` + `BigInteger` FK
- `src/reservation/presentation/schemas.py`: `ReservationOut.user_id: int`

실제 UUID를 `ReservationOut`에 넣으면 `user_id / int_type` ValidationError가 발생하는 것을 확인했다. 예약 도메인·ORM·응답·테스트 데이터를 함께 맞춰야 한다. Python dataclass의 타입 힌트만으로는 실행 시 차단되지 않으므로 생성 성공만으로 통합이 끝났다고 판단하면 안 된다.

슬롯의 `id`, `restaurant_id`는 이번 사용자 UUID 변경 대상이 아니다. 실제 PostgreSQL FK 변경·마이그레이션은 실행하지 않았다.

## 3. 직접 따라 하는 검사 순서

### ① 변경 기준부터 확인

```bash
cd /Users/young/DEV/back-end-project/B-backend-Fastapi
git branch --show-current
git rev-parse HEAD
git status --short
git diff -- src/common/errors.py src/slot/domain/time_slot.py src/slot/domain/exceptions.py
```

`git diff`에는 새 파일 내용이 나오지 않으므로 `day_range.py`, `tests/slot/test_time_slot.py`도 에디터로 읽는다. GitHub에서 `Commit 2fa81ee`를 보고 있는지, PR 전체 `Files changed`를 보고 있는지 구분한다.

### ② 원본을 건드리지 않는 복제본에서 충돌 검사

아래 명령은 현재 소스·테스트를 임시 복제본에만 스냅샷 커밋한다. 임시 AppError도 비교를 위해 이 복제본에만 포함한다. 원본 브랜치에 커밋하거나 push하지 않는다.

```bash
CHECK_DIR=$(mktemp -d /tmp/pr8-manual-XXXXXX)
git clone --no-hardlinks . "$CHECK_DIR"
cp -R src/. "$CHECK_DIR/src/"
cp -R tests/. "$CHECK_DIR/tests/"
git -C "$CHECK_DIR" add src tests
git -C "$CHECK_DIR" -c user.name=Review -c user.email=review@localhost \
  commit -m 'Temporary snapshot for compatibility check'
git -C "$CHECK_DIR" remote set-url origin https://github.com/aiopenjh/B-backend-Fastapi.git
git -C "$CHECK_DIR" fetch origin \
  refs/pull/8/head:refs/remotes/review/pr8 \
  refs/heads/dev:refs/remotes/review/dev
git -C "$CHECK_DIR" log -1 --oneline review/pr8
git -C "$CHECK_DIR" merge-tree --write-tree HEAD review/pr8
```

로컬 경로로 복제했으므로 `remote set-url`로 복제본의 origin만 GitHub로 바꾼다.

`merge-tree`는 충돌 시 종료 코드 1을 반환한다. 충돌 목록과 `CONFLICT` 메시지를 읽는다. 실제 작업 트리를 병합하지 않으므로 원본에서 `git merge --abort`를 실행할 필요가 없다. 지정 커밋까지 비교하려면 마지막 대상을 `2fa81ee983f79dade5cbdb27bb25a543089441ab`로 바꾼다.

### ③ 계약을 읽고 맞대어 보기

PR의 `common/errors.py → common/error_handlers.py → common/schemas.py` 순서로 읽는다.

질문 세 가지를 코드에서 확인한다:

1. 핸들러가 읽는 속성 이름은 무엇인가? → `error_code`.
2. 예외 생성자의 첫째·둘째 인자는 무엇인가? → `message`, `errors`.
3. 응답의 errors 값 타입은 무엇인가? → 필드별 문자열 목록.

그다음 `slot/domain/exceptions.py`, `_violation()`의 각 호출이 같은 계약을 지키는지 확인한다. Git 충돌을 없애는 작업과 이 계약을 맞추는 작업은 별도로 확인해야 한다.

### ④ 테스트 실행과 도메인 경계값 검사

원본에서 현재 상태를 확인하는 명령:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q tests/common tests/reservation
```

두 번째 명령 통과만으로 전체 성공으로 판단하지 않는다. 수정 후 임시 복제본에서도 전체 테스트를 실행한다. 복제본에는 `.venv`가 없으므로 원본 인터프리터의 절대 경로를 사용한다.

시간을 고정하고 아래 입력을 하나씩 넣어 본다. 각 실패에서는 `reserved_guests`가 바뀌지 않아야 한다.

| 조건 | 검사할 결과 |
| --- | --- |
| 정원 10, 예약 2, 최대 4, 미래 슬롯에 3명 예약 | 예약 5명, 잔여 5명 |
| 위 상태에서 3명 release | 예약 2명으로 복구 |
| now == starts_at | SlotAlreadyStarted |
| 최대 4명인데 5명 요청 | PartySizeExceeded |
| 잔여 1명·최대 4명인데 2명 요청 | SlotSoldOut |
| 이미 시작했고 정원도 가득 참 | SlotAlreadyStarted 우선 |
| 0명 요청, 예약보다 많이 release | ValueError, 좌석 불변 |

### ⑤ HTTP 응답까지 검사

현재 slot API는 연결되지 않았으므로 `/docs`에서 슬롯 요청을 호출하는 방식만으로는 검증할 수 없다. PR 공통 코드와 로컬 슬롯 코드를 합친 임시 복제본에서 아래 진단 파일을 `/tmp/pr8-http-manual.py`로 저장하고 실행한다. 실제 DB는 사용하지 않는다.

```python
from datetime import UTC, datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from common.error_handlers import register_error_handlers
from common.middleware import register_middleware
from slot.domain.time_slot import TimeSlot

app = FastAPI()
register_middleware(app)
register_error_handlers(app)
now = datetime(2026, 11, 4, 3, tzinfo=UTC)

@app.get('/probe/{case}')
def probe(case: str):
    starts = now if case == 'started' else now + timedelta(hours=1)
    slot = TimeSlot(
        id=7, restaurant_id=1, starts_at=starts,
        ends_at=now + timedelta(hours=2), capacity=10,
        reserved_guests=9 if case == 'sold-out' else 2,
        max_party_size=4,
    )
    slot.reserve(5 if case == 'party-size' else 2, now)
    return {'ok': True}

client = TestClient(app, raise_server_exceptions=False)
for case, code in [
    ('started', 'SLOT_ALREADY_STARTED'),
    ('party-size', 'PARTY_SIZE_EXCEEDED'),
    ('sold-out', 'SLOT_SOLD_OUT'),
]:
    response = client.get('/probe/' + case)
    body = response.json()
    print(case, response.status_code, body)
    assert response.status_code == 409
    assert body['code'] == code
    assert body['success'] is False
    assert body['request_id'] == response.headers['X-Request-ID']
    assert all(isinstance(v, list) and all(isinstance(x, str) for x in v)
               for v in body['errors'].values())
```

실행:

```bash
cd "$CHECK_DIR"
PYTHONPATH=src /Users/young/DEV/back-end-project/B-backend-Fastapi/.venv/bin/python \
  /tmp/pr8-http-manual.py
```

복제본에 PR의 정식 공통 예외 코드를 통합한 뒤 실행해야 한다. 현재 코드에서는 첫 409 검사부터 실패하는 것이 재현 결과다. 수정 후에는 3종 모두 409와 해당 코드, 문자열 목록 errors를 반환해야 한다.

### ⑥ UUID 경계를 마지막으로 확인

```bash
rg -n 'user_id|owner_id|UUID|BigInteger' src/user src/reservation src/owner
```

사용자 id가 지나가는 도메인 → 레포지토리 → ORM FK → 응답 스키마 → 테스트 픽스처를 순서대로 확인한다. UUID 예시값을 응답 스키마에 실제로 넣어 검증한다. 사용자 DB 모델과 FK가 준비된 뒤에는 별도 테스트 DB에서 타입과 저장·조회를 확인해야 한다.

## 4. 완료 판단과 검증 범위

- 두 파일의 Git 충돌을 해소한다.
- 정식 AppError, 슬롯 error_code, 예외 인자 형식을 함께 맞춘다.
- 전체 pytest가 수집부터 끝까지 통과한다.
- 슬롯 3종 오류가 HTTP 409와 정해진 코드로 나오는지 확인한다.
- 실패 요청에서 좌석이 유지되고 정상 예약·취소가 복구되는지 확인한다.
- UUID와 예약 user_id의 연결을 맞춘다.

이번 검증은 Git 병합 계산, 기존 테스트, 순수 도메인 실행, 임시 FastAPI 앱의 HTTP 응답, UUID 응답 검증까지다. 실제 DB, 회원가입 API 종단간 흐름, 인증 토큰, 행 락 동시성은 검증하지 않았다. PR에도 회원가입 레포지토리·인증 의존성은 골격 단계라고 명시되어 있다.
