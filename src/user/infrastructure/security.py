# [담당1 - 강성수]

import bcrypt
from user.domain.hasher import PasswordHasher


class BcryptPasswordHasher(PasswordHasher):
    def hash(self, raw_password: str) -> str:
        pwd_bytes = raw_password.encode("utf-8")
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(pwd_bytes, salt)
        return hashed.decode("utf-8")

    def verify(self, raw_password: str, hashed_password: str) -> bool:
        pwd_bytes = raw_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
