import os
from pathlib import Path

from dotenv import load_dotenv
import pymysql

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def connect_db():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3305")),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "fishbowl_demo"),
        charset="utf8mb4",
    )


def main() -> int:
    username = os.getenv("FISHBOWL_USERNAME", "")
    password = os.getenv("FISHBOWL_PASSWORD", "")

    print(f"username_present={bool(username)}")
    print(f"password_present={bool(password)}")
    print(f"username_length={len(username)}")
    print(f"password_length={len(password)}")
    print(f"username_has_outer_single_quotes={username.startswith("'") and username.endswith("'")}")
    print(f"username_has_outer_double_quotes={username.startswith('"') and username.endswith('"')}")
    print(f"password_has_outer_single_quotes={password.startswith("'") and password.endswith("'")}")
    print(f"password_has_outer_double_quotes={password.startswith('"') and password.endswith('"')}")
    print(f"username_has_leading_or_trailing_whitespace={username != username.strip()}")
    print(f"password_has_leading_or_trailing_whitespace={password != password.strip()}")

    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM sysuser")
            sysuser_columns = {row[0] for row in cur.fetchall()}
            active_column = "activeFlag" if "activeFlag" in sysuser_columns else None
            cur.execute(
                f"SELECT username{', activeFlag' if active_column else ''} FROM sysuser WHERE username = %s",
                (username.strip(),),
            )
            exact = cur.fetchone()
            print(f"exact_username_match_in_sysuser={bool(exact)}")
            if exact:
                if active_column:
                    print(f"matched_user_active={bool(exact[1])}")
            else:
                cur.execute(
                    "SELECT username FROM sysuser WHERE LOWER(username) = LOWER(%s)",
                    (username.strip(),),
                )
                ci = cur.fetchall()
                print(f"case_insensitive_username_match_count={len(ci)}")
                cur.execute("SELECT COUNT(*) FROM sysuser")
                count = cur.fetchone()[0]
                print(f"sysuser_count={count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
