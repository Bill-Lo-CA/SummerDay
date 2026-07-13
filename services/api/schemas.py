from pydantic import BaseModel, Field

from services.audio.models import AudioAssetRef, LessonSentence, SpeechProfile


class VocabularyItem(BaseModel):
    lexical_item: str
    surface_form: str
    part_of_speech: str
    french_definition: str
    english_hint: str
    source_sentence: str
    lemma: str | None = None
    morphology: str | None = None


class LessonFocus(BaseModel):
    title: str
    explanation: str
    evidence: str


class DailyLesson(BaseModel):
    id: str
    title: str
    level: str
    source_title: str
    source_url: str
    source_revision: str
    article_text: str
    core_vocabulary: list[VocabularyItem] = Field(min_length=8, max_length=12)
    morphology_focus: LessonFocus
    pronunciation_focus: LessonFocus
    sentences: list[LessonSentence] = Field(default_factory=list)
    speech_profile: SpeechProfile | None = None
    learning_audio: AudioAssetRef | None = None
    natural_audio: AudioAssetRef | None = None
