from app.scanner.naming import (
    clean_title,
    extract_order,
    slugify,
    sort_key,
    subtitle_base,
)


def test_extract_order_variants():
    assert extract_order("001 Course Intro")[0] == 1
    assert extract_order("12. Roof Details")[0] == 12
    assert extract_order("02 - Setup")[0] == 2
    assert extract_order("Lesson 49 - Fog")[0] == 49
    assert extract_order("3D Modeling")[0] is None  # don't eat a real leading digit


def test_clean_title():
    assert clean_title("001 Course Intro.mp4") == "Course Intro"
    assert clean_title("12. Roof Details and Gold.mp4") == "Roof Details and Gold"
    assert clean_title("02_getting_started.mp4") == "getting started"
    assert (
        clean_title("02_Lets get started - Stylized Station's Crafting Hall.ts")
        == "Lets get started"
    )


def test_sort_key_natural_order():
    names = ["10 - Y.mp4", "2 - X.mp4", "1 - A.mp4", "Bonus.mp4"]
    assert sorted(names, key=sort_key) == [
        "1 - A.mp4",
        "2 - X.mp4",
        "10 - Y.mp4",
        "Bonus.mp4",
    ]


def test_subtitle_base_strips_lang():
    assert subtitle_base("001 Course Intro_en") == "001 Course Intro"
    assert subtitle_base("Intro.es") == "Intro"
    assert subtitle_base("Intro") == "Intro"


def test_slugify():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("Unreal Engine 5") == "unreal-engine-5"
