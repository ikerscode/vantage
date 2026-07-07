from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserClaims(BaseModel):
    sub: str
    name: str
    roles: list[str]
