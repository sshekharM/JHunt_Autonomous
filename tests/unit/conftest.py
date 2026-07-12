"""
Unit-test conftest — provides env vars so pydantic Settings can initialise
without a real .env file.  Does not touch the database.
"""
import os
import base64
from cryptography.fernet import Fernet

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-32-bytes-xxxxxxxx")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "testminiocredential")
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())
