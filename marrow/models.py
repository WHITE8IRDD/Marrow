from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Word:
    start: float
    end: float
    text: str
    score: float = 0.0  # normalized speech energy, 0..1


@dataclass
class Sentence:
    start: float
    end: float
    text: str
    words: List[Word] = field(default_factory=list)
    speaker: Optional[str] = None


@dataclass
class Candidate:
    start: float
    end: float
    sentences: List[Sentence]
    heuristic: float = 0.0
    llm: Optional[dict] = None
    llm_score: Optional[float] = None
    final: float = 0.0
    title: str = ""
    reason: str = ""
    hashtags: List[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.sentences)
