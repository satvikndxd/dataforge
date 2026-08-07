from backend.core.security import (
    Role,
    create_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    role_at_least,
    verify_password,
)


def test_password_roundtrip():
    stored = hash_password("hunter22!")
    assert verify_password("hunter22!", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("hunter22!", "garbage")


def test_jwt_roundtrip():
    token = create_token("usr_1", "org_1", "owner")
    claims = decode_token(token)
    assert claims is not None
    assert claims.sub == "usr_1" and claims.org == "org_1" and claims.kind == "access"


def test_jwt_tamper_rejected():
    token = create_token("usr_1", "org_1", "owner")
    assert decode_token(token[:-4] + "AAAA") is None
    assert decode_token("not.a.token") is None


def test_api_key_hashing():
    plaintext, digest = generate_api_key()
    assert plaintext.startswith("df_live_")
    assert hash_api_key(plaintext) == digest


def test_rbac_ordering():
    assert role_at_least(Role.OWNER, Role.ADMIN)
    assert role_at_least("builder", Role.REVIEWER)
    assert not role_at_least(Role.VIEWER, Role.BUILDER)
