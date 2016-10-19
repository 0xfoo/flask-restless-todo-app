# -*- coding: utf-8 -*-

import re
import json
from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash
from flask import url_for
from flask_login import UserMixin

from app import db, login_manager

EMAIL_REGEX = re.compile(r'^\S+@\S+\.\S+$')
USERNAME_REGEX = re.compile(r'^\S+$')


def check_length(attribute, length):
    """Checks the attribute's length."""
    try:
        return bool(attribute) and len(attribute) <= length
    except:
        return False


class BaseModel:
    """Base for all models, providing save, delete and from_dict methods."""

    def __commit(self):
        """Commits the current db.session, does rollback on failure."""
        from sqlalchemy.exc import IntegrityError
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()

    def delete(self):
        """Deletes this model from the db (through db.session)"""
        db.session.delete(self)
        self.__commit()

    def save(self):
        """Adds this model to the db (through db.session)"""
        db.session.add(self)
        self.__commit()
        return self

    @classmethod
    def from_dict(cls, model_dict):
        return cls(**model_dict).save()


class User(UserMixin, db.Model, BaseModel):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True)
    email = db.Column(db.String(64), unique=True)
    password_hash = db.Column(db.String(128))
    member_since = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)

    todolists = db.relationship('TodoList', backref='user', lazy='dynamic')

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)

    def __repr__(self):
        if self.is_admin:
            return '<Admin {0}>'.format(self.username)
        return '<User {0}>'.format(self.username)


    @property
    def name(self):
        return self.username

    @name.setter
    def name(self, username):
        is_valid_length = check_length(username, 64)
        if not is_valid_length or not bool(USERNAME_REGEX.match(username)):
            raise ValueError('{} is not a valid username'.format(username))
        self.username = username

    @property
    def emailaddress(self):
        return self.email

    @emailaddress.setter
    def emailaddress(self, email):
        if not check_length(email, 64) or not bool(EMAIL_REGEX.match(email)):
            raise ValueError('{} is not a valid email address'.format(email))
        self.email = email

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        if not bool(password):
            raise ValueError('no password given')

        hashed_password = generate_password_hash(password)
        if not check_length(hashed_password, 128):
            raise ValueError('not a valid password, hash is too long')
        else:
            self.password_hash = hashed_password

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def seen(self):
        self.last_seen = datetime.utcnow()
        return self.save()

    def to_dict(self):
        return {
            'username': self.username,
            'user_url': url_for(
                'api.get_user', username=self.username, _external=True
            ),
            'member_since': self.member_since,
            'last_seen': self.last_seen,
            'todolists': url_for(
                'api.get_user_todolists',
                username=self.username, _external=True
            ),
            'todolist_count': self.todolists.count()
        }

    def promote_to_admin(self):
        self.is_admin = True
        return self.save()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class TodoList(db.Model, BaseModel):
    __tablename__ = 'todolist'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    creator = db.Column(db.String(64), db.ForeignKey('user.username'))
    todos = db.relationship('Todo', backref='todolist', lazy='dynamic')

    def __init__(self, title=None, creator=None, created_at=None):
        self.title = title or 'untitled'
        self.creator = creator
        self.created_at = created_at or datetime.utcnow()

    def __repr__(self):
        return '<Todolist: {0}>'.format(self.title)

    @staticmethod
    def is_valid_title(list_title):
        return check_length(list_title, 128)

    def change_title(self, new_title):
        self.title = new_title
        self.save()

    def to_dict(self):
        if self.creator:
            todos_url = url_for(
                'api.get_user_todolist_todos',
                todolist_id=self.id,
                username=self.creator,
                _external=True,
            )
        else:
            todos_url = url_for(
                'api.get_todolist_todos',
                todolist_id=self.id,
                _external=True,
            )

        return {
            'title': self.title,
            'creator': self.creator,
            'created_at': self.created_at,
            'total_todo_count': self.count_todos(),
            'open_todo_count': self.count_open(),
            'finished_todo_count': self.count_finished(),
            'todos': todos_url,
        }

    def count_todos(self):
        return self.todos.order_by(None).count()

    def count_finished(self):
        return self.todos.filter_by(is_finished=True).count()

    def count_open(self):
        return self.todos.filter_by(is_finished=False).count()


class Todo(db.Model, BaseModel):
    __tablename__ = 'todo'
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, index=True, default=None)
    is_finished = db.Column(db.Boolean, default=False)
    creator = db.Column(db.String(64), db.ForeignKey('user.username'))
    todolist_id = db.Column(db.Integer, db.ForeignKey('todolist.id'))

    def __init__(self, description, todolist_id, creator=None,
                 created_at=None):
        self.description = description
        self.todolist_id = todolist_id
        self.creator = creator
        self.created_at = created_at or datetime.utcnow()

    def __repr__(self):
        return '<{0} todo: {1} by {2}>'.format(
            self.status, self.description, self.creator or 'None')

    @property
    def status(self):
        return 'finished' if self.is_finished else 'open'


    def finished(self):
        self.is_finished = True
        self.finished_at = datetime.utcnow()
        self.save()

    def reopen(self):
        self.is_finished = False
        self.finished_at = None
        self.save()

    def to_dict(self):
        return {
            'description': self.description,
            'creator': self.creator,
            'created_at': self.created_at,
            'status': self.status,
        }
