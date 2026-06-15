from textutils.slug import slugify


def test_slugify_collapses_repeated_spaces():
    assert slugify("Hello   World") == "hello-world"


def test_slugify_preserves_punctuation_separated_words():
    assert slugify("Hello, World!") == "hello-world"
