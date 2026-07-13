from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationCase:
    category: str
    text: str


LETTER_NAMES = (
    "a, bé, cé, dé, e, effe, gé, ache, i, ji, ka, elle, aime, enne, o, pé, ku, erre, esse, té, u, vé, double vé, iks, i grec, zède",
)
VOCABULARY = (
    "une habitude", "améliorer", "se réveiller", "dépendre de", "avoir besoin de",
    "être en forme", "tout à fait", "une journée", "prendre soin de", "faire attention",
    "un quartier", "une fenêtre", "un chemin", "commencer", "continuer", "choisir",
    "comprendre", "apprendre", "écouter", "regarder", "raconter", "expliquer",
    "important", "possible", "souvent", "ensemble", "maintenant", "demain", "beaucoup", "parfois",
)
CONNECTED = (
    "Les enfants arrivent à l'école.", "Vous avez un ami à Paris.", "Il est encore en avance.",
    "Nous allons au marché demain.", "Ils ont acheté une orange.", "On écoute une histoire.",
    "Elle habite dans un appartement.", "Vous êtes très aimable.", "Les oiseaux chantent au matin.",
    "Un grand homme entre dans la salle.", "Nous avons appris une nouvelle chanson.",
    "Il faut écouter attentivement.", "Les petits enfants jouent ensemble.", "C'est une belle occasion.",
    "Vous êtes arrivé avant midi.", "Ils ont un autre exercice.", "Elle est en bonne santé.",
    "Nous parlons avec nos amis.", "On prend un café après le cours.", "Les étudiants lisent un article.",
)
ARTICLE = (
    "La journée commence tôt dans le petit village.", "Les habitants travaillent ensemble pour protéger la rivière.",
    "Chaque matin, une famille ouvre les fenêtres de sa maison.", "Le marché attire des visiteurs de plusieurs quartiers.",
    "Les enfants découvrent les plantes dans le jardin.", "Un chemin tranquille traverse la forêt près du village.",
    "Les abeilles vivent dans une grande colonie près des fleurs.", "La bibliothèque propose des livres pour tous les âges.",
    "Le musée présente une histoire importante de la région.", "Les voyageurs observent les oiseaux au bord du lac.",
    "Une petite équipe prépare une activité pour les habitants.", "Le professeur explique pourquoi cette tradition continue.",
    "Les familles se retrouvent souvent pendant la fête.", "La pluie change parfois le programme de la journée.",
    "Les élèves écrivent leurs observations dans un carnet.", "Le village conserve plusieurs bâtiments anciens.",
    "Les visiteurs peuvent apprendre beaucoup pendant cette promenade.", "Une association organise des rencontres chaque semaine.",
    "Le soleil revient après une matinée nuageuse.", "Cette région est connue pour ses paysages variés.",
)


def evaluation_cases() -> list[EvaluationCase]:
    return (
        [EvaluationCase("letter", text) for text in LETTER_NAMES[0].split(", ")]
        + [EvaluationCase("vocabulary", text) for text in VOCABULARY]
        + [EvaluationCase("connected_speech", text) for text in CONNECTED]
        + [EvaluationCase("article_sentence", text) for text in ARTICLE]
    )
