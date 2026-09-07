from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class StaffUserCreate(UserCreate):
    role: str = Field(pattern="^(admin|advisor|finance)$")


class StaffUserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|advisor|finance)$")
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if self.role is None and self.is_active is None:
            raise ValueError("role or is_active is required")
        return self


class StaffUserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
