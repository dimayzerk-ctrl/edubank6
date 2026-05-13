from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from config import Config
from models import db, User, Transaction, SavingsAccount
from forms import RegisterForm, LoginForm, TransferForm, SavingsForm, PaymentForm

# 1. Создаём приложение
app = Flask(__name__)
app.config.from_object(Config)

# 2. Инициализируем базу данных
db.init_app(app)

# 3. Настраиваем LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- Главная страница ---
@app.route('/')
def index():
    # Если уже залогинен — идёт на дашборд, иначе на приветственную страницу
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


# --- Регистрация ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = RegisterForm()
    if form.validate_on_submit():
        # Проверяем, не занят ли email или username
        if User.query.filter_by(email=form.email.data).first():
            flash('Этот email уже зарегистрирован')
            return redirect(url_for('register'))
        if User.query.filter_by(username=form.username.data).first():
            flash('Это имя пользователя уже занято')
            return redirect(url_for('register'))

        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()  # получаем user.id до commit

        # ВАЖНО: создаём SavingsAccount сразу при регистрации
        savings = SavingsAccount(user_id=user.id, balance=0.0)
        db.session.add(savings)
        db.session.commit()

        flash('Регистрация прошла успешно! Войдите в систему.')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


# --- Вход ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Неверный email или пароль')
    return render_template('login.html', form=form)


# --- Дашборд ---
@app.route('/dashboard')
@login_required
def dashboard():
    savings = SavingsAccount.query.filter_by(user_id=current_user.id).first()
    # Если по какой-то причине SavingsAccount не существует — создаём
    if not savings:
        savings = SavingsAccount(user_id=current_user.id, balance=0.0)
        db.session.add(savings)
        db.session.commit()
    return render_template('dashboard.html', savings=savings)


# --- Переводы ---
@app.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    form = TransferForm()
    if form.validate_on_submit():
        amount = float(form.amount.data)
        recipient = User.query.filter_by(username=form.recipient.data).first()

        if not recipient:
            flash('Пользователь не найден')
            return redirect(url_for('transfer'))
        if recipient.id == current_user.id:
            flash('Нельзя переводить самому себе')
            return redirect(url_for('transfer'))
        if current_user.balance < amount:
            flash('Недостаточно средств')
            return redirect(url_for('transfer'))

        current_user.balance -= amount
        recipient.balance += amount

        transaction = Transaction(
            sender_id=current_user.id,
            receiver_id=recipient.id,
            amount=amount,
            description=form.description.data or f'Перевод пользователю {recipient.username}'
        )
        db.session.add(transaction)
        db.session.commit()
        flash(f'Перевод {amount} ₽ пользователю {recipient.username} выполнен')
        return redirect(url_for('dashboard'))
    return render_template('transfer.html', form=form)


# --- Накопления ---
@app.route('/savings', methods=['GET', 'POST'])
@login_required
def savings():
    form = SavingsForm()
    savings = SavingsAccount.query.filter_by(user_id=current_user.id).first()
    # Защита: если SavingsAccount вдруг не создан
    if not savings:
        savings = SavingsAccount(user_id=current_user.id, balance=0.0)
        db.session.add(savings)
        db.session.commit()

    if form.validate_on_submit():
        amount = float(form.amount.data)
        if form.action.data == 'deposit':
            if current_user.balance >= amount:
                current_user.balance -= amount
                savings.balance += amount
                flash('Средства переведены в накопления')
            else:
                flash('Недостаточно средств')
        elif form.action.data == 'withdraw':
            if savings.balance >= amount:
                savings.balance -= amount
                current_user.balance += amount
                flash('Средства выведены с накоплений')
            else:
                flash('Недостаточно накоплений')
        db.session.commit()
        return redirect(url_for('savings'))
    return render_template('savings.html', form=form, savings=savings)


# --- Платежи ---
@app.route('/payments', methods=['GET', 'POST'])
@login_required
def payments():
    form = PaymentForm()
    if form.validate_on_submit():
        amount = float(form.amount.data)
        if current_user.balance < amount:
            flash('Недостаточно средств')
            return redirect(url_for('payments'))
        current_user.balance -= amount
        transaction = Transaction(
            sender_id=current_user.id,
            receiver_id=current_user.id,
            amount=amount,
            description=f'Оплата: {form.category.data}'
        )
        db.session.add(transaction)
        db.session.commit()
        flash('Платёж выполнен')
        return redirect(url_for('payments'))
    return render_template('payments.html', form=form)


# --- История ---
@app.route('/history')
@login_required
def history():
    transactions = Transaction.query.filter(
        (Transaction.sender_id == current_user.id) |
        (Transaction.receiver_id == current_user.id)
    ).order_by(Transaction.timestamp.desc()).all()
    return render_template('history.html', transactions=transactions)


# --- Выход ---
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
