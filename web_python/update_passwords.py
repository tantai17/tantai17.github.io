import sqlite3
from werkzeug.security import generate_password_hash

# Kết nối tới cơ sở dữ liệu
con = sqlite3.connect('database.db')
cur = con.cursor()

# Lấy tất cả người dùng
cur.execute("SELECT id, username, password FROM users")
users = cur.fetchall()

# Mã hóa mật khẩu và cập nhật lại cơ sở dữ liệu
for user in users:
    user_id = user[0]
    plain_password = user[2]
    hashed_password = generate_password_hash(plain_password)
    cur.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_password, user_id))

# Lưu thay đổi và đóng kết nối cơ sở dữ liệu
con.commit()
con.close()

print("Passwords have been hashed and updated.")
