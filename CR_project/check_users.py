import flask.json
try:
    from flask.json import JSONEncoder
except ImportError:
    import json
    class JSONEncoder(json.JSONEncoder):
        def default(self, obj):
            if hasattr(obj, '__json__'): return obj.__json__()
            return super().default(obj)
    flask.json.JSONEncoder = JSONEncoder

from flask import Flask
from mongoengine import connect
from models import User

app = Flask(__name__)
# Add the json_encoder shim just in case
if not hasattr(app, 'json_encoder'):
    app.json_encoder = JSONEncoder

app.config['MONGODB_SETTINGS'] = {
    'db': 'crms_db',
    'host': 'localhost',
    'port': 27017
}

connect('crms_db', host='localhost', port=27017)

print("--- User Records ---")
users = User.objects.all()
if users:
    for user in users:
        print(f"ID: {user.id} ({type(user.id)}), Username: {user.username}, Email: {user.email}, Role: {user.role}")
else:
    print("No users found in database.")

admin = User.objects(email='admin@gmail.com').first()
if admin:
    print(f"\nAdmin found: {admin.username} (ID: {admin.id}, type: {type(admin.id)})")
else:
    print("\nAdmin@gmail.com NOT found!")
