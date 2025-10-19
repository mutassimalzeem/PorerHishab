import os, datetime
from passlib.context import CryptContext
from jose import jwt, JWTError
from dotenv import load_dotenv
from datetime import timedelta
from typing import Optional


load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY', 'default_secret_key')

ALGORITHM = os.getenv('ALGORITHM', 'default_algorithm')

ACCESS_TOKEN_EXPIRE_MINUTE = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTE', 'default_access_token_expire_minute'))


#   Password helpers
pwd_context = CryptContext(schemes=['bcrypt'], deprecated = 'auto')

def get_password_hash(plain_password: str) -> str:
    return pwd_context.hash(plain_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_context.verify(plain_password, hashed_password)



#   JWT Token helpers

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates an access token with the given data and expires after the given delta.

    Args:
        data (dict): Data to encode into the token.
        expires_delta (Optional[timedelta], optional): Expiration time delta. Defaults to None.

    Returns:
        str: The encoded access token.
    """
    to_encode = data.copy()
    compute_expiry = datetime.datetime.now(datetime.timezone.utc) + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTE))
    to_encode.update({"exp": compute_expiry})
    return jwt.encode(to_encode, SECRET_KEY, algorithm= ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        jwt.decode(token, SECRET_KEY, algorithms= [ALGORITHM])
        
    except JWTError:
        raise ValueError("Invalid or expired token")