import argparse
import os
from functools import lru_cache
from pathlib import Path
from typing import Callable

import stanza
from pydantic import BaseModel


PROCESSORS = "tokenize,mwt,pos,lemma,depparse"
MODEL_DIR = Path(os.getenv("STANZA_RESOURCES_DIR", "data/stanza"))


class TokenAnalysis(BaseModel):
    text: str
    lemma: str
    upos: str
    feats: str | None
    head: int
    deprel: str


class SentenceAnalysis(BaseModel):
    text: str
    tokens: list[TokenAnalysis]


class SuitabilityAnalysis(BaseModel):
    classification: str
    word_count: int
    sentence_count: int
    average_sentence_length: float
    longest_sentence_length: int
    proper_noun_density: float
    number_density: float
    morphology_opportunities: int


class NLPAnalysis(BaseModel):
    sentences: list[SentenceAnalysis]
    suitability: SuitabilityAnalysis


@lru_cache(maxsize=1)
def pipeline():
    return stanza.Pipeline(
        "fr",
        processors=PROCESSORS,
        model_dir=str(MODEL_DIR),
        download_method=None,
        use_gpu=os.getenv("STANZA_USE_GPU") == "1",
        verbose=False,
    )


def analyze_text(text: str, processor: Callable | None = None) -> NLPAnalysis:
    document = (processor or pipeline())(text)
    sentences = [
        SentenceAnalysis(
            text=sentence.text,
            tokens=[
                TokenAnalysis(
                    text=word.text,
                    lemma=word.lemma or word.text,
                    upos=word.upos or "X",
                    feats=word.feats,
                    head=word.head,
                    deprel=word.deprel or "dep",
                )
                for word in sentence.words
            ],
        )
        for sentence in document.sentences
    ]
    tokens = [token for sentence in sentences for token in sentence.tokens]
    word_tokens = [token for token in tokens if token.upos != "PUNCT"]
    lengths = [sum(token.upos != "PUNCT" for token in sentence.tokens) for sentence in sentences]
    word_count = len(word_tokens)
    proper_density = sum(token.upos == "PROPN" for token in word_tokens) / max(word_count, 1)
    number_density = sum(token.upos == "NUM" for token in word_tokens) / max(word_count, 1)
    average = word_count / max(len(sentences), 1)
    longest = max(lengths, default=0)

    # ponytail: initial A1 heuristic; replace with calibrated learner-data thresholds.
    suitable = average <= 24 and longest <= 40 and proper_density <= 0.15 and number_density <= 0.08
    suitability = SuitabilityAnalysis(
        classification="suitable" if suitable else "too_difficult",
        word_count=word_count,
        sentence_count=len(sentences),
        average_sentence_length=round(average, 2),
        longest_sentence_length=longest,
        proper_noun_density=round(proper_density, 3),
        number_density=round(number_density, 3),
        morphology_opportunities=sum(
            token.upos in {"VERB", "AUX"} and token.feats is not None and "VerbForm=Fin" in token.feats
            for token in word_tokens
        ),
    )
    return NLPAnalysis(sentences=sentences, suitability=suitability)


def download_models() -> None:
    stanza.download("fr", processors=PROCESSORS, model_dir=str(MODEL_DIR), verbose=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage SummerDay French NLP models.")
    parser.add_argument("command", choices=("download",))
    if parser.parse_args().command == "download":
        download_models()


if __name__ == "__main__":
    main()
