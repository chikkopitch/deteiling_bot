import re
from unicodedata import normalize

from app.database.models import FAQItem


def normalize_search(value: str) -> str:
    value = normalize("NFKC", value).casefold().replace("ё", "е")
    return " ".join(re.findall(r"[a-zа-я0-9]+", value))


def rank_faq(items: list[FAQItem], query: str) -> list[FAQItem]:
    normalized = normalize_search(query)
    tokens = set(normalized.split())
    if not tokens:
        return []
    ranked = []
    for item in items:
        question = normalize_search(item.question)
        answer = normalize_search(item.answer)
        keywords = normalize_search(item.keywords or "")
        score = 0
        if normalized in question:
            score += 100
        if normalized in keywords:
            score += 70
        if normalized in answer:
            score += 40
        score += sum(10 for token in tokens if token in question)
        score += sum(6 for token in tokens if token in keywords)
        score += sum(2 for token in tokens if token in answer)
        if score:
            ranked.append((score, item.sort_order, item.question.casefold(), item))
    return [
        item
        for _, _, _, item in sorted(ranked, key=lambda row: (-row[0], row[1], row[2]))
    ]
