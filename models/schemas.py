from pydantic import BaseModel, Field
from typing import List, Optional

class Name(BaseModel):
    full: str

class Node(BaseModel):
    id: Optional[int]
    name: Optional[Name] = None
    title: Optional[dict] = None
    format: Optional[str] = None

class StaffEdge(BaseModel):
    role: str
    node: Node

class VA(BaseModel):
    name: Name

class CharEdge(BaseModel):
    role: str
    node: Node
    voiceActors: List[VA]

class StudioNode(BaseModel):
    name: str

class Studio(BaseModel):
    nodes: List[StudioNode]

class AnimeData(BaseModel):
    id: int
    title: dict
    source: Optional[str] = "ORIGINAL"
    format: Optional[str]
    averageScore: Optional[int] = 0
    genres: List[str]
    studios: Studio
    staff: dict # edges
    characters: Optional[dict] = None
    @property
    def romaji_title(self) -> str:
        return self.title.get("romaji", "Unknown")