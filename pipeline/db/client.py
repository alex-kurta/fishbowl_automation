import pymysql

from pipeline.config import DB_CONFIG


def connect():
    return pymysql.connect(**DB_CONFIG)


def run_query(sql, params=None):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            columns = [d[0] for d in cursor.description]
            return rows, columns
    finally:
        conn.close()