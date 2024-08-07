import sqlite3

def delete_all_tables(db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Lấy danh sách tất cả các bảng trong cơ sở dữ liệu
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    # Xóa từng bảng một, ngoại trừ bảng sqlite_sequence
    for table in tables:
        if table[0] != 'sqlite_sequence':
            cursor.execute(f"DROP TABLE IF EXISTS {table[0]}")
            print(f"Table {table[0]} deleted.")

    conn.commit()
    conn.close()

# Gọi hàm để xóa tất cả các bảng trong maintenance.db
delete_all_tables('database.db')

print("All tables except sqlite_sequence have been deleted successfully.")
