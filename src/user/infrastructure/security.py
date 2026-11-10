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
        within_limit = len(pwd_bytes) <= BCRYPT_MAX_BYTES
        # 한도를 넘겨도 bcrypt 비용은 동일하게 들인다. 입력을 잘라 인증하지 않는다.
        hashed_bytes = hashed_password.encode("utf-8")
        matched = bcrypt.checkpw(pwd_bytes if within_limit else b"", hashed_bytes)
        return within_limit and matched
