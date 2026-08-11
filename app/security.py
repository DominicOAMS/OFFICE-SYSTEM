import re
import secrets
import string

PASSWORD_REGEX = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{6,}$")

DEFAULT_PASSWORD = "password"

PASSWORD_REQUIREMENTS = (
    "Password must be at least 6 characters long and include at least one letter, "
    "one number, and one special character."
)


def is_valid_password(password):
    return bool(PASSWORD_REGEX.match(password or ""))


def generate_temp_password():
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*?"),
    ]
    rest = [secrets.choice(string.ascii_letters + string.digits) for _ in range(4)]
    chars = required + rest
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)
