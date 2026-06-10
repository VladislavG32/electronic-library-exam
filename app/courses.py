from datetime import datetime

from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from models import db, Course, Category, User, Review
from tools import CoursesFilter, ImageSaver

bp = Blueprint('courses', __name__, url_prefix='/courses')

COURSE_PARAMS = [
    'author_id', 'name', 'category_id', 'short_desc', 'full_desc'
]

def params():
    return {p: (request.form.get(p) or '').strip() for p in COURSE_PARAMS}

def search_params():
    return {
        'name': request.args.get('name'),
        'category_ids': [x for x in request.args.getlist('category_ids') if x],
    }

@bp.route('/')
def index():
    courses = CoursesFilter(**search_params()).perform()
    pagination = db.paginate(courses)
    courses = pagination.items
    categories = db.session.execute(db.select(Category)).scalars()
    return render_template('courses/index.html',
                           courses=courses,
                           categories=categories,
                           pagination=pagination,
                           search_params=search_params())

@bp.route('/new')
@login_required
def new():
    course = Course()
    categories = db.session.execute(db.select(Category)).scalars()
    users = db.session.execute(db.select(User)).scalars()
    return render_template('courses/new.html',
                           categories=categories,
                           users=users,
                           course=course)

@bp.route('/create', methods=['POST'])
@login_required
def create():
    f = request.files.get('background_img')
    img = None
    course = Course()
    try:
        if f and f.filename:
            img = ImageSaver(f).save()

        image_id = img.id if img else None
        course = Course(**params(), background_image_id=image_id)
        db.session.add(course)
        db.session.commit()
    except IntegrityError as err:
        flash(f'Возникла ошибка при записи данных в БД. Проверьте корректность введённых данных. ({err})', 'danger')
        db.session.rollback()
        categories = db.session.execute(db.select(Category)).scalars()
        users = db.session.execute(db.select(User)).scalars()
        return render_template('courses/new.html',
                               categories=categories,
                               users=users,
                               course=course)

    flash(f'Курс {course.name} был успешно добавлен!', 'success')
    return redirect(url_for('courses.index'))

@bp.route('/<int:course_id>')
def show(course_id):
    course = db.get_or_404(Course, course_id)

    # 5 последних отзывов
    last_reviews = (db.session.execute(
        db.select(Review)
        .where(Review.course_id == course_id)
        .order_by(Review.created_at.desc())
        .limit(5)
    ).scalars().all())

    return render_template('courses/show.html',
                           course=course,
                           last_reviews=last_reviews)

@bp.route('/<int:course_id>/reviews')
def reviews(course_id):
    course = db.get_or_404(Course, course_id)

    stmt = (db.select(Review)
            .where(Review.course_id == course_id)
            .order_by(Review.created_at.desc()))
    pagination = db.paginate(stmt)
    reviews_items = pagination.items

    return render_template('courses/reviews.html',
                           course=course,
                           reviews=reviews_items,
                           pagination=pagination)

@bp.route('/<int:course_id>/reviews/create', methods=['POST'])
@login_required
def create_review(course_id):
    course = db.get_or_404(Course, course_id)

    text = (request.form.get('text') or '').strip()
    rating_raw = (request.form.get('rating') or '').strip()

    # валидация
    try:
        rating = int(rating_raw)
    except ValueError:
        rating = 0

    if not text:
        flash('Текст отзыва не должен быть пустым.', 'danger')
        return redirect(url_for('courses.show', course_id=course_id))

    if rating < 1 or rating > 5:
        flash('Оценка должна быть числом от 1 до 5.', 'danger')
        return redirect(url_for('courses.show', course_id=course_id))

    review = Review(
        rating=rating,
        text=text,
        course_id=course_id,
        author_id=current_user.id,
        created_at=datetime.utcnow()
    )

    try:
        db.session.add(review)

        # пересчёт рейтинга курса
        course.rating_sum += rating
        course.rating_num += 1

        db.session.commit()
    except IntegrityError as err:
        db.session.rollback()
        flash(f'Ошибка при сохранении отзыва. ({err})', 'danger')
        return redirect(url_for('courses.show', course_id=course_id))

    flash('Отзыв добавлен!', 'success')
    return redirect(url_for('courses.show', course_id=course_id))
