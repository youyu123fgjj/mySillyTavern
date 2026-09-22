from contextlib import asynccontextmanager, contextmanager
from queue import Queue
from sqlite3 import connect
from functools import wraps
import asyncio

from src.back.config import sqlite_path, sqlite_max_connections


class SQLiteConnectionPool:
    def __init__(self):
        self._pool = Queue(maxsize=sqlite_max_connections)
        for _ in range(sqlite_max_connections):
            # isolation_level=None 关闭驱动的隐式事务，事务边界一律由 transaction 显式控制
            self._pool.put(connect(sqlite_path, check_same_thread=False, isolation_level=None))

    @asynccontextmanager
    async def connection(self):
        """
        从连接池获取连接，自动管理其回收
        :return: 连接对象
        """
        conn = self._pool.get()
        try:
            yield conn
        finally:
            if conn.in_transaction:
                # 事务没有正常结束，回滚，避免脏事务被下一个取到该连接的请求复用
                conn.rollback()
            self._pool.put(conn)

    def close_all(self):
        while not self._pool.empty():
            self._pool.get().close()


pool = SQLiteConnectionPool()


@contextmanager
def transaction(conn):
    """显式事务。BEGIN IMMEDIATE 立即获取写锁，保证「先校验后写入」的过程中不会被其他连接插入写操作"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def auto_connection(func):
    """异步版本的数据库连接装饰器"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        async with pool.connection() as conn:
            # 如果原函数是异步的
            if asyncio.iscoroutinefunction(func):
                return await func(*args, conn=conn, **kwargs)
            # 如果是同步函数
            else:
                return func(*args, conn=conn, **kwargs)

    return wrapper


async def get_connection():
    """FastAPI依赖注入用的获取连接函数"""
    async with pool.connection() as conn:
        yield conn

