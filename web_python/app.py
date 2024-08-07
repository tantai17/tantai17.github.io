import io
from turtle import color
from flask import Flask, abort, jsonify, render_template, redirect, send_file, url_for, request, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import os
import sqlite3
import logging
from flask import g
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib import colors


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/images'
app.config['DEBUG'] = True

# Mã hóa mật khẩu mới
hashed_password = generate_password_hash('password')

# So sánh mật khẩu đã mã hóa
is_correct = check_password_hash(hashed_password, 'password')
print(f'Password is correct: {is_correct}')

# Hàm kiểm tra phần mở rộng của file ảnh
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('You need to log in first.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(required_role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'logged_in' not in session:
                flash('You need to log in first.')
                return redirect(url_for('login'))
            if session.get('role') != required_role:
                flash('You do not have the required permissions to access this page.')
                return redirect(url_for('login'))  # Bạn có thể redirect đến một trang khác nếu muốn
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.route('/admin/home')
def admin_home():
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    # Kết nối tới database
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Thống kê thiết bị
    c.execute('SELECT COUNT(*) FROM devices')
    total_devices = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM devices WHERE status = 'Hoạt động'")
    active_devices = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM devices WHERE status = 'Không hoạt động'")
    inactive_devices = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM maintenance WHERE status = 'Đang sửa chữa'")
    maintenance_devices = c.fetchone()[0]

    # Thống kê người dùng
    c.execute("SELECT COUNT(*) FROM users WHERE role != 'admin'")
    total_users = c.fetchone()[0]

    # Thống kê bảo trì
    today = datetime.today().strftime('%Y-%m-%d')
    c.execute(f"SELECT COUNT(*) FROM maintenance WHERE maintenance_date < '{today}'")
    past_maintenance = c.fetchone()[0]

    c.execute(f"SELECT COUNT(*) FROM maintenance WHERE maintenance_date = '{today}'")
    today_maintenance = c.fetchone()[0]

    c.execute(f"SELECT COUNT(*) FROM maintenance WHERE maintenance_date > '{today}'")
    upcoming_maintenance = c.fetchone()[0]

    # Yêu cầu cập nhật thiết bị
    c.execute("SELECT COUNT(*) FROM maintenance WHERE status = 'pending'")
    device_update_requests = c.fetchone()[0]

    # Thống kê thông báo
    c.execute("SELECT COUNT(*) FROM notifications")
    total_notifications = c.fetchone()[0]

    conn.close()

    return render_template('admin/home.html', 
                           total_devices=total_devices,
                           active_devices=active_devices,
                           inactive_devices=inactive_devices,
                           maintenance_devices=maintenance_devices,
                           total_users=total_users,
                           past_maintenance=past_maintenance,
                           today_maintenance=today_maintenance,
                           upcoming_maintenance=upcoming_maintenance,
                           device_update_requests=device_update_requests,
                           total_notifications=total_notifications)

import logging

# Kiểm tra Đăng nhập
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        con = sqlite3.connect('database.db')
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        con.close()
        
        if user and check_password_hash(user[2], password):
            session['logged_in'] = True
            session['username'] = user[1]
            session['role'] = user[3]
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

# Trang chủ admin
@app.route('/admin_home')
@login_required
def admin_home_page():
    print('User role in admin_home:', session.get('role'))
    if session.get('role') == 'admin':
        return render_template('admin/home.html')
    else:
        return redirect(url_for('login'))


#Đăng nhập user
@app.route('/user_home')
@login_required
def user_home():
    # Kiểm tra nếu người dùng đã đăng nhập và có vai trò là 'user'
    if not session.get('logged_in') or session.get('role') != 'user':
        return redirect(url_for('login'))

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # Lấy tên người dùng từ session
    username = session.get('username')

    # Lấy các thông báo đã gửi cho người dùng hiện tại
    c.execute('''
        SELECT n.sender_username, n.content, n.timestamp
        FROM notifications n
        JOIN notification_recipients r ON n.id = r.notification_id
        WHERE r.recipient_username = ?
    ''', (username,))
    notifications = c.fetchall()

    # Lấy các lịch bảo trì của người dùng hiện tại
    c.execute('''
        SELECT m.id, m.maintenance_date, m.description, d.device_name, m.status, m.location
        FROM maintenance m
        JOIN devices d ON m.device_code = d.device_code
        WHERE m.assigned_user = (
            SELECT id FROM users WHERE username = ?
        )
    ''', (username,))
    maintenance_records = c.fetchall()

    conn.close()
    return render_template('user/home.html', notifications=notifications, maintenance_records=maintenance_records)

#Đăng xuất
@app.route('/logout')
def logout():
    print(session)
    session.pop('logged_in', None)
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('login'))

#Mặc định khi vào web
@app.route('/')
@login_required
def home():
    role = session.get('role')
    print(f"User role in home route: {role}")  # Debugging line
    if session.get('role') == 'admin':
        return redirect(url_for('admin_home'))
    elif session.get('role') == 'user':
        return redirect(url_for('user_home'))
    else:
        return redirect(url_for('login'))

#Add thiết bị của admin
@app.route('/add_device', methods=['GET', 'POST'])
@login_required
def add_device():
    if request.method == 'POST':
        device_code = request.form['device_code']
        device_name = request.form['device_name']
        start_date = request.form['start_date']
        status = request.form['status']
        technical_spec = request.form['technical_spec']
        location = request.form['location']
        
        device_image = None
        if 'device_image' in request.files:
            file = request.files['device_image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename) # type: ignore
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                device_image = f'images/{filename}'  # Sử dụng dấu / thay vì \\
        
        try:
            with sqlite3.connect('database.db') as conn:
                c = conn.cursor()
                c.execute('INSERT INTO devices (device_code, device_name, device_image, start_date, status, technical_spec, location) VALUES (?, ?, ?, ?, ?, ?, ?)',
                          (device_code, device_name, device_image, start_date, status, technical_spec, location))
                conn.commit()
                flash('Device added successfully')
                return redirect(url_for('add_device'))
        except sqlite3.Error as e:
            flash(f'Error: {e}')
            return redirect(url_for('add_device'))

    try:
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM devices')
            devices = c.fetchall()
            return render_template('admin/add_device.html', devices=devices)
    except sqlite3.Error as e:
        flash(f'Error: {e}')
        return redirect(url_for('add_device'))

#Delete thiết bị của admin
@app.route('/delete_device/<device_code>', methods=['POST'])
@login_required
def delete_device(device_code):
    try:
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('DELETE FROM devices WHERE device_code=?', (device_code,))
        conn.commit()
        conn.close()
        flash('Device deleted successfully')
    except sqlite3.Error as e:
        flash(f'Error: {e}')
    return redirect(url_for('add_device'))

#Edit thiết bị của admin
@app.route('/edit_device/<device_code>', methods=['GET', 'POST'])
@login_required
def edit_device(device_code):
    try:
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            if request.method == 'POST':
                # Lấy dữ liệu từ form
                device_name = request.form['device_name']
                start_date = request.form['start_date']
                status = request.form['status']
                technical_spec = request.form['technical_spec']
                location = request.form['location']

                # Nếu có file mới được tải lên
                if 'device_image' in request.files:
                    file = request.files['device_image']
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                        device_image = os.path.join('images', filename)
                    else:
                        device_image = None
                else:
                    device_image = None

                # Cập nhật cơ sở dữ liệu
                if device_image:
                    c.execute('''UPDATE devices SET device_name=?, device_image=?, start_date=?, status=?, technical_spec=?, location=? WHERE device_code=?''',
                              (device_name, device_image, start_date, status, technical_spec, location, device_code))
                else:
                    c.execute('''UPDATE devices SET device_name=?, start_date=?, status=?, technical_spec=?, location=? WHERE device_code=?''',
                              (device_name, start_date, status, technical_spec, location, device_code))
                conn.commit()

                flash('Device updated successfully')
                return redirect(url_for('add_device'))
            else:
                c.execute('SELECT * FROM devices WHERE device_code=?', (device_code,))
                device = c.fetchone()
                if device:
                    return render_template('admin/edit_device.html', device=device)
                else:
                    flash('Device not found')
                    return redirect(url_for('add_device'))
    except sqlite3.Error as e:
        flash(f'Error: {e}')
        return redirect(url_for('add_device'))

#Tìm kiếm thiết bị của admin
@app.route('/list_of_devices', methods=['GET'])
@login_required
def list_of_devices():
    search_query = request.args.get('search', '')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Truy vấn thiết bị với tìm kiếm
    c.execute('''
        SELECT device_code, device_name, device_image, start_date, status, technical_spec, location
        FROM devices
        WHERE device_name LIKE ? OR device_code LIKE ? OR technical_spec LIKE ? OR location LIKE ?
    ''', ('%' + search_query + '%', '%' + search_query + '%', '%' + search_query + '%', '%' + search_query + '%'))
    
    devices = c.fetchall()
    conn.close()
    
    return render_template('admin/add_device.html', devices=devices)

DATABASE = 'database.db'
def connect_db():
    return sqlite3.connect(DATABASE)

#L=Tạo lịch bảo trì của admin, tìm kiếm
@app.route('/schedule_maintenance', methods=['GET', 'POST'])
def schedule_maintenance():
    search_query = request.args.get('search', '')

    if request.method == 'POST':
        maintenance_date = request.form.get('maintenance_date')
        description = request.form.get('description')
        device_code = request.form.get('device_code')
        assigned_user = request.form.get('assigned_user')
        status = request.form.get('status')
        location = request.form.get('location')

        if not (maintenance_date and description and device_code and assigned_user and status and location):
            flash('Vui lòng điền đầy đủ thông tin vào tất cả các trường.', 'error')
        else:
            try:
                conn = sqlite3.connect('database.db')
                c = conn.cursor()

                # Thêm lịch bảo trì vào cơ sở dữ liệu
                c.execute('''
                    INSERT INTO maintenance (maintenance_date, description, device_code, assigned_user, status, location)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (maintenance_date, description, device_code, assigned_user, status, location))
                conn.commit()
                flash('Lịch bảo trì đã được thêm thành công', 'success')

            except sqlite3.Error as e:
                flash(f'Lỗi: {e}', 'error')

            finally:
                if conn:
                    conn.close()

    try:
        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        # Lấy danh sách thiết bị và người dùng
        c.execute('SELECT device_code, device_name FROM devices')
        devices = c.fetchall()

        c.execute('SELECT id, username FROM users WHERE role != "admin"')
        users = c.fetchall()

        # Lấy danh sách lịch bảo trì với chức năng tìm kiếm
        query = '''
            SELECT m.id, m.maintenance_date, m.description, d.device_name, u.username, m.status, m.location
            FROM maintenance m
            JOIN devices d ON m.device_code = d.device_code
            JOIN users u ON m.assigned_user = u.id
        '''

        if search_query:
            query += '''
                WHERE m.maintenance_date LIKE ? 
                OR m.description LIKE ? 
                OR d.device_name LIKE ? 
                OR u.username LIKE ? 
                OR m.status LIKE ? 
                OR m.location LIKE ?
            '''
            c.execute(query, 
                ('%' + search_query + '%',) * 6)
        else:
            c.execute(query)

        maintenance_records = c.fetchall()

    except sqlite3.Error as e:
        flash(f'Lỗi: {e}', 'error')
        devices = []
        users = []
        maintenance_records = []

    finally:
        if conn:
            conn.close()

    return render_template('admin/schedule_maintenance.html', devices=devices, users=users, maintenance_records=maintenance_records, search_query=search_query)






#Lấy thiết bị vào lịch bảo trì
@app.route('/get_device_info/<device_codes>')
@login_required
def get_device_info(device_codes):
    conn = None
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        # Chia chuỗi device_codes thành danh sách
        device_code_list = device_codes.split(',')

        # Lấy thông tin của tất cả thiết bị
        placeholders = ','.join('?' for _ in device_code_list)
        c.execute(f'SELECT device_code, status, location FROM devices WHERE device_code IN ({placeholders})', device_code_list)
        device_info_list = c.fetchall()

        # Trả về danh sách thông tin thiết bị dưới dạng JSON
        return jsonify([{'device_code': info[0], 'status': info[1], 'location': info[2]} for info in device_info_list])
    except sqlite3.Error as e:
        flash(f'Error: {e}', 'error')
        return jsonify([])
    finally:
        if conn:
            conn.close()


#Xóa lịch bảo trì
@app.route('/delete_maintenance/<int:maintenance_id>', methods=['POST'])
@login_required
def delete_maintenance(maintenance_id):
    try:
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute('DELETE FROM maintenance WHERE id = ?', (maintenance_id,))
            conn.commit()
            flash('Maintenance record deleted successfully', 'success')
    except sqlite3.Error as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('schedule_maintenance'))

#Sửa lịch bảo trì
@app.route('/edit_maintenance/<int:maintenance_id>', methods=['GET', 'POST'])
@login_required
def edit_maintenance(maintenance_id):
    conn = None
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        if request.method == 'POST':
            maintenance_date = request.form['maintenance_date']
            description = request.form['description']
            device_code = request.form['device_id']
            assigned_user = request.form['assigned_user']
            status = request.form['status']
            location = request.form['location']

            c.execute('''
                UPDATE maintenance
                SET maintenance_date = ?, description = ?, device_code = ?, assigned_user = ?, status = ?, location = ?
                WHERE id = ?
            ''', (maintenance_date, description, device_code, assigned_user, status, location, maintenance_id))
            conn.commit()
            flash('Maintenance record updated successfully', 'success')
            return redirect(url_for('schedule_maintenance'))

        c.execute('SELECT * FROM maintenance WHERE id = ?', (maintenance_id,))
        maintenance = c.fetchone()

        c.execute('SELECT device_code, device_name FROM devices')
        devices = c.fetchall()

        c.execute('SELECT id, username FROM users WHERE role != "admin"')
        users = c.fetchall()

    except sqlite3.Error as e:
        flash(f'Error: {e}', 'error')
        return redirect(url_for('schedule_maintenance'))
    finally:
        if conn:
            conn.close()

    return render_template('admin/edit_maintenance.html', maintenance=maintenance, devices=devices, users=users)

#Add user cho thông báo
def get_users():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT username FROM users WHERE role = "user"')
    users = c.fetchall()
    conn.close()
    return users

#Add thông báo củ admin
@app.route('/notifications', methods=['GET', 'POST'])
def notifications():
    if request.method == 'POST':
        selected_users = request.form.getlist('users')  # Lấy danh sách người dùng được chọn
        content = request.form['content']
        sender_username = session.get('username', 'admin')  # Lấy tên người gửi từ session, hoặc mặc định là 'admin'
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        # Chèn thông báo vào bảng notifications
        c.execute('INSERT INTO notifications (sender_username, content, timestamp) VALUES (?, ?, ?)',
                  (sender_username, content, timestamp))
        notification_id = c.lastrowid  # Lấy ID của thông báo vừa chèn

        # Chèn người nhận vào bảng notification_recipients
        for username in selected_users:
            c.execute('INSERT INTO notification_recipients (notification_id, recipient_username) VALUES (?, ?)',
                      (notification_id, username))
        
        conn.commit()
        conn.close()

        return redirect(url_for('notifications'))

    search_query = request.args.get('search', '')

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Lấy danh sách người dùng
    c.execute('SELECT username FROM users WHERE role != "admin"')
    users = c.fetchall()

    # Lấy danh sách thông báo với chức năng tìm kiếm
    query = '''
        SELECT n.id, n.sender_username, n.content, n.timestamp, GROUP_CONCAT(r.recipient_username) AS recipients
        FROM notifications n
        LEFT JOIN notification_recipients r ON n.id = r.notification_id
        GROUP BY n.id
    '''

    if search_query:
        query += '''
            HAVING n.sender_username LIKE ? 
            OR n.timestamp LIKE ?
            OR n.content LIKE ? 
            OR GROUP_CONCAT(r.recipient_username) LIKE ?
        '''
        c.execute(query, 
            ('%' + search_query + '%',) * 4)
    else:
        c.execute(query)

    notifications = c.fetchall()
    conn.close()
    
    return render_template('admin/notifications.html', users=users, notifications=notifications)

#Edit thông báo của admin
@app.route('/edit_notification/<int:id>', methods=['GET', 'POST'])
def edit_notification(id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    if request.method == 'POST':
        content = request.form['content']
        selected_users = request.form.getlist('users')  # Lấy danh sách người dùng được chọn
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Cập nhật nội dung thông báo
        c.execute('UPDATE notifications SET content = ?, timestamp = ? WHERE id = ?', (content, timestamp, id))
        
        # Xóa người nhận cũ
        c.execute('DELETE FROM notification_recipients WHERE notification_id = ?', (id,))
        
        # Thêm người nhận mới
        for username in selected_users:
            c.execute('INSERT INTO notification_recipients (notification_id, recipient_username) VALUES (?, ?)',
                      (id, username))

        conn.commit()
        conn.close()
        return redirect(url_for('notifications'))

    c.execute('SELECT * FROM notifications WHERE id = ?', (id,))
    notification = c.fetchone()

    # Lấy danh sách người dùng
    c.execute('SELECT username FROM users WHERE role = "user"')
    users = c.fetchall()

    # Lấy người nhận hiện tại
    c.execute('SELECT recipient_username FROM notification_recipients WHERE notification_id = ?', (id,))
    recipients = c.fetchall()
    recipients = [r[0] for r in recipients]

    conn.close()
    
    return render_template('admin/edit_notification.html', notification=notification, users=users, recipients=recipients)

#Delete thông báo của admin
@app.route('/delete_notification/<int:id>')
def delete_notification(id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('DELETE FROM notification_recipients WHERE notification_id = ?', (id,))
    c.execute('DELETE FROM notifications WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('notifications'))


def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/user/request_device_update', methods=['GET', 'POST'])
@login_required
def request_device_update():
    conn = get_db_connection()
    c = conn.cursor()

    if request.method == 'POST':
        device_code = request.form.get('device_code')

        if device_code:
            c.execute('SELECT * FROM devices WHERE device_code = ?', (device_code,))
            device = c.fetchone()
            c.execute('SELECT device_code, device_name FROM devices')
            devices = c.fetchall()
            conn.close()
            return render_template('user/request_device_update.html', device=device, devices=devices)
    
    # GET request or no device selected
    c.execute('SELECT device_code, device_name FROM devices')
    devices = c.fetchall()
    conn.close()
    
    return render_template('user/request_device_update.html', devices=devices)

@app.route('/user/submit_device_update_request', methods=['POST'])
@login_required
def submit_device_update_request():
    conn = get_db_connection()
    c = conn.cursor()

    device_code = request.form['device_code']
    new_status = request.form['new_status']
    username = session.get('username')

    # Insert the update request into the device_update_requests table
    c.execute('''
        INSERT INTO device_update_requests (device_code, new_status, requested_by, timestamp, request_status)
        VALUES (?, ?, (SELECT id FROM users WHERE username = ?), ?, 'pending')
    ''', (device_code, new_status, username, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    
    conn.commit()
    conn.close()
    
    flash('Device update request submitted successfully!', 'success')
    return redirect(url_for('user_home'))

@app.route('/admin/device_update_requests')
@login_required
def device_update_requests():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, device_code, new_status, requested_by, timestamp FROM device_update_requests WHERE request_status = "pending"')
    requests = c.fetchall()
    conn.close()

    return render_template('admin/device_update_requests.html', requests=requests)

@app.route('/approve_update_request/<int:request_id>', methods=['POST'])
@login_required
def approve_update_request(request_id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    c = conn.cursor()

    # Lấy thông tin yêu cầu cập nhật
    c.execute('SELECT device_code, new_status FROM device_update_requests WHERE id = ?', (request_id,))
    request_info = c.fetchone()

    if request_info:
        device_code, new_status = request_info

        # Cập nhật trạng thái của thiết bị
        c.execute('UPDATE devices SET status = ? WHERE device_code = ?', (new_status, device_code))

        # Cập nhật trạng thái của yêu cầu
        c.execute('UPDATE device_update_requests SET request_status = "approved" WHERE id = ?', (request_id,))

        conn.commit()
        flash('Yêu cầu đã được xác nhận thành công.', 'success')

    conn.close()
    return redirect(url_for('device_update_requests'))

@app.route('/reject_update_request/<int:request_id>', methods=['POST'])
@login_required
def reject_update_request(request_id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    c = conn.cursor()

    # Cập nhật trạng thái của yêu cầu
    c.execute('UPDATE device_update_requests SET request_status = "rejected" WHERE id = ?', (request_id,))

    conn.commit()
    flash('Yêu cầu đã bị từ chối.', 'warning')

    conn.close()
    return redirect(url_for('device_update_requests'))

#Đang ký tài khoản
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO users (username, password, role)
                    VALUES (?, ?, 'user')
                ''', (username, hashed_password))
                conn.commit()
                flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Tên đăng nhập đã tồn tại. Vui lòng chọn tên khác.', 'danger')
    return render_template('register.html')

#Đôit mật khẩu user
@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if not session.get('logged_in'):
        flash('Vui lòng đăng nhập trước.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        username = session.get('username')

        if new_password != confirm_password:
            flash('Mật khẩu mới không khớp.', 'danger')
            return redirect(url_for('change_password'))

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if not user or not check_password_hash(user['password'], current_password):
            flash('Mật khẩu hiện tại không đúng.', 'danger')
            return redirect(url_for('change_password'))

        hashed_new_password = generate_password_hash(new_password)
        conn = get_db_connection()
        conn.execute('UPDATE users SET password = ? WHERE username = ?', (hashed_new_password, username))
        conn.commit()
        conn.close()

        flash('Đổi mật khẩu thành công!', 'success')
        return redirect(url_for('user_home'))

    return render_template('user/change_password.html')

# Thêm route để quản lý người dùng
@app.route('/manage_users')
def manage_users():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return redirect(url_for('login'))
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role FROM users")
    users = cursor.fetchall()
    conn.close()
    return render_template('admin/manage_users.html', users=users)


# Route để thêm người dùng
@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password, role))
        conn.commit()
        conn.close()
        flash('Thêm người dùng thành công!')
        return redirect(url_for('manage_users'))
    return render_template('admin/add_user.html')

# Route để sửa người dùng
@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if request.method == 'POST':
        password = generate_password_hash(request.form['password'])
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (password, user_id))
        conn.commit()
        conn.close()
        flash('Đổi mật khẩu thành công!')
        return redirect(url_for('manage_users'))
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return render_template('admin/edit_user.html', user=user)

# Route để xóa người dùng
@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash('Xóa người dùng thành công!')
    return redirect(url_for('manage_users'))



@app.route('/image/<int:part_id>')
def get_image(part_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute('SELECT image FROM parts WHERE id = ?', (part_id,))
    image_data = c.fetchone()[0]
    conn.close()
    
    if image_data:
        return send_file(io.BytesIO(image_data), mimetype='image/jpeg')
    return 'Image not found', 404
# Route để thêm phụ tùng
@app.route('/add_part', methods=['GET', 'POST'])
def add_part():
    if request.method == 'POST':
        part_code = request.form['part_code']
        part_name = request.form['part_name']
        part_description = request.form['part_description']
        quantity = request.form['quantity']
        location = request.form['location']
        
        # Xử lý hình ảnh
        image = request.files['image']
        image_data = image.read() if image else None

        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        c.execute('''
        INSERT INTO parts (part_code, part_name, part_description, quantity, image, location) VALUES
        (?, ?, ?, ?, ?, ?)
        ''', (part_code, part_name, part_description, quantity, image_data, location))

        conn.commit()
        conn.close()
        return redirect(url_for('manage_parts'))

    return render_template('admin/add_part.html')


# Route để sửa phụ tùng
@app.route('/edit_part/<string:part_code>', methods=['GET', 'POST'])
def edit_part(part_code):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    if request.method == 'POST':
        part_name = request.form['part_name']
        part_description = request.form['part_description']
        quantity = request.form['quantity']
        image_url = request.form['image_url']
        location = request.form['location']

        cursor.execute('''
            UPDATE parts
            SET part_name = ?, part_description = ?, quantity = ?, part_image = ?, location = ?
            WHERE part_code = ?
        ''', (part_name, part_description, quantity, image_url, location, part_code))
        conn.commit()

        return redirect(url_for('manage_part'))

    cursor.execute('SELECT * FROM parts WHERE part_code = ?', (part_code,))
    part = cursor.fetchone()

    if not part:
        return "Part not found", 404

    return render_template('admin/edit_part.html', part=part)



# Route để xóa phụ tùng
@app.route('/delete_part/<string:part_code>', methods=['POST'])
def delete_part(part_code):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM parts WHERE part_code = ?", (part_code,))
    conn.commit()
    conn.close()
    flash('Xóa phụ tùng thành công!')
    return redirect(url_for('manage_parts'))


# Route để quản lý phụ tùng
@app.route('/manage_parts')
def manage_parts():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM parts")
    parts = cursor.fetchall()
    conn.close()
    return render_template('admin/manage_parts.html', parts=parts)


# Route for viewing budgets
@app.route('/manage_budgets')
def manage_budgets():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    budgets = conn.execute('SELECT * FROM budgets').fetchall()
    conn.close()
    return render_template('admin/manage_budgets.html', budgets=budgets)

# Route for adding a budget
@app.route('/add_budget', methods=['GET', 'POST'])
def add_budget():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        amount = request.form['amount']
        conn = get_db_connection()
        conn.execute('INSERT INTO budgets (name, amount, remaining) VALUES (?, ?, ?)', (name, amount, amount))
        conn.commit()
        conn.close()
        return redirect(url_for('manage_budgets'))

    return render_template('admin/add_budget.html')

# Route for editing a budget
@app.route('/edit_budget/<int:id>', methods=['GET', 'POST'])
def edit_budget(id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    budget = conn.execute('SELECT * FROM budgets WHERE id = ?', (id,)).fetchone()

    if request.method == 'POST':
        name = request.form['name']
        amount = request.form['amount']
        spent = request.form['spent']
        remaining = float(amount) - float(spent)
        conn.execute('UPDATE budgets SET name = ?, amount = ?, spent = ?, remaining = ? WHERE id = ?',
                     (name, amount, spent, remaining, id))
        conn.commit()
        conn.close()
        return redirect(url_for('manage_budgets'))

    conn.close()
    return render_template('admin/edit_budget.html', budget=budget)

# Route for deleting a budget
@app.route('/delete_budget/<int:id>', methods=['POST'])
def delete_budget(id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    conn.execute('DELETE FROM budgets WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('manage_budgets'))

#PDF thiết bị
def get_devices_by_ids(device_ids):
    query = "SELECT * FROM devices WHERE device_code IN ({seq})".format(seq=','.join(['?']*len(device_ids)))
    cur = get_db().execute(query, device_ids)
    return cur.fetchall()

@app.route('/export_devices_pdf', methods=['POST'])
def export_devices_pdf():
    device_ids = request.form.getlist('device_ids')
    if not device_ids:
        return "No devices selected for PDF export.", 400

    devices = get_devices_by_ids(device_ids)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Đăng ký các font DejaVu
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'static/fonts/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'static/fonts/DejaVuSans-Bold.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Oblique', 'static/fonts/DejaVuSans-Oblique.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-BoldOblique', 'static/fonts/DejaVuSans-BoldOblique.ttf'))

    # Thêm tiêu đề
    styles = getSampleStyleSheet()
    header_style = styles['Normal']
    header_style.fontName = 'DejaVuSans-Bold'
    header_style.fontSize = 9

    # Tạo bảng tiêu đề hai cột sát lề trái và phải
    header_data = [
        [Paragraph("&nbsp &nbsp TRƯỜNG ĐẠI HỌC TIỀN GIANG<br/>PHÒNG QUẢN LÝ CƠ SỞ VẬT CHẤT", header_style), 
         Paragraph("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM<br/>&nbsp &nbsp &nbsp &nbsp Độc lập - Tự do - Hạnh phúc", header_style)]
    ]
    header_table = Table(header_data, colWidths=[3*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))  # Spacer to add some space between header and content

    title_style = styles['Title']
    title_style.fontName = 'DejaVuSans-Bold'
    title_style.fontSize = 16
    elements.append(Paragraph("Danh Sách Thiết Bị", title_style))
    elements.append(Spacer(1, 20))  # Spacer to add some space between title and table

    # Dữ liệu bảng
    data = [
        ["Mã Thiết Bị", "Tên Thiết Bị", "Ngày Bắt Đầu", "Trạng Thái", "Thông Số Kỹ Thuật", "Nơi Sử Dụng"]
    ]

    for device in devices:
        data.append([
            device['device_code'],
            device['device_name'],
            device['start_date'],
            device['status'],
            device['technical_spec'],
            device['location']
        ])

    # Điều chỉnh kích thước cột và sử dụng wordwrap
    col_widths = [1.2 * inch] * 6
    col_widths[4] = 2.5 * inch  # Tăng kích thước cột cho "Thông số kỹ thuật"

    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), '#d0d0d0'),
        ('TEXTCOLOR', (0, 0), (-1, 0), '#000000'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (-1, -1), '#f0f0f0'),
        ('GRID', (0, 0), (-1, -1), 1, '#c0c0c0'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVuSans'),
        ('WORDWRAP', (4, 1), (-1, -1), 'ALL'),  # Áp dụng wordwrap cho cột "Thông số kỹ thuật"
    ]))

    elements.append(table)

    doc.build(elements)

    buffer.seek(0)
    pdf_output = os.path.join(os.getcwd(), 'output', 'devices.pdf')
    os.makedirs(os.path.dirname(pdf_output), exist_ok=True)
    with open(pdf_output, 'wb') as f:
        f.write(buffer.getvalue())

    return send_file(pdf_output, as_attachment=True)

#PDF lịch bảo trì
@app.route('/export_maintenance_pdf', methods=['POST'])
def export_maintenance_pdf():
    maintenance_ids = request.form.getlist('maintenance_ids')
    if not maintenance_ids:
        return "No maintenance records selected for PDF export.", 400

    maintenance_records = get_maintenance_by_ids(maintenance_ids)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Đăng ký các font DejaVu
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'static/fonts/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'static/fonts/DejaVuSans-Bold.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Oblique', 'static/fonts/DejaVuSans-Oblique.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-BoldOblique', 'static/fonts/DejaVuSans-BoldOblique.ttf'))

    # Thêm tiêu đề
    styles = getSampleStyleSheet()
    header_style = styles['Normal']
    header_style.fontName = 'DejaVuSans-Bold'
    header_style.fontSize = 9

    # Tạo bảng tiêu đề hai cột sát lề trái và phải
    header_data = [
        [Paragraph("&nbsp &nbsp TRƯỜNG ĐẠI HỌC TIỀN GIANG<br/>PHÒNG QUẢN LÝ CƠ SỞ VẬT CHẤT", header_style), 
         Paragraph("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM<br/>&nbsp &nbsp &nbsp &nbsp Độc lập - Tự do - Hạnh phúc", header_style)]
    ]
    header_table = Table(header_data, colWidths=[3*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))  # Spacer to add some space between header and content
    # Thêm tiêu đề
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    title_style.fontName = 'DejaVuSans-Bold'
    title_style.fontSize = 16
    elements.append(Paragraph("Danh Sách Lịch Bảo Trì", title_style))

    # Dữ liệu bảng
    data = [
        ["Ngày Bảo Trì", "Mô Tả Nội Dung Bảo Trì", "Thiết Bị", "Người Thực Hiện Bảo Trì", "Trạng Thái", "Nơi Sử Dụng"]
    ]

    for record in maintenance_records:
        data.append([
            record['maintenance_date'],
            record['description'],
            record['device_code'],
            record['assigned_user'],
            record['status'],
            record['location']
        ])

    # Điều chỉnh kích thước cột và sử dụng wordwrap
    col_widths = [1.2*inch]*6
    col_widths[1] = 2.5*inch  # Tăng kích thước cột cho "Mô tả nội dung bảo trì"

    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), '#d0d0d0'),
        ('TEXTCOLOR', (0, 0), (-1, 0), '#000000'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (-1, -1), '#f0f0f0'),
        ('GRID', (0, 0), (-1, -1), 1, '#c0c0c0'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVuSans'),
        ('WORDWRAP', (1, 1), (-1, -1), 'ALL'),  # Áp dụng wordwrap cho cột "Mô tả nội dung bảo trì"
    ]))

    elements.append(table)

    doc.build(elements)

    buffer.seek(0)
    pdf_output = os.path.join(os.getcwd(), 'output', 'maintenance.pdf')
    os.makedirs(os.path.dirname(pdf_output), exist_ok=True)
    with open(pdf_output, 'wb') as f:
        f.write(buffer.getvalue())

    return send_file(pdf_output, as_attachment=True)

def get_maintenance_by_ids(maintenance_ids):
    query = "SELECT * FROM maintenance WHERE id IN ({seq})".format(seq=','.join(['?']*len(maintenance_ids)))
    cur = get_db().execute(query, maintenance_ids)
    return cur.fetchall()

#PDF Quản Lý Phụ Tùng
def get_parts_by_ids(part_ids):
    query = "SELECT id, part_code, part_name, part_description, quantity, location FROM parts WHERE part_code IN ({seq})".format(seq=','.join(['?']*len(part_ids)))
    cur = get_db().execute(query, part_ids)
    return cur.fetchall()

@app.route('/export_parts_pdf', methods=['POST'])
def export_parts_pdf():
    part_ids = request.form.getlist('part_ids')
    if not part_ids:
        return "No parts selected for PDF export.", 400

    parts = get_parts_by_ids(part_ids)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Đăng ký các font DejaVu
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'static/fonts/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'static/fonts/DejaVuSans-Bold.ttf'))

    # Thiết lập style
    styles = getSampleStyleSheet()
    normal_style = styles['Normal']
    bold_style = ParagraphStyle(
        name='Bold',
        parent=normal_style,
        fontName='DejaVuSans-Bold',
        fontSize=12,
    )
    title_style = ParagraphStyle(
        name='Title',
        parent=normal_style,
        fontName='DejaVuSans-Bold',
        fontSize=16,
        alignment=1,  # Center alignment
    )
    header_style = ParagraphStyle(
        name='Header',
        parent=normal_style,
        fontName='DejaVuSans-Bold',
        fontSize=12,
        alignment=1,
        spaceAfter=10,
    )

    # Thêm tiêu đề
    styles = getSampleStyleSheet()
    header_style = styles['Normal']
    header_style.fontName = 'DejaVuSans-Bold'
    header_style.fontSize = 9

    # Tạo bảng tiêu đề hai cột sát lề trái và phải
    header_data = [
        [Paragraph("&nbsp &nbsp TRƯỜNG ĐẠI HỌC TIỀN GIANG<br/>PHÒNG QUẢN LÝ CƠ SỞ VẬT CHẤT", header_style), 
         Paragraph("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM<br/>&nbsp &nbsp &nbsp &nbsp Độc lập - Tự do - Hạnh phúc", header_style)]
    ]
    header_table = Table(header_data, colWidths=[3*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))  # Spacer to add some space between header and content
    # Thêm các tiêu đề
    
    elements.append(Paragraph("DANH SÁCH PHỤ TÙNG", title_style))
    elements.append(Spacer(1, 20))

    # Tạo bảng dữ liệu
    data = [["Mã Phụ Tùng", "Tên Phụ Tùng", "Mô Tả", "Số Lượng", "Vị Trí"]]
    for part in parts:
        data.append([
            part['part_code'],
            part['part_name'],
            part['part_description'],
            part['quantity'],
            part['location']
        ])

    table = Table(data, colWidths=[1.2*inch]*5)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), '#d0d0d0'),
        ('TEXTCOLOR', (0, 0), (-1, 0), '#000000'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (-1, -1), '#f0f0f0'),
        ('GRID', (0, 0), (-1, -1), 1, '#c0c0c0'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVuSans'),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    pdf_output = os.path.join(os.getcwd(), 'output', 'parts.pdf')
    with open(pdf_output, 'wb') as f:
        f.write(buffer.getvalue())

    return send_file(pdf_output, as_attachment=True)

#PDF QL Ngân Sách
def get_budgets_by_ids(budget_ids):
    query = "SELECT id, name, amount, spent, remaining FROM budgets WHERE id IN ({seq})".format(
        seq=','.join(['?']*len(budget_ids))
    )
    cur = get_db().execute(query, budget_ids)
    budgets = cur.fetchall()
    cur.close()
    return budgets

@app.route('/export_budgets_pdf', methods=['POST'])
def export_budgets_pdf():
    budget_ids = request.form.getlist('budget_ids')
    if not budget_ids:
        return "No budgets selected", 400

    budgets = get_budgets_by_ids(budget_ids)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Đăng ký các font DejaVu
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'static/fonts/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'static/fonts/DejaVuSans-Bold.ttf'))

    # Thiết lập style
    styles = getSampleStyleSheet()
    normal_style = styles['Normal']
    bold_style = ParagraphStyle(
        name='Bold',
        parent=normal_style,
        fontName='DejaVuSans-Bold',
        fontSize=12,
    )
    title_style = ParagraphStyle(
        name='Title',
        parent=normal_style,
        fontName='DejaVuSans-Bold',
        fontSize=16,
        alignment=1,  # Center alignment
    )
    header_style = ParagraphStyle(
        name='Header',
        parent=normal_style,
        fontName='DejaVuSans-Bold',
        fontSize=12,
        alignment=1,
        spaceAfter=10,
    )

    # Thêm tiêu đề
    styles = getSampleStyleSheet()
    header_style = styles['Normal']
    header_style.fontName = 'DejaVuSans-Bold'
    header_style.fontSize = 9

    # Tạo bảng tiêu đề hai cột sát lề trái và phải
    header_data = [
        [Paragraph("&nbsp &nbsp TRƯỜNG ĐẠI HỌC TIỀN GIANG<br/>PHÒNG QUẢN LÝ CƠ SỞ VẬT CHẤT", header_style), 
         Paragraph("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM<br/>&nbsp &nbsp &nbsp &nbsp Độc lập - Tự do - Hạnh phúc", header_style)]
    ]
    header_table = Table(header_data, colWidths=[3*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))  # Spacer to add some space between header and content
    # Thêm các tiêu đề
    elements.append(Paragraph("DANH SÁCH NGÂN SÁCH", title_style))
    elements.append(Spacer(1, 20))

    # Tạo bảng dữ liệu
    data = [["ID", "Tên", "Số Tiền", "Đã Chi", "Còn Lại"]]
    for budget in budgets:
        data.append([
            budget['id'],
            budget['name'],
            budget['amount'],
            budget['spent'],
            budget['remaining']
        ])

    table = Table(data, colWidths=[1*inch]*5)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), '#d0d0d0'),
        ('TEXTCOLOR', (0, 0), (-1, 0), '#000000'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (-1, -1), '#f0f0f0'),
        ('GRID', (0, 0), (-1, -1), 1, '#c0c0c0'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVuSans'),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    pdf_output = os.path.join(os.getcwd(), 'output', 'budgets.pdf')
    with open(pdf_output, 'wb') as f:
        f.write(buffer.getvalue())

    return send_file(pdf_output, as_attachment=True)

#PDF Thống kê
def get_active_devices_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM devices WHERE status = 'active'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_maintenance_devices_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM devices WHERE status = 'maintenance'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_inactive_devices_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM devices WHERE status = 'inactive'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_total_devices_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM devices")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_device_update_requests_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM device_update_requests WHERE new_status = 'pending'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_total_users_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE role != 'admin'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_past_maintenance_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM maintenance WHERE maintenance_date < DATE('now')")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_today_maintenance_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM maintenance WHERE maintenance_date = DATE('now')")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_upcoming_maintenance_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM maintenance WHERE maintenance_date > DATE('now')")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_total_notifications_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM notifications")
    count = cursor.fetchone()[0]
    conn.close()
    return count

@app.route('/export_dashboard_pdf', methods=['POST'])
def export_dashboard_pdf():
    # Lấy dữ liệu thống kê
    active_devices = get_active_devices_count()
    maintenance_devices = get_maintenance_devices_count()
    inactive_devices = get_inactive_devices_count()
    total_devices = get_total_devices_count()
    device_update_requests = get_device_update_requests_count()
    total_users = get_total_users_count()
    past_maintenance = get_past_maintenance_count()
    today_maintenance = get_today_maintenance_count()
    upcoming_maintenance = get_upcoming_maintenance_count()
    total_notifications = get_total_notifications_count()

    # Tạo PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Đăng ký các font DejaVu
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'static/fonts/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'static/fonts/DejaVuSans-Bold.ttf'))

    # Thiết lập style
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name='Title',
        parent=styles['Title'],
        fontName='DejaVuSans-Bold',
        fontSize=16,
        alignment=1,  # Center alignment
        spaceAfter=20
    )
    section_style = ParagraphStyle(
        name='Section',
        parent=styles['Heading2'],
        fontName='DejaVuSans-Bold',
        fontSize=14,
        spaceAfter=10
    )
    normal_style = styles['Normal']
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), '#d0d0d0'),
        ('TEXTCOLOR', (0, 0), (-1, 0), '#000000'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (-1, -1), '#f0f0f0'),
        ('GRID', (0, 0), (-1, -1), 1, '#c0c0c0'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVuSans'),
    ])

     # Thêm tiêu đề
    styles = getSampleStyleSheet()
    header_style = styles['Normal']
    header_style.fontName = 'DejaVuSans-Bold'
    header_style.fontSize = 9

    # Tạo bảng tiêu đề hai cột sát lề trái và phải
    header_data = [
        [Paragraph("&nbsp &nbsp TRƯỜNG ĐẠI HỌC TIỀN GIANG<br/>PHÒNG QUẢN LÝ CƠ SỞ VẬT CHẤT", header_style), 
         Paragraph("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM<br/>&nbsp &nbsp &nbsp &nbsp Độc lập - Tự do - Hạnh phúc", header_style)]
    ]
    header_table = Table(header_data, colWidths=[3*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))  # Spacer to add some space between header and content
    # Thêm tiêu đề
    elements.append(Paragraph("Thống Kê Hệ Thống", title_style))
    elements.append(Spacer(1, 20))

    # Tạo bảng dữ liệu thống kê
    data = [
        ['Tiêu Đề', 'Số Lượng'],
        ['Thiết bị hoạt động', active_devices],
        ['Thiết bị bảo trì', maintenance_devices],
        ['Thiết bị không hoạt động', inactive_devices],
        ['Tổng số thiết bị', total_devices],
        ['Yêu cầu cập nhật thiết bị đang chờ', device_update_requests],
        ['Tổng số người dùng (trừ Admin)', total_users],
        ['Bảo trì đã qua', past_maintenance],
        ['Bảo trì hôm nay', today_maintenance],
        ['Bảo trì sắp tới', upcoming_maintenance],
        ['Tổng số thông báo', total_notifications]
    ]

    table = Table(data, colWidths=[3*inch, 2*inch])
    table.setStyle(table_style)

    elements.append(table)

    doc.build(elements)

    buffer.seek(0)
    pdf_output = os.path.join(os.getcwd(), 'output', 'dashboard.pdf')
    with open(pdf_output, 'wb') as f:
        f.write(buffer.getvalue())

    return send_file(pdf_output, as_attachment=True)

#PDF Thông báo
def get_notifications_by_ids(notification_ids):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM notifications WHERE id IN ({seq})".format(
        seq=','.join(['?']*len(notification_ids)))
    cursor.execute(query, notification_ids)
    notifications = cursor.fetchall()
    conn.close()
    return notifications

@app.route('/export_notifications_pdf', methods=['POST'])
def export_notifications_pdf():
    notification_ids = request.form.getlist('notification_ids')
    if not notification_ids:
        return "No notifications selected", 400

    notifications = get_notifications_by_ids(notification_ids)

    # Tạo PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Đăng ký các font DejaVu
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'static/fonts/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'static/fonts/DejaVuSans-Bold.ttf'))

    # Thiết lập style
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name='Title',
        parent=styles['Title'],
        fontName='DejaVuSans-Bold',
        fontSize=16,
        alignment=1,  # Center alignment
        spaceAfter=20
    )
    section_style = ParagraphStyle(
        name='Section',
        parent=styles['Heading2'],
        fontName='DejaVuSans-Bold',
        fontSize=14,
        spaceAfter=10
    )
    normal_style = styles['Normal']
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), '#d0d0d0'),
        ('TEXTCOLOR', (0, 0), (-1, 0), '#000000'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (-1, -1), '#f0f0f0'),
        ('GRID', (0, 0), (-1, -1), 1, '#c0c0c0'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVuSans'),
    ])

     # Thêm tiêu đề
    styles = getSampleStyleSheet()
    header_style = styles['Normal']
    header_style.fontName = 'DejaVuSans-Bold'
    header_style.fontSize = 9

    # Tạo bảng tiêu đề hai cột sát lề trái và phải
    header_data = [
        [Paragraph("&nbsp &nbsp TRƯỜNG ĐẠI HỌC TIỀN GIANG<br/>PHÒNG QUẢN LÝ CƠ SỞ VẬT CHẤT", header_style), 
         Paragraph("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM<br/>&nbsp &nbsp &nbsp &nbsp Độc lập - Tự do - Hạnh phúc", header_style)]
    ]
    header_table = Table(header_data, colWidths=[3*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))  # Spacer to add some space between header and content
    # Thêm tiêu đề
    elements.append(Paragraph("Danh Sách Thông Báo", title_style))
    elements.append(Spacer(1, 20))

    # Tạo bảng dữ liệu thông báo
    data = [
        ['ID', 'Người gửi', 'Nội dung', 'Thời gian gửi']
    ]
    for notification in notifications:
        data.append([notification[0], notification[1], notification[2], notification[3]])

    table = Table(data, colWidths=[1*inch, 2*inch, 3*inch, 2*inch])
    table.setStyle(table_style)

    elements.append(table)

    doc.build(elements)

    buffer.seek(0)
    pdf_output = os.path.join(os.getcwd(), 'output', 'notifications.pdf')
    with open(pdf_output, 'wb') as f:
        f.write(buffer.getvalue())

    return send_file(pdf_output, as_attachment=True)

#PDF YCCN
def get_device_update_requests_by_ids(request_ids):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM device_update_requests WHERE id IN ({seq})".format(
        seq=','.join(['?']*len(request_ids)))
    cursor.execute(query, request_ids)
    requests = cursor.fetchall()
    conn.close()
    return requests

@app.route('/export_device_update_requests_pdf', methods=['POST'])
def export_device_update_requests_pdf():
    request_ids = request.form.getlist('request_ids')
    if not request_ids:
        return "No requests selected", 400

    requests = get_device_update_requests_by_ids(request_ids)

    # Tạo PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Đăng ký các font DejaVu
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'static/fonts/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'static/fonts/DejaVuSans-Bold.ttf'))

    # Thiết lập style
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name='Title',
        parent=styles['Title'],
        fontName='DejaVuSans-Bold',
        fontSize=16,
        alignment=1,  # Center alignment
        spaceAfter=20
    )
    section_style = ParagraphStyle(
        name='Section',
        parent=styles['Heading2'],
        fontName='DejaVuSans-Bold',
        fontSize=14,
        spaceAfter=10
    )
    normal_style = styles['Normal']
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), '#d0d0d0'),
        ('TEXTCOLOR', (0, 0), (-1, 0), '#000000'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (-1, -1), '#f0f0f0'),
        ('GRID', (0, 0), (-1, -1), 1, '#c0c0c0'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVuSans'),
    ])

     # Thêm tiêu đề
    styles = getSampleStyleSheet()
    header_style = styles['Normal']
    header_style.fontName = 'DejaVuSans-Bold'
    header_style.fontSize = 9

    # Tạo bảng tiêu đề hai cột sát lề trái và phải
    header_data = [
        [Paragraph("&nbsp &nbsp TRƯỜNG ĐẠI HỌC TIỀN GIANG<br/>PHÒNG QUẢN LÝ CƠ SỞ VẬT CHẤT", header_style), 
         Paragraph("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM<br/>&nbsp &nbsp &nbsp &nbsp Độc lập - Tự do - Hạnh phúc", header_style)]
    ]
    header_table = Table(header_data, colWidths=[3*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))  # Spacer to add some space between header and content
    # Thêm tiêu đề
    elements.append(Paragraph("Danh Sách Yêu Cầu Cập Nhật Trạng Thái Thiết Bị", title_style))
    elements.append(Spacer(1, 20))

    # Tạo bảng dữ liệu yêu cầu cập nhật
    data = [
        ['ID', 'Mã thiết bị', 'Trạng thái mới', 'ID người dùng', 'Thời gian yêu cầu']
    ]
    for req in requests:
        data.append([req[0], req[1], req[2], req[3], req[4]])

    table = Table(data, colWidths=[1*inch, 1.5*inch, 1.5*inch, 1*inch, 1.5*inch])
    table.setStyle(table_style)

    elements.append(table)

    doc.build(elements)

    buffer.seek(0)
    pdf_output = os.path.join(os.getcwd(), 'output', 'device_update_requests.pdf')
    with open(pdf_output, 'wb') as f:
        f.write(buffer.getvalue())

    return send_file(pdf_output, as_attachment=True)



def get_users_by_ids(user_ids):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id IN ({seq})".format(
        seq=','.join(['?']*len(user_ids))), user_ids)
    users = cursor.fetchall()
    conn.close()
    return users

@app.route('/export_users_pdf', methods=['POST'])
def export_users_pdf():
    user_ids = request.form.getlist('user_ids')
    if not user_ids:
        return "No users selected", 400

    users = get_users_by_ids(user_ids)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Tiêu đề tài liệu
    title = "Danh Sách Người Dùng"
    elements.append(Paragraph(title, style=getSampleStyleSheet()['Title']))

    # Dữ liệu bảng
    data = [['ID', 'Tên Đăng Nhập', 'Vai Trò']]
    for user in users:
        data.append([user[0], user[1], user[3]])

    pdfmetrics.registerFont(TTFont('DejaVuSans', 'static/fonts/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'static/fonts/DejaVuSans-Bold.ttf'))
    # Tạo bảng với các kiểu dáng đẹp hơn
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVuSans'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))

    elements.append(table)

    doc.build(elements)

    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='users.pdf', mimetype='application/pdf')


if __name__ == '__main__':
    app.run(debug=True)
