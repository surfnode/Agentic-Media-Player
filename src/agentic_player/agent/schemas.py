from pydantic import BaseModel, Field
from typing import Literal, Optional, List

class Command(BaseModel):
    action: Literal[
        "download", "play", "pause", "stop", "next", "prev", "shuffle",
        "search_shows", "lyrics"
    ] = Field(
        description=(
            "The action to perform. 'next'/'prev' skip tracks, 'shuffle' toggles "
            "shuffle, 'lyrics' fetches song lyrics (no query = current track). "
            "These transport/lyrics actions need no query."
        )
    )
    query: Optional[str] = Field(
        default=None,
        description=(
            "The search term, song, or artist name. For downloads: ONLY the clean "
            "artist/song name - never filler words like 'playlist', 'songs', 'album', "
            "or numbers (numbers go in the count field instead). For lyrics: "
            "'artist - song' or just a song title; omit for the currently playing track."
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
            "Conversational reply - warm and natural, like a music-savvy friend. "
            "It is spoken aloud by TTS, so keep it reasonably short. For downloads: "
            "if media_type is unknown, ask audio or video; for multi-track requests "
            "without a number, ask how many. For lyrics, keep it brief ('Let me pull those up.')."
        )
    )
    commands: List[Command] = Field(
        default_factory=list,
        description=(
            "Actions to execute. Most conversational turns (artist questions, opinions, "
            "chat about music) should produce NO commands. Only issue commands when the "
            "user clearly asks for playback, downloads, lyrics, or concert searches."
        )
    )
