# [담당1 - 강성수] 실제 bcrypt 해시 동작 테스트
from user.infrastructure.security import BcryptPasswordHasher

hasher = BcryptPasswordHasher()
HASHED = hasher.hash("abcd1234!")


def test_verify_accepts_correct_password():
    assert hasher.verify("abcd1234!", HASHED) is True


def test_verify_rejects_wrong_password():
    assert hasher.verify("wrong1234!", HASHED) is False


def test_verify_returns_false_for_password_over_72_bytes():
    # bcrypt 5는 72바이트를 넘으면 ValueError를 던진다 → 로그인 500 방지
    assert hasher.verify("a" * 73, HASHED) is False


def test_verify_does_not_truncate_to_72_bytes():
    # 앞 72바이트가 저장된 비밀번호와 같아도 통과하면 안 된다
    hashed_72 = hasher.hash("a" * 72)

    assert hasher.verify("a" * 72 + "b", hashed_72) is False


def test_verify_counts_bytes_not_characters():
    # 한글 1자 = UTF-8 3바이트. 25자 = 75바이트
    assert hasher.verify("가" * 25, HASHED) is False
