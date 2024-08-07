import sqlite3
from werkzeug.security import generate_password_hash
def create_tables():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Tạo bảng devices nếu chưa tồn tại
    c.execute('''
    CREATE TABLE IF NOT EXISTS devices (
        device_code TEXT PRIMARY KEY ,
        device_name TEXT NOT NULL,
        device_image TEXT NOT NULL,
        start_date DATE NOT NULL,
        status TEXT NOT NULL,
        technical_spec TEXT NOT NULL,
        location TEXT NOT NULL
    )
    ''')

    # Tạo bảng maintenance nếu chưa tồn tại
    c.execute('''
    CREATE TABLE IF NOT EXISTS maintenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    maintenance_date TEXT NOT NULL,
    description TEXT NOT NULL,
    device_code TEXT NOT NULL,  
    assigned_user INTEGER NOT NULL,
    status TEXT NOT NULL,
    location TEXT NOT NULL,
    FOREIGN KEY (device_code) REFERENCES devices (device_code),
    FOREIGN KEY (assigned_user) REFERENCES users (id)
)

    ''')

    # Tạo bảng users nếu chưa tồn tại
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )
    ''')

        # Tạo bảng notifications nếu chưa tồn tại
    c.execute('''
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_username TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )
    ''')


     # Tạo bảng notification_recipients nếu chưa tồn tại
    c.execute('''
    CREATE TABLE IF NOT EXISTS notification_recipients (
        notification_id INTEGER NOT NULL,
        recipient_username TEXT NOT NULL,
        FOREIGN KEY (notification_id) REFERENCES notifications (id),
        FOREIGN KEY (recipient_username) REFERENCES users (username)
    )
    ''')

    # Tạo bảng device_update_requests nếu chưa tồn tại
    c.execute('''
    CREATE TABLE IF NOT EXISTS device_update_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_code TEXT NOT NULL,
        requested_by INTEGER NOT NULL,
        new_status TEXT NOT NULL,
        request_status TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (device_code) REFERENCES devices (device_code),
        FOREIGN KEY (requested_by) REFERENCES users (id)
    )
    ''')
    conn.commit()
    conn.close()

def add_initial_data():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Mã hóa mật khẩu trước khi thêm vào cơ sở dữ liệu
    c.execute('''
    INSERT OR IGNORE INTO users (username, password, role) VALUES
    ('admin', ? , 'admin'),
    ('user1', ? , 'user'),
    ('user2', ? , 'user')
    ''', (
        generate_password_hash('password'),
        generate_password_hash('password1'),
        generate_password_hash('password2')
    ))



     # Thêm dữ liệu mẫu vào bảng devices
    c.execute('''
    INSERT OR IGNORE INTO devices (device_code, device_name, device_image, start_date, status, technical_spec, location) VALUES
    ('MH001', 'Màn hình', 'mh001.jpeg', '2023-01-01', 'Hoạt động', 'Dell, E2722HS, 27Inch, Full HD, 60HZ', 'B202'),
    ('MH002', 'Màn hình', 'mh002.jpeg', '2023-01-02', 'Hoạt động', 'Hp, E2722HS, 27Inch, Full HD, 60HZ', 'B204'),
    ('MC001', 'Máy chiếu', 'mc001.jpg', '2023-01-02', 'Hoạt động', 'Viewsonic, Xuất xứ: Trung quốc', 'B202'),
    ('MC002', 'Máy chiếu', 'mc002.webp', '2023-01-02', 'Đang sửa chữa', 'VimGo, Xuất xứ: Trung quốc', 'B204')         
    ''')

    # Thêm dữ liệu mẫu vào bảng maintenance
    c.execute('''
    INSERT OR IGNORE INTO maintenance (maintenance_date, description, device_code, assigned_user, status, location) VALUES
    ('2024-07-20', 'Lịch bảo trì Màn hình 001', 'MD001', 1, 'Hoạt động', 'B202'),
    ('2024-07-21', 'Lịch bảo trì Máy chiếu 001', 'MC001', 1, 'Hoạt động', 'B202'),
    ('2024-07-20', 'Lịch bảo trì Màn hình 002', 'MD002', 2, 'Hoạt động', 'B204'),
    ('2024-07-21', 'Lịch bảo trì Máy chiếu 002', 'MC002', 2, 'Đang sửa chữa', 'B204')
    ''')
    

    # Tạo bảng parts nếu chưa tồn tại
# Tạo bảng parts nếu chưa tồn tại
    c.execute('''
    CREATE TABLE IF NOT EXISTS parts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        part_code TEXT NOT NULL UNIQUE,
        part_name TEXT NOT NULL,
        part_description TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        image BLOB,
        location TEXT
    )
    ''')

    c.execute('''CREATE TABLE IF NOT EXISTS budgets
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  amount REAL NOT NULL,
                  spent REAL NOT NULL DEFAULT 0,
                  remaining REAL NOT NULL DEFAULT 0)''')

    # Other table creation commands...
    
    conn.commit()
    conn.close()

def check_database():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Kiểm tra dữ liệu trong bảng users
    c.execute('SELECT * FROM users')
    users = c.fetchall()
    print("Users in database:", users)

    conn.close()

# Mã hóa mật khẩu mới
hashed_password = generate_password_hash('password')



if __name__ == '__main__':
    create_tables()
    add_initial_data()
    check_database()
    print("Database created and initial data added.")
