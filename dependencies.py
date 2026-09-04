import datetime
import os
from collections.abc import Callable, Generator

import bcrypt
import jwt
import mysql.connector
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mysql.connector import pooling


load_dotenv()

bearer_scheme = HTTPBearer(auto_error=False)

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

rds_db_config = {
    "user": os.getenv("DB_USER"),
    "host": os.getenv("RDS_HOST"),
    "password": os.getenv("RDS_PASSWORD"),
    "database": os.getenv("DB_NAME"),
}

pool = None


def get_pool() -> pooling.MySQLConnectionPool:
    global pool
    if pool is None:
        missing = [key for key, value in rds_db_config.items() if not value]
        if missing:
            raise RuntimeError(
                f"Missing database configuration: {', '.join(sorted(missing))}"
            )
        pool = pooling.MySQLConnectionPool(
            pool_name="mypool",
            pool_size=10,
            **rds_db_config,
        )
    return pool


def get_db():
    return get_pool().get_connection()


def get_db_connection() -> Generator:
    connection = get_db()
    try:
        yield connection
    finally:
        connection.close()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def _require_jwt_secret() -> str:
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY is required")
    return SECRET_KEY


def create_access_token(
    data: dict,
    expires_delta: datetime.timedelta = datetime.timedelta(days=7),
) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = data.copy()
    payload.update({"iat": now, "exp": now + expires_delta})
    return jwt.encode(payload, _require_jwt_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _require_jwt_secret(), algorithms=[ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def require_roles(*allowed_roles: str) -> Callable:
    def dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return dependency
