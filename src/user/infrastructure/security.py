# [담당1 - 강성수]

import bcrypt
from user.domain.hasher import PasswordHasher

# bcrypt는 72바이트까지만 받는다. 넘으면 bcrypt 5가 ValueError를 던진다
BCRYPT_MAX_BYTES = 72


class BcryptPasswordHasher(PasswordHasher):
    def hash(self, raw_password: str) -> str:
        pwd_bytes = raw_password.encode("utf-8")
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(pwd_bytes, salt)
        return hashed.decode("utf-8")

    def verify(self, raw_password: str, hashed_password: str) -> bool:
        pwd_bytes = raw_password.encode("utf-8")
        # 가입 때 72바이트 이하로 막으므로 더 긴 값은 저장된 비밀번호일 수 없다.
        # 잘라서 비교하면 앞 72바이트만 맞아도 통과하므로 자르지 않고 거절한다
        if len(pwd_bytes) > BCRYPT_MAX_BYTES:
            return False
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
