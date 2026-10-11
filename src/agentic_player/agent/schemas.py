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
    query: Optional[str] = Field(
        default=None,
        description=(
            "The search term, song, or artist name. For downloads: ONLY the clean "
            "artist/song name - never filler words like 'playlist', 'songs', 'album', "
            "or numbers (numbers go in the count field instead)."
        )
    )
    media_type: Optional[Literal["audio", "video"]] = Field(
        default=None,
        description="Must be 'audio' or 'video'. Leave null if you need to ask the user."
    )
    count: Optional[int] = Field(
        default=None,
        description=(
            "How many songs to download for multi-track requests (playlists, 'top 5', "
            "'10 songs'). Use null for a single song. If the user wants multiple tracks "
            "but gave no number, leave count null and ASK how many songs they want."
        )
    )

class AgentResponse(BaseModel):
    spoken_reply: str = Field(
        description=(
            "Conversational reply. For downloads: if media_type is unknown, ask audio or video; "
            "if it's a multi-track request without a number, ask how many songs they want."
        )
    )
    commands: List[Command] = Field(
        default_factory=list,
        description="List of actions. DO NOT issue a download action unless media_type is explicitly known."
    )
