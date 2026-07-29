from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from .config import DB_CONFIG


class Database:
    """数据库连接管理器"""

    def __init__(self):
        self._connection = None

    def get_connection(self):
        if self._connection is None or not self._connection.open:
            self._connection = pymysql.connect(**DB_CONFIG)
        return self._connection

    def close(self):
        if self._connection and self._connection.open:
            self._connection.close()
            self._connection = None

    def current_connection_id(self) -> int | None:
        conn = self._connection
        if conn is None or not conn.open:
            return None
        return conn.thread_id()

    def kill_current_connection(self):
        connection_id = self.current_connection_id()
        if connection_id is None:
            self._connection = None
            return
        admin_conn = None
        try:
            admin_conn = pymysql.connect(**DB_CONFIG)
            with admin_conn.cursor() as cursor:
                cursor.execute(f"KILL CONNECTION {connection_id}")
            admin_conn.commit()
        except Exception:
            # If KILL fails we still fall back to closing the local connection.
            pass
        finally:
            if admin_conn and admin_conn.open:
                admin_conn.close()
            if self._connection:
                try:
                    self._connection.close()
                except Exception:
                    pass
            self._connection = None

    @contextmanager
    def cursor(self, dict_cursor=True):
        """获取游标的上下文管理器"""
        conn = self.get_connection()
        cursor = conn.cursor(DictCursor if dict_cursor else None)
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()

    def execute(self, sql, params=None):
        """执行 SQL"""
        with self.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.rowcount

    def executemany(self, sql, params_list):
        """批量执行 SQL"""
        with self.cursor() as cursor:
            cursor.executemany(sql, params_list)
            return cursor.rowcount

    def fetch_one(self, sql, params=None):
        """查询单条"""
        with self.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def fetch_all(self, sql, params=None):
        """查询所有"""
        with self.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()


# 全局数据库实例
db = Database()


def init_db():
    """初始化数据库连接"""
    db.get_connection()
    print(
        f"Database connected: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    )


def close_db():
    """关闭数据库连接"""
    db.close()
    print("Database connection closed")


def interrupt_db():
    """中断并关闭数据库连接。"""
    db.kill_current_connection()
    print("Database connection interrupted and closed")
