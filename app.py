from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from datetime import datetime
from werkzeug.utils import secure_filename
import os
from flask import send_from_directory


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///assignment.db"
app.config["SECRET_KEY"] = "secret_key_here"

db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

app.config["UPLOAD_FOLDER"] = "uploads/"
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB limit
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(80), nullable=False)
    profile = db.relationship("Profile", backref="user", uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    student = db.relationship("User", foreign_keys=[student_id], backref="assignments")
    teacher = db.relationship("User", foreign_keys=[teacher_id], backref="graded_assignments")
    grade = db.Column(db.Integer)
    submitted = db.Column(db.Boolean, default=False)
    deadline = db.Column(db.DateTime, nullable=False)
    criteria = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(200))

class DraftAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    student = db.relationship("User", backref="draft_assignments")

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"))
    assignment = db.relationship("Assignment", backref="comments")
    text = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", backref="comments")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]
        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/dashboard")
@login_required
def dashboard():
    '''
    if current_user.role == "principal":
        return render_template("principal_dashboard.html", teachers=User.query.filter_by(role="teacher").all())'''
    if current_user.role == "principal":
        teachers = User.query.filter_by(role="teacher").all()
        assignments = Assignment.query.all()
        return render_template("principal_dashboard.html", teachers=teachers, assignments=assignments)
    elif current_user.role == "teacher":
        assignments = Assignment.query.filter_by(teacher_id=current_user.id).all()
        return render_template("teacher_assignments.html", assignments=assignments)
        '''return render_template("teacher_assignments.html", assignments=Assignment.query.filter_by(teacher_id=current_user.id).all())'''
    
    elif current_user.role == "student":
        return render_template("student_dashboard.html", assignments=current_user.assignments, draft_assignments=current_user.draft_assignments)
    
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/create_assignment', methods=['GET', 'POST'])
@login_required
def create_assignment():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        teacher_id = request.form['teacher_id']
        deadline_str = request.form['deadline']
        criteria = request.form['criteria']

        # Check if the file is uploaded
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        else:
            flash("Invalid file format. Only PDF, DOC, and DOCX are allowed.")
            return redirect(url_for('create_assignment'))

        # Convert deadline to datetime object
        try:
            deadline = datetime.fromisoformat(deadline_str)
        except ValueError:
            flash('Invalid date format for deadline.')
            return redirect(url_for('create_assignment'))

        assignment = Assignment(
            title=title,
            description=description,
            student_id=current_user.id,
            teacher_id=teacher_id,
            deadline=deadline,
            criteria=criteria,
            file_path=file_path,  # Save the file path in the database
        )
        db.session.add(assignment)
        db.session.commit()
        flash('Assignment created successfully!')
        return redirect(url_for('student_dashboard'))

    teachers = User.query.filter_by(role='teacher').all()
    return render_template('create_assignment.html', teachers=teachers)


@app.route('/download/<filename>')
@login_required
def download_file(filename):
    # Replace 'uploads/' with the directory where your files are stored
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)



@app.route("/student_dashboard")
@login_required
def student_dashboard():
    return render_template("student_dashboard.html", assignments=current_user.assignments, draft_assignments=current_user.draft_assignments)


@app.route("/submit_assignment/<int:draft_id>", methods=["POST"])
@login_required
def submit_assignment(draft_id):
    draft_assignment = DraftAssignment.query.get(draft_id)
    assignment = Assignment(title=draft_assignment.title, description=draft_assignment.description, student_id=draft_assignment.student_id, deadline=draft_assignment.deadline, criteria=draft_assignment.criteria)
    db.session.add(assignment)
    db.session.delete(draft_assignment)
    db.session.commit()
    return redirect(url_for("dashboard"))
'''
# Workable
@app.route("/teacher_assignments")
@login_required
def teacher_assignments():
    if current_user.role != "teacher":
        abort(403) 
    assignments = Assignment.query.filter_by(teacher_id=current_user.id).all()
    return render_template("teacher_assignments.html", assignments=assignments)'''

#Workable
@app.route("/grade_assignment/<int:assignment_id>", methods=["GET", "POST"])
@login_required
def grade_assignment(assignment_id):
    if current_user.role != "teacher":
        abort(403)
    assignment = Assignment.query.get(assignment_id)
    if assignment.teacher_id != current_user.id:
        abort(403)
    if request.method == "POST":
        grade = request.form["grade"]
        assignment.grade = grade
        db.session.commit()
        return redirect(url_for("teacher_assignments"))
    return render_template("grade_assignment.html", assignment=assignment)

@app.route("/re_grade_assignment/<int:assignment_id>", methods=["GET", "POST"])
@login_required
def re_grade_assignment(assignment_id):
    if current_user.role != "principal":
        abort(403)  # Forbidden, only principals can access this route
    assignment = Assignment.query.get(assignment_id)
    if request.method == "POST":
        grade = request.form["grade"]
        assignment.grade = grade
        db.session.commit()
        return redirect(url_for("dashboard"))
    return render_template("re_grade_assignment.html", assignment=assignment)

@app.route('/edit_assignment/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def edit_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.student_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        assignment.title = request.form['title']
        assignment.description = request.form['description']
        db.session.commit()
        flash('Assignment updated successfully!')
        return redirect(url_for('student_dashboard'))
    return render_template('edit_assignment.html', assignment=assignment)

@app.route("/comment_assignment/<int:assignment_id>", methods=["GET", "POST"])
@login_required
def comment_assignment(assignment_id):
    assignment = Assignment.query.get(assignment_id)
    if request.method == "POST":
        text = request.form["text"]
        comment = Comment(text=text, assignment_id=assignment_id, user_id=current_user.id)
        db.session.add(comment)
        db.session.commit()
        return redirect(url_for("dashboard"))
    return render_template("comment_assignment.html", assignment=assignment)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all() 
    app.run(debug=True)