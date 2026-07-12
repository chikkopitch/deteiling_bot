from uuid import uuid4
from app.database.models import FAQItem
from app.services.faq import normalize_search, rank_faq


def test_faq_normalization_handles_case_punctuation_and_yo() -> None:
    assert normalize_search("  ЧЁРНЫЕ-пятна?! ") == "черные пятна"


def test_faq_question_match_ranks_above_answer_match() -> None:
    question = FAQItem(
        id=uuid4(),
        question="Как удалить шерсть?",
        answer="Ответ",
        keywords="животные",
        sort_order=0,
    )
    answer = FAQItem(
        id=uuid4(),
        question="Другой вопрос",
        answer="Мы удаляем шерсть",
        keywords=None,
        sort_order=0,
    )
    assert rank_faq([answer, question], "шерсть") == [question, answer]
