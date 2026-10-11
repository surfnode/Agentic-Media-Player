from pydantic import BaseModel, Field
from typing import Literal, Optional, List

class Command(BaseModel):
    action: Literal[
        "download", "play", "pause", "stop", "next", "prev", "shuffle", "search_shows"
    ] = Field(
        description=(
            "The action to perform. 'next' and 'prev' skip tracks, "
            "'shuffle' toggles shuffle mode. These need no query."
        )
    )
    query: Optional[str] = Field(default=None, description="The search term, song, or the artist name when searching for shows")
    media_type: Optional[Literal["audio", "video"]] = Field(default=None, description="Must be 'audio' or 'video'. Leave null if you need to ask the user.")

class AgentResponse(BaseModel):
    spoken_reply: str = Field(description="Conversational reply. If downloading and media_type is unknown, ask the user if they want audio or video.")
    commands: List[Command] = Field(default_factory=list, description="List of actions. DO NOT issue a download action unless media_type is explicitly known.")
