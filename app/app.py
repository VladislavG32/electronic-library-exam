import os
import hashlib
from datetime import datetime

import bleach
import markdown
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import func

from models import db, User, Role, Book, Genre, BookCover, Review, ReviewStatus


app = Flask(__name__)
application = app

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config.from_pyfile('config.py')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'media', 'images')

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'Для выполнения данного действия необходимо пройти процедуру аутентификации'
login_manager.init_app(app)


ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    'p', 'br', 'hr', 'pre', 'code', 'h1', 'h2', 'h3',
    'h4', 'h5', 'h6', 'span', 'div', 'ul', 'ol', 'li',
    'strong', 'em', 'blockquote'
]

RATINGS = {
    5: 'отлично',
    4: 'хорошо',
    3: 'удовлетворительно',
    2: 'неудовлетворительно',
    1: 'плохо',
    0: 'ужасно'
}


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def md_to_html(text):
    html = markdown.markdown(text or '')
    return bleach.clean(html, tags=ALLOWED_TAGS)


def role_required(*roles):
    def decorator(func_view):
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Для выполнения данного действия необходимо пройти процедуру аутентификации', 'warning')
                return redirect(url_for('login', next=request.url))
            if not current_user.has_role(*roles):
                flash('У вас недостаточно прав для выполнения данного действия', 'danger')
                return redirect(url_for('index'))
            return func_view(*args, **kwargs)
        wrapper.__name__ = func_view.__name__
        return wrapper
    return decorator


@app.context_processor
def inject_helpers():
    return {
        'RATINGS': RATINGS,
        'md_to_html': md_to_html
    }


@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    pagination = Book.query.order_by(Book.year.desc()).paginate(page=page, per_page=10, error_out=False)
    return render_template('index.html', pagination=pagination, books=pagination.items)


@app.route('/login', methods=['GET', 'POST'])
@app.route('/auth/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_value = request.form.get('login')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(login=login_value).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            return redirect(request.args.get('next') or url_for('index'))

        flash('Невозможно аутентифицироваться с указанными логином и паролем', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(request.referrer or url_for('index'))


@app.route('/images/<int:cover_id>')
def image(cover_id):
    cover = db.get_or_404(BookCover, cover_id)
    return send_from_directory(app.config['UPLOAD_FOLDER'], cover.storage_filename)


@app.route('/books/<int:book_id>')
def book_show(book_id):
    book = db.get_or_404(Book, book_id)

    approved_status = ReviewStatus.query.filter_by(name='Одобрена').first()
    reviews = Review.query.filter_by(book_id=book.id, status_id=approved_status.id).order_by(Review.created_at.desc()).all()

    my_review = None
    if current_user.is_authenticated:
        my_review = Review.query.filter_by(book_id=book.id, user_id=current_user.id).first()

    return render_template('book_show.html', book=book, reviews=reviews, my_review=my_review)


@app.route('/books/create', methods=['GET', 'POST'])
@role_required('Администратор')
def book_create():
    genres = Genre.query.order_by(Genre.name).all()

    if request.method == 'POST':
        try:
            book = Book(
                title=request.form.get('title'),
                short_description=bleach.clean(request.form.get('short_description', ''), tags=[]),
                year=int(request.form.get('year')),
                publisher=request.form.get('publisher'),
                author=request.form.get('author'),
                pages=int(request.form.get('pages'))
            )

            genre_ids = request.form.getlist('genres')
            book.genres = Genre.query.filter(Genre.id.in_(genre_ids)).all()

            db.session.add(book)
            db.session.flush()

            file = request.files.get('cover')
            if not file or not file.filename:
                raise ValueError('Не загружена обложка')

            content = file.read()
            file.seek(0)
            md5_hash = hashlib.md5(content).hexdigest()

            cover = BookCover(
                file_name=file.filename,
                mime_type=file.mimetype,
                md5_hash=md5_hash,
                book_id=book.id
            )
            db.session.add(cover)
            db.session.flush()

            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], cover.storage_filename))

            db.session.commit()
            flash('Книга успешно добавлена', 'success')
            return redirect(url_for('book_show', book_id=book.id))

        except Exception:
            db.session.rollback()
            flash('При сохранении данных возникла ошибка. Проверьте корректность введённых данных.', 'danger')

    return render_template('book_form.html', book=None, genres=genres, action='Добавить книгу')


@app.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
@role_required('Администратор', 'Модератор')
def book_edit(book_id):
    book = db.get_or_404(Book, book_id)
    genres = Genre.query.order_by(Genre.name).all()

    if request.method == 'POST':
        try:
            book.title = request.form.get('title')
            book.short_description = bleach.clean(request.form.get('short_description', ''), tags=[])
            book.year = int(request.form.get('year'))
            book.publisher = request.form.get('publisher')
            book.author = request.form.get('author')
            book.pages = int(request.form.get('pages'))

            genre_ids = request.form.getlist('genres')
            book.genres = Genre.query.filter(Genre.id.in_(genre_ids)).all()

            db.session.commit()
            flash('Книга успешно обновлена', 'success')
            return redirect(url_for('book_show', book_id=book.id))

        except Exception:
            db.session.rollback()
            flash('При сохранении данных возникла ошибка. Проверьте корректность введённых данных.', 'danger')

    return render_template('book_form.html', book=book, genres=genres, action='Редактировать книгу')


@app.route('/books/<int:book_id>/delete', methods=['POST'])
@role_required('Администратор')
def book_delete(book_id):
    book = db.get_or_404(Book, book_id)

    if book.cover:
        path = os.path.join(app.config['UPLOAD_FOLDER'], book.cover.storage_filename)
        if os.path.exists(path):
            os.remove(path)

    db.session.delete(book)
    db.session.commit()

    flash('Книга успешно удалена', 'success')
    return redirect(url_for('index'))


@app.route('/books/<int:book_id>/reviews/create', methods=['GET', 'POST'])
@login_required
def review_create(book_id):
    book = db.get_or_404(Book, book_id)

    existing_review = Review.query.filter_by(book_id=book.id, user_id=current_user.id).first()
    if existing_review:
        flash('Вы уже оставляли рецензию на эту книгу', 'warning')
        return redirect(url_for('book_show', book_id=book.id))

    if request.method == 'POST':
        try:
            pending_status = ReviewStatus.query.filter_by(name='На рассмотрении').first()

            review = Review(
                book_id=book.id,
                user_id=current_user.id,
                rating=int(request.form.get('rating')),
                text=bleach.clean(request.form.get('text', ''), tags=[]),
                status_id=pending_status.id
            )

            db.session.add(review)
            db.session.commit()

            flash('Рецензия отправлена на рассмотрение', 'success')
            return redirect(url_for('book_show', book_id=book.id))

        except Exception:
            db.session.rollback()
            flash('При сохранении рецензии возникла ошибка', 'danger')

    return render_template('review_form.html', book=book)


@app.route('/my-reviews')
@login_required
def my_reviews():
    if not current_user.has_role('Пользователь'):
        flash('У вас недостаточно прав для выполнения данного действия', 'danger')
        return redirect(url_for('index'))

    reviews = Review.query.filter_by(user_id=current_user.id).order_by(Review.created_at.desc()).all()
    return render_template('my_reviews.html', reviews=reviews)


@app.route('/moderation/reviews')
@role_required('Модератор')
def moderation_reviews():
    page = request.args.get('page', 1, type=int)
    pending_status = ReviewStatus.query.filter_by(name='На рассмотрении').first()

    pagination = Review.query.filter_by(status_id=pending_status.id).order_by(Review.created_at.asc()).paginate(
        page=page,
        per_page=10,
        error_out=False
    )

    return render_template('moderation_reviews.html', pagination=pagination, reviews=pagination.items)


@app.route('/moderation/reviews/<int:review_id>')
@role_required('Модератор')
def moderate_review(review_id):
    review = db.get_or_404(Review, review_id)
    return render_template('moderate_review.html', review=review)


@app.route('/moderation/reviews/<int:review_id>/approve', methods=['POST'])
@role_required('Модератор')
def approve_review(review_id):
    review = db.get_or_404(Review, review_id)
    status = ReviewStatus.query.filter_by(name='Одобрена').first()
    review.status_id = status.id
    db.session.commit()
    flash('Рецензия одобрена', 'success')
    return redirect(url_for('moderation_reviews'))


@app.route('/moderation/reviews/<int:review_id>/reject', methods=['POST'])
@role_required('Модератор')
def reject_review(review_id):
    review = db.get_or_404(Review, review_id)
    status = ReviewStatus.query.filter_by(name='Отклонена').first()
    review.status_id = status.id
    db.session.commit()
    flash('Рецензия отклонена', 'success')
    return redirect(url_for('moderation_reviews'))


def init_database():
    db.drop_all()
    db.create_all()

    admin_role = Role(name='Администратор', description='Суперпользователь, имеет полный доступ к системе')
    moderator_role = Role(name='Модератор', description='Может редактировать книги и модерировать рецензии')
    user_role = Role(name='Пользователь', description='Может оставлять рецензии')

    db.session.add_all([admin_role, moderator_role, user_role])
    db.session.flush()

    statuses = [
        ReviewStatus(name='На рассмотрении'),
        ReviewStatus(name='Одобрена'),
        ReviewStatus(name='Отклонена')
    ]
    db.session.add_all(statuses)

    genres = [
        Genre(name='Роман'),
        Genre(name='Фантастика'),
        Genre(name='Детектив'),
        Genre(name='Научная литература'),
        Genre(name='История')
    ]
    db.session.add_all(genres)
    db.session.flush()

    admin = User(login='admin', last_name='Администратор', first_name='Системы', middle_name='', role_id=admin_role.id)
    admin.set_password('admin')

    moderator = User(login='moderator', last_name='Модератор', first_name='Системы', middle_name='', role_id=moderator_role.id)
    moderator.set_password('moderator')

    user = User(login='user', last_name='Иванов', first_name='Иван', middle_name='Иванович', role_id=user_role.id)
    user.set_password('user')

    db.session.add_all([admin, moderator, user])
    db.session.flush()

    books = [
        Book(
            title='Мастер и Маргарита',
            short_description='Роман Михаила Булгакова о добре, зле, любви и свободе выбора.',
            year=1967,
            publisher='Азбука',
            author='Михаил Булгаков',
            pages=480,
            genres=[genres[0]]
        ),
        Book(
            title='Солярис',
            short_description='Научно-фантастический роман о контакте человека с неизвестной формой разума.',
            year=1961,
            publisher='АСТ',
            author='Станислав Лем',
            pages=320,
            genres=[genres[1], genres[3]]
        ),
        Book(
            title='Шерлок Холмс: Этюд в багровых тонах',
            short_description='Первое произведение о знаменитом сыщике Шерлоке Холмсе.',
            year=1887,
            publisher='Эксмо',
            author='Артур Конан Дойл',
            pages=256,
            genres=[genres[2]]
        )
    ]

    db.session.add_all(books)
    db.session.flush()

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    for book in books:
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="300" height="420">
<rect width="300" height="420" fill="#212529"/>
<text x="150" y="190" font-size="26" fill="white" text-anchor="middle">Книга</text>
<text x="150" y="230" font-size="18" fill="white" text-anchor="middle">{book.title[:20]}</text>
</svg>'''
        content = svg.encode('utf-8')
        cover = BookCover(
            file_name='cover.svg',
            mime_type='image/svg+xml',
            md5_hash=hashlib.md5(content).hexdigest(),
            book_id=book.id
        )
        db.session.add(cover)
        db.session.flush()

        with open(os.path.join(app.config['UPLOAD_FOLDER'], cover.storage_filename), 'wb') as f:
            f.write(content)

    db.session.commit()


if __name__ == '__main__':
    app.run()
