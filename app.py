from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import mysql.connector
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'warungbiru_secret_key'
app.config['SESSION_TYPE'] = 'filesystem'

# Koneksi database
def get_db_connection():
    conn = mysql.connector.connect(
        host='warbir-u66541.vm.elestio.app',
        port=24306,
        user='root',
        password='eC-s1mRvFrr330cyr7--S',
        database='warbir',
        autocommit=False
    )
    return conn

# Decorator untuk memeriksa login admin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes untuk halaman customer
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/menu')
def menu():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM menu WHERE tersedia = 1 ORDER BY kategori, nama")
    menu_items = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('menu.html', menu_items=menu_items)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'cart' not in session:
        session['cart'] = []
    
    menu_id = int(request.form['menu_id'])
    quantity = int(request.form['quantity'])
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM menu WHERE id = %s", (menu_id,))
    menu_item = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if menu_item:
        # Cek apakah item sudah ada di cart
        item_exists = False
        for item in session['cart']:
            if item['id'] == menu_id:
                item['quantity'] += quantity
                item_exists = True
                break
        
        if not item_exists:
            cart_item = {
                'id': menu_item['id'],
                'nama': menu_item['nama'],
                'harga': float(menu_item['harga']),
                'quantity': quantity,
                'kategori': menu_item['kategori']
            }
            session['cart'].append(cart_item)
    
    session.modified = True
    return jsonify({
        'status': 'success',
        'message': 'Item berhasil ditambahkan ke keranjang',
        'cart_count': len(session['cart'])
    })

@app.route('/remove_from_cart/<int:item_id>')
def remove_from_cart(item_id):
    if 'cart' in session:
        session['cart'] = [item for item in session['cart'] if item['id'] != item_id]
        session.modified = True
    
    return redirect(url_for('view_cart'))

@app.route('/clear_cart')
def clear_cart():
    if 'cart' in session:
        session.pop('cart')
    
    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    cart = session.get('cart', [])
    total = sum(item['harga'] * item['quantity'] for item in cart)
    return render_template('cart.html', cart=cart, total=total)

@app.route('/checkout', methods=['POST'])
def checkout():
    try:
        data = request.get_json()
        nama = data.get('nama_pelanggan', '').strip()
        metode = data.get('metode_pembayaran')
        items = data.get('items')
        total = data.get('total_harga')
        
        if not nama:
            return jsonify({"status": "error", "message": "Nama pelanggan harus diisi"}), 400
        
        if not items:
            return jsonify({"status": "error", "message": "Keranjang kosong"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Simpan ke tabel pesanan
        cursor.execute("""
            INSERT INTO pesanan (nama_pelanggan, total_harga, status, metode_pembayaran)
            VALUES (%s, %s, %s, %s)
        """, (nama, total, "pending", metode))
        pesanan_id = cursor.lastrowid

        # Simpan detail pesanan
        for item in items:
            cursor.execute("""
                INSERT INTO detail_pesanan (pesanan_id, menu_id, quantity, harga)
                VALUES (%s, %s, %s, %s)
            """, (
                pesanan_id,
                item["id"],
                item["quantity"],
                item["price"]
            ))

        conn.commit()
        
        # Kosongkan keranjang
        session.pop('cart', None)
        
        return jsonify({
            "status": "success", 
            "pesanan_id": pesanan_id,
            "message": "Pesanan berhasil dibuat!"
        })
    
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

# Routes untuk admin
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admin WHERE username = %s AND password = %s", (username, password))
        admin = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if admin:
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error='Username atau password salah')
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Ambil semua menu
    cursor.execute("SELECT * FROM menu ORDER BY kategori, nama")
    menu_items = cursor.fetchall()
    
    # PERBAIKAN: Ambil semua pesanan dengan query yang lebih sederhana
    cursor.execute("""
        SELECT 
            p.id,
            p.nama_pelanggan,
            p.total_harga,
            p.status,
            p.metode_pembayaran,
            p.created_at,
            COUNT(dp.id) as item_count
        FROM pesanan p
        LEFT JOIN detail_pesanan dp ON p.id = dp.pesanan_id
        WHERE p.nama_pelanggan IS NOT NULL 
        AND p.nama_pelanggan != ''
        GROUP BY p.id
        ORDER BY p.created_at DESC
    """)
    orders = cursor.fetchall()
    
    # HITUNG STATISTIK
    cursor.execute("SELECT COUNT(*) as total FROM pesanan")
    total_pesanan = cursor.fetchone()['total']
    
    cursor.execute("SELECT SUM(total_harga) as total FROM pesanan WHERE status = 'completed'")
    result = cursor.fetchone()
    total_pendapatan = result['total'] if result['total'] else 0
    
    cursor.execute("SELECT COUNT(*) as pending FROM pesanan WHERE status = 'pending'")
    pending_orders = cursor.fetchone()['pending']
    
    cursor.close()
    conn.close()
    
    return render_template('admin_dashboard.html', 
                          menu_items=menu_items,
                          orders=orders,
                          total_pesanan=total_pesanan,
                          total_pendapatan=total_pendapatan,
                          pending_orders=pending_orders)

@app.route('/admin/menu/add', methods=['POST'])
@admin_required
def add_menu():
    try:
        nama = request.form['nama']
        harga = float(request.form['harga'])
        kategori = request.form['kategori']
        tersedia = request.form.get('tersedia', 'off') == 'on'
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO menu (nama, harga, kategori, tersedia)
            VALUES (%s, %s, %s, %s)
        """, (nama, harga, kategori, tersedia))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'status': 'success', 'message': 'Menu berhasil ditambahkan'})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/menu/edit/<int:menu_id>', methods=['POST'])
@admin_required
def edit_menu(menu_id):
    try:
        nama = request.form['nama']
        harga = float(request.form['harga'])
        kategori = request.form['kategori']
        tersedia = request.form.get('tersedia', 'off') == 'on'
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE menu 
            SET nama = %s, harga = %s, kategori = %s, tersedia = %s
            WHERE id = %s
        """, (nama, harga, kategori, tersedia, menu_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'status': 'success', 'message': 'Menu berhasil diperbarui'})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/menu/delete/<int:menu_id>', methods=['GET', 'POST'])
@admin_required
def delete_menu(menu_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Cek apakah menu digunakan dalam pesanan
        cursor.execute("SELECT COUNT(*) as count FROM detail_pesanan WHERE menu_id = %s", (menu_id,))
        result = cursor.fetchone()
        
        if result['count'] > 0:
            cursor.close()
            conn.close()
            return jsonify({'status': 'error', 'message': 'Menu tidak dapat dihapus karena sudah digunakan dalam pesanan'}), 400
        
        cursor.execute("DELETE FROM menu WHERE id = %s", (menu_id,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        # HAPUS FLASH MESSAGES! Hanya return JSON untuk AJAX
        return jsonify({'status': 'success', 'message': 'Menu berhasil dihapus'})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/order/update_status', methods=['POST'])
@admin_required
def update_order_status():
    try:
        order_id = request.form['order_id']
        status = request.form['status']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE pesanan 
            SET status = %s 
            WHERE id = %s
        """, (status, order_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'status': 'success', 'message': 'Status pesanan berhasil diperbarui'})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/order/detail/<int:order_id>')
@admin_required
def order_detail(order_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Ambil detail pesanan
    cursor.execute("""
        SELECT p.*, dp.quantity, dp.harga as item_harga,
               m.nama as menu_nama, m.kategori
        FROM pesanan p
        JOIN detail_pesanan dp ON p.id = dp.pesanan_id
        JOIN menu m ON dp.menu_id = m.id
        WHERE p.id = %s
    """, (order_id,))
    
    order_details = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    if not order_details:
        return redirect(url_for('admin_dashboard'))
    
    return render_template('order_detail.html', 
                         order=order_details[0],
                         order_details=order_details)

@app.route('/admin/reset_customer_data')
@admin_required
def admin_reset_customer_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Hapus semua data pesanan dan detail pesanan
        cursor.execute("DELETE FROM detail_pesanan")
        cursor.execute("DELETE FROM pesanan")
        
        conn.commit()
        flash('Data pelanggan berhasil direset', 'success')
    
    except Exception as e:
        conn.rollback()
        flash(f'Error: {str(e)}', 'danger')
    
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('admin_login'))

# API untuk mendapatkan data statistik
@app.route('/api/stats')
@admin_required
def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT 
            COUNT(*) as total_orders,
            SUM(CASE WHEN status = 'completed' THEN total_harga ELSE 0 END) as total_revenue,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_orders,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_orders
        FROM pesanan
    """)
    
    stats = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    return jsonify(stats)

# API untuk mendapatkan data pesanan terbaru
@app.route('/api/recent_orders')
@admin_required
def get_recent_orders():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT p.*, COUNT(dp.id) as item_count
        FROM pesanan p
        LEFT JOIN detail_pesanan dp ON p.id = dp.pesanan_id
        GROUP BY p.id
        ORDER BY p.created_at DESC
        LIMIT 10
    """)
    
    orders = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify(orders)

@app.route('/admin/api/check_new_orders')
@admin_required
def check_new_orders():
    try:
        last_order_id = request.args.get('last_order_id', 0, type=int)
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Ambil pesanan yang lebih baru dari last_order_id
        cursor.execute("""
            SELECT 
                p.id,
                p.nama_pelanggan,
                p.total_harga,
                p.status,
                p.metode_pembayaran,
                p.created_at
            FROM pesanan p
            WHERE p.created_at > %s 
            AND p.nama_pelanggan IS NOT NULL 
            AND p.nama_pelanggan != ''
            ORDER BY p.id DESC
            LIMIT 10
        """, (last_order_id,))
        
        new_orders = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Format created_at agar bisa di-serialize
        for order in new_orders:
            if order['created_at'] and isinstance(order['created_at'], datetime):
                order['created_at'] = order['created_at'].isoformat()
        
        return jsonify({
            'status': 'success',
            'new_orders': new_orders,
            'count': len(new_orders)
        })
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)