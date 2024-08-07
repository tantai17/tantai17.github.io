import sqlite3

# Kết nối tới cơ sở dữ liệu
con = sqlite3.connect('database.db')
cur = con.cursor()

# Truy vấn tất cả người dùng
cur.execute("SELECT * FROM users")
users = cur.fetchall()

# Đóng kết nối cơ sở dữ liệu
con.close()

# In dữ liệu người dùng
for user in users:
    print(user)
