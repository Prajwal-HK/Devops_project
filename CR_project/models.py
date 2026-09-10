from datetime import datetime
from flask_mongoengine import MongoEngine
from flask_login import UserMixin

db = MongoEngine()

class User(db.Document, UserMixin):
    id = db.IntField(primary_key=True)
    username = db.StringField(max_length=20, unique=True, required=True)
    email = db.StringField(max_length=120, unique=True, required=True)
    password = db.StringField(max_length=128, required=True)
    role = db.StringField(max_length=20, required=True)
    profile_photo = db.StringField(max_length=100, default='default.jpg')
    otp = db.StringField(max_length=6)
    
    meta = {'collection': 'users'}

    @property
    def student_profile(self):
        return StudentProfile.objects(user_id=self.id).first()

    @property
    def attendances(self):
        return Attendance.objects(student_id=self.id)

    @property
    def marks(self):
        return Mark.objects(student_id=self.id)

    @property
    def submissions(self):
        return Submission.objects(student_id=self.id)

    @property
    def certificates(self):
        return Certificate.objects(student_id=self.id)

    @property
    def job_applications(self):
        return JobApplication.objects(student_id=self.id)

    @property
    def feedbacks(self):
        return Feedback.objects(student_id=self.id)

    @property
    def complaints(self):
        return Grievance.objects(student_id=self.id)

class StudentProfile(db.Document):
    id = db.IntField(primary_key=True)
    user_id = db.IntField(required=True)
    full_name = db.StringField(max_length=100, required=True)
    roll_no = db.StringField(max_length=20, unique=True, required=True)
    phone = db.StringField(max_length=15)
    address = db.StringField()
    academic_history = db.StringField()
    course_id = db.IntField()

    meta = {'collection': 'profiles'}

    @property
    def user(self):
        return User.objects(id=self.user_id).first()

    @property
    def course(self):
        return Course.objects(id=self.course_id).first()

class Course(db.Document):
    id = db.IntField(primary_key=True)
    name = db.StringField(max_length=100, unique=True, required=True)
    description = db.StringField()

    meta = {'collection': 'courses'}

    @property
    def subjects(self):
        return Subject.objects(course_id=self.id)

    @property
    def students(self):
        return StudentProfile.objects(course_id=self.id)

class Subject(db.Document):
    id = db.IntField(primary_key=True)
    name = db.StringField(max_length=100, required=True)
    semester = db.IntField(required=True)
    course_id = db.IntField(required=True)
    faculty_name = db.StringField(max_length=100)

    meta = {'collection': 'subjects'}

    @property
    def course(self):
        return Course.objects(id=self.course_id).first()

    @property
    def marks(self):
        return Mark.objects(subject_id=self.id)

    @property
    def attendances(self):
        return Attendance.objects(subject_id=self.id)

    @property
    def assignments(self):
        return Assignment.objects(subject_id=self.id)

class Mark(db.Document):
    id = db.IntField(primary_key=True)
    student_id = db.IntField(required=True)
    subject_id = db.IntField(required=True)
    internal_marks = db.FloatField(default=0.0)
    semester_marks = db.FloatField(default=0.0)
    total_marks = db.FloatField(default=0.0)
    grade = db.StringField(max_length=2)
    status = db.StringField(max_length=10, default='Pass')

    meta = {'collection': 'marks'}

    @property
    def student(self):
        return User.objects(id=self.student_id).first()

    @property
    def subject(self):
        return Subject.objects(id=self.subject_id).first()

class Attendance(db.Document):
    id = db.IntField(primary_key=True)
    student_id = db.IntField(required=True)
    subject_id = db.IntField(required=True)
    date = db.DateTimeField(default=datetime.utcnow)
    status = db.StringField(max_length=10, required=True)

    meta = {'collection': 'attendance'}

    @property
    def student(self):
        return User.objects(id=self.student_id).first()

    @property
    def subject(self):
        return Subject.objects(id=self.subject_id).first()

class Assignment(db.Document):
    id = db.IntField(primary_key=True)
    subject_id = db.IntField(required=True)
    title = db.StringField(max_length=200, required=True)
    description = db.StringField()
    file_path = db.StringField(max_length=200)
    deadline = db.DateTimeField(required=True)

    meta = {'collection': 'assignments'}

    @property
    def subject(self):
        return Subject.objects(id=self.subject_id).first()

    @property
    def submissions(self):
        return Submission.objects(assignment_id=self.id)

class Submission(db.Document):
    id = db.IntField(primary_key=True)
    assignment_id = db.IntField(required=True)
    student_id = db.IntField(required=True)
    file_path = db.StringField(max_length=200, required=True)
    marks_obtained = db.FloatField()
    submitted_at = db.DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'submissions'}

    @property
    def assignment(self):
        return Assignment.objects(id=self.assignment_id).first()

    @property
    def student(self):
        return User.objects(id=self.student_id).first()

class Notice(db.Document):
    id = db.IntField(primary_key=True)
    title = db.StringField(max_length=200, required=True)
    content = db.StringField(required=True)
    category = db.StringField(max_length=50, default='General')
    created_at = db.DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'notices'}

class Certificate(db.Document):
    id = db.IntField(primary_key=True)
    student_id = db.IntField(required=True)
    title = db.StringField(max_length=200, required=True)
    cert_type = db.StringField(max_length=50, default='Achievement')
    file_path = db.StringField(max_length=200, required=True)
    is_verified = db.BooleanField(default=False)
    uploaded_at = db.DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'certificates'}

    @property
    def student(self):
        return User.objects(id=self.student_id).first()

class Job(db.Document):
    id = db.IntField(primary_key=True)
    company_name = db.StringField(max_length=100, required=True)
    position = db.StringField(max_length=100, required=True)
    location = db.StringField(max_length=100)
    description = db.StringField()
    requirements = db.StringField()
    interview_date = db.DateTimeField()
    status = db.StringField(max_length=20, default='Open')

    meta = {'collection': 'jobs'}

    @property
    def applications(self):
        return JobApplication.objects(job_id=self.id)

class JobApplication(db.Document):
    id = db.IntField(primary_key=True)
    job_id = db.IntField(required=True)
    student_id = db.IntField(required=True)
    status = db.StringField(max_length=20, default='Applied')
    offer_status = db.StringField(max_length=20, default='Pending')
    applied_at = db.DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'job_applications'}

    @property
    def job(self):
        return Job.objects(id=self.job_id).first()

    @property
    def student(self):
        return User.objects(id=self.student_id).first()

class Feedback(db.Document):
    id = db.IntField(primary_key=True)
    student_id = db.IntField(required=True)
    content = db.StringField(required=True)
    rating = db.IntField()

    meta = {'collection': 'feedback'}

    @property
    def student(self):
        return User.objects(id=self.student_id).first()

class Grievance(db.Document):
    id = db.IntField(primary_key=True)
    student_id = db.IntField(required=True)
    subject = db.StringField(max_length=200, required=True)
    description = db.StringField(required=True)
    status = db.StringField(max_length=20, default='Pending')
    admin_response = db.StringField()
    created_at = db.DateTimeField(default=datetime.utcnow)

    meta = {'collection': 'grievances'}

    @property
    def student(self):
        return User.objects(id=self.student_id).first()
