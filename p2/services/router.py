"""The symbol-question router: recognise "is there a function X?" and "what functions are in file Y?".

Those two kinds of Question are answered from the Index without the model (ADR-0004).
"""
import re

NAME = r"`?(\w+(?:\.\w+)*)`?"
END = r"(?: (?:in|в) .*)?\W*$"
RU_FUNCTION = r"(?:функци\w*|метод\w*)"
HAS_FUNCTION_PATTERNS = [
    r"is there (?:a |an |any )?(?:function|method) (?:called |named )?" + NAME + END,
    r"does (?:a |the |any )?(?:function|method) " + NAME + " exists?" + END,
    r"(?:есть|существует) ли (?:(?:в|у) (?:\S+ ){1,2})?" + RU_FUNCTION + " (?:с именем |под названием )?" + NAME + END,
]

FILE = r"`?([\w./-]+\.\w+)`?"
IN_FILE = r"(?:in|inside|from|of) (?:the )?(?:file )?" + FILE + r"\W*$"
RU_IN_FILE = r"(?:в|из|внутри) (?:файле |файла )?" + FILE + r"\W*$"
FILE_FUNCTIONS_PATTERNS = [
    r"(?:what|which) (?:functions|methods) (?:are |exist )?(?:there )?(?:defined )?" + IN_FILE,
    r"(?:what|which) (?:functions|methods) (?:does|do) (?:the )?(?:file )?" + FILE + r" (?:have|contain|define)\W*$",
    r"what are (?:all )?the (?:functions|methods) (?:defined )?" + IN_FILE,
    r"(?:list|show)(?: me)? (?:all )?(?:the )?(?:functions|methods) " + IN_FILE,
    r"какие " + RU_FUNCTION + " (?:есть |определены |имеются )?" + RU_IN_FILE,
    r"какие " + RU_FUNCTION + " (?:содержит|имеет|определяет) (?:файл )?" + FILE + r"\W*$",
    r"(?:покажи|выведи|перечисли|список|перечень)\w* (?:все |всех )?" + RU_FUNCTION + " " + RU_IN_FILE,
]


class RouterService:
    def route_question(self, question):
        """Recognise a symbol question: ("has_function", name), ("file_functions", filename) or None.

        None means any other Question, which goes to the model.
        """
        question = question.strip()
        for kind, patterns in [("has_function", HAS_FUNCTION_PATTERNS), ("file_functions", FILE_FUNCTIONS_PATTERNS)]:
            for pattern in patterns:
                match = re.search(pattern, question, re.IGNORECASE)
                if match:
                    return kind, match.group(1)
        return None


router_service = RouterService()
