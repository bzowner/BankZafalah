import sqlite3
import random
import io
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from captcha.image import ImageCaptcha 

app = Flask(__name__)
app.secret_key = 'zafalah_secret_key'
DB_NAME = "bank.db"

# --- DATABASE CONNECTION ---
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# --- INITIALIZE DATABASE ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # 1. Users Table (Added role, job_title, employment_status)
    # role: 'user', 'employee', 'ceo'
    # employment_status: 'none', 'pending', 'hired'
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, balance REAL, account_no TEXT, 
                  role TEXT, job_title TEXT, employment_status TEXT)''')
    
    # 2. Transactions Table
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY, user_id INTEGER, description TEXT, amount REAL, date TEXT, type TEXT)''')

    # 3. Requests Table (Handles Deposits, Withdrawals, Loans, Job Apps)
    c.execute('''CREATE TABLE IF NOT EXISTS requests 
                 (id INTEGER PRIMARY KEY, user_id INTEGER, type TEXT, amount REAL, details TEXT, date TEXT, status TEXT)''')
    
    # 4. Create CEO (Role: CEO)
    c.execute("SELECT * FROM users WHERE username = 'zaf.ceo'")
    if not c.fetchone():
        hashed_pw = generate_password_hash('bz2025') 
        massive_balance = 9999999999999999999.0 
        c.execute("INSERT INTO users (username, password, balance, account_no, role, job_title, employment_status) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                  ('zaf.ceo', hashed_pw, massive_balance, 'ZF-CEO-001', 'ceo', 'Chief Executive Officer', 'hired'))

    # 5. Create Dummy Account
    c.execute("SELECT * FROM users WHERE username = 'Dummy'")
    if not c.fetchone():
        hashed_pw = generate_password_hash('1234')
        c.execute("INSERT INTO users (username, password, balance, account_no, role, job_title, employment_status) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                  ('Dummy', hashed_pw, 10000.00, 'ZF-DUMMY-001', 'user', 'None', 'none'))

    conn.commit()
    conn.close()
    print("Database Initialized.")

init_db()

# --- CAPTCHA ---
@app.route('/captcha_image')
def captcha_image():
    image = ImageCaptcha(width=280, height=90)
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    captcha_text = "".join(random.choice(letters) for i in range(5))
    session['captcha_ans'] = captcha_text
    data = image.generate(captcha_text)
    return send_file(io.BytesIO(data.getvalue()), mimetype='image/png')

# --- ROUTES ---

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        user_input = request.form.get('captcha', '').upper()
        if user_input != session.get('captcha_ans', ''):
            flash("Incorrect Captcha code.")
            return redirect(url_for('home')) # Redirect to home to keep it snappy

        username = request.form['username']
        password = request.form['password']
        account_no = f"ZF-{random.randint(1000,9999)}-{random.randint(1000,9999)}"
        hashed_pw = generate_password_hash(password)

        conn = get_db_connection()
        try:
            # Users are created ACTIVE immediately as 'user'
            conn.execute('INSERT INTO users (username, password, balance, account_no, role, job_title, employment_status) VALUES (?, ?, ?, ?, ?, ?, ?)',
                         (username, hashed_pw, 0.00, account_no, 'user', 'None', 'none'))
            conn.commit()
            flash("Account created! Log in now.")
            return redirect(url_for('home'))
        except sqlite3.IntegrityError:
            flash("Username already taken.")
        finally:
            conn.close()
            
    return redirect(url_for('home')) # Signups happen on index page modal/tab

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()

    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        return redirect(url_for('dashboard'))
    else:
        flash("Invalid credentials")
        return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('home'))
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    # Common Data for Everyone (History, Requests)
    transactions = conn.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 10', (session['user_id'],)).fetchall()
    my_requests = conn.execute('SELECT * FROM requests WHERE user_id = ? ORDER BY id DESC', (session['user_id'],)).fetchall()
    
    # CEO Specific Data
    ceo_data = {}
    if user['role'] == 'ceo':
        ceo_data['all_users'] = conn.execute('SELECT * FROM users WHERE role != "ceo"').fetchall()
        # Requests that are pending (Job Apps, Loans, Cash)
        ceo_data['pending_requests'] = conn.execute('''
            SELECT r.*, u.username, u.role as user_role
            FROM requests r 
            JOIN users u ON r.user_id = u.id 
            WHERE r.status = "pending"
        ''').fetchall()
        # Employees list
        ceo_data['employees'] = conn.execute('SELECT * FROM users WHERE role = "employee"').fetchall()

    conn.close()
    return render_template('dashboard.html', user=user, transactions=transactions, my_requests=my_requests, ceo_data=ceo_data)

# --- USER ACTIONS ---

@app.route('/submit_request', methods=['POST'])
def submit_request():
    if 'user_id' not in session: return redirect(url_for('home'))
    
    req_type = request.form.get('type') # Deposit, Withdraw, Loan, Job Application
    amount = 0.0
    details = request.form.get('details', '')

    # Job Application Logic
    if req_type == 'Job Application':
        conn = get_db_connection()
        conn.execute('UPDATE users SET employment_status = "pending" WHERE id = ?', (session['user_id'],))
        conn.execute('INSERT INTO requests (user_id, type, amount, details, date, status) VALUES (?, ?, ?, ?, ?, ?)',
                     (session['user_id'], 'Job Application', 0, 'Requesting Employment', datetime.now().strftime("%Y-%m-%d"), 'pending'))
        conn.commit()
        conn.close()
        flash("Job Application Sent to CEO.")
        return redirect(url_for('dashboard'))

    # Financial Request Logic
    try:
        amount = float(request.form.get('amount'))
    except ValueError:
        flash("Invalid amount")
        return redirect(url_for('dashboard'))

    if amount <= 0:
        flash("Amount must be positive")
        return redirect(url_for('dashboard'))

    user_id = session['user_id']
    date_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = get_db_connection()

    if req_type == 'Withdraw':
        user = conn.execute('SELECT balance FROM users WHERE id = ?', (user_id,)).fetchone()
        if user['balance'] < amount:
            flash("Insufficient funds.")
            conn.close()
            return redirect(url_for('dashboard'))
        # Deduct immediately
        conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, user_id))
        flash("Funds removed. Visit branch (CEO) for cash.")
    
    elif req_type == 'Deposit':
        flash("Give cash to CEO to finalize deposit.")

    elif req_type == 'Loan':
        flash("Loan application submitted for review.")

    conn.execute('INSERT INTO requests (user_id, type, amount, details, date, status) VALUES (?, ?, ?, ?, ?, ?)',
                 (user_id, req_type, amount, details, date_now, 'pending'))
    conn.commit()
    conn.close()
    
    return redirect(url_for('dashboard'))

@app.route('/transfer', methods=['POST'])
def transfer():
    if 'user_id' not in session: return redirect(url_for('home'))
    recipient_name = request.form.get('recipient')
    try:
        amount = float(request.form.get('amount'))
    except: return redirect(url_for('dashboard'))
    
    user_id = session['user_id']
    date_now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = get_db_connection()
    sender = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    recipient = conn.execute('SELECT * FROM users WHERE username = ?', (recipient_name,)).fetchone()
    
    if not recipient: flash("User not found")
    elif sender['balance'] < amount: flash("Insufficient Funds")
    elif amount <= 0: flash("Invalid Amount")
    elif recipient['id'] == sender['id']: flash("Cannot transfer to self")
    else:
        conn.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, user_id))
        conn.execute('INSERT INTO transactions (user_id, description, amount, date, type) VALUES (?, ?, ?, ?, ?)', (user_id, f"To {recipient_name}", amount, date_now, "Debit"))
        conn.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, recipient['id']))
        conn.execute('INSERT INTO transactions (user_id, description, amount, date, type) VALUES (?, ?, ?, ?, ?)', (recipient['id'], f"From {sender['username']}", amount, date_now, "Credit"))
        conn.commit()
        flash("Transfer Successful!")
    conn.close()
    return redirect(url_for('dashboard'))


# --- CEO ACTIONS ---

@app.route('/ceo_action', methods=['POST'])
def ceo_action():
    if session.get('role') != 'ceo': return redirect(url_for('home'))
    
    action_type = request.form.get('action_type')
    req_id = request.form.get('req_id')
    user_id = request.form.get('user_id')
    
    conn = get_db_connection()

    # 1. Handle Requests (Deposit, Withdraw, Loan, Job)
    if action_type == 'approve_request' or action_type == 'reject_request':
        req = conn.execute('SELECT * FROM requests WHERE id = ?', (req_id,)).fetchone()
        new_status = 'approved' if 'approve' in action_type else 'rejected'
        
        if req and req['status'] == 'pending':
            # Job App
            if req['type'] == 'Job Application':
                if new_status == 'approved':
                    # Assign title from form
                    job_title = request.form.get('job_title', 'Bank Staff')
                    conn.execute('UPDATE users SET role="employee", employment_status="hired", job_title=? WHERE id=?', (job_title, req['user_id']))
                    flash(f"Hired new employee: {job_title}")
                else:
                    conn.execute('UPDATE users SET employment_status="none" WHERE id=?', (req['user_id'],))
            
            # Financials
            elif req['type'] == 'Deposit' and new_status == 'approved':
                conn.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (req['amount'], req['user_id']))
                conn.execute('INSERT INTO transactions (user_id, description, amount, date, type) VALUES (?, ?, ?, ?, ?)',
                             (req['user_id'], "Deposit Approved", req['amount'], req['date'], "Credit"))
            
            elif req['type'] == 'Loan' and new_status == 'approved':
                conn.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (req['amount'], req['user_id']))
                conn.execute('INSERT INTO transactions (user_id, description, amount, date, type) VALUES (?, ?, ?, ?, ?)',
                             (req['user_id'], f"Loan Approved: {req['details']}", req['amount'], req['date'], "Credit"))
            
            elif req['type'] == 'Withdraw' and new_status == 'rejected':
                # Refund money
                conn.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (req['amount'], req['user_id']))
                flash("Withdrawal rejected. Money refunded.")

            conn.execute('UPDATE requests SET status = ? WHERE id = ?', (new_status, req_id))
    
    # 2. Fire Employee
    elif action_type == 'fire_employee':
        conn.execute('UPDATE users SET role="user", job_title="None", employment_status="none" WHERE id=?', (user_id,))
        flash("Employee Fired.")

    # 3. Delete User
    elif action_type == 'delete_user':
        conn.execute('DELETE FROM users WHERE id=?', (user_id,))
        flash("User Deleted.")

    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
