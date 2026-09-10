import os
import io
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from mongoengine import connect, Document, StringField, IntField, FloatField, BooleanField, DateTimeField, ReferenceField, ListField, EmailField, DictField, DateField, FileField
from models import db, User, StudentProfile, Course, Subject, Mark, Attendance, Assignment, Submission, Notice, Certificate, Job, JobApplication, Feedback, Grievance

# 1. Setup Flask App to read SQLAlchemy
app = Flask(__name__)
# Use absolute path to ensure it finds the DB
base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, 'instance', 'new_site.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# 2. Define MongoEngine equivalents (Mental mapping, will use models.py after refactor)
# For migration, we'll use a direct approach or define temp classes.
# Let's define the MongoEngine connection first.
MONGO_DB = 'crms_db'
connect(MONGO_DB, host='localhost', port=27017)

def migrate():
    with app.app_context():
        print("Starting migration from SQLite to MongoDB...")
        
        # --- 1. Courses ---
        print("Migrating Courses...")
        courses = Course.query.all()
        id_map_course = {}
        for c in courses:
            # We'll store the old ID to maintain relationships during migration
            # Actually, MongoDB will generate new ObjectIds.
            # We'll map: old_course_id -> mongo_course_object
            pass

        # To avoid duplicating models here, I'll first refactor models.py 
        # but keep a backup of the old one or use SQLAlchemy directly to read.
        # Actually, it's safer to read all data as dicts first.

        def to_dict(row):
            return {column.name: getattr(row, column.name) for column in row.__table__.columns}

        data = {
            'users': [to_dict(u) for u in User.query.all()],
            'profiles': [to_dict(p) for p in StudentProfile.query.all()],
            'courses': [to_dict(c) for c in Course.query.all()],
            'subjects': [to_dict(s) for s in Subject.query.all()],
            'marks': [to_dict(m) for m in Mark.query.all()],
            'attendance': [to_dict(a) for a in Attendance.query.all()],
            'assignments': [to_dict(a) for a in Assignment.query.all()],
            'submissions': [to_dict(s) for s in Submission.query.all()],
            'notices': [to_dict(n) for n in Notice.query.all()],
            'certificates': [to_dict(c) for c in Certificate.query.all()],
            'jobs': [to_dict(j) for j in Job.query.all()],
            'job_applications': [to_dict(j) for j in JobApplication.query.all()],
            'feedback': [to_dict(f) for f in Feedback.query.all()],
            'grievances': [to_dict(g) for g in Grievance.query.all()],
        }
        
        print(f"Loaded {len(data['users'])} users, {len(data['courses'])} courses, etc.")

        # Now we need to insert them into MongoDB using PyMongo for simplicity in the script
        from pymongo import MongoClient
        client = MongoClient('localhost', 27017)
        m_db = client[MONGO_DB]

        # Clear existing collections to avoid duplicates if re-run
        for col in data.keys():
            m_db[col].delete_many({})

        # Insert data
        for col, records in data.items():
            if records:
                m_db[col].insert_many(records)
                print(f"Inserted {len(records)} into {col}")

        print("Migration complete!")

if __name__ == "__main__":
    migrate()
