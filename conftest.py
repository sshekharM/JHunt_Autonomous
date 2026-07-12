"""
Root conftest — sets minimum env vars before any app module is imported.
Must run before tests/conftest.py which imports app.main.
"""
import os
from cryptography.fernet import Fernet

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-32-bytes-xxxxxxxx")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "testminiocredential")
os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())
os.environ.setdefault("GOOGLE_CLIENT_ID", "test")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test")
