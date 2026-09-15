from pydantic import BaseModel, Field
from typing import Literal, Optional, List

class Command(BaseModel):
    action: Literal["download", "play", "pause", "stop"] = Field(description="The action to perform")
    query: Optional[str] = Field(default=None, description="The search term or song to download, if applicable")

class AgentResponse(BaseModel):
    spoken_reply: str = Field(description="A short, conversational reply to the user.")
    commands: List[Command] = Field(default_factory=list, description="A list of background commands to execute.")
