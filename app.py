import os
import io
from datetime import datetime, timedelta
from flask import Flask, render_template, url_for, flash, redirect, request, jsonify, send_file, abort
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, current_user, logout_user, login_required
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER

# Monkeypatch for Flask 3.0+ compatibility with Flask-MongoEngine
import flask.json
try:
    from flask.json import JSONEncoder
except ImportError:
    import json
    class JSONEncoder(json.JSONEncoder):
        def default(self, obj):
            if hasattr(obj, '__json__'):
                return obj.__json__()
            return super().default(obj)
    flask.json.JSONEncoder = JSONEncoder
from models import db, User, StudentProfile, Course, Subject, Mark, Attendance, Assignment, Submission, Notice, Certificate, Job, JobApplication, Feedback, Grievance

app = Flask(__name__)
# Compatibility for Flask-MongoEngine and Flask 3.0
if not hasattr(app, 'json_encoder'):
    try:
        from flask.json import JSONEncoder
        app.json_encoder = JSONEncoder
    except ImportError:
        app.json_encoder = None

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', '5791628bb0b13ce0c676dfde280ba245')
app.config['MONGODB_SETTINGS'] = {
    'db': os.getenv('MONGO_DB', 'crms_db'),
    'host': os.getenv('MONGO_HOST', 'localhost'),
    'port': int(os.getenv('MONGO_PORT', '27017'))
}
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'images', 'profiles')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    try:
        print(f"DEBUG: [User Loader] Loading user_id: {user_id}")
        u = User.objects(id=int(user_id)).first()
        print(f"DEBUG: [User Loader] Result: {u.username if u else 'None'}")
        return u
    except Exception as e:
        print(f"DEBUG: [User Loader] ERROR: {e}")
        return None

@app.context_processor
def inject_now():
    return {'datetime': datetime}

# --- AUTH ROUTES ---
@app.route("/")
@app.route("/home")
def home():
    notices = Notice.objects.order_by('-created_at').limit(5)
    return render_template('home.html', notices=notices)

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        
        # Check if user already exists
        existing_user = User.objects(db.Q(email=email) | db.Q(username=username)).first()
        if existing_user:
            if existing_user.email == email:
                flash('Email already registered. Please use a different email or login.', 'danger')
            else:
                flash('Username already taken. Please choose another one.', 'danger')
            return redirect(url_for('register'))
            
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # Generate new integer ID
        max_user = User.objects.order_by('-id').first()
        new_user_id = (max_user.id + 1) if max_user else 1
        
        user = User(id=new_user_id, username=username, email=email, password=hashed_password, role=role)
        user.save()
        
        if role == 'student':
            max_profile = StudentProfile.objects.order_by('-id').first()
            new_profile_id = (max_profile.id + 1) if max_profile else 1
            profile = StudentProfile(id=new_profile_id, user_id=user.id, full_name=username, roll_no=f"STU{user.id:04d}")
            profile.save()
            
        flash('Account created! You can now login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.objects(email=email).first()
        print(f"DEBUG: [Login] Email: {email}, Found: {user.username if user else 'None'}")
        if user and bcrypt.check_password_hash(user.password, password):
            print(f"DEBUG: [Login] Password OK for {user.username}")
            login_user(user)
            print(f"DEBUG: [Login] login_user() done. current_user: {current_user.username if current_user.is_authenticated else 'Anon'}")
            flash(f'Welcome back, {user.username}!', 'success')
            next_page = request.args.get('next')
            print(f"DEBUG: [Login] Redirecting to: {next_page or 'dashboard'}")
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Login Unsuccessful. Please check your email and password.', 'danger')
    return render_template('login.html')

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('home'))

# --- DASHBOARD & MODULE ROUTES ---
@app.route("/dashboard")
@login_required
def dashboard():
    print(f"DEBUG: [Dashboard] Accessing as: {current_user.username} (Authenticated: {current_user.is_authenticated})")
    if current_user.role == 'admin':
        student_count = User.objects(role='student').count()
        course_count = Course.objects.count()
        jobs_count = Job.objects.count()
        apps_count = JobApplication.objects.count()
        
        # Real attendance rate
        all_att = Attendance.objects.all()
        present_att = sum(1 for a in all_att if a.status == 'Present')
        att_pct = round((present_att / len(all_att) * 100) if all_att else 0, 1)
        
        # Real pass/placement percentage
        all_marks = Mark.objects.all()
        pass_count = sum(1 for m in all_marks if m.status == 'Pass')
        pass_pct = round((pass_count / len(all_marks) * 100) if all_marks else 0, 1)
        placement_pct = round((JobApplication.objects(status='Selected').count() / student_count * 100) if student_count else 0, 1)
        
        # Pending task counts (REAL data)
        pending_grievances = Grievance.objects(status='Pending').count()
        pending_certs = Certificate.objects(is_verified=False).count()
        pending_apps = JobApplication.objects(status='Applied').count()
        
        # Course distribution for chart
        courses = Course.objects.all()
        course_labels = [c.name for c in courses]
        course_students = [len(c.students) for c in courses]
        
        # Subject-wise avg for performance chart
        subjects = Subject.objects.all()
        perf_labels = [s.name[:15] for s in subjects]
        perf_data = []
        sub_att_data = [] # New attendance data
        for sub in subjects:
            # Performance
            sub_marks = Mark.objects(subject_id=sub.id)
            avg = round(sum(m.total_marks for m in sub_marks) / len(sub_marks), 1) if sub_marks else 0
            perf_data.append(avg)
            # Attendance
            sub_atts = Attendance.objects(subject_id=sub.id)
            att_avg = round((sum(1 for a in sub_atts if a.status == 'Present') / len(sub_atts) * 100), 1) if sub_atts else 0
            sub_att_data.append(att_avg)
            
        # Weekly Attendance Trend (Last 7 Days)
        today = datetime.today().date()
        att_trend_labels = []
        att_trend_data = []
        for i in range(6, -1, -1):
            date = today - timedelta(days=i)
            att_trend_labels.append(date.strftime('%b %d'))
            day_atts = Attendance.objects(date=date)
            if day_atts:
                present = sum(1 for a in day_atts if a.status == 'Present')
                att_trend_data.append(round((present / len(day_atts) * 100), 1))
            else:
                att_trend_data.append(0)
        
        return render_template('admin_dashboard.html', 
            student_count=student_count,
            course_count=course_count,
            placement_pct=placement_pct,
            jobs_count=jobs_count,
            apps_count=apps_count,
            att_pct=att_pct,
            pass_pct=pass_pct,
            pending_grievances=pending_grievances,
            pending_certs=pending_certs,
            pending_apps=pending_apps,
            course_labels=course_labels,
            course_students=course_students,
            perf_labels=perf_labels,
            perf_data=perf_data,
            att_trend_labels=att_trend_labels,
            att_trend_data=att_trend_data,
            sub_att_data=sub_att_data
        )
    else:
        profile = StudentProfile.objects(user_id=current_user.id).first()
        notices = Notice.objects.order_by('-created_at').limit(5)
        
        # Live Stats Calculation
        marks = Mark.objects(student_id=current_user.id)
        attendances = Attendance.objects(student_id=current_user.id)
        
        # CGPA
        total_obtained = sum(m.total_marks for m in marks)
        total_max = len(marks) * 100 if marks else 0
        cgpa = (total_obtained / total_max * 10) if total_max > 0 else 0
        
        # Attendance %
        present_count = sum(1 for a in attendances if a.status == 'Present')
        att_pct = (present_count / len(attendances) * 100) if attendances else 0
        
        # Shortage Logic
        subjects = Subject.objects(course_id=profile.course_id)
        shortage_subjects = []
        for sub in subjects:
            sub_att = [a for a in attendances if a.subject_id == sub.id]
            s_present = sum(1 for a in sub_att if a.status == 'Present')
            s_total = len(sub_att)
            s_pct = (s_present / s_total * 100) if s_total > 0 else 0
            if s_pct < 75 and s_total > 0:
                shortage_subjects.append({'name': sub.name, 'pct': s_pct})

        # Weekly trend (last 6 unique dates)
        unique_dates = sorted(list(set(a.date for a in attendances)), reverse=True)[:6]
        unique_dates.reverse()
        weekly_stats = []
        for d in unique_dates:
            d_att = [a for a in attendances if a.date == d]
            d_present = sum(1 for a in d_att if a.status == 'Present')
            d_pct = (d_present / len(d_att) * 100) if d_att else 0
            weekly_stats.append({'date': d.strftime('%b %d'), 'pct': d_pct})
        
        # Certificates
        verified_certs = Certificate.objects(student_id=current_user.id, is_verified=True)
        
        # Applications
        applications = JobApplication.objects(student_id=current_user.id).order_by('-applied_at')
        
        return render_template('student_dashboard.html', 
                               profile=profile, 
                               notices=notices, 
                               marks=marks, 
                               cgpa=cgpa, 
                               att_pct=att_pct,
                               shortage_subjects=shortage_subjects,
                               weekly_stats=weekly_stats,
                               verified_certs=verified_certs,
                               applications=applications)

# --- MODULE 2: STUDENT PROFILE ---
@app.route("/profile/update", methods=['GET', 'POST'])
@login_required
def update_profile():
    if current_user.role != 'student':
        return redirect(url_for('dashboard'))
    profile = StudentProfile.objects(user_id=current_user.id).first()
    if request.method == 'POST':
        profile.full_name = request.form.get('full_name')
        profile.phone = request.form.get('phone')
        profile.address = request.form.get('address')
        
        # Handle Profile Photo Upload
        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"user_{current_user.id}_{file.filename}")
                file.save(os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], filename))
                current_user.profile_photo = os.path.join('profiles', filename).replace('\\', '/')
        
        profile.save()
        current_user.save()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('update_profile.html', profile=profile)

@app.route("/profile/change-password", methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not bcrypt.check_password_hash(current_user.password, old_password):
            flash('Current password incorrect', 'danger')
        elif new_password != confirm_password:
            flash('Passwords do not match', 'danger')
        else:
            hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            current_user.password = hashed_password
            current_user.save()
            flash('Password updated!', 'success')
            return redirect(url_for('dashboard'))
    return render_template('change_password.html')

@app.route("/profile/academic-history")
@login_required
def academic_history():
    if current_user.role != 'student':
        return redirect(url_for('dashboard'))
    marks = Mark.objects(student_id=current_user.id)
    attendances = Attendance.objects(student_id=current_user.id)
    # Group attendance by subject
    att_summary = {}
    for att in attendances:
        sub_name = att.subject.name
        if sub_name not in att_summary:
            att_summary[sub_name] = {'present': 0, 'total': 0}
        att_summary[sub_name]['total'] += 1
        if att.status == 'Present':
            att_summary[sub_name]['present'] += 1
            
    for sub in att_summary:
        att_summary[sub]['percent'] = (att_summary[sub]['present'] / att_summary[sub]['total']) * 100
        
    return render_template('academic_history.html', marks=marks, att_summary=att_summary)

# --- MODULE 3: COURSE & SUBJECT (ADMIN) ---
@app.route("/admin/courses", methods=['GET', 'POST'])
@login_required
def manage_courses():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name = request.form.get('name')
        desc = request.form.get('description')
        # Generate a new Int ID based on max existing ID (simulating auto-increment)
        max_id = Course.objects.order_by('-id').first()
        new_id = (max_id.id + 1) if max_id else 1
        course = Course(id=new_id, name=name, description=desc)
        course.save()
        flash('Course added!', 'success')
    courses = Course.objects.all()
    return render_template('manage_courses.html', courses=courses)

@app.route("/admin/course/edit/<int:course_id>", methods=['POST'])
@login_required
def edit_course(course_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    course = Course.objects(id=course_id).first()
    if not course: abort(404)
    course.name = request.form.get('name')
    course.description = request.form.get('description')
    course.save()
    flash('Course updated successfully!', 'success')
    return redirect(url_for('manage_courses'))

@app.route("/admin/course/delete/<int:course_id>", methods=['POST'])
@login_required
def delete_course(course_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    course = Course.objects(id=course_id).first()
    if not course: abort(404)
    # Check if course has subjects
    if course.subjects:
        flash('Cannot delete course with active subjects. Please remove subjects first.', 'danger')
    else:
        course.delete()
        flash('Course deleted!', 'warning')
    return redirect(url_for('manage_courses'))

@app.route("/admin/subjects", methods=['GET', 'POST'])
@login_required
def manage_subjects():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name = request.form.get('name')
        sem = int(request.form.get('semester'))
        course_id = int(request.form.get('course_id'))
        faculty = request.form.get('faculty')
        max_id = Subject.objects.order_by('-id').first()
        new_id = (max_id.id + 1) if max_id else 1
        subject = Subject(id=new_id, name=name, semester=sem, course_id=course_id, faculty_name=faculty)
        subject.save()
        flash('Subject added!', 'success')
    subjects = Subject.objects.all()
    courses = Course.objects.all()
    return render_template('manage_subjects.html', subjects=subjects, courses=courses)

@app.route("/admin/subject/edit/<int:subject_id>", methods=['POST'])
@login_required
def edit_subject(subject_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    subject = Subject.objects(id=subject_id).first()
    if not subject: abort(404)
    subject.name = request.form.get('name')
    subject.semester = int(request.form.get('semester'))
    subject.course_id = int(request.form.get('course_id'))
    subject.faculty_name = request.form.get('faculty')
    subject.save()
    flash('Subject updated successfully!', 'success')
    return redirect(url_for('manage_subjects'))

@app.route("/admin/subject/delete/<int:subject_id>", methods=['POST'])
@login_required
def delete_subject(subject_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    subject = Subject.objects(id=subject_id).first()
    if not subject: abort(404)
    subject.delete()
    flash('Subject removed!', 'warning')
    return redirect(url_for('manage_subjects'))

# --- MODULE 4: MARKS & RESULTS ---
@app.route("/marks/upload", methods=['GET', 'POST'])
@login_required
def upload_marks():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        stu_id = request.form.get('student_id')
        sub_id = request.form.get('subject_id')
        internal = float(request.form.get('internal'))
        semester = float(request.form.get('semester'))
        
        # Weighted Total: Internal (40%) + Semester (60%)
        # Here we assume internal is out of 100 or scale it. 
        # Requirement says Internal (40), Semester (60)
        total = internal + semester 
        status = 'Pass' if total >= 40 else 'Fail'
        
        # Calculate Grade
        if total >= 90: grade = 'A+'
        elif total >= 80: grade = 'A'
        elif total >= 70: grade = 'B'
        elif total >= 60: grade = 'C'
        elif total >= 50: grade = 'D'
        elif total >= 40: grade = 'E'
        else: grade = 'F'

        # Check for existing record
        existing_mark = Mark.objects(student_id=int(stu_id), subject_id=int(sub_id)).first()
        if existing_mark:
            existing_mark.internal_marks = internal
            existing_mark.semester_marks = semester
            existing_mark.total_marks = total
            existing_mark.status = status
            existing_mark.grade = grade
            existing_mark.save()
            flash('Marks updated successfully!', 'success')
        else:
            max_id = Mark.objects.order_by('-id').first()
            new_id = (max_id.id + 1) if max_id else 1
            mark = Mark(id=new_id, student_id=int(stu_id), subject_id=int(sub_id), 
                        internal_marks=internal, semester_marks=semester, 
                        total_marks=total, status=status, grade=grade)
            mark.save()
            flash('Marks uploaded successfully!', 'success')
            
    students = User.objects(role='student')
    subjects = Subject.objects.all()
    return render_template('upload_marks.html', students=students, subjects=subjects)

@app.route("/profile/results")
@login_required
def view_results():
    if current_user.role != 'student':
        return redirect(url_for('dashboard'))
    
    marks = Mark.objects(student_id=current_user.id)
    
    # Calculate CGPA
    total_obtained = sum(m.total_marks for m in marks)
    total_max = len(marks) * 100
    cgpa = (total_obtained / total_max * 10) if total_max > 0 else 0
    
    # Semester breakdown
    sem_results = {}
    for mark in marks:
        sem = mark.subject.semester
        if sem not in sem_results:
            sem_results[sem] = {'marks': [], 'total': 0, 'count': 0}
        sem_results[sem]['marks'].append(mark)
        sem_results[sem]['total'] += mark.total_marks
        sem_results[sem]['count'] += 1
    
    for sem in sem_results:
        sem_results[sem]['sgpa'] = (sem_results[sem]['total'] / (sem_results[sem]['count'] * 100)) * 10

    return render_template('student_results.html', marks=marks, cgpa=cgpa, sem_results=sem_results)

@app.route("/marks/report/<int:student_id>")
@login_required
def generate_report(student_id):
    if current_user.role != 'admin' and current_user.id != student_id:
        return redirect(url_for('dashboard'))
    
    student = User.objects(id=student_id).first()
    if not student: abort(404)
    marks = Mark.objects(student_id=student_id)
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], alignment=TA_CENTER, fontSize=24, spaceAfter=20, textColor=colors.indigo)
    header_style = ParagraphStyle('HeaderStyle', parent=styles['Normal'], alignment=TA_CENTER, fontSize=12, spaceAfter=10, textColor=colors.grey)
    table_header_style = ParagraphStyle('TableHeader', parent=styles['Normal'], fontSize=10, textColor=colors.whitesmoke, alignment=TA_CENTER)
    
    # Header Branding
    elements.append(Paragraph("CRMS ACADEMIC INSTITUTION", title_style))
    elements.append(Paragraph("Official Academic Performance Statement", header_style))
    elements.append(Spacer(1, 20))
    
    # Student Details Table
    student_data = [
        ["Student Name:", student.student_profile.full_name],
        ["Roll Number:", student.student_profile.roll_no],
        ["Academic Program:", student.student_profile.course.name if student.student_profile.course else "General"],
        ["Statement Date:", datetime.now().strftime('%B %d, %Y')]
    ]
    st_table = Table(student_data, colWidths=[120, 300])
    st_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('TEXTCOLOR', (0,0), (0,-1), colors.indigo),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    elements.append(st_table)
    elements.append(Spacer(1, 30))
    
    # Marks Table
    marks_data = [["CODE", "SUBJECT MODULE", "INTERNAL", "EXTERN", "TOTAL", "GRADE", "STATUS"]]
    total_obtained = 0
    total_max = 0
    passed_subjects = 0
    
    for mark in marks:
        row = [
            f"#{mark.subject_id}",
            mark.subject.name,
            str(mark.internal_marks),
            str(mark.semester_marks),
            str(mark.total_marks),
            mark.grade or "-",
            mark.status
        ]
        marks_data.append(row)
        total_obtained += mark.total_marks
        total_max += 100
        if mark.status == 'Pass': passed_subjects += 1
    
    marks_table = Table(marks_data, colWidths=[50, 180, 60, 60, 50, 50, 60])
    marks_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.indigo),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 1, colors.grey),
        ('FONTSIZE', (0,1), (-1,-1), 9),
        ('TEXTCOLOR', (0,1), (-1,-1), colors.black),
    ]))
    elements.append(marks_table)
    elements.append(Spacer(1, 40))
    
    # Performance Metrics
    cgpa = (total_obtained / total_max * 10) if total_max > 0 else 0
    summary_data = [
        ["CREDITS EARNED:", f"{passed_subjects} Modules"],
        ["AGGREGATE SCORE:", f"{total_obtained} / {total_max}"],
        ["CALCULATED CGPA:", f"{cgpa:.2f} / 10.0"]
    ]
    summary_table = Table(summary_data, colWidths=[150, 150])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0,0), (0,-1), colors.indigo),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('LINEBELOW', (0,-1), (-1,-1), 1, colors.indigo),
    ]))
    elements.append(summary_table)
    
    # Footer
    elements.append(Spacer(1, 60))
    elements.append(Paragraph("This is a computer-generated academic statement and does not require a physical signature.", header_style))
    
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f'results_{student.student_profile.roll_no}.pdf', mimetype='application/pdf')

# --- MODULE 5: ATTENDANCE ---
@app.route("/attendance/mark", methods=['GET', 'POST'])
@login_required
def mark_attendance():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    
    selected_subject_id = request.args.get('subject_id', type=int)
    students_to_mark = []
    
    if selected_subject_id:
        subject = Subject.objects(id=selected_subject_id).first()
        if not subject: abort(404)
        # Get students enrolled in the course that contains this subject
        student_ids = [sp.user_id for sp in StudentProfile.objects(course_id=subject.course_id)]
        students_to_mark = User.objects(id__in=student_ids)

    if request.method == 'POST':
        sub_id = request.form.get('subject_id')
        date_str = request.form.get('date')
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.today().date()
        
        # Process bulk attendance
        student_ids = request.form.getlist('student_ids')
        for stu_id in student_ids:
            status = request.form.get(f'status_{stu_id}')
            if status:
                # Check for existing entry to prevent duplicates
                existing = Attendance.objects(
                    student_id=int(stu_id), 
                    subject_id=int(sub_id), 
                    date=date_obj
                ).first()
                
                if existing:
                    existing.status = status
                    existing.save()
                else:
                    # Generic auto-id for Attendance
                    max_id = Attendance.objects.order_by('-id').first()
                    new_id = (max_id.id + 1) if max_id else 1
                    att = Attendance(id=new_id, student_id=int(stu_id), subject_id=int(sub_id), date=date_obj, status=status)
                    att.save()
        
        flash('Bulk attendance processed successfully!', 'success')
        return redirect(url_for('mark_attendance', subject_id=sub_id))
        
    subjects = Subject.objects.all()
    return render_template('mark_attendance.html', 
                           subjects=subjects, 
                           students_to_mark=students_to_mark,
                           selected_subject_id=selected_subject_id)

@app.route("/profile/attendance")
@login_required
def attendance_report():
    if current_user.role != 'student':
        return redirect(url_for('dashboard'))
    
    # Get all subjects in the student's course
    profile = StudentProfile.objects(user_id=current_user.id).first()
    if not profile or not profile.course:
        flash('Course enrollment not found. Please contact admin.', 'warning')
        return redirect(url_for('dashboard'))
        
    subjects = Subject.objects(course_id=profile.course_id)
    attendance_data = []
    total_present = 0
    total_sessions = 0
    shortage_subjects = []
    
    # Monthly trend calculation (last 6 months)
    # Simple mock-up for now based on actual data
    monthly_stats = {}
    
    for sub in subjects:
        # Attendance Logic
        sub_att = Attendance.objects(student_id=current_user.id, subject_id=sub.id)
        present = sum(1 for a in sub_att if a.status == 'Present')
        total = len(sub_att)
        pct = (present / total * 100) if total > 0 else 0
        
        # Shortage Logic (75% threshold)
        required_classes = 0
        if pct < 75:
            # Formula: (Present + x) / (Total + x) >= 0.75
            # Present + x >= 0.75 * Total + 0.75x
            # 0.25x >= 0.75 * Total - Present
            # x >= (0.75 * Total - Present) / 0.25
            if total > 0:
                required_classes = max(0, int((0.75 * total - present) / 0.25))
            else:
                required_classes = 0 # Can't determine yet
            shortage_subjects.append({'name': sub.name, 'pct': pct, 'required': required_classes})
            
        attendance_data.append({
            'subject': sub.name,
            'present': present,
            'absent': total - present,
            'total': total,
            'percentage': pct,
            'shortage': required_classes
        })
        
        total_present += present
        total_sessions += total
        
    overall_pct = (total_present / total_sessions * 100) if total_sessions > 0 else 0
    
    return render_template('attendance_report.html', 
                           attendance_data=attendance_data, 
                           overall_pct=overall_pct,
                           shortage_subjects=shortage_subjects)

# --- MODULE 6: ASSIGNMENTS ---
@app.route("/assignments/create", methods=['GET', 'POST'])
@login_required
def create_assignment():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        sub_id = request.form.get('subject_id')
        title = request.form.get('title')
        desc = request.form.get('description')
        deadline = datetime.strptime(request.form.get('deadline'), '%Y-%m-%dT%H:%M')
        
        file = request.files.get('file')
        file_path = None
        if file and file.filename != '':
            filename = secure_filename(f"assn_{sub_id}_{int(datetime.now().timestamp())}_{file.filename}")
            file_path = filename
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        # Generate ID
        max_id = Assignment.objects.order_by('-id').first()
        new_id = (max_id.id + 1) if max_id else 1
        assign = Assignment(id=new_id, subject_id=int(sub_id), title=title, description=desc, deadline=deadline, file_path=file_path)
        assign.save()
        flash('Assignment published successfully!', 'success')
        return redirect(url_for('manage_assignments'))
    subjects = Subject.objects.all()
    return render_template('create_assignment.html', subjects=subjects)

@app.route("/assignments/manage")
@login_required
def manage_assignments():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    assignments = Assignment.objects.order_by('-deadline')
    return render_template('manage_assignments.html', assignments=assignments)

@app.route("/profile/assignments")
@login_required
def view_assignments():
    if current_user.role != 'student':
        return redirect(url_for('dashboard'))
    profile = StudentProfile.objects(user_id=current_user.id).first()
    if not profile or not profile.course:
        flash('Course enrollment not found.', 'warning')
        return redirect(url_for('dashboard'))
    subjects = Subject.objects(course_id=profile.course_id)
    subject_ids = [s.id for s in subjects]
    assignments = Assignment.objects(subject_id__in=subject_ids).order_by('deadline')
    submissions = {s.assignment_id: s for s in Submission.objects(student_id=current_user.id)}
    return render_template('assignments.html', assignments=assignments, submissions=submissions)

@app.route("/assignments/submit/<int:assignment_id>", methods=['POST'])
@login_required
def submit_assignment(assignment_id):
    if current_user.role != 'student':
        return redirect(url_for('dashboard'))
    assignment = Assignment.objects(id=assignment_id).first()
    if not assignment: abort(404)
    if assignment.deadline < datetime.now():
        flash('Submission deadline has passed!', 'danger')
        return redirect(url_for('view_assignments'))
    file = request.files.get('file')
    if not file or file.filename == '' or not file.filename.lower().endswith('.pdf'):
        flash('Please upload a valid PDF file.', 'danger')
        return redirect(url_for('view_assignments'))
    existing = Submission.objects(assignment_id=assignment_id, student_id=current_user.id).first()
    filename = secure_filename(f"sub_{assignment_id}_{current_user.id}_{int(datetime.now().timestamp())}.pdf")
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    if existing:
        existing.file_path = filename
        existing.submitted_at = datetime.utcnow()
        existing.save()
    else:
        max_id = Submission.objects.order_by('-id').first()
        new_id = (max_id.id + 1) if max_id else 1
        new_sub = Submission(id=new_id, assignment_id=assignment_id, student_id=current_user.id, file_path=filename)
        new_sub.save()
    flash('Assignment submitted successfully!', 'success')
    return redirect(url_for('view_assignments'))

@app.route("/assignments/view-submissions/<int:assignment_id>")
@login_required
def view_submissions(assignment_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    assignment = Assignment.objects(id=assignment_id).first()
    if not assignment: abort(404)
    submissions = Submission.objects(assignment_id=assignment_id)
    return render_template('view_submissions.html', assignment=assignment, submissions=submissions)

@app.route("/assignments/grade/<int:submission_id>", methods=['POST'])
@login_required
def grade_submission(submission_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    submission = Submission.objects(id=submission_id).first()
    if not submission: abort(404)
    marks = request.form.get('marks')
    if marks:
        submission.marks_obtained = float(marks)
        submission.save()
        flash(f'Graded successfully!', 'success')
    return redirect(url_for('view_submissions', assignment_id=submission.assignment_id))

@app.route("/admin/assignment/edit/<int:assignment_id>", methods=['POST'])
@login_required
def edit_assignment(assignment_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    assignment = Assignment.objects(id=assignment_id).first()
    if not assignment: abort(404)
    assignment.title = request.form.get('title')
    assignment.description = request.form.get('description')
    deadline_str = request.form.get('deadline')
    if deadline_str:
        assignment.deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
    
    file = request.files.get('file')
    if file and file.filename != '':
        filename = secure_filename(f"assn_{assignment.subject_id}_{int(datetime.now().timestamp())}_{file.filename}")
        assignment.file_path = filename
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
    assignment.save()
    flash('Assignment updated successfully!', 'success')
    return redirect(url_for('manage_assignments'))

@app.route("/admin/assignment/delete/<int:assignment_id>", methods=['POST'])
@login_required
def delete_assignment(assignment_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    assignment = Assignment.objects(id=assignment_id).first()
    if not assignment: abort(404)
    assignment.delete()
    flash('Assignment deleted!', 'warning')
    return redirect(url_for('manage_assignments'))

# --- MODULE 7: NOTICES ---
@app.route("/admin/notices", methods=['GET', 'POST'])
@login_required
def manage_notices():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        category = request.form.get('category')
        max_id = Notice.objects.order_by('-id').first()
        new_id = (max_id.id + 1) if max_id else 1
        notice = Notice(id=new_id, title=title, content=content, category=category)
        notice.save()
        
        # Optional email notifications to all students
        try:
            from flask_mail import Message, Mail
            mail = Mail(app)
            students = User.objects(role='student')
            recipient_emails = [s.email for s in students if s.email]
            if recipient_emails:
                msg = Message(
                    subject=f"[CRMS Notice] {title}",
                    recipients=recipient_emails,
                    body=f"Category: {category}\n\n{content}\n\n---\nThis is an automated notification from CRMS Academic System."
                )
                mail.send(msg)
        except Exception:
            pass  # Email is optional; continue silently if not configured
        
        flash(f'Notice broadcast successfully to all students!', 'success')
        return redirect(url_for('manage_notices'))
    
    notices = Notice.objects.order_by('-created_at')
    return render_template('manage_notices.html', notices=notices)

@app.route("/admin/notices/delete/<int:notice_id>", methods=['POST'])
@login_required
def delete_notice(notice_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    notice = Notice.objects(id=notice_id).first()
    if not notice: abort(404)
    notice.delete()
    flash('Notice retracted.', 'info')
    return redirect(url_for('manage_notices'))

@app.route("/admin/notice/edit/<int:notice_id>", methods=['POST'])
@login_required
def edit_notice(notice_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    notice = Notice.objects(id=notice_id).first()
    if not notice: abort(404)
    notice.title = request.form.get('title')
    notice.content = request.form.get('content')
    notice.category = request.form.get('category')
    notice.save()
    flash('Notice updated successfully!', 'success')
    return redirect(url_for('manage_notices'))

@app.route("/notices")
def notices_list():
    category = request.args.get('cat', 'All')
    if category and category != 'All':
        notices = Notice.objects(category=category).order_by('-created_at')
    else:
        notices = Notice.objects.order_by('-created_at')
    return render_template('notices.html', notices=notices, active_cat=category)

@app.route("/api/notifications")
@login_required
def api_notifications():
    # Return latest 5 notices as JSON for the notification bell
    notices = Notice.objects.order_by('-created_at').limit(5)
    data = [{'id': n.id, 'title': n.title, 'category': n.category, 
             'date': n.created_at.strftime('%d %b')} for n in notices]
    return jsonify({'count': len(notices), 'notices': data})

# --- MODULE 8: CERTIFICATIONS ---
@app.route("/profile/certificates", methods=['GET', 'POST'])
@login_required
def my_certificates():
    if current_user.role != 'student':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        title = request.form.get('title')
        cert_type = request.form.get('cert_type', 'Achievement')
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('Please select a file to upload.', 'danger')
            return redirect(url_for('my_certificates'))
        ext = file.filename.rsplit('.', 1)[-1].lower()
        if ext not in ['pdf', 'jpg', 'jpeg', 'png']:
            flash('Only PDF, JPG or PNG files are accepted.', 'danger')
            return redirect(url_for('my_certificates'))
        filename = secure_filename(f"cert_{current_user.id}_{int(datetime.now().timestamp())}.{ext}")
        file.save(os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], filename))
        
        max_id = Certificate.objects.order_by('-id').first()
        new_id = (max_id.id + 1) if max_id else 1
        cert = Certificate(id=new_id, student_id=current_user.id, title=title, file_path=filename, cert_type=cert_type)
        cert.save()
        flash('Certificate submitted for verification!', 'success')
        return redirect(url_for('my_certificates'))
    certs = Certificate.objects(student_id=current_user.id).order_by('-uploaded_at')
    return render_template('my_certificates.html', certificates=certs)

@app.route("/admin/certificates")
@login_required
def admin_certificates():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    pending = Certificate.objects(is_verified=False).order_by('-uploaded_at')
    verified = Certificate.objects(is_verified=True).order_by('-uploaded_at')
    return render_template('admin_certificates.html', pending=pending, verified=verified)

@app.route("/admin/certificates/verify/<int:cert_id>", methods=['POST'])
@login_required
def verify_certificate(cert_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    cert = Certificate.objects(id=cert_id).first()
    if not cert: abort(404)
    action = request.form.get('action')
    if action == 'verify':
        cert.is_verified = True
        cert.save()
        flash(f'Certificate "{cert.title}" verified!', 'success')
    elif action == 'reject':
        cert.delete()
        flash('Certificate rejected and removed.', 'info')
    return redirect(url_for('admin_certificates'))

# --- MODULE 9: PLACEMENT ---
@app.route("/placement/jobs", methods=['GET', 'POST'])
@login_required
def manage_jobs():
    if request.method == 'POST' and current_user.role == 'admin':
        company = request.form.get('company')
        pos = request.form.get('position')
        loc = request.form.get('location')
        desc = request.form.get('description')
        req = request.form.get('requirements')
        i_date_str = request.form.get('interview_date')
        
        i_date = None
        if i_date_str:
            try:
                i_date = datetime.strptime(i_date_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                i_date = None
            
        max_id = Job.objects.order_by('-id').first()
        new_id = (max_id.id + 1) if max_id else 1
        job = Job(id=new_id, company_name=company, position=pos, location=loc, description=desc, requirements=req, interview_date=i_date)
        job.save()
        flash('Job posted successfully!', 'success')
        return redirect(url_for('manage_jobs'))
        
    jobs = Job.objects.order_by('-id')
    applied_job_ids = []
    if current_user.role == 'student':
        applied_job_ids = [a.job_id for a in JobApplication.objects(student_id=current_user.id)]
        
    return render_template('jobs.html', jobs=jobs, applied_job_ids=applied_job_ids)

@app.route("/admin/job/edit/<int:job_id>", methods=['POST'])
@login_required
def edit_job(job_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    job = Job.objects(id=job_id).first()
    if not job: abort(404)
    job.company_name = request.form.get('company')
    job.position = request.form.get('position')
    job.location = request.form.get('location')
    job.description = request.form.get('description')
    job.requirements = request.form.get('requirements')
    job.status = request.form.get('status')
    
    i_date_str = request.form.get('interview_date')
    if i_date_str:
        job.interview_date = datetime.strptime(i_date_str, '%Y-%m-%dT%H:%M')
        
    job.save()
    flash('Job details updated!', 'success')
    return redirect(url_for('manage_jobs'))

@app.route("/admin/job/delete/<int:job_id>", methods=['POST'])
@login_required
def delete_job(job_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    job = Job.objects(id=job_id).first()
    if not job: abort(404)
    job.delete()
    flash('Job posting deleted!', 'warning')
    return redirect(url_for('manage_jobs'))

@app.route("/placement/apply/<int:job_id>", methods=['POST'])
@login_required
def apply_job(job_id):
    if current_user.role != 'student':
        flash('Only students can apply for jobs.', 'danger')
        return redirect(url_for('dashboard'))
        
    existing = JobApplication.objects(job_id=job_id, student_id=current_user.id).first()
    if existing:
        flash('You have already applied for this position.', 'warning')
    else:
        max_id = JobApplication.objects.order_by('-id').first()
        new_id = (max_id.id + 1) if max_id else 1
        app_entry = JobApplication(id=new_id, job_id=job_id, student_id=current_user.id)
        app_entry.save()
        flash('Application submitted successfully!', 'success')
    return redirect(url_for('manage_jobs'))

@app.route("/admin/placement/applications/<int:job_id>")
@login_required
def view_job_applications(job_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    job = Job.objects(id=job_id).first()
    if not job: abort(404)
    applications = JobApplication.objects(job_id=job_id)
    return render_template('admin_applications.html', job=job, applications=applications)

@app.route("/admin/placement/update-status/<int:app_id>", methods=['POST'])
@login_required
def update_app_status(app_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    application = JobApplication.objects(id=app_id).first()
    if not application: abort(404)
    status = request.form.get('status')
    offer_status = request.form.get('offer_status')
    
    if status:
        application.status = status
    if offer_status:
        application.offer_status = offer_status
        
    application.save()
    flash('Application status updated!', 'success')
    return redirect(url_for('view_job_applications', job_id=application.job_id))

@app.route("/profile/my-applications")
@login_required
def student_applications():
    if current_user.role != 'student':
        return redirect(url_for('dashboard'))
    applications = JobApplication.objects(student_id=current_user.id).order_by('-applied_at')
    return render_template('student_applications.html', applications=applications)

# --- MODULE 12: ANALYTICS & REPORTS ---
@app.route("/admin/analytics")
@login_required
def admin_analytics():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    
    courses = Course.objects.all()
    all_students = User.objects(role='student')
    total_students = len(all_students)
    
    # Overall Pass / Fail counts
    all_marks = Mark.objects.all()
    pass_count = sum(1 for m in all_marks if m.status == 'Pass')
    fail_count = sum(1 for m in all_marks if m.status == 'Fail')
    pass_pct = round((pass_count / len(all_marks) * 100) if all_marks else 0, 1)
    
    # Toppers List (top 10 by average total_marks)
    topper_data = []
    for student in all_students:
        s_marks = Mark.objects(student_id=student.id)
        if s_marks:
            avg = round(sum(m.total_marks for m in s_marks) / len(s_marks), 1)
            cgpa = round(avg / 10, 2)
            profile = student.student_profile
            topper_data.append({
                'name': profile.full_name if profile else student.username,
                'roll_no': profile.roll_no if profile else 'N/A',
                'course': profile.course.name if profile and profile.course else 'N/A',
                'avg': avg,
                'cgpa': cgpa
            })
    toppers = sorted(topper_data, key=lambda x: x['avg'], reverse=True)[:10]
    
    # Course-wise analysis
    course_analysis = []
    for course in courses:
        c_students = [sp.user_id for sp in course.students]  # Adjusted for MongoEngine properties
        student_ids = [sp.id for sp in course.students] # In models.py id is user_id but check
        # Actually in models.py it's id and user_id. 
        # c_students = [sp.user for sp in course.students if sp.user]
        student_ids = [sp.user_id for sp in course.students]
        c_marks = Mark.objects(student_id__in=student_ids)
        c_pass = sum(1 for m in c_marks if m.status == 'Pass')
        c_fail = sum(1 for m in c_marks if m.status == 'Fail')
        c_total = len(c_marks)
        c_pass_pct = round((c_pass / c_total * 100) if c_total else 0, 1)
        c_avg = round(sum(m.total_marks for m in c_marks) / c_total if c_total else 0, 1)
        course_analysis.append({
            'name': course.name,
            'student_count': len(course.students),
            'pass_pct': c_pass_pct,
            'avg_marks': c_avg,
            'pass_count': c_pass,
            'fail_count': c_fail
        })
    
    # Subject-wise avg marks for chart
    subjects = Subject.objects.all()
    subject_chart = []
    for sub in subjects:
        sub_marks = Mark.objects(subject_id=sub.id)
        if sub_marks:
            sub_avg = round(sum(m.total_marks for m in sub_marks) / len(sub_marks), 1)
            subject_chart.append({'name': sub.name[:20], 'avg': sub_avg})
    
    # Overall Attendance %
    all_att = Attendance.objects.all()
    present_att = sum(1 for a in all_att if a.status == 'Present')
    overall_att_pct = round((present_att / len(all_att) * 100) if all_att else 0, 1)
    
    return render_template('admin_analytics.html',
        total_students=total_students,
        pass_pct=pass_pct,
        pass_count=pass_count,
        fail_count=fail_count,
        overall_att_pct=overall_att_pct,
        toppers=toppers,
        course_analysis=course_analysis,
        subject_chart=subject_chart,
        total_courses=len(courses)
    )

@app.route("/admin/analytics/download-report")
@login_required
def download_analytics_report():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # --- Header ---
    c.setFillColorRGB(0.13, 0.09, 0.27)
    c.rect(0, height - 80, width, 80, fill=True, stroke=False)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(40, height - 40, "CRMS - Analytics & Performance Report")
    c.setFont("Helvetica", 10)
    c.drawString(40, height - 58, f"Generated on: {datetime.now().strftime('%B %d, %Y at %H:%M')}")
    
    # --- Summary Stats ---
    y = height - 110
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Executive Summary")
    c.line(40, y - 5, width - 40, y - 5)
    
    all_marks = Mark.objects.all()
    pass_count = sum(1 for m in all_marks if m.status == 'Pass')
    fail_count = sum(1 for m in all_marks if m.status == 'Fail')
    pass_pct = round((pass_count / len(all_marks) * 100) if all_marks else 0, 1)
    total_students = User.objects(role='student').count()
    
    y -= 25
    c.setFont("Helvetica", 11)
    stats = [
        ("Total Students", str(total_students)),
        ("Total Courses", str(Course.objects.count())),
        ("Overall Pass Rate", f"{pass_pct}%"),
        ("Records Graded", str(len(all_marks))),
    ]
    for label, value in stats:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, f"{label}:")
        c.setFont("Helvetica", 11)
        c.drawString(200, y, value)
        y -= 20
    
    # --- Toppers List ---
    y -= 20
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Top Performers")
    c.line(40, y - 5, width - 40, y - 5)
    y -= 25
    
    all_students = User.objects(role='student')
    topper_data = []
    for student in all_students:
        s_marks = Mark.objects(student_id=student.id)
        if s_marks:
            avg = round(sum(m.total_marks for m in s_marks) / len(s_marks), 1)
            cgpa = round(avg / 10, 2)
            profile = student.student_profile
            topper_data.append({
                'name': profile.full_name if profile else student.username,
                'course': profile.course.name if profile and profile.course else 'N/A',
                'avg': avg,
                'cgpa': cgpa
            })
    toppers = sorted(topper_data, key=lambda x: x['avg'], reverse=True)[:10]
    
    c.setFont("Helvetica-Bold", 10)
    headers = ["Rank", "Student Name", "Course", "Avg Marks", "CGPA"]
    col_x = [40, 90, 270, 400, 470]
    for i, h in enumerate(headers):
        c.drawString(col_x[i], y, h)
    y -= 5
    c.line(40, y, width - 40, y)
    y -= 15
    c.setFont("Helvetica", 10)
    for rank, t in enumerate(toppers, 1):
        if y < 80:
            c.showPage()
            y = height - 60
        c.drawString(col_x[0], y, str(rank))
        c.drawString(col_x[1], y, t['name'][:25])
        c.drawString(col_x[2], y, t['course'][:18])
        c.drawString(col_x[3], y, str(t['avg']))
        c.drawString(col_x[4], y, str(t['cgpa']))
        y -= 18
    
    # --- Course-Wise Analysis ---
    if y < 120:
        c.showPage()
        y = height - 60
    y -= 20
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Course-Wise Analysis")
    c.line(40, y - 5, width - 40, y - 5)
    y -= 25
    
    courses = Course.objects.all()
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Course")
    c.drawString(220, y, "Students")
    c.drawString(300, y, "Pass Rate")
    c.drawString(390, y, "Avg Marks")
    y -= 5
    c.line(40, y, width - 40, y)
    y -= 15
    c.setFont("Helvetica", 10)
    for course in courses:
        student_ids = [sp.user_id for sp in course.students]
        c_marks = Mark.objects(student_id__in=student_ids)
        c_pass = sum(1 for m in c_marks if m.status == 'Pass')
        c_pct = round((c_pass / len(c_marks) * 100) if c_marks else 0, 1)
        c_avg = round(sum(m.total_marks for m in c_marks) / len(c_marks) if c_marks else 0, 1)
        
        if y < 80:
            c.showPage()
            y = height - 60
        c.drawString(40, y, course.name[:25])
        c.drawString(220, y, str(len(course.students)))
        c.drawString(300, y, f"{c_pct}%")
        c.drawString(390, y, str(c_avg))
        y -= 18
    
    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(40, 30, "CRMS - College Record Management System | Confidential Academic Report")
    
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"CRMS_Analytics_Report_{datetime.now().strftime('%Y%m%d')}.pdf", mimetype='application/pdf')

# --- MODULE 11: FEEDBACK & GRIEVANCE ---
@app.route("/feedback", methods=['GET', 'POST'])
@login_required
def submit_feedback():
    if request.method == 'POST':
        content = request.form.get('content')
        rating = int(request.form.get('rating'))
        max_id = Feedback.objects.order_by('-id').first()
        new_id = (max_id.id + 1) if max_id else 1
        fb = Feedback(id=new_id, student_id=current_user.id, content=content, rating=rating)
        fb.save()
        flash('Feedback submitted! Thank you for your input.', 'success')
        return redirect(url_for('submit_feedback'))
    feedbacks = Feedback.objects(student_id=current_user.id).order_by('-id')
    return render_template('feedback.html', feedbacks=feedbacks)

@app.route("/grievance", methods=['GET', 'POST'])
@login_required
def submit_grievance():
    if request.method == 'POST':
        subject = request.form.get('subject')
        desc = request.form.get('description')
        max_id = Grievance.objects.order_by('-id').first()
        new_id = (max_id.id + 1) if max_id else 1
        gr = Grievance(id=new_id, student_id=current_user.id, subject=subject, description=desc)
        gr.save()
        flash('Grievance submitted! Admin will respond soon.', 'success')
        return redirect(url_for('submit_grievance'))
    grievances = Grievance.objects(student_id=current_user.id).order_by('-created_at')
    return render_template('grievance.html', grievances=grievances)

@app.route("/admin/feedback")
@login_required
def admin_feedback():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    feedbacks = Feedback.objects.order_by('-id')
    total = len(feedbacks)
    avg_rating = round(sum(f.rating for f in feedbacks if f.rating) / total, 1) if total else 0
    rating_dist = {i: sum(1 for f in feedbacks if f.rating == i) for i in range(1, 6)}
    return render_template('admin_feedback.html', feedbacks=feedbacks, total=total, avg_rating=avg_rating, rating_dist=rating_dist)

@app.route("/admin/feedback/delete/<int:fb_id>", methods=['POST'])
@login_required
def delete_feedback(fb_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    fb = Feedback.objects(id=fb_id).first()
    if not fb: abort(404)
    fb.delete()
    flash('Feedback entry removed.', 'info')
    return redirect(url_for('admin_feedback'))

@app.route("/admin/grievances")
@login_required
def admin_grievances():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    pending = Grievance.objects(status='Pending').order_by('-created_at')
    resolved = Grievance.objects(status='Resolved').order_by('-created_at')
    return render_template('admin_grievances.html', pending=pending, resolved=resolved)

@app.route("/admin/grievances/respond/<int:gr_id>", methods=['POST'])
@login_required
def respond_grievance(gr_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    gr = Grievance.objects(id=gr_id).first()
    if not gr: abort(404)
    gr.admin_response = request.form.get('response')
    gr.status = request.form.get('status', 'Resolved')
    gr.save()
    flash('Response submitted successfully!', 'success')
    return redirect(url_for('admin_grievances'))

@app.route("/admin/grievance/delete/<int:gr_id>", methods=['POST'])
@login_required
def delete_grievance(gr_id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    gr = Grievance.objects(id=gr_id).first()
    if not gr: abort(404)
    gr.delete()
    flash('Grievance record deleted.', 'warning')
    return redirect(url_for('admin_grievances'))

# --- CREATE DB AND RUN ---
if __name__ == '__main__':
    with app.app_context():
        # MongoEngine doesn't use create_all()
        # Create a default admin if not exists
        if not User.objects(role='admin').first():
            admin = User(id=1, username='admin', email='admin@crms.com', password=bcrypt.generate_password_hash('admin123').decode('utf-8'), role='admin')
            admin.save()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')), debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')
