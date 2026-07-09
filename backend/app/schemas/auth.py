from pydantic import BaseModel

from app.models.user import User


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    avatar_url: str | None
    is_global_admin: bool

    @classmethod
    def from_model(cls, user: User) -> UserOut:
        return cls(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            is_global_admin=user.is_global_admin,
        )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
