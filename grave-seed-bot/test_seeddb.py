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

def test_images_saved_and_exported():
    d = db()
    s = d.add("img1", "amazing", "three chests", 1, "a")
    d.set_message(s.id, 5, "https://discord.com/channels/1/2/5",
                  ["https://cdn.example/a.png", "https://cdn.example/b.png"])
    assert d.get("img1").images.split("\n") == ["https://cdn.example/a.png", "https://cdn.example/b.png"]
    assert "https://cdn.example/a.png https://cdn.example/b.png" in d.export_csv()

def test_old_database_gets_images_column(tmp_path):
    import sqlite3
    p = tmp_path / "old.db"
    c = sqlite3.connect(p)
    c.execute("""CREATE TABLE seeds (id INTEGER PRIMARY KEY AUTOINCREMENT, seed TEXT NOT NULL,
        seed_key TEXT NOT NULL UNIQUE, tier TEXT NOT NULL, reason TEXT NOT NULL, map TEXT,
        building TEXT, location TEXT, submitter_id INTEGER NOT NULL, submitter_name TEXT NOT NULL,
        created_at INTEGER NOT NULL, message_id INTEGER, message_url TEXT)""")
    c.execute("INSERT INTO seeds VALUES (1,'old','old','good','r',NULL,NULL,NULL,1,'a',0,NULL,NULL)")
    c.commit(); c.close()
    d = SeedDB(str(p))
    assert d.get("old").images is None
