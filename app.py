from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from calendar import monthrange
import io
import pandas as pd
from flask import send_file
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from werkzeug.utils import secure_filename
import pandas as pd
from sqlalchemy.orm import joinedload  # เพิ่มด้านบน
from sqlalchemy.orm import relationship
from flask_migrate import Migrate



app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'a1b2c3randomstringxyz')

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    "DATABASE_URL",
    "postgresql://leave_user:r2gFAEfxP9e6NGFmgpyUS3uUdjagQwtv@dpg-d13p44q4d50c73e6ld40-a.singapore-postgres.render.com/leave_app_db_8p5d"
)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)




# --- Flask-Login Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# -------------------- Models --------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='staff')
    prefix = db.Column(db.String(20))  # 👈 เพิ่มคำนำหน้า เช่น นาย นางสาว
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    position = db.Column(db.String(100))  # 👈 เพิ่มตำแหน่ง เช่น ครู เจ้าหน้าที่
    department = db.Column(db.String(100))
    


class LeaveRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), db.ForeignKey('user.username'), nullable=False)
    leave_type = db.Column(db.String(20), nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    date = db.Column(db.Date, nullable=True)
    reason = db.Column(db.String(200), nullable=True)
    time_from = db.Column(db.String(10), nullable=True)
    time_to = db.Column(db.String(10), nullable=True)
    hours = db.Column(db.Float, nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='รออนุมัติ') 
    contact_info = db.Column(db.String(255), nullable=True)
    user = relationship('User', backref='leaves')
    approved_by = db.Column(db.String(80), nullable=True)  # username ของผู้อนุมัติ
    
class UserNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    filename = db.Column(db.String(255))
    filepath = db.Column(db.String(255))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="notes")


with app.app_context():
    db.create_all()

# --- Login Manager User Loader ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------- Routes --------------------

@app.route('/admin/download_user_template')
@login_required
def download_user_template():
    if current_user.role != 'admin':
        return "คุณไม่มีสิทธิ์เข้าถึง", 403

    # เตรียม DataFrame เปล่า
    columns = ['username', 'password', 'role', 'prefix', 'first_name', 'last_name', 'position', 'department']
    df = pd.DataFrame(columns=columns)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Users')

    output.seek(0)
    return send_file(output, download_name='user_template.xlsx', as_attachment=True)

@app.route('/admin/import_users', methods=['GET', 'POST'])
@login_required
def import_users():
    if current_user.role != 'admin':
        flash('เฉพาะแอดมินเท่านั้นที่เข้าถึงได้', 'error')
        return redirect(url_for('home'))

    if request.method == 'POST':
        file = request.files['excel_file']
        if file and file.filename.endswith('.xlsx'):
            try:
                df = pd.read_excel(file)

                expected_columns = ['username', 'password', 'prefix', 'first_name', 'last_name', 'position', 'department', 'role']
                if not all(col in df.columns for col in expected_columns):
                    flash('กรุณาตรวจสอบว่าหัวตารางครบถ้วนตามที่กำหนด', 'error')
                    return redirect(request.url)

                imported_count = 0
                for _, row in df.iterrows():
                    if User.query.filter_by(username=row['username']).first():
                        continue  # ข้าม username ซ้ำ

                    user = User(
                        username=row['username'],
                        password=generate_password_hash(str(row['password'])),  # เข้ารหัส
                        prefix=row['prefix'],
                        first_name=row['first_name'],
                        last_name=row['last_name'],
                        position=row['position'],
                        department=row['department'],
                        role=row['role']
                    )
                    db.session.add(user)
                    imported_count += 1

                db.session.commit()
                flash(f'นำเข้า {imported_count} ผู้ใช้สำเร็จ', 'success')
                return redirect(url_for('admin_dashboard'))

            except Exception as e:
                flash(f'เกิดข้อผิดพลาด: {str(e)}', 'error')
                return redirect(request.url)

        flash('กรุณาอัปโหลดเฉพาะไฟล์ .xlsx เท่านั้น', 'error')
    return render_template('upload_users.html')

@app.route('/print_leave_form/<int:leave_id>')
@login_required
def print_leave_form(leave_id):
    leave = LeaveRequest.query.get_or_404(leave_id)

    if current_user.role != 'admin' and current_user.username != leave.username:
        flash('คุณไม่มีสิทธิ์เข้าถึงใบลานี้', 'error')
        return redirect(url_for('report'))

    user = User.query.filter_by(username=leave.username).first()

    template_path = os.path.join('static', 'forms', 'leave_form_template.pdf')
    if not os.path.exists(template_path):
        return "ไม่พบไฟล์ฟอร์มใบลา กรุณาอัปโหลดไว้ใน static/forms/", 404

    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(595, 842))
    pdfmetrics.registerFont(TTFont('THSarabun', os.path.join('static', 'fonts', 'THSarabunNew.ttf')))
    c.setFont('THSarabun', 13)

    full_name = f"{user.prefix} {user.first_name} {user.last_name}"
    start_date = leave.date if leave.leave_type == 'ลาย่อย' else leave.start_date
    end_date = leave.date if leave.leave_type == 'ลาย่อย' else leave.end_date
    leave_days = leave.hours if leave.leave_type == 'ลาย่อย' else (
        (leave.end_date - leave.start_date).days + 1 if leave.start_date and leave.end_date else 1)

    # ✔ ดึงข้อมูลการลาครั้งก่อนหน้าประเภทเดียวกัน (ก่อนใบนี้)
    last_leave = LeaveRequest.query.filter(
        LeaveRequest.username == leave.username,
        LeaveRequest.leave_type == leave.leave_type,
        LeaveRequest.id != leave.id,
        LeaveRequest.status == 'อนุมัติ',
        LeaveRequest.submitted_at < leave.submitted_at
    ).order_by(LeaveRequest.submitted_at.desc()).first()

    # ✔ สรุปจำนวนวันลาครั้งก่อน (exclude ใบนี้)
    previous_leaves = LeaveRequest.query.filter(
        LeaveRequest.username == leave.username,
        LeaveRequest.leave_type == leave.leave_type,
        LeaveRequest.status == 'อนุมัติ',
        LeaveRequest.id != leave.id,
        LeaveRequest.submitted_at < leave.submitted_at
    ).all()

    total_before = 0
    for l in previous_leaves:
        if l.leave_type == 'ลาย่อย' and l.hours:
            total_before += l.hours
        elif l.start_date and l.end_date:
            total_before += (l.end_date - l.start_date).days + 1

    total_with_current = total_before + (leave_days or 0)
    
    approver = User.query.filter_by(username=leave.approved_by).first() if leave.approved_by else None
    approval_date = leave.submitted_at.strftime('%d/%m/%Y') if leave.status == 'อนุมัติ' else '-'
    
    if leave.status == 'อนุมัติ' and approver:
        approver_fullname = f"{approver.prefix or ''}{approver.first_name} {approver.last_name}"
        approver_position = approver.position or '-'
    else:
        approver_fullname = '-'
        approver_position = '-'

    # 🎯 ใส่ลงในตำแหน่งที่ต้องการบนฟอร์ม
    c.drawString(275, 166, approver_fullname)     # ตำแหน่ง: ชื่อผู้อนุมัติ
    c.drawString(290, 127, approver_position)     # ตำแหน่ง: ตำแหน่งผู้อนุมัติ
    c.drawString(277, 90, approval_date)         # ตำแหน่ง: วันที่อนุมัติ

    # 🖨 วาดข้อความลงฟอร์ม
    c.drawString(388.67, 705.71, leave.submitted_at.strftime('%d/%m/%Y'))
    c.drawString(145, 614, full_name)
    c.drawString(270.99, 613.90, user.position)
    c.drawString(96, 562, leave.leave_type)
    c.drawString(110, 527, leave.leave_type)
    c.drawString(175.20, 562, leave.reason or "-")
    c.drawString(110.62, 543.47, start_date.strftime('%d/%m/%Y'))
    c.drawString(203.35, 543.47, end_date.strftime('%d/%m/%Y'))
    c.drawString(300.46, 543.47, f"{leave_days:.1f}" if leave.leave_type == 'ลาย่อย' else str(int(leave_days)))

    # ✅ ติดต่อได้ที่
    c.drawString(204.95, 508.28, leave.contact_info or "-")

    # ✅ การลาครั้งก่อน (วันที่ - จำนวนวัน)
    if last_leave:
        prev_start = last_leave.date if last_leave.leave_type == 'ลาย่อย' else last_leave.start_date
        prev_end = last_leave.date if last_leave.leave_type == 'ลาย่อย' else last_leave.end_date
        prev_days = last_leave.hours if last_leave.leave_type == 'ลาย่อย' else (
            (last_leave.end_date - last_leave.start_date).days + 1 if last_leave.start_date and last_leave.end_date else 1)

        c.drawString(192.64, 527.08, prev_start.strftime('%d/%m/%Y'))
        c.drawString(280.96, 527.08, prev_end.strftime('%d/%m/%Y'))
        c.drawString(385.74, 527.08, f"{prev_days:.1f}" if last_leave.leave_type == 'ลาย่อย' else str(int(prev_days)))
    else:
        c.drawString(230.64, 527.08, "-")
        c.drawString(315.96, 527.08, "-")
        c.drawString(400.74, 527.08, "-")

    # ✅ สรุปสถิติ
    if leave.leave_type == 'ลาป่วย':
        c.drawString(175, 330, str(int(total_before)))
        c.drawString(237, 330, str(int(leave_days)))
        c.drawString(300, 330, str(int(total_with_current)))
    elif leave.leave_type == 'ลากิจ':
        c.drawString(175, 300, str(int(total_before)))
        c.drawString(237, 300, str(int(leave_days)))
        c.drawString(300, 300, str(int(total_with_current)))
    elif leave.leave_type == 'ลาย่อย':
        c.drawString(285, 463, f"{total_before:.1f}")
        c.drawString(340, 463, f"{leave_days:.1f}")
        c.drawString(400, 463, f"{total_with_current:.1f}")

    # ✅ ลายเซ็นและสถานะ
    c.drawString(396.21, 473.22, user.first_name)
    c.drawString(380, 452.89, full_name)
    c.drawString(405.61, 434.95, user.position)

    if leave.status == 'อนุมัติ':
        c.drawString(377.02, 342.18, "X")

    c.save()

    # รวมกับเทมเพลต
    packet.seek(0)
    overlay = PdfReader(packet)
    template = PdfReader(template_path)
    writer = PdfWriter()
    page = template.pages[0]
    page.merge_page(overlay.pages[0])
    writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)

    return send_file(output, download_name=f"ใบลาของ_{user.first_name}.pdf", as_attachment=True)



@app.route('/')
@login_required
def home():
    username = current_user.username

    # ดึงใบลาล่าสุด
    latest_leave = LeaveRequest.query.filter_by(username=username).order_by(LeaveRequest.submitted_at.desc()).first()

    # นับใบลาที่อนุมัติ (status ที่มีคำว่า 'อนุมัติ')
    approved_count = LeaveRequest.query.filter(
        LeaveRequest.username == username,
        LeaveRequest.status.like('%อนุมัติ%')
    ).count()

    # ดึงใบลาที่รออนุมัติ
    pending_leaves = LeaveRequest.query.filter_by(username=username, status='รออนุมัติ').all()

    # ดึงใบลาล่าสุด (limit 5 ใบ)
    leaves = LeaveRequest.query.filter_by(username=username).order_by(LeaveRequest.submitted_at.desc()).limit(5).all()

    return render_template('home.html',
                           latest_leave=latest_leave,
                           approved_count=approved_count,
                           pending_leaves=pending_leaves,
                           leaves=leaves)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']
        user = User.query.filter_by(username=u).first()
        if user and check_password_hash(user.password, p):
            login_user(user)
            session['username'] = user.username
            session['role'] = user.role
            flash("เข้าสู่ระบบสำเร็จ")
            return redirect(url_for('home'))
        flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    return render_template('login.html')

@app.route('/user/<int:user_id>/upload_note', methods=['POST'])
@login_required
def upload_user_note(user_id):
    if current_user.role != 'admin':
        abort(403)
    user = User.query.get_or_404(user_id)
    file = request.files['file']
    if file:
        filename = secure_filename(file.filename)
        folder = os.path.join('static/uploads/notes', str(user.id))
        os.makedirs(folder, exist_ok=True)
        filepath = os.path.join(folder, filename)
        file.save(filepath)
        note = UserNote(user_id=user.id, filename=filename, filepath=f'uploads/notes/{user.id}/{filename}')
        db.session.add(note)
        db.session.commit()
        flash('เพิ่มบันทึกเรียบร้อยแล้ว', 'success')
    return redirect(url_for('view_user_leaves', user_id=user.id))

@app.route('/delete_note/<int:note_id>', methods=['POST'])
@login_required
def delete_user_note(note_id):
    note = UserNote.query.get_or_404(note_id)
    if current_user.role != 'admin':
        abort(403)
    try:
        os.remove(os.path.join('static', note.filepath))
    except:
        pass
    db.session.delete(note)
    db.session.commit()
    flash('ลบบันทึกเรียบร้อยแล้ว', 'success')
    return redirect(url_for('view_user_leaves', user_id=note.user_id))


@app.route('/export_user_leaves/<int:user_id>')
@login_required
def export_user_leaves(user_id):
    start_month = request.args.get('start_month')
    end_month = request.args.get('end_month')
    
    user = User.query.get_or_404(user_id)
    
    query = LeaveRequest.query.filter_by(username=user.username)

    if start_month:
        start_date = datetime.strptime(start_month, "%Y-%m")
        query = query.filter(
            (LeaveRequest.date >= start_date) | 
            (LeaveRequest.start_date >= start_date)
        )
    if end_month:
        end_date = datetime.strptime(end_month, "%Y-%m")
        last_day = monthrange(end_date.year, end_date.month)[1]
        end_date = end_date.replace(day=last_day)
        query = query.filter(
            (LeaveRequest.date <= end_date) | 
            (LeaveRequest.end_date <= end_date)
        )

    leaves = query.order_by(LeaveRequest.submitted_at.desc()).all()

    data = []
    for leave in leaves:
        if leave.leave_type == 'ลาย่อย':
            leave_days = 1 if leave.date else 0
        elif leave.start_date and leave.end_date:
            leave_days = (leave.end_date - leave.start_date).days + 1
        else:
            leave_days = 0

        if leave.reason and 'รออนุมัติ' in leave.reason:
            status = 'รออนุมัติ'
        else:
            status = 'อนุมัติแล้ว'

        data.append({
            "ชื่อ-นามสกุล": f"{user.first_name} {user.last_name}",
            "ประเภทการลา": leave.leave_type,
            "วันที่ลา": leave.date.strftime('%d/%m/%Y') if leave.leave_type == 'ลาย่อย' and leave.date else (
                f"{leave.start_date.strftime('%d/%m/%Y')} - {leave.end_date.strftime('%d/%m/%Y')}"
                if leave.start_date and leave.end_date else '-'),
            "จำนวนวันลา": leave_days if leave.leave_type in ['ลาป่วย', 'ลากิจ'] else '',
            "จำนวนชั่วโมง": leave.hours if leave.leave_type == 'ลาย่อย' else '',
            "เวลา (จาก-ถึง)": f"{leave.time_from} - {leave.time_to}" if leave.leave_type == 'ลาย่อย' else '',
            "เหตุผล": leave.reason,
            "สถานะ": status,
            "วันที่ส่งใบลา": leave.submitted_at.strftime('%d/%m/%Y %H:%M') if leave.submitted_at else '-',
        })

    df = pd.DataFrame(data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Leaves')

    output.seek(0)
    filename = f"leave_report_{user.first_name}_{user.last_name}.xlsx"
    return send_file(output, download_name=filename, as_attachment=True)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash("ออกจากระบบเรียบร้อยแล้ว")
    return redirect(url_for('login'))

@app.route('/admin/leaves')
@login_required
def admin_leaves():
    if current_user.role != 'admin':
        return "คุณไม่มีสิทธิ์เข้าถึงหน้านี้", 403

    page = request.args.get('page', 1, type=int)
    per_page = 20  # ✅ แสดง 20 รายการต่อหน้า

    query = LeaveRequest.query.join(User, LeaveRequest.username == User.username)

    if current_user.position not in ['ผู้อำนวยการ', 'ผู้รับใบอนุญาต', 'ผู้จัดการทั่วไป']:
        query = query.filter(User.department == current_user.department)

    query = query.order_by(LeaveRequest.submitted_at.desc())

    pagination = query.paginate(page=page, per_page=per_page)
    leaves = pagination.items

    return render_template('admin_leaves.html', leaves=leaves, pagination=pagination)


@app.route('/admin/leaves/<int:leave_id>/approve', methods=['POST'])
@login_required
def approve_leave(leave_id):
    leave = LeaveRequest.query.get_or_404(leave_id)
    user = User.query.filter_by(username=leave.username).first()

    if current_user.role != 'admin':
        return "คุณไม่มีสิทธิ์เข้าถึงหน้านี้", 403

    if current_user.position not in ['ผู้อำนวยการ', 'ผู้รับใบอนุญาต', 'ผู้จัดการทั่วไป'] and user.department != current_user.department:
        flash("คุณสามารถอนุมัติได้เฉพาะใบลาของแผนกเดียวกันเท่านั้น")
        return redirect(url_for('admin_leaves'))

    leave.status = 'อนุมัติ'
    leave.approved_by = current_user.username  # บันทึกผู้ที่อนุมัติจริง
    db.session.commit()
    flash("อนุมัติใบลาเรียบร้อยแล้ว")
    return redirect(url_for('admin_leaves'))


@app.route('/admin/leaves/<int:leave_id>/reject', methods=['POST'])
@login_required
def reject_leave(leave_id):
    if current_user.role != 'admin':
        return "คุณไม่มีสิทธิ์เข้าถึงหน้านี้", 403
    leave = LeaveRequest.query.get_or_404(leave_id)
    leave.status = 'ไม่อนุมัติ'
    db.session.commit()
    flash("ไม่อนุมัติใบลาเรียบร้อยแล้ว")
    return redirect(url_for('admin_leaves'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']
        role = request.form.get('role', 'staff')
        if User.query.filter_by(username=u).first():
            flash("มีชื่อผู้ใช้นี้แล้ว")
            return redirect(url_for('register'))
        hashed_pw = generate_password_hash(p)
        new_user = User(username=u, password=hashed_pw, role=role)
        db.session.add(new_user)
        db.session.commit()
        flash("สมัครสมาชิกสำเร็จ! กรุณาเข้าสู่ระบบ")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = current_user
    if request.method == 'POST':
        user.first_name = request.form['first_name']
        user.last_name = request.form['last_name']
        user.department = request.form['department']
        user.prefix = request.form['prefix']
        user.position = request.form['position']
        db.session.commit()
        flash("บันทึกข้อมูลส่วนตัวเรียบร้อยแล้ว")
        return redirect(url_for('profile'))
    return render_template('profile.html', user=user)

@app.route('/leave', methods=['GET', 'POST'])
@login_required
def leave():
    if request.method == 'POST':
        leave_type = request.form['leave_type']
        reason = request.form['reason']
        contact_info = request.form.get('contact_info')  # ✅ รับค่าจากฟอร์ม
        time_from = request.form.get('time_from')
        time_to = request.form.get('time_to')
        hours = request.form.get('hours')

        if leave_type == 'ลาย่อย':
            date_str = request.form.get('date')
            date_val = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
            leave = LeaveRequest(
                username=current_user.username,
                leave_type=leave_type,
                date=date_val,
                reason=reason,
                contact_info=contact_info,
                time_from=time_from,
                time_to=time_to,
                hours=float(hours) if hours else None
            )
        else:
            start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
            leave = LeaveRequest(
                username=current_user.username,
                leave_type=leave_type,
                start_date=start_date,
                end_date=end_date,
                reason=reason,
                contact_info=contact_info,
                hours=((end_date - start_date).days + 1)
            )

        db.session.add(leave)
        db.session.commit()
        flash("ส่งคำขอลาเรียบร้อยแล้ว")
        return redirect(url_for('home'))

    return render_template('leave_form.html')


@app.route('/leave/edit/<int:leave_id>', methods=['GET', 'POST'])
@login_required
def edit_leave(leave_id):
    leave = LeaveRequest.query.get_or_404(leave_id)
    if leave.username != current_user.username or leave.status != 'รออนุมัติ':
        flash("ไม่สามารถแก้ไขใบลานี้ได้", "error")
        return redirect(url_for('home'))

    if request.method == 'POST':
        leave.leave_type = request.form['leave_type']
        leave.reason = request.form['reason']
        leave.contact_info = request.form.get('contact_info')

        if leave.leave_type == 'ลาย่อย':
            leave.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            leave.time_from = request.form.get('time_from')
            leave.time_to = request.form.get('time_to')
            leave.hours = float(request.form.get('hours') or 0)
            leave.start_date = None
            leave.end_date = None
        else:
            leave.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
            leave.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
            leave.date = None
            leave.hours = (leave.end_date - leave.start_date).days + 1
            leave.time_from = None
            leave.time_to = None

        db.session.commit()
        flash("แก้ไขใบลาเรียบร้อยแล้ว")
        return redirect(url_for('home'))

    return render_template('edit_leave_form.html', leave=leave)

@app.route('/leave/cancel/<int:leave_id>', methods=['POST'])
@login_required
def cancel_leave(leave_id):
    leave = LeaveRequest.query.get_or_404(leave_id)
    if leave.username != current_user.username or leave.status != 'รออนุมัติ':
        flash("ไม่สามารถยกเลิกใบลานี้ได้", "error")
        return redirect(url_for('home'))

    db.session.delete(leave)
    db.session.commit()
    flash("ยกเลิกใบลาเรียบร้อยแล้ว")
    return redirect(url_for('home'))

@app.route('/admin/delete_leave/<int:leave_id>', methods=['POST'])
@login_required
def delete_leave(leave_id):
    if current_user.role != 'admin':
        flash("คุณไม่มีสิทธิ์ลบใบลา", "error")
        return redirect(url_for('admin_dashboard'))

    leave = LeaveRequest.query.get_or_404(leave_id)
    db.session.delete(leave)
    db.session.commit()
    flash("ลบใบลาเรียบร้อยแล้ว", "success")
    
    # 👉 redirect กลับไปยังหน้าประวัติของ user คนเดิม
    user = User.query.filter_by(username=leave.username).first()
    return redirect(url_for('view_user_leaves', user_id=user.id))

@app.route('/report')
@login_required
def report():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # กรองใบลาเฉพาะของ user ที่ล็อกอินอยู่เสมอ
    query = LeaveRequest.query.filter_by(username=current_user.username)

    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            query = query.filter(
                ((LeaveRequest.date >= start_date) & (LeaveRequest.date <= end_date)) |
                ((LeaveRequest.start_date <= end_date) & (LeaveRequest.end_date >= start_date))
            )
        except ValueError:
            flash("รูปแบบวันที่ไม่ถูกต้อง", "error")

    leaves = query.order_by(LeaveRequest.submitted_at.desc()).all()

    # สรุปเฉพาะใบที่อนุมัติ
    summary = {'ลากิจ': 0, 'ลาป่วย': 0, 'ลาย่อย': 0.0}
    for leave in leaves:
        if leave.leave_type == 'ลาย่อย' and leave.date:
            leave.leave_days = 1
        elif leave.start_date and leave.end_date:
            leave.leave_days = (leave.end_date - leave.start_date).days + 1
        else:
            leave.leave_days = 0

        if leave.status == 'อนุมัติ':
            if leave.leave_type == 'ลาย่อย':
                summary['ลาย่อย'] += leave.hours or 0
            else:
                summary[leave.leave_type] += leave.leave_days

    # ดึง note ของ user ปัจจุบัน ไม่ว่าจะ role อะไร ก็เห็นของตัวเอง
    notes = UserNote.query.filter_by(user_id=current_user.id).order_by(UserNote.uploaded_at.desc()).all()

    return render_template(
        'report.html',
        leaves=leaves,
        summary=summary,
        start_date=start_date_str,
        end_date=end_date_str,
        notes=notes
    )







@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return "คุณไม่มีสิทธิ์เข้าถึงหน้านี้", 403

    users = User.query.all()

    # ✅ คำนวณจำนวนใบลารออนุมัติ เฉพาะในแผนกเดียวกัน (ยกเว้น ผู้อำนวยการ/ผู้รับใบอนุญาต เห็นทั้งหมด)
    if current_user.position in ['ผู้อำนวยการ', 'ผู้รับใบอนุญาต']:
        pending_count = LeaveRequest.query.filter_by(status='รออนุมัติ').count()
    else:
        pending_count = LeaveRequest.query.join(User, LeaveRequest.username == User.username) \
            .filter(LeaveRequest.status == 'รออนุมัติ') \
            .filter(User.department == current_user.department) \
            .count()

    return render_template('admin.html', users=users, pending_count=pending_count)



@app.route('/admin/search')
@login_required
def admin_search():
    query = request.args.get('q', '')
    users = User.query.filter(User.first_name.contains(query) | User.last_name.contains(query)).all()
    return render_template('admin.html', users=users)

@app.route('/change_password/<int:user_id>', methods=['POST'])
@login_required
def change_password(user_id):
    if current_user.role != 'admin':
        return "คุณไม่มีสิทธิ์เข้าถึงหน้านี้", 403
    user = User.query.get(user_id)
    if not user:
        flash("ไม่พบผู้ใช้ที่ต้องการ")
        return redirect(url_for('admin_dashboard'))
    new_password = request.form.get('new_password')
    if not new_password or len(new_password) < 4:
        flash("กรุณาระบุรหัสผ่านใหม่อย่างน้อย 4 ตัวอักษร")
        return redirect(url_for('admin_dashboard'))
    user.password = generate_password_hash(new_password)
    db.session.commit()
    flash(f"เปลี่ยนรหัสผ่านของ {user.username} เรียบร้อยแล้ว")
    return redirect(url_for('admin_dashboard'))

@app.route('/change_password_self', methods=['GET', 'POST'])
@login_required
def change_password_self():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not check_password_hash(current_user.password, current_password):
            flash('รหัสผ่านเดิมไม่ถูกต้อง', 'danger')
            return redirect(url_for('change_password_self'))

        if new_password != confirm_password:
            flash('รหัสผ่านใหม่ไม่ตรงกัน', 'danger')
            return redirect(url_for('change_password_self'))

        if len(new_password) < 4:
            flash('รหัสผ่านใหม่ต้องมีอย่างน้อย 4 ตัวอักษร', 'danger')
            return redirect(url_for('change_password_self'))

        current_user.password = generate_password_hash(new_password)
        db.session.commit()

        flash('เปลี่ยนรหัสผ่านเรียบร้อยแล้ว', 'success')
        return redirect(url_for('profile'))

    return render_template('change_password_self.html')


@app.route('/change_role/<int:user_id>', methods=['POST'])
@login_required
def change_role(user_id):
    if current_user.role != 'admin':
        return "คุณไม่มีสิทธิ์เข้าถึงหน้านี้", 403
    user = User.query.get(user_id)
    if user:
        new_role = request.form.get('role')
        if new_role in ['staff', 'admin']:
            user.role = new_role
            db.session.commit()
            flash(f"เปลี่ยนบทบาทของ {user.username} เป็น {new_role} เรียบร้อยแล้ว")
        else:
            flash("บทบาทที่ระบุไม่ถูกต้อง")
    else:
        flash("ไม่พบผู้ใช้ที่ต้องการ")
    return redirect(url_for('admin_dashboard'))

@app.context_processor
def inject_pending_count():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            # ✅ ผู้อำนวยการ หรือ ผู้รับใบอนุญาต เห็นทุกแผนก
            if current_user.position in ['ผู้อำนวยการ', 'ผู้รับใบอนุญาต']:
                count = LeaveRequest.query.filter_by(status='รออนุมัติ').count()
            else:
                # ✅ เห็นเฉพาะใบลาของแผนกตัวเอง
                count = LeaveRequest.query.join(User, LeaveRequest.username == User.username) \
                    .filter(LeaveRequest.status == 'รออนุมัติ') \
                    .filter(User.department == current_user.department) \
                    .count()
            return dict(pending_count=count)
    return dict(pending_count=0)


@app.route('/user/<int:user_id>/leaves')
@login_required
def view_user_leaves(user_id):
    if current_user.role != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'error')
        return redirect(url_for('home'))

    user = User.query.get_or_404(user_id)

    start_month = request.args.get('start_month')
    end_month = request.args.get('end_month')

    query = LeaveRequest.query.filter_by(username=user.username)

    if start_month and end_month:
        try:
            start_date = datetime.strptime(start_month, '%Y-%m').date()
            end_dt = datetime.strptime(end_month, '%Y-%m')
            last_day = monthrange(end_dt.year, end_dt.month)[1]
            end_date = date(end_dt.year, end_dt.month, last_day)

            query = query.filter(
                (
                    (LeaveRequest.date >= start_date) & (LeaveRequest.date <= end_date)
                ) | (
                    (LeaveRequest.start_date <= end_date) & (LeaveRequest.end_date >= start_date)
                )
            )
        except ValueError:
            flash('รูปแบบเดือนไม่ถูกต้อง', 'error')

    leaves = query.order_by(LeaveRequest.submitted_at.desc()).all()

    summary = {'ลาป่วย': 0, 'ลากิจ': 0, 'ลาย่อย': 0.0}

    for leave in leaves:
        # กำหนดจำนวนวันให้ใช้แสดงในตาราง
        if leave.leave_type == 'ลาย่อย' and leave.date:
            leave.days = 1
        elif leave.start_date and leave.end_date:
            leave.days = (leave.end_date - leave.start_date).days + 1
        else:
            leave.days = 0

        # ✅ สรุปเฉพาะใบที่อนุมัติเท่านั้น
        if leave.status == 'อนุมัติ':
            if leave.leave_type == 'ลาย่อย':
                summary['ลาย่อย'] += leave.hours or 0
            else:
                summary[leave.leave_type] += leave.days

        # ✅ กำหนดสถานะ fallback เผื่อไม่ได้ระบุ
        if leave.status not in ['อนุมัติ', 'ไม่อนุมัติ']:
            leave.status = 'รออนุมัติ'

    return render_template('view_user_leaves.html', user=user, leaves=leaves, summary=summary)




@app.context_processor
def inject_user():
    if current_user.is_authenticated:
        return dict(current_user=current_user)
    return dict(current_user=None)

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))  # Render จะให้ค่า PORT อัตโนมัติ
    app.run(host='0.0.0.0', port=port)
