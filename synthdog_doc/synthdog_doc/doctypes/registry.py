"""doc_type -> page builder."""
import importlib

MODULES = {"paper_single": "paper", "paper_double": "paper", "newspaper": "newspaper", "ppt": "ppt", "exam": "exam",
           "book": "book", "magazine": "magazine", "textbook": "textbook", "report": "report"}


def make(doc_type, lang, rng, version=0):
    mod = importlib.import_module(f"synthdog_doc.doctypes.{MODULES[doc_type]}")
    if MODULES[doc_type] == "paper":
        return mod.make(rng, lang, doc_type == "paper_double", version)
    return mod.make(rng, lang, version)
