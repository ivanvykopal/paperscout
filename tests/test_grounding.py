"""Offline tests for field-level reference grounding (no network)."""

import pytest

from paperscout.bibtex import BibtexVerifier, reference_from_entry, split_bibtex_authors
from paperscout.grounding import Grounder, Reference
from paperscout.markdown_refs import MarkdownRefParser
from paperscout.types import Paper


def paper(title, authors, year, venue, source="dblp", doi=None, identifier=None):
    return Paper(title=title, authors=authors, year=year, abstract="", source=source,
                 identifier=identifier or title[:10], url=f"https://example.org/{source}",
                 pdf_url=None, published=None, categories=[], venue=venue, doi=doi)


ATTENTION_AUTHORS = ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit",
                     "Llion Jones", "Aidan N. Gomez", "Lukasz Kaiser", "Illia Polosukhin"]
ATTENTION = paper("Attention is All you Need", ATTENTION_AUTHORS, 2017, "NIPS", doi=None)
ATTENTION_ARXIV = paper("Attention Is All You Need", ATTENTION_AUTHORS, 2017, "arXiv", source="arxiv",
                        identifier="1706.03762")
GPT3 = paper("Language Models are Few-Shot Learners", ["Tom B. Brown", "Benjamin Mann", "Nick Ryder"],
             2020, "NeurIPS")
BERT = paper("BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
             ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee", "Kristina Toutanova"], 2019,
             "Proceedings of NAACL-HLT", source="doi", doi="10.18653/v1/n19-1423")


class FakeBackend:
    def __init__(self, papers=(), error=None, lookups=None):
        self.papers, self.error, self.lookups = list(papers), error, lookups or {}

    def search(self, query, limit=5):
        if self.error:
            raise self.error
        return [Paper.from_dict(p.to_dict()) for p in self.papers]

    def lookup(self, identifier):
        if self.error:
            raise self.error
        return self.lookups.get(identifier)


class FakeSearcher:
    def __init__(self, **backends):
        self.backends = backends
        self.BACKENDS = dict.fromkeys(backends)

    def _get_backend(self, source):
        return self.backends[source]


def ground(ref, **backends):
    return Grounder(sources=[s for s in backends if s != "crossref" or backends[s].papers is not None],
                    searcher=FakeSearcher(**backends), use_cache=False).ground(ref)


def default_backends(**overrides):
    backends = {
        "dblp": FakeBackend([ATTENTION, GPT3]),
        "arxiv": FakeBackend([ATTENTION_ARXIV]),
        "crossref": FakeBackend([], lookups={"10.18653/v1/n19-1423": BERT}),
    }
    backends.update(overrides)
    return backends


def statuses(result):
    return {c.field: c.status for c in result.checks}


def test_correct_reference_is_verified():
    ref = Reference("Attention Is All You Need", ["Vaswani, Ashish"] + ATTENTION_AUTHORS[1:], year=2017,
                    venue="Advances in Neural Information Processing Systems 30")
    result = ground(ref, **default_backends())
    assert result.verdict == "verified", result.issues
    assert {p.source for p in result.versions} == {"dblp", "arxiv"}


def test_invented_author_is_mismatch():
    ref = Reference("Attention Is All You Need", ["Smith, John", "Vaswani, Ashish"], authors_truncated=True,
                    year=2017)
    result = ground(ref, **default_backends())
    assert result.verdict == "mismatch"
    assert statuses(result)["authors"] == "mismatch"
    assert any("Smith, John" in i for i in result.issues)


def test_omitted_authors_without_et_al_is_mismatch_but_et_al_is_fine():
    two = ["Ashish Vaswani", "Noam Shazeer"]
    assert ground(Reference("Attention Is All You Need", two, year=2017), **default_backends()).verdict == "mismatch"
    assert ground(Reference("Attention Is All You Need", two, authors_truncated=True, year=2017),
                  **default_backends()).verdict == "verified"


def test_altered_title_with_real_authors_is_mismatch_not_verified():
    ref = Reference("Language Models are Zero-Shot Learners", ["Brown, Tom B.", "Mann, Benjamin"],
                    authors_truncated=True, year=2020, venue="NeurIPS")
    result = ground(ref, **default_backends())
    assert result.verdict == "mismatch"
    assert statuses(result)["title"] == "mismatch"
    assert "zero" in result.checks[0].note


def test_wrong_venue_and_year():
    ref = Reference("Attention Is All You Need", ATTENTION_AUTHORS, year=2022, venue="ICML")
    result = ground(ref, **default_backends())
    assert statuses(result)["venue"] == "mismatch"
    assert statuses(result)["year"] == "mismatch"
    assert result.verdict == "mismatch"


def test_off_by_one_year_needs_review_only():
    ref = Reference("Attention Is All You Need", ATTENTION_AUTHORS, year=2018, venue="NeurIPS")
    result = ground(ref, **default_backends())
    assert statuses(result)["year"] == "minor"
    assert result.verdict == "review"


def test_venue_only_confirmable_from_preprint_needs_review():
    ref = Reference("Attention Is All You Need", ATTENTION_AUTHORS, year=2017, venue="ICML")
    result = ground(ref, **default_backends(dblp=FakeBackend([])))
    assert statuses(result)["venue"] == "unconfirmed"
    assert result.verdict == "review"


def test_findings_is_not_main_conference():
    record = paper("Some Findings Paper", ["Ann Lee"], 2023, "findings-emnlp", source="acl_anthology")
    ref = Reference("Some Findings Paper", ["Lee, Ann"], year=2023,
                    venue="Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing")
    result = ground(ref, dblp=FakeBackend([record]))
    assert statuses(result)["venue"] == "mismatch"


def test_altered_title_found_through_author_query():
    class AuthorOnlyBackend(FakeBackend):
        def search(self, query, limit=5):
            return [Paper.from_dict(GPT3.to_dict())] if query.startswith("brown") else []

    ref = Reference("Language Models are Zero-Shot Learners", ["Brown, Tom B.", "Mann, Benjamin"],
                    authors_truncated=True, year=2020)
    result = ground(ref, dblp=AuthorOnlyBackend(), crossref=FakeBackend([]))
    assert result.verdict == "mismatch"
    assert result.matched.title == GPT3.title


def test_unknown_title_is_not_found_with_closest_candidate():
    ref = Reference("Hierarchical Contrastive Retrieval Alignment for Fact-Checking", ["Kowalski, Peter"], year=2023)
    result = ground(ref, **default_backends())
    assert result.verdict == "not_found"
    assert result.matched is None


def test_source_failure_is_unverifiable_not_not_found():
    ref = Reference("Hierarchical Contrastive Retrieval Alignment for Fact-Checking", ["Kowalski, Peter"], year=2023)
    result = ground(ref, **default_backends(arxiv=FakeBackend(error=ConnectionError("timeout"))))
    assert result.verdict == "unverifiable"
    assert "arxiv" in result.source_errors


def test_source_failure_does_not_hide_match_elsewhere():
    ref = Reference("Attention Is All You Need", ATTENTION_AUTHORS, year=2017, venue="NeurIPS")
    result = ground(ref, **default_backends(arxiv=FakeBackend(error=ConnectionError("timeout"))))
    assert result.verdict == "verified"


def test_doi_pointing_to_other_paper_is_mismatch():
    ref = Reference("Attention Is All You Need", ATTENTION_AUTHORS, year=2017, venue="NeurIPS",
                    doi="10.18653/v1/n19-1423")
    result = ground(ref, **default_backends())
    assert statuses(result)["doi"] == "mismatch"
    assert result.verdict == "mismatch"


def test_nonexistent_doi_is_mismatch():
    ref = Reference("Attention Is All You Need", ATTENTION_AUTHORS, year=2017, venue="NeurIPS",
                    doi="10.9999/does-not-exist")
    result = ground(ref, **default_backends())
    assert statuses(result)["doi"] == "mismatch"


def test_valid_doi_grounds_reference_even_without_search_hits():
    ref = Reference("BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
                    ["Devlin, Jacob", "Chang, Ming-Wei", "Lee, Kenton", "Toutanova, Kristina"], year=2019,
                    venue="NAACL", doi="10.18653/v1/N19-1423")
    result = ground(ref, **default_backends())
    assert result.verdict == "verified", result.issues
    assert result.doi == "10.18653/v1/n19-1423"


def test_name_variants_and_diacritics_match():
    record = paper("A Study", ["Jörg Müller", "Anna van der Berg", "Wei Wang 0001", "Quoc V. Le"], 2020, "ACL")
    entry = {"ID": "k", "TITLE": "A Study", "YEAR": "2020", "BOOKTITLE": "ACL",
             "AUTHOR": r"M{\"u}ller, J{\"o}rg and van der Berg, Anna and Wang, Wei and Le, Quoc V."}
    result = ground(reference_from_entry(entry), dblp=FakeBackend([record]))
    assert result.verdict == "verified", result.issues


def test_reordered_authors_needs_review():
    ref = Reference("Attention Is All You Need",
                    ["Ashish Vaswani", "Niki Parmar", "Noam Shazeer"] + ATTENTION_AUTHORS[3:], year=2017)
    result = ground(ref, **default_backends())
    assert result.verdict == "review"


def test_bibtex_field_extraction():
    authors, truncated = split_bibtex_authors("Brown, Tom and {Barnes and Noble} and others")
    assert authors == ["Brown, Tom", "Barnes and Noble"] and truncated

    ref = reference_from_entry({
        "ID": "x", "TITLE": "{BERT}: Pre-training", "AUTHOR": "Devlin, Jacob", "YEAR": "2019",
        "JOURNAL": "arXiv preprint arXiv:1810.04805", "URL": "https://doi.org/10.18653/v1/N19-1423",
    })
    assert ref.title == "BERT: Pre-training"
    assert ref.arxiv_id == "1810.04805"
    assert ref.doi == "10.18653/v1/n19-1423"

    ref = reference_from_entry({"ID": "y", "TITLE": "T", "EPRINT": "1910.10683", "ARCHIVEPREFIX": "arXiv",
                                "DOI": "10.48550/arXiv.1910.10683"})
    assert ref.arxiv_id == "1910.10683" and ref.doi == ""


def test_markdown_reference_extracts_venue_and_truncation():
    parsed = MarkdownRefParser()._parse_single_reference(
        "Tom Brown, Benjamin Mann, and 29 others. 2020. Language models are few-shot learners. "
        "In Advances in Neural Information Processing Systems, pages 1877–1901."
    )
    assert parsed["title"] == "Language models are few-shot learners"
    assert parsed["venue"] == "Advances in Neural Information Processing Systems"
    assert parsed["authors_truncated"] is True
    assert parsed["authors"] == ["Tom Brown", "Benjamin Mann"]


def test_annotated_bib_enriches_only_trusted_entries(tmp_path):
    bib = tmp_path / "in.bib"
    bib.write_text(
        "@inproceedings{good-key:1,\n  title = {Attention Is All You Need},\n"
        "  author = {Vaswani, Ashish and others},\n  year = {2017}\n}\n\n"
        "@inproceedings{bad,\n  title = {Attention Is All You Need},\n"
        "  author = {Smith, John},\n  year = {2017}\n}\n",
        encoding="utf-8",
    )
    record = paper("Attention Is All You Need", ATTENTION_AUTHORS, 2017, "NeurIPS", doi="10.5555/3295222")
    grounder = Grounder(sources=["dblp"], searcher=FakeSearcher(dblp=FakeBackend([record])), use_cache=False)
    verifier = BibtexVerifier(grounder=grounder)
    results = verifier.verify_file(str(bib))
    assert [r.verdict for r in results] == ["verified", "mismatch"]

    out = tmp_path / "out.bib"
    verifier.write_annotated_bibtex(str(bib), str(out), results, enrich=True)
    text = out.read_text(encoding="utf-8")
    assert "% paperscout: verified" in text and "% paperscout: mismatch" in text
    assert text.count("doi = {10.5555/3295222}") == 1
    assert text.index("doi = {10.5555/3295222}") < text.index("@inproceedings{bad")


@pytest.mark.parametrize("title", ["", "{}"])
def test_missing_title_is_unverifiable(title):
    result = ground(Reference(title), **default_backends())
    assert result.verdict == "unverifiable"
