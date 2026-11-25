import pytest
from seeddb import SeedDB

def db():
    return SeedDB(":memory:")

def test_add_and_duplicate_case_and_space_insensitive():
    d = db()
    d.add("Ab12 Cd", "great", "Two keys near spawn", 1, "a")
    assert d.get("ab12cd").tier == "great"
    with pytest.raises(KeyError):
        d.add(" AB12 CD ", "good", "again", 2, "b")

def test_instant_requires_location_details():
    d = db()
    with pytest.raises(ValueError):
        d.add("x1", "instant", "exit is right there", 1, "a", map="Town", building="Church")
    s = d.add("x1", "instant", "exit is right there", 1, "a",
              map="Town", building="Church", location="Basement, behind altar")
    assert (s.map, s.building, s.location) == ("Town", "Church", "Basement, behind altar")

def test_reason_required_and_bad_tier():
    d = db()
    with pytest.raises(ValueError): d.add("s", "good", "  ", 1, "a")
    with pytest.raises(ValueError): d.add("s", "legendary", "r", 1, "a")

def test_remove_counts_export_message():
    d = db()
    s = d.add("s1", "perfect", "all loot", 1, "a")
    d.set_message(s.id, 99, "https://discord.com/channels/1/2/99")
    assert d.get("s1").message_url.endswith("/99")
    d.add("s2", "mediocre", "meh", 1, "a")
    assert d.counts()["perfect"] == 1 and d.counts()["mediocre"] == 1
    assert "s1,Perfect,all loot" in d.export_csv()
    assert d.remove("S1").seed == "s1" and d.get("s1") is None
    assert len(d.list()) == 1 and len(d.list(tier="mediocre")) == 1
