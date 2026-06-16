from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

book_genres = db.Table(
    'book_genres',
    db.Column('book_id', db.Integer, db.ForeignKey('books.id', ondelete='CASCADE'), primary_key=True),
    db.Column('genre_id', db.Integer, db.ForeignKey('genres.id', ondelete='CASCADE'), primary_key=True)
)


class Role(db.Model):
    __tablename__ = 'roles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False)

    users = db.relationship('User', back_populates='role')


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100), nullable=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)

    role = db.relationship('Role', back_populates='users')
    reviews = db.relationship('Review', back_populates='user')

    @property
    def full_name(self):
        return ' '.join([self.last_name, self.first_name, self.middle_name or '']).strip()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_role(self, *roles):
        return self.role and self.role.name in roles


class Genre(db.Model):
    __tablename__ = 'genres'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)


class Book(db.Model):
    __tablename__ = 'books'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    short_description = db.Column(db.Text, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    publisher = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255), nullable=False)
    pages = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    genres = db.relationship('Genre', secondary=book_genres, backref='books')
    cover = db.relationship('BookCover', back_populates='book', uselist=False, cascade='all, delete-orphan')
    reviews = db.relationship('Review', back_populates='book', cascade='all, delete-orphan')

    @property
    def approved_reviews(self):
        return [r for r in self.reviews if r.status and r.status.name == 'Одобрена']

    @property
    def reviews_count(self):
        return len(self.approved_reviews)

    @property
    def average_rating(self):
        reviews = self.approved_reviews
        if not reviews:
            return 0
        return round(sum(r.rating for r in reviews) / len(reviews), 2)


class BookCover(db.Model):
    __tablename__ = 'book_covers'

    id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    md5_hash = db.Column(db.String(255), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id', ondelete='CASCADE'), nullable=False)

    book = db.relationship('Book', back_populates='cover')

    @property
    def storage_filename(self):
        ext = ''

        if self.file_name and '.' in self.file_name:
            ext = '.' + self.file_name.rsplit('.', 1)[1].lower()

        return f'{self.md5_hash}{ext}'

class ReviewStatus(db.Model):
    __tablename__ = 'review_statuses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)


class Review(db.Model):
    __tablename__ = 'reviews'

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status_id = db.Column(db.Integer, db.ForeignKey('review_statuses.id'), nullable=False)

    book = db.relationship('Book', back_populates='reviews')
    user = db.relationship('User', back_populates='reviews')
    status = db.relationship('ReviewStatus')

    __table_args__ = (
        db.UniqueConstraint('book_id', 'user_id', name='uq_review_book_user'),
    )
