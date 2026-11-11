import os
from pathlib import Path

from dotenv import load_dotenv
import pymysql

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def main() -> int:
    conn = pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3305")),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "fishbowl_demo"),
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    CHAR_LENGTH(userPwd),
                    userPwd = MD5('test'),
                    userPwd = SHA1('test'),
                    userPwd = 'test'
                FROM sysuser
                WHERE username = 'api_user'
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        print("user_not_found")
        return 1

    print(f"pwd_len={row[0]}")
    print(f"equals_md5_test={bool(row[1])}")
    print(f"equals_sha1_test={bool(row[2])}")
    print(f"equals_plain_test={bool(row[3])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
