#!/usr/bin/env python3
"""نسخ/استعادة قاعدة SQLite عبر وحدة sqlite3.backup (لقطة متسقة).

الاستعمال:
    python3 scripts/sqlite_backup.py backup <المصدر> <الوجهة>
    python3 scripts/sqlite_backup.py restore <المصدر> <الوجهة>
"""

import sys

import sqlite3


def main():
    action, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    src_con = sqlite3.connect(src)
    try:
        if action == "backup":
            dst_con = sqlite3.connect(dst)
            try:
                src_con.backup(dst_con)
            finally:
                dst_con.close()
        elif action == "restore":
            dst_con = sqlite3.connect(dst)
            try:
                src_con.backup(dst_con)
            finally:
                dst_con.close()
        else:
            sys.exit(f"إجراء غير معروف: {action}")
    finally:
        src_con.close()


if __name__ == "__main__":
    main()
