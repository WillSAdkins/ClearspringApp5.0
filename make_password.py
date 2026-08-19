"""Generate a strong admin password.

Run:  python make_password.py
"""
import secrets

# Word-based passwords are far easier to type on a phone than random
# characters, and a four-word phrase from this list is very hard to guess.
WORDS = """anchor beacon canyon cedar clover compass copper cotton crimson
dawn delta ember falcon forest garnet gentle granite harbour harvest hazel
iron ivory jasper juniper kettle lantern laurel linen meadow mineral north
oakwood orchard pebble pilgrim quarry quiet rowan saffron sandstone shelter
silver spruce stanza summit thistle timber vessel violet walnut willow winter"""\
    .split()


def make(words=4):
    return "-".join(secrets.choice(WORDS) for _ in range(words))


if __name__ == "__main__":
    pw = make()
    print("\nYour new admin password:\n")
    print(f"    {pw}\n")
    print("Add it to run.bat (local):")
    print(f"    set ADMIN_PASSWORD={pw}\n")
    print("And set it on your host as an environment variable.")
    print("Write it down somewhere safe — it isn't stored anywhere.\n")
