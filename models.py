from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import secrets
import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    
    # One-to-many relationship with API keys
    api_keys = db.relationship('ApiKey', backref='user', lazy=True, cascade="all, delete-orphan")
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def generate_api_key(self, name="Default"):
        """Generate a new API key for this user"""
        api_key = ApiKey(
            user_id=self.id,
            key=secrets.token_urlsafe(32),
            name=name
        )
        db.session.add(api_key)
        db.session.commit()
        return api_key

class ApiKey(db.Model):
    __tablename__ = 'api_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    key = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    last_used_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f"<ApiKey {self.name}>"
    
    def mark_used(self):
        """Update the last_used_at timestamp"""
        self.last_used_at = datetime.datetime.utcnow()
        db.session.commit()