from datetime import datetime
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

PASSWORD_SPECIAL_CHAR_REGEX = re.compile(r"[!@#$%^&*(),.?\":{}|<>]")
PasswordStr = Annotated[str, StringConstraints(strip_whitespace=False)]



class Token(BaseModel):
    access_token: str
    token_type: str


class NewUserCreate(BaseModel):

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid"
    )
    
    username: str = Field(
        description="Users username", 
        min_length=5, 
        max_length=100,
        examples=["user@example.com", "a.seddighi"]
    )
    

    name: str = Field(
        min_length=1, 
        max_length=50,
        description="User full name",
        examples=["Amir sed"]
    )


    password: PasswordStr = Field(
        min_length=8, 
        max_length=128,
        description="Must contain uppercase,lowercase,numbers and special chars"
    )
    password_repeat: PasswordStr = Field(min_length=8, max_length=128)


    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        if not PASSWORD_SPECIAL_CHAR_REGEX.search(v):
            raise ValueError("Password must contain at least one special character")
        return v


    @model_validator(mode="after")
    def check_password_match(self) -> "NewUserCreate":
        if self.password != self.password_repeat:
            raise ValueError("Password and password repeat are not match")
        return self


class CurrentUserInfoResponse(BaseModel):
    username: str
    name: str
    created_at: datetime
