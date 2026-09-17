from pydantic import BaseModel, Field
from typing import Literal, Optional, List

class Command(BaseModel):
    action: Literal["download", "play", "pause", "stop"] = Field(description="The action to perform")
    query: Optional[str] = Field(default=None, description="The search term or song to download, if applicable")
    media_type: Optional[Literal["audio", "video"]] = Field(default=None, description="Must be 'audio' or 'video'. Leave null if you need to ask the user.")

class AgentResponse(BaseModel):
    spoken_reply: str = Field(description="Conversational reply. If downloading and media_type is unknown, ask the user if they want audio or video.")
    commands: List[Command] = Field(default_factory=list, description="List of actions. DO NOT issue a download action unless media_type is explicitly known.")
