from src.wiki import get_blurb, get_commons_thumb

demo_species = [
    ("Balaenoptera", "musculus"),
    ("Carcharodon",  "carcharias"),
    ("Architeuthis", "dux"),
    ("Gadus",        "morhua"),
    ("Aptenodytes",  "forsteri"),
]

for g, s in demo_species:
    print(f"\n=== {g} {s} ===")

    summary, page = get_blurb(g, s)
    print("Blurb:", summary)
    print("Read more:", page)

    thumb, author, lic, lic_url, up_date, ret_date = get_commons_thumb(g, s)

    citation = (f"Image © {author}, {lic} "
            f"({lic_url}) — uploaded {up_date}, retrieved {ret_date}")
    if thumb:
        print("Thumbnail:", thumb)
        print(f"citation",citation)
    else:
        print("No image found 😢")

