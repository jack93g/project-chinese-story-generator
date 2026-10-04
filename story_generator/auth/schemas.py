from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    # Capped so a huge body can't make the server hash megabytes of input.
    password: str = Field(min_length=1, max_length=1024)


class CurrentUserResponse(BaseModel):
    # The database key, as a string: the identifier tracking uses for a
    # logged-in user. The username is for the UI only.
    id: str
    username: str
