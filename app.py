import base64
from datetime import datetime, timedelta
import os
import random
import string
from flask import Flask, Response, flash, redirect, render_template_string, request, session, url_for
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "edusphere-secret-key-change-in-production"
)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4 MB max logo upload
db_url = os.environ.get("DATABASE_URL", "sqlite:///school_saas.db").replace(
    "postgres://", "postgresql://", 1
)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

SUPER_ADMIN_EMAIL = os.environ.get("SUPER_ADMIN_EMAIL", "owner@edusphere.com")
SUPER_ADMIN_PASSWORD = os.environ.get("SUPER_ADMIN_PASSWORD", "owner123")
MOMO_MERCHANT_NUMBER = os.environ.get("MOMO_MERCHANT_NUMBER", "231880242760")

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


# ==========================================
# 1. DATABASE MODELS
# ==========================================
class PlatformConfig(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  subscription_amount = db.Column(db.Float, default=100.0)
  subscription_currency = db.Column(db.String(10), default="USD")
  merchant_number = db.Column(db.String(30), default=MOMO_MERCHANT_NUMBER)


class SuperBroadcast(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  title = db.Column(db.String(120), nullable=False)
  message = db.Column(db.String(800), nullable=False)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)


class School(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(100), nullable=False)
  admin_email = db.Column(db.String(120), unique=True, nullable=False)
  admin_password = db.Column(db.String(200), nullable=False)
  logo_data = db.Column(db.Text, nullable=True)
  trial_end_date = db.Column(
      db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=30)
  )
  is_active = db.Column(db.Boolean, default=True)
  subscription_end_date = db.Column(db.DateTime, nullable=True)

  def has_access(self):
    if not self.is_active:
      return False
    if (
        self.subscription_end_date
        and datetime.utcnow() < self.subscription_end_date
    ):
      return True
    return datetime.utcnow() < self.trial_end_date


class Classroom(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  school_id = db.Column(db.Integer, db.ForeignKey("school.id"), nullable=False)
  name = db.Column(db.String(50), nullable=False)


class Parent(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  school_id = db.Column(db.Integer, db.ForeignKey("school.id"), nullable=False)
  full_name = db.Column(db.String(100), nullable=False)
  email = db.Column(db.String(120), unique=True, nullable=False)
  phone = db.Column(db.String(30), nullable=True)
  password = db.Column(db.String(200), nullable=False)


class Student(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  classroom_id = db.Column(
      db.Integer, db.ForeignKey("classroom.id"), nullable=False
  )
  parent_id = db.Column(db.Integer, db.ForeignKey("parent.id"), nullable=True)
  full_name = db.Column(db.String(100), nullable=False)
  email = db.Column(db.String(120), unique=True, nullable=False)
  password = db.Column(db.String(200), nullable=False)
  parent_contact = db.Column(db.String(20))


class Teacher(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  school_id = db.Column(db.Integer, db.ForeignKey("school.id"), nullable=False)
  classroom_id = db.Column(
      db.Integer, db.ForeignKey("classroom.id"), nullable=False
  )
  full_name = db.Column(db.String(100), nullable=False)
  email = db.Column(db.String(120), unique=True, nullable=False)
  password = db.Column(db.String(200), nullable=False)
  salary = db.Column(db.Float, default=0.0)
  is_paid = db.Column(db.Boolean, default=False)


class Cashier(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  school_id = db.Column(db.Integer, db.ForeignKey("school.id"), nullable=False)
  full_name = db.Column(db.String(100), nullable=False)
  email = db.Column(db.String(120), unique=True, nullable=False)
  password = db.Column(db.String(200), nullable=False)


class Attendance(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  student_id = db.Column(
      db.Integer, db.ForeignKey("student.id"), nullable=False
  )
  date = db.Column(
      db.String(20), default=lambda: datetime.now().strftime("%Y-%m-%d")
  )
  status = db.Column(db.String(10), nullable=False)


class Grade(db.Model):
  """Official Report Card Period / Exam Grades."""

  id = db.Column(db.Integer, primary_key=True)
  student_id = db.Column(
      db.Integer, db.ForeignKey("student.id"), nullable=False
  )
  period = db.Column(db.String(40), default="1st Period")
  subject = db.Column(db.String(50), nullable=False)
  score = db.Column(db.Float, nullable=False)


class AssessmentRecord(db.Model):
  """Continuous Assessment Grades (Quiz, Assignment, Seat Work, Test) separate from final report card."""

  id = db.Column(db.Integer, primary_key=True)
  student_id = db.Column(
      db.Integer, db.ForeignKey("student.id"), nullable=False
  )
  teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=True)
  category = db.Column(db.String(30), default="Quiz")
  label = db.Column(db.String(60), default="Quiz 1")
  subject = db.Column(db.String(50), nullable=False)
  score = db.Column(db.Float, nullable=False)
  max_score = db.Column(db.Float, default=100.0)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Announcement(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  school_id = db.Column(db.Integer, db.ForeignKey("school.id"), nullable=False)
  author_label = db.Column(db.String(80), default="Principal")
  message = db.Column(db.String(600), nullable=False)
  date_posted = db.Column(db.DateTime, default=datetime.utcnow)


class FeeRecord(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  student_id = db.Column(
      db.Integer, db.ForeignKey("student.id"), nullable=False
  )
  currency = db.Column(db.String(10), default="USD")
  total_fees = db.Column(db.Float, default=0.0)
  amount_paid = db.Column(db.Float, default=0.0)
  is_cleared = db.Column(db.Boolean, default=False)
  last_receipt_code = db.Column(db.String(40), nullable=True)
  last_payment_date = db.Column(db.String(30), nullable=True)


class FeeTransaction(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  student_id = db.Column(
      db.Integer, db.ForeignKey("student.id"), nullable=False
  )
  amount = db.Column(db.Float, nullable=False)
  currency = db.Column(db.String(10), default="USD")
  receipt_code = db.Column(db.String(40), nullable=False)
  recorded_by = db.Column(db.String(80), default="Cashier")
  created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Assignment(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  teacher_id = db.Column(
      db.Integer, db.ForeignKey("teacher.id"), nullable=False
  )
  classroom_id = db.Column(
      db.Integer, db.ForeignKey("classroom.id"), nullable=False
  )
  subject_tag = db.Column(db.String(60), default="General")
  title = db.Column(db.String(120), nullable=False)
  description = db.Column(db.String(800), nullable=False)
  date_given = db.Column(
      db.String(20), default=lambda: datetime.now().strftime("%Y-%m-%d")
  )
  due_date = db.Column(db.String(20), nullable=False)


class PaymentRequest(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  school_id = db.Column(db.Integer, db.ForeignKey("school.id"), nullable=False)
  amount = db.Column(db.Float, nullable=False)
  currency = db.Column(db.String(10), default="USD")
  provider = db.Column(db.String(30), default="MTN")
  payer_phone = db.Column(db.String(30), nullable=True)
  momo_tx_id = db.Column(db.String(80), nullable=True)
  reference = db.Column(db.String(50), unique=True, nullable=False)
  status = db.Column(db.String(20), default="Pending")
  date_requested = db.Column(db.DateTime, default=datetime.utcnow)


class PortalMessage(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  school_id = db.Column(db.Integer, db.ForeignKey("school.id"), nullable=False)
  parent_id = db.Column(db.Integer, db.ForeignKey("parent.id"), nullable=True)
  student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=True)
  sender_label = db.Column(db.String(80), nullable=False)
  direction = db.Column(db.String(20), default="to_parent")
  body = db.Column(db.String(800), nullable=False)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DirectMessage(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  school_id = db.Column(db.Integer, db.ForeignKey("school.id"), nullable=False)
  sender_key = db.Column(db.String(40), nullable=False)
  sender_name = db.Column(db.String(100), nullable=False)
  receiver_key = db.Column(db.String(40), nullable=False)
  receiver_name = db.Column(db.String(100), nullable=False)
  body = db.Column(db.String(800), nullable=False)
  is_read = db.Column(db.Boolean, default=False)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ==========================================
# 2. HELPERS, RANKING & NOTIFICATIONS
# ==========================================
def ensure_sqlite_columns():
  if not db.engine.url.drivername.startswith("sqlite"):
    return
  expected_columns = {
      "direct_message": [("is_read", "BOOLEAN DEFAULT 0")],
      "school": [("logo_data", "TEXT")],
      "assignment": [("subject_tag", "VARCHAR(60) DEFAULT 'General'")],
      "grade": [("period", "VARCHAR(40) DEFAULT '1st Period'")],
      "fee_record": [
          ("last_receipt_code", "VARCHAR(40)"),
          ("last_payment_date", "VARCHAR(30)"),
      ],
      "payment_request": [
          ("provider", "VARCHAR(30) DEFAULT 'MTN'"),
          ("payer_phone", "VARCHAR(30)"),
          ("momo_tx_id", "VARCHAR(80)"),
      ],
  }
  with db.engine.begin() as conn:
    for table_name, cols_to_add in expected_columns.items():
      existing = [
          row[1]
          for row in conn.execute(text(f"PRAGMA table_info({table_name})"))
      ]
      if not existing:
        continue
      for col_name, col_def in cols_to_add:
        if col_name not in existing:
          conn.execute(
              text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}")
          )



with app.app_context():
  db.create_all()
  ensure_sqlite_columns()

def get_platform_config():
  cfg = PlatformConfig.query.first()
  if not cfg:
    cfg = PlatformConfig(
        subscription_amount=100.0,
        subscription_currency="USD",
        merchant_number=MOMO_MERCHANT_NUMBER,
    )
    db.session.add(cfg)
    db.session.commit()
  return cfg


def format_money(amount, currency="USD"):
  cur = (currency or "USD").upper()
  if cur == "LRD":
    return f"L${amount:,.2f} LRD"
  return f"${amount:,.2f} USD"


def ordinal(n):
  if 11 <= (n % 100) <= 13:
    suffix = "th"
  else:
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
  return f"{n}{suffix}"


def compute_class_rank(student):
  classmates = Student.query.filter_by(classroom_id=student.classroom_id).all()
  total_students = len(classmates)
  if total_students == 0:
    return "N/A", 0.0

  averages = []
  target_avg = 0.0
  for mate in classmates:
    m_grades = Grade.query.filter_by(student_id=mate.id).all()
    avg = (
        round(sum(g.score for g in m_grades) / len(m_grades), 2)
        if m_grades
        else 0.0
    )
    averages.append((mate.id, avg))
    if mate.id == student.id:
      target_avg = avg

  averages.sort(key=lambda item: item[1], reverse=True)
  rank_num = 1
  for idx, (sid, avg) in enumerate(averages, start=1):
    if idx > 1 and avg < averages[idx - 2][1]:
      rank_num = idx
    if sid == student.id:
      break

  return f"{ordinal(rank_num)} out of {total_students} students", target_avg


def school_logo_html(school, size=48):
  if school and school.logo_data:
    return (
        f'<img src="{school.logo_data}" alt="{school.name} logo" '
        f'style="width:{size}px;height:{size}px;object-fit:cover;border-radius:12px;border:1px solid #e5e7eb;">'
    )
  return (
      f'<div style="width:{size}px;height:{size}px;border-radius:12px;background:#eef2ff;color:#4f46e5;'
      'display:inline-flex;align-items:center;justify-content:center;font-weight:700;">'
      '<i class="fas fa-school"></i></div>'
  )


def render_super_broadcasts_banner():
  broadcasts = (
      SuperBroadcast.query.order_by(SuperBroadcast.id.desc()).limit(3).all()
  )
  if not broadcasts:
    return ""
  items = "".join([
      f'<div class="mb-1"><strong><i class="fas fa-bullhorn me-1"></i>{b.title}:</strong> {b.message} '
      f'<small class="text-muted">({b.created_at.strftime("%Y-%m-%d")})</small></div>'
      for b in broadcasts
  ])
  return f'<div class="alert alert-primary shadow-sm border-primary mb-3">{items}</div>'


def render_unread_dm_banner(receiver_key):
  unread = (
      DirectMessage.query.filter_by(receiver_key=receiver_key, is_read=False)
      .order_by(DirectMessage.id.desc())
      .all()
  )
  if not unread:
    return ""
  by_sender = {}
  for m in unread:
    if m.sender_key not in by_sender:
      by_sender[m.sender_key] = {
          "name": m.sender_name,
          "count": 0,
          "latest": m.body,
      }
    by_sender[m.sender_key]["count"] += 1

  chips = ""
  for skey, info in by_sender.items():
    preview = (
        info["latest"][:55] + "..."
        if len(info["latest"]) > 55
        else info["latest"]
    )
    chips += f"""
        <div class="d-flex justify-content-between align-items-center bg-white border rounded p-2 mb-1">
            <div>
                <span class="badge bg-danger me-1">{info['count']} new</span>
                <strong>{info['name']}</strong>: <span class="text-muted small">"{preview}"</span>
            </div>
            <a href="/chat?to={skey}" class="btn btn-sm btn-primary">Open & Reply</a>
        </div>
        """
  return f"""
    <div class="alert alert-warning border-warning shadow-sm mb-3">
        <div class="fw-bold mb-2"><i class="fas fa-bell text-danger me-1"></i>You have {len(unread)} unread direct message(s):</div>
        {chips}
    </div>
    """


def send_parent_alert(
    phone_number,
    message,
    student=None,
    parent_id=None,
    sender_label="Cashier",
    direction="to_parent",
):
  resolved_school_id = None
  resolved_parent_id = parent_id
  resolved_student_id = student.id if student else None

  if student:
    classroom = Classroom.query.get(student.classroom_id)
    if classroom:
      resolved_school_id = classroom.school_id
    if not resolved_parent_id and student.parent_id:
      resolved_parent_id = student.parent_id

  if resolved_parent_id and not resolved_school_id:
    pr = Parent.query.get(resolved_parent_id)
    if pr:
      resolved_school_id = pr.school_id

  if resolved_school_id:
    try:
      db.session.add(
          PortalMessage(
              school_id=resolved_school_id,
              parent_id=resolved_parent_id,
              student_id=resolved_student_id,
              sender_label=sender_label,
              direction=direction,
              body=message,
          )
      )
      db.session.commit()
    except Exception as exc:
      db.session.rollback()
      print(f"\n[PORTAL MESSAGE DB ERROR] {exc}\n")

  print("\n" + "=" * 60)
  print(f"🌐 [IN-PORTAL MESSAGE] Sender: {sender_label} | Dir: {direction}")
  if phone_number:
    print(f"   Contact on file: {phone_number}")
  print(f"📝 MESSAGE: {message}")
  print("=" * 60 + "\n")


def initiate_momo_request(phone_number, amount, currency, reference, tx_id=""):
  print("\n" + "=" * 60)
  print(f"💳 [MOMO COLLECTION RECORD] Ref: {reference} | TxID: {tx_id or 'N/A'}")
  print(f"   Payer: {phone_number} -> Merchant: {MOMO_MERCHANT_NUMBER}")
  print(f"   Amount: {format_money(amount, currency)}")
  print("=" * 60 + "\n")
  return True


def safe_commit(error_message="Database error (duplicate email or invalid data)."):
  try:
    db.session.commit()
    return True
  except IntegrityError:
    db.session.rollback()
    flash(error_message, "danger")
    return False


def get_school_for_student(student):
  classroom = Classroom.query.get(student.classroom_id)
  return School.query.get(classroom.school_id) if classroom else None


def check_school_access_or_lockout(school):
  if not school:
    flash("School record not found.", "danger")
    return redirect(url_for("home"))
  if not school.has_access():
    return render_template_string(
        BASE_HTML,
        content=f"""
        <div class="container mt-5" style="max-width: 560px;">
            <div class="card p-5 border-danger text-center">
                <i class="fas fa-lock fa-3x text-danger mb-3"></i>
                <h3 class="text-danger">Access Paused — Subscription Required</h3>
                <p class="text-muted mt-2"><strong>{school.name}</strong> is currently locked until subscription payment is approved by the platform owner.</p>
                <a href="/school/login" class="btn btn-primary mt-3"><i class="fas fa-school me-1"></i>School Admin Payment Portal</a>
            </div>
        </div>
        """,
    )
  return None


def get_current_chat_actor():
  if session.get("student_id"):
    st = Student.query.get(session["student_id"])
    if st:
      sch = get_school_for_student(st)
      return (
          sch.id if sch else None,
          f"student:{st.id}",
          f"{st.full_name} (Student)",
          "student",
          "/student/dashboard",
      )
  if session.get("parent_id"):
    pr = Parent.query.get(session["parent_id"])
    if pr:
      return (
          pr.school_id,
          f"parent:{pr.id}",
          f"{pr.full_name} (Parent)",
          "adult",
          "/parent/dashboard",
      )
  if session.get("teacher_id"):
    tc = Teacher.query.get(session["teacher_id"])
    if tc:
      return (
          tc.school_id,
          f"teacher:{tc.id}",
          f"{tc.full_name} (Teacher)",
          "adult",
          "/teacher/dashboard",
      )
  if session.get("cashier_id"):
    ca = Cashier.query.get(session["cashier_id"])
    if ca:
      return (
          ca.school_id,
          f"cashier:{ca.id}",
          f"{ca.full_name} (Cashier)",
          "adult",
          "/cashier/dashboard",
      )
  if session.get("school_id"):
    sch = School.query.get(session["school_id"])
    if sch:
      return (
          sch.id,
          f"principal:{sch.id}",
          f"Principal ({sch.name})",
          "adult",
          "/school/dashboard",
      )
  return None, None, None, None, "/"


@app.context_processor
def inject_unread_count():
  _, actor_key, _, _, _ = get_current_chat_actor()
  count = 0
  if actor_key:
    count = DirectMessage.query.filter_by(
        receiver_key=actor_key, is_read=False
    ).count()
  return {"nav_unread_count": count}


def get_allowed_chat_contacts(school_id, actor_key, role_group):
  contacts = []
  if role_group == "student":
    mates = (
        Student.query.join(Classroom)
        .filter(Classroom.school_id == school_id)
        .all()
    )
    for m in mates:
      key = f"student:{m.id}"
      if key != actor_key:
        cl = Classroom.query.get(m.classroom_id)
        unread_from = DirectMessage.query.filter_by(
            sender_key=key, receiver_key=actor_key, is_read=False
        ).count()
        contacts.append({
            "key": key,
            "name": m.full_name,
            "badge": f"Classmate • {cl.name if cl else ''}",
            "unread": unread_from,
        })
  else:
    sch = School.query.get(school_id)
    if sch and f"principal:{sch.id}" != actor_key:
      key = f"principal:{sch.id}"
      contacts.append({
          "key": key,
          "name": f"Principal ({sch.name})",
          "badge": "Principal / Admin",
          "unread": DirectMessage.query.filter_by(
              sender_key=key, receiver_key=actor_key, is_read=False
          ).count(),
      })
    for t in Teacher.query.filter_by(school_id=school_id).all():
      key = f"teacher:{t.id}"
      if key != actor_key:
        contacts.append({
            "key": key,
            "name": t.full_name,
            "badge": "Teacher",
            "unread": DirectMessage.query.filter_by(
                sender_key=key, receiver_key=actor_key, is_read=False
            ).count(),
        })
    for c in Cashier.query.filter_by(school_id=school_id).all():
      key = f"cashier:{c.id}"
      if key != actor_key:
        contacts.append({
            "key": key,
            "name": c.full_name,
            "badge": "Cashier",
            "unread": DirectMessage.query.filter_by(
                sender_key=key, receiver_key=actor_key, is_read=False
            ).count(),
        })
    for p in Parent.query.filter_by(school_id=school_id).all():
      key = f"parent:{p.id}"
      if key != actor_key:
        contacts.append({
            "key": key,
            "name": p.full_name,
            "badge": "Parent",
            "unread": DirectMessage.query.filter_by(
                sender_key=key, receiver_key=actor_key, is_read=False
            ).count(),
        })
  return contacts


# ==========================================
# 3. GLOBAL STYLES, SCROLLBOXES & PWA SHELL
# ==========================================
BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#4f46e5">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="EduSphere">
    <link rel="manifest" href="/manifest.json">
    <title>EduSphere SaaS</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background-color: #f3f4f6; font-family: 'Inter', sans-serif; color: #1f2937; }
        .navbar { background: linear-gradient(135deg, #4f46e5, #4338ca) !important; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
        .card { border: none; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.06); }
        .btn { border-radius: 8px; font-weight: 600; padding: 8px 16px; transition: all 0.2s; }
        .btn-sm { padding: 4px 10px; font-size: 0.82rem; }
        .btn-primary { background-color: #4f46e5; border-color: #4f46e5; }
        .btn-primary:hover { background-color: #4338ca; border-color: #4338ca; }
        .btn-success { background-color: #10b981; border-color: #10b981; }
        .table { background: white; border-radius: 12px; overflow: hidden; }
        .badge { padding: 5px 10px; border-radius: 20px; font-weight: 600; }
        .scroll-feed { max-height: 340px; overflow-y: auto; padding-right: 4px; }
        .chat-thread { max-height: 410px; overflow-y: auto; background: #f8fafc; border-radius: 12px; padding: 12px; border: 1px solid #e2e8f0; }
        .chat-bubble-me { background: #4f46e5; color: white; border-radius: 14px 14px 2px 14px; padding: 8px 12px; max-width: 80%; }
        .chat-bubble-them { background: white; color: #1f2937; border: 1px solid #e5e7eb; border-radius: 14px 14px 14px 2px; padding: 8px 12px; max-width: 80%; }
        .print-only { display: none; }
        @media print {
            body { background: white !important; }
            .navbar, .no-print, .btn, form { display: none !important; }
            .print-only { display: block !important; }
            .container { max-width: 100% !important; margin: 0 !important; padding: 0 !important; }
            .card { box-shadow: none !important; border: 1px solid #d1d5db !important; }
            .scroll-feed { max-height: none !important; overflow: visible !important; }
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark no-print">
        <div class="container">
            <a class="navbar-brand fw-bold" href="/"><i class="fas fa-graduation-cap me-2"></i>EduSphere</a>
            <div class="ms-auto d-flex gap-2 align-items-center">
                <a href="/chat" class="btn btn-light btn-sm text-primary position-relative">
                    <i class="fas fa-comments me-1"></i>Private Chat
                    {% if nav_unread_count > 0 %}
                        <span class="badge bg-danger ms-1">{{ nav_unread_count }}</span>
                    {% endif %}
                </a>
                <a href="/account/password" class="btn btn-outline-light btn-sm"><i class="fas fa-key me-1"></i>Password</a>
                <a href="/logout" class="btn btn-outline-light btn-sm"><i class="fas fa-sign-out-alt me-1"></i>Logout</a>
            </div>
        </div>
    </nav>
    <div class="container mt-4 pb-5">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }} shadow-sm no-print"><i class="fas fa-info-circle me-2"></i>{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {{ content | safe }}
    </div>
    <script>
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', function() {
                navigator.serviceWorker.register('/sw.js').catch(function() {});
            });
        }
    </script>
</body>
</html>
"""


@app.route("/manifest.json")
def pwa_manifest():
  manifest = """{
  "name": "EduSphere School Portal",
  "short_name": "EduSphere",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#f3f4f6",
  "theme_color": "#4f46e5",
  "description": "School management, fees, grades, and private school chat portal.",
  "icons": [
    {
      "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 192 192'%3E%3Crect width='192' height='192' rx='36' fill='%234f46e5'/%3E%3Ctext x='96' y='122' font-size='96' text-anchor='middle' fill='white' font-family='Arial'%3EE%3C/text%3E%3C/svg%3E",
      "sizes": "192x192",
      "type": "image/svg+xml"
    },
    {
      "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'%3E%3Crect width='512' height='512' rx='96' fill='%234f46e5'/%3E%3Ctext x='256' y='325' font-size='256' text-anchor='middle' fill='white' font-family='Arial'%3EE%3C/text%3E%3C/svg%3E",
      "sizes": "512x512",
      "type": "image/svg+xml"
    }
  ]
}"""
  return Response(manifest, mimetype="application/manifest+json")


@app.route("/sw.js")
def pwa_sw():
  sw_code = """
self.addEventListener('install', function(event) {
  self.skipWaiting();
});
self.addEventListener('activate', function(event) {
  event.waitUntil(clients.claim());
});
self.addEventListener('fetch', function(event) {
  event.respondWith(fetch(event.request));
});
"""
  return Response(sw_code, mimetype="application/javascript")


# ==========================================
# 4. HOME, AUTH & PASSWORD CHANGE
# ==========================================
@app.route("/")
def home():
  cfg = get_platform_config()
  content = f"""
    <div class="text-center mt-4 mb-5">
        <h1 class="display-4 fw-bold text-primary mb-2"><i class="fas fa-graduation-cap me-2"></i>EduSphere</h1>
        <p class="lead text-muted mb-2">Multi-Tenant School Management, Academic, Fee & Private Chat Platform</p>
        <span class="badge bg-light text-dark border mb-4">30-Day Free Trial • Subscription: {format_money(cfg.subscription_amount, cfg.subscription_currency)}/mo • Installable on Mobile</span>

        <div class="row justify-content-center mb-4">
            <div class="col-md-5 mb-3">
                <div class="card p-4 text-center h-100">
                    <i class="fas fa-school fa-3x text-primary mb-3"></i>
                    <h4>School Admin (Principal)</h4>
                    <p class="text-muted small">Upload school logo, manage classes, reassign teachers, parents, student lookup & messages.</p>
                    <a href="/school/login" class="btn btn-primary mt-auto">School Admin Login</a>
                </div>
            </div>
            <div class="col-md-5 mb-3">
                <div class="card p-4 text-center h-100">
                    <i class="fas fa-calculator fa-3x text-success mb-3"></i>
                    <h4>Cashier Portal</h4>
                    <p class="text-muted small">Set USD/LRD fees, record installment receipts, view parent replies & message parents.</p>
                    <a href="/cashier/login" class="btn btn-success mt-auto">Cashier Login</a>
                </div>
            </div>
        </div>

        <div class="row justify-content-center mt-3">
            <div class="col-md-3"><a href="/teacher/login" class="btn btn-outline-dark w-100 mb-2"><i class="fas fa-chalkboard-teacher me-2"></i>Teacher Login</a></div>
            <div class="col-md-3"><a href="/student/login" class="btn btn-outline-dark w-100 mb-2"><i class="fas fa-user-graduate me-2"></i>Student Login</a></div>
            <div class="col-md-3"><a href="/parent/login" class="btn btn-outline-dark w-100 mb-2"><i class="fas fa-users me-2"></i>Parent Login</a></div>
        </div>

        <div class="mt-4">
            <a href="/admin/login" class="text-muted small text-decoration-none"><i class="fas fa-crown me-1"></i> Owner (Super Admin) Login</a>
        </div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/logout")
def logout():
  session.clear()
  flash("Logged out successfully.", "info")
  return redirect(url_for("home"))


@app.route("/account/password", methods=["GET", "POST"])
def change_password():
  school_id, actor_key, actor_name, _, dash_url = get_current_chat_actor()
  if not actor_key:
    flash("Please log in first to change your password.", "warning")
    return redirect(url_for("home"))

  if request.method == "POST":
    new_pw = request.form["new_password"].strip()
    if len(new_pw) < 4:
      flash("Password must be at least 4 characters.", "danger")
      return redirect(url_for("change_password"))
    hashed = bcrypt.generate_password_hash(new_pw).decode("utf-8")
    role, raw_id = actor_key.split(":")
    uid = int(raw_id)
    if role == "student":
      obj = Student.query.get(uid)
      obj.password = hashed
    elif role == "parent":
      obj = Parent.query.get(uid)
      obj.password = hashed
    elif role == "teacher":
      obj = Teacher.query.get(uid)
      obj.password = hashed
    elif role == "cashier":
      obj = Cashier.query.get(uid)
      obj.password = hashed
    elif role == "principal":
      obj = School.query.get(uid)
      obj.admin_password = hashed
    db.session.commit()
    flash("Password updated successfully!", "success")
    return redirect(dash_url)

  content = f"""
    <div class="container mt-5" style="max-width: 420px;">
        <div class="card p-4">
            <h4 class="mb-2"><i class="fas fa-key text-primary me-2"></i>Change Password</h4>
            <p class="text-muted small mb-3">Signed in as <strong>{actor_name}</strong></p>
            <form method="POST">
                <input type="password" name="new_password" class="form-control mb-3" placeholder="Enter New Password" required>
                <button class="btn btn-primary w-100">Update Password</button>
            </form>
            <a href="{dash_url}" class="btn btn-link btn-sm mt-2">Back to Dashboard</a>
        </div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


# ==========================================
# 5. SUPER ADMIN (OWNER + BROADCASTS + FULL DELETE)
# ==========================================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
  if request.method == "POST":
    if (
        request.form["email"] == SUPER_ADMIN_EMAIL
        and request.form["password"] == SUPER_ADMIN_PASSWORD
    ):
      session["is_super_admin"] = True
      return redirect(url_for("admin_dashboard"))
    flash("Invalid Credentials", "danger")
  content = """
    <div class="container mt-5" style="max-width: 400px;"><div class="card p-4"><h3 class="text-center mb-4">Super Admin Login</h3>
    <form method="POST"><input class="form-control mb-3" name="email" placeholder="Owner Email" required>
    <input class="form-control mb-3" name="password" type="password" placeholder="Password" required>
    <button class="btn btn-primary w-100">Login</button></form></div></div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/admin/update_subscription_pricing", methods=["POST"])
def update_subscription_pricing():
  if not session.get("is_super_admin"):
    return redirect(url_for("admin_login"))
  cfg = get_platform_config()
  cfg.subscription_amount = float(request.form["amount"])
  cfg.subscription_currency = request.form["currency"]
  db.session.commit()
  flash(
      "Updated monthly subscription to"
      f" {format_money(cfg.subscription_amount, cfg.subscription_currency)}.",
      "success",
  )
  return redirect(url_for("admin_dashboard"))


@app.route("/admin/broadcast", methods=["POST"])
def admin_broadcast():
  if not session.get("is_super_admin"):
    return redirect(url_for("admin_login"))
  title = request.form["title"].strip()
  message = request.form["message"].strip()
  if title and message:
    db.session.add(SuperBroadcast(title=title, message=message))
    db.session.commit()
    flash("Broadcast message published to all schools.", "success")
  return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete_broadcast/<int:broadcast_id>")
def admin_delete_broadcast(broadcast_id):
  if not session.get("is_super_admin"):
    return redirect(url_for("admin_login"))
  b = SuperBroadcast.query.get_or_404(broadcast_id)
  db.session.delete(b)
  db.session.commit()
  flash("Broadcast deleted.", "info")
  return redirect(url_for("admin_dashboard"))


@app.route("/admin/toggle_school/<int:school_id>")
def toggle_school_access(school_id):
  if not session.get("is_super_admin"):
    return redirect(url_for("admin_login"))
  school = School.query.get_or_404(school_id)
  school.is_active = not school.is_active
  if school.is_active and (
      not school.trial_end_date or datetime.utcnow() > school.trial_end_date
  ):
    school.trial_end_date = datetime.utcnow() + timedelta(days=30)
  db.session.commit()
  flash(
      f"{school.name} status updated ({'Active' if school.is_active else 'Locked'}).",
      "info",
  )
  return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete_school/<int:school_id>")
def admin_delete_school(school_id):
  if not session.get("is_super_admin"):
    return redirect(url_for("admin_login"))
  school = School.query.get_or_404(school_id)
  classrooms = Classroom.query.filter_by(school_id=school.id).all()
  for c in classrooms:
    students = Student.query.filter_by(classroom_id=c.id).all()
    for s in students:
      Attendance.query.filter_by(student_id=s.id).delete()
      Grade.query.filter_by(student_id=s.id).delete()
      AssessmentRecord.query.filter_by(student_id=s.id).delete()
      FeeRecord.query.filter_by(student_id=s.id).delete()
      FeeTransaction.query.filter_by(student_id=s.id).delete()
      db.session.delete(s)
    Assignment.query.filter_by(classroom_id=c.id).delete()
    db.session.delete(c)
  Teacher.query.filter_by(school_id=school.id).delete()
  Cashier.query.filter_by(school_id=school.id).delete()
  Parent.query.filter_by(school_id=school.id).delete()
  Announcement.query.filter_by(school_id=school.id).delete()
  PaymentRequest.query.filter_by(school_id=school.id).delete()
  PortalMessage.query.filter_by(school_id=school.id).delete()
  DirectMessage.query.filter_by(school_id=school.id).delete()
  db.session.delete(school)
  db.session.commit()
  flash(f"School '{school.name}' and all its records were deleted.", "info")
  return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete_payment/<int:payment_id>")
def admin_delete_payment(payment_id):
  if not session.get("is_super_admin"):
    return redirect(url_for("admin_login"))
  req = PaymentRequest.query.get_or_404(payment_id)
  db.session.delete(req)
  db.session.commit()
  flash("Payment request deleted.", "info")
  return redirect(url_for("admin_dashboard"))


@app.route("/admin/dashboard")
def admin_dashboard():
  if not session.get("is_super_admin"):
    return redirect(url_for("admin_login"))
  cfg = get_platform_config()
  schools = School.query.all()
  payments = PaymentRequest.query.order_by(PaymentRequest.id.desc()).all()
  broadcasts = SuperBroadcast.query.order_by(SuperBroadcast.id.desc()).all()

  school_rows = ""
  for s in schools:
    status = (
        '<span class="badge bg-success">Active</span>'
        if s.has_access()
        else '<span class="badge bg-danger">Blocked / Locked</span>'
    )
    toggle_label = "Block" if s.is_active else "Unlock"
    school_rows += f"""
        <tr>
            <td>{school_logo_html(s, 36)} <strong class="ms-1">{s.name}</strong></td>
            <td>{s.admin_email}</td>
            <td>{status}</td>
            <td class="d-flex gap-1">
                <a href="/admin/toggle_school/{s.id}" class="btn btn-sm btn-outline-warning text-dark">{toggle_label}</a>
                <a href="/admin/delete_school/{s.id}" onclick="return confirm('Delete this school and all its data?');" class="btn btn-sm btn-outline-danger"><i class="fas fa-trash"></i></a>
            </td>
        </tr>
        """

  payment_rows = ""
  for p in payments:
    school = School.query.get(p.school_id)
    badge = (
        '<span class="badge bg-success">Approved</span>'
        if p.status == "Approved"
        else '<span class="badge bg-warning text-dark">Pending</span>'
    )
    approve_btn = (
        f"<a href='/admin/approve_payment/{p.id}' class='btn btn-sm btn-success'>Approve</a>"
        if p.status == "Pending"
        else ""
    )
    payment_rows += f"""
        <tr>
            <td><strong>{school.name if school else 'School'}</strong><br><small class="text-muted">{p.provider or 'MoMo'} • {p.payer_phone or '-'}</small></td>
            <td>{format_money(p.amount, p.currency)}<br><small class="text-muted">TxID: {p.momo_tx_id or p.reference}</small></td>
            <td>{badge}</td>
            <td class="d-flex gap-1">
                {approve_btn}
                <a href='/admin/delete_payment/{p.id}' class='btn btn-sm btn-outline-danger'><i class="fas fa-trash"></i></a>
            </td>
        </tr>
        """

  broadcast_rows = "".join([
      f"""
        <li class="list-group-item d-flex justify-content-between align-items-start gap-2">
            <div><strong>{b.title}</strong> <small class="text-muted">({b.created_at.strftime('%Y-%m-%d')})</small><br><span class="small">{b.message}</span></div>
            <a href="/admin/delete_broadcast/{b.id}" class="btn btn-sm btn-outline-danger"><i class="fas fa-trash"></i></a>
        </li>
        """
      for b in broadcasts
  ])

  usd_selected = "selected" if cfg.subscription_currency == "USD" else ""
  lrd_selected = "selected" if cfg.subscription_currency == "LRD" else ""

  content = f"""
    <div class="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-2">
        <h2><i class="fas fa-crown text-warning me-2"></i>Super Admin Dashboard</h2>
        <a href="/admin/register_school" class="btn btn-success"><i class="fas fa-plus me-2"></i>Register School</a>
    </div>

    <div class="row mb-4">
        <div class="col-md-6 mb-3">
            <div class="card p-4 h-100 border-primary">
                <h5><i class="fas fa-sliders-h text-primary me-2"></i>Subscription Rate & Merchant Wallet</h5>
                <p class="text-muted small mb-3">Wallet: <strong>{cfg.merchant_number}</strong> • Rate: <strong>{format_money(cfg.subscription_amount, cfg.subscription_currency)}</strong>/mo</p>
                <form method="POST" action="/admin/update_subscription_pricing" class="row g-2 align-items-center">
                    <div class="col-4"><input type="number" step="0.01" min="0.01" name="amount" class="form-control" value="{cfg.subscription_amount}" required></div>
                    <div class="col-4">
                        <select name="currency" class="form-select">
                            <option value="USD" {usd_selected}>USD ($)</option>
                            <option value="LRD" {lrd_selected}>LRD (L$)</option>
                        </select>
                    </div>
                    <div class="col-4"><button type="submit" class="btn btn-primary w-100">Save</button></div>
                </form>
            </div>
        </div>
        <div class="col-md-6 mb-3">
            <div class="card p-4 h-100 border-info">
                <h5><i class="fas fa-bullhorn text-info me-2"></i>Send Message to All Schools</h5>
                <form method="POST" action="/admin/broadcast" class="mb-2">
                    <input type="text" name="title" class="form-control form-control-sm mb-2" placeholder="Notice Title (e.g., System Update)" required>
                    <div class="d-flex gap-2">
                        <input type="text" name="message" class="form-control form-control-sm" placeholder="Message shown on every school dashboard..." required>
                        <button type="submit" class="btn btn-info text-white btn-sm">Send</button>
                    </div>
                </form>
                <div class="scroll-feed" style="max-height:130px;">
                    <ul class="list-group">{broadcast_rows or '<li class="list-group-item text-muted small">No global broadcasts yet.</li>'}</ul>
                </div>
            </div>
        </div>
    </div>

    <div class="row">
        <div class="col-md-7 mb-3">
            <div class="card p-4">
                <h4><i class="fas fa-school text-primary me-2"></i>Registered Schools (Block / Unlock)</h4>
                <div class="table-responsive mt-2">
                    <table class="table table-hover align-middle"><thead class="table-light"><tr><th>School</th><th>Email</th><th>Status</th><th>Action</th></tr></thead><tbody>{school_rows or '<tr><td colspan="4">No schools yet.</td></tr>'}</tbody></table>
                </div>
            </div>
        </div>
        <div class="col-md-5 mb-3">
            <div class="card p-4 border-warning">
                <h4><i class="fas fa-money-bill-wave text-warning me-2"></i>Subscription Payments</h4>
                <div class="table-responsive mt-2">
                    <table class="table table-hover align-middle"><thead class="table-light"><tr><th>School</th><th>Payment</th><th>Status</th><th>Action</th></tr></thead><tbody>{payment_rows or '<tr><td colspan="4">No payment requests yet.</td></tr>'}</tbody></table>
                </div>
            </div>
        </div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/admin/register_school", methods=["GET", "POST"])
def admin_register_school():
  if not session.get("is_super_admin"):
    return redirect(url_for("admin_login"))
  if request.method == "POST":
    hashed = bcrypt.generate_password_hash(request.form["password"]).decode(
        "utf-8"
    )
    start_active = request.form.get("start_mode", "trial") == "trial"
    db.session.add(
        School(
            name=request.form["name"],
            admin_email=request.form["email"],
            admin_password=hashed,
            is_active=start_active,
        )
    )
    if safe_commit("That school admin email is already registered."):
      flash(
          f"School '{request.form['name']}' created ({'30-Day Trial' if start_active else 'Locked Until Payment'}).",
          "success",
      )
      return redirect(url_for("admin_dashboard"))
  content = """
    <div class="container mt-5" style="max-width: 500px;"><div class="card p-4"><h3>Register New School</h3>
    <form method="POST">
        <input class="form-control mb-3" name="name" placeholder="School Name" required>
        <input class="form-control mb-3" name="email" placeholder="School Admin Email" required>
        <input class="form-control mb-3" name="password" type="password" placeholder="Admin Password" required>
        <label class="form-label small text-muted">Initial Access Mode</label>
        <select name="start_mode" class="form-select mb-3">
            <option value="trial">Active (30-Day Free Trial)</option>
            <option value="locked">Blocked / Locked Until Payment Approved</option>
        </select>
        <button class="btn btn-success w-100">Create School</button>
    </form></div></div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/admin/approve_payment/<int:payment_id>")
def approve_payment(payment_id):
  if not session.get("is_super_admin"):
    return redirect(url_for("admin_login"))
  req = PaymentRequest.query.get_or_404(payment_id)
  school = School.query.get(req.school_id)
  if school:
    base_dt = (
        school.subscription_end_date
        if school.subscription_end_date
        and school.subscription_end_date > datetime.utcnow()
        else datetime.utcnow()
    )
    school.subscription_end_date = base_dt + timedelta(days=30)
    school.is_active = True
  req.status = "Approved"
  db.session.commit()
  flash(
      f"Approved payment for {school.name if school else 'school'} (+30 days).",
      "success",
  )
  return redirect(url_for("admin_dashboard"))


# ==========================================
# 6. SCHOOL ADMIN (PRINCIPAL + LOGO + TEACHER REASSIGN + NOTIFICATIONS)
# ==========================================
@app.route("/school/login", methods=["GET", "POST"])
def school_login():
  if request.method == "POST":
    school = School.query.filter_by(admin_email=request.form["email"]).first()
    if school and bcrypt.check_password_hash(
        school.admin_password, request.form["password"]
    ):
      session.clear()
      session["school_id"] = school.id
      session["school_name"] = school.name
      return redirect(url_for("school_dashboard"))
    flash("Invalid Credentials", "danger")
  content = """
    <div class="container mt-5" style="max-width: 400px;"><div class="card p-4"><h3 class="text-center mb-4">School Admin Login</h3>
    <form method="POST"><input class="form-control mb-3" name="email" placeholder="Email" required>
    <input class="form-control mb-3" name="password" type="password" placeholder="Password" required>
    <button class="btn btn-primary w-100">Login</button></form></div></div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/school/upload_logo", methods=["POST"])
def school_upload_logo():
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  school = School.query.get(session["school_id"])
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked

  file = request.files.get("logo")
  if not file or not file.filename:
    flash("Please choose an image file first.", "warning")
    return redirect(url_for("school_dashboard"))

  mime = file.mimetype or "image/png"
  if not mime.startswith("image/"):
    flash("Only image files (PNG, JPG, WEBP) are allowed.", "danger")
    return redirect(url_for("school_dashboard"))

  raw = file.read()
  b64 = base64.b64encode(raw).decode("utf-8")
  school.logo_data = f"data:{mime};base64,{b64}"
  db.session.commit()
  flash("School logo updated!", "success")
  return redirect(url_for("school_dashboard"))


@app.route("/school/send_parent_message", methods=["POST"])
def school_send_parent_message():
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  school = School.query.get(session["school_id"])
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked

  parent_id = int(request.form["parent_id"])
  msg_text = request.form["message"].strip()
  parent = Parent.query.filter_by(id=parent_id, school_id=school.id).first()
  if not parent or not msg_text:
    flash("Select a valid parent and enter a message.", "warning")
    return redirect(url_for("school_dashboard"))

  child = Student.query.filter_by(parent_id=parent.id).first()
  send_parent_alert(
      parent.phone or (child.parent_contact if child else ""),
      msg_text,
      student=child,
      parent_id=parent.id,
      sender_label="Principal",
      direction="to_parent",
  )
  flash(f"Message delivered to {parent.full_name}'s portal inbox.", "success")
  return redirect(url_for("school_dashboard"))


@app.route("/school/delete_message/<int:msg_id>")
def school_delete_message(msg_id):
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  msg = PortalMessage.query.filter_by(
      id=msg_id, school_id=session["school_id"]
  ).first_or_404()
  db.session.delete(msg)
  db.session.commit()
  flash("Message deleted.", "info")
  return redirect(url_for("school_dashboard"))


@app.route("/school/delete_announcement/<int:ann_id>")
def school_delete_announcement(ann_id):
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  ann = Announcement.query.filter_by(
      id=ann_id, school_id=session["school_id"]
  ).first_or_404()
  db.session.delete(ann)
  db.session.commit()
  flash("Announcement deleted.", "info")
  return redirect(url_for("school_dashboard"))


@app.route("/school/dashboard")
def school_dashboard():
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  school = School.query.get(session["school_id"])
  cfg = get_platform_config()
  if not school.has_access():
    return redirect(url_for("school_subscribe"))

  search_q = request.args.get("q", "").strip()
  search_results_html = ""
  if search_q:
    pattern = f"%{search_q}%"
    matched_students = (
        Student.query.join(Classroom)
        .filter(Classroom.school_id == school.id)
        .filter(
            (Student.full_name.ilike(pattern)) | (Student.email.ilike(pattern))
        )
        .all()
    )
    if matched_students:
      m_rows = ""
      for st in matched_students:
        cl = Classroom.query.get(st.classroom_id)
        parent = Parent.query.get(st.parent_id) if st.parent_id else None
        fee = FeeRecord.query.filter_by(student_id=st.id).first()
        cur = fee.currency if fee else "USD"
        total = fee.total_fees if fee else 0.0
        paid = fee.amount_paid if fee else 0.0
        bal = max(0.0, total - paid)
        f_badge = (
            '<span class="badge bg-success">Cleared</span>'
            if bal <= 0
            else f'<span class="badge bg-warning text-dark">Bal: {format_money(bal, cur)}</span>'
        )
        m_rows += f"""
                <tr>
                    <td><strong>{st.full_name}</strong><br><small class="text-muted">{st.email}</small></td>
                    <td>{cl.name if cl else 'N/A'}</td>
                    <td>{parent.full_name if parent else 'Unlinked'}<br><small class="text-muted">{st.parent_contact or '-'}</small></td>
                    <td>{f_badge}</td>
                    <td>
                        <a href="/report_card/{st.id}" class="btn btn-sm btn-outline-primary mb-1">Report</a>
                        <a href="/receipt/{st.id}" class="btn btn-sm btn-outline-success mb-1">Receipt</a>
                    </td>
                </tr>
                """
      search_results_html = f"""
            <div class="table-responsive mt-3">
                <table class="table table-sm table-bordered align-middle mb-0">
                    <thead class="table-light"><tr><th>Student</th><th>Class</th><th>Parent</th><th>Fees</th><th>Records</th></tr></thead>
                    <tbody>{m_rows}</tbody>
                </table>
            </div>
            """
    else:
      search_results_html = f'<p class="text-muted small mt-2 mb-0">No student matched "<strong>{search_q}</strong>".</p>'

  classrooms = Classroom.query.filter_by(school_id=school.id).all()
  parents = Parent.query.filter_by(school_id=school.id).all()
  announcements = (
      Announcement.query.filter_by(school_id=school.id)
      .order_by(Announcement.date_posted.desc())
      .all()
  )
  inbox_msgs = (
      PortalMessage.query.filter_by(school_id=school.id)
      .order_by(PortalMessage.id.desc())
      .all()
  )

  total_students = (
      Student.query.join(Classroom)
      .filter(Classroom.school_id == school.id)
      .count()
  )
  total_teachers = Teacher.query.filter_by(school_id=school.id).count()
  total_parents = len(parents)

  class_cards = "".join([
      f'<div class="col-md-4 mb-3"><div class="card p-3 text-center"><i class="fas fa-chalkboard fa-2x text-secondary mb-2"></i><h5>{c.name}</h5><a href="/school/view_class/{c.id}" class="btn btn-sm btn-outline-primary w-100 mt-2">Manage Students</a></div></div>'
      for c in classrooms
  ])
  ann_list = "".join([
      f"""
        <li class='list-group-item d-flex justify-content-between align-items-start gap-2'>
            <div><small class='text-muted'>{a.date_posted.strftime('%Y-%m-%d')} • {a.author_label}</small><br>{a.message}</div>
            <a href='/school/delete_announcement/{a.id}' class='btn btn-sm btn-outline-danger'><i class='fas fa-trash'></i></a>
        </li>
        """
      for a in announcements
  ])

  parent_opts = "".join([
      f"<option value='{p.id}'>{p.full_name} ({p.email})</option>"
      for p in parents
  ])
  inbox_html = "".join([
      f"""
        <li class='list-group-item d-flex justify-content-between align-items-start gap-2'>
            <div>
                <small class='text-muted'>{m.created_at.strftime('%Y-%m-%d %H:%M')} • <strong>{m.sender_label}</strong></small><br>
                <span>{m.body}</span>
            </div>
            <a href='/school/delete_message/{m.id}' class='btn btn-sm btn-outline-danger'><i class='fas fa-trash'></i></a>
        </li>
        """
      for m in inbox_msgs
  ])

  trial_days = max(0, (school.trial_end_date - datetime.utcnow()).days)
  banner = ""
  if not school.subscription_end_date:
    banner = f"<div class='alert alert-warning shadow-sm'><i class='fas fa-exclamation-triangle me-2'></i><strong>Trial ends in {trial_days} days.</strong> <a href='/school/subscribe' class='btn btn-sm btn-dark ms-2'>Subscribe ({format_money(cfg.subscription_amount, cfg.subscription_currency)}/mo)</a></div>"

  content = f"""
    {render_super_broadcasts_banner()}
    {render_unread_dm_banner(f"principal:{school.id}")}
    {banner}
    <div class="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-2">
        <div class="d-flex align-items-center gap-3">
            {school_logo_html(school, 56)}
            <div>
                <h2 class="mb-0">{school.name}</h2>
                <small class="text-muted">Principal / School Admin Portal</small>
            </div>
        </div>
        <div class="d-flex flex-wrap gap-2">
            <a href="/school/manage_parents" class="btn btn-dark"><i class="fas fa-users me-1"></i>Parents & Link</a>
            <a href="/school/manage_teachers" class="btn btn-warning text-dark"><i class="fas fa-chalkboard-teacher me-1"></i>Teachers</a>
            <a href="/school/manage_cashiers" class="btn btn-info text-white"><i class="fas fa-calculator me-1"></i>Cashiers</a>
            <a href="/school/add_class" class="btn btn-primary"><i class="fas fa-plus me-1"></i>Class</a>
            <a href="/school/subscribe" class="btn btn-outline-success"><i class="fas fa-mobile-alt me-1"></i>Subscription</a>
        </div>
    </div>

    <div class="row mb-4">
        <div class="col-md-7 mb-3">
            <div class="card p-4 h-100 border-primary">
                <h5><i class="fas fa-search text-primary me-2"></i>Quick Student Lookup</h5>
                <form method="GET" action="/school/dashboard" class="row g-2 mt-1">
                    <div class="col-8">
                        <input type="text" name="q" class="form-control" placeholder="Search student by name or email..." value="{search_q}">
                    </div>
                    <div class="col-4 d-flex gap-1">
                        <button type="submit" class="btn btn-primary w-100">Search</button>
                        {"<a href='/school/dashboard' class='btn btn-outline-secondary'>Clear</a>" if search_q else ""}
                    </div>
                </form>
                {search_results_html}
            </div>
        </div>
        <div class="col-md-5 mb-3">
            <div class="card p-4 h-100">
                <h5><i class="fas fa-image text-primary me-2"></i>School Logo / Profile Image</h5>
                <form method="POST" action="/school/upload_logo" enctype="multipart/form-data" class="d-flex gap-2 mt-2">
                    <input type="file" name="logo" accept="image/*" class="form-control form-control-sm" required>
                    <button type="submit" class="btn btn-sm btn-primary">Upload</button>
                </form>
                <small class="text-muted mt-2">Appears on dashboards, report cards, and fee receipts.</small>
            </div>
        </div>
    </div>

    <div class="row mb-4">
        <div class="col-md-4 mb-2"><div class="card p-3 text-center bg-primary text-white"><h3>{total_students}</h3><p class="mb-0">Total Students</p></div></div>
        <div class="col-md-4 mb-2"><div class="card p-3 text-center bg-warning text-dark"><h3>{total_teachers}</h3><p class="mb-0">Total Teachers</p></div></div>
        <div class="col-md-4 mb-2"><div class="card p-3 text-center bg-dark text-white"><h3>{total_parents}</h3><p class="mb-0">Linked Parents</p></div></div>
    </div>

    <div class="row">
        <div class="col-md-7 mb-3">
            <h4>Class Sections</h4>
            <div class="row">{class_cards or '<p class="text-muted">No classes yet. Click "+ Class" to add one.</p>'}</div>

            <div class="card p-4 mt-3">
                <h5><i class="fas fa-envelope-open-text text-primary me-2"></i>Principal ↔ Parent Portal Messages</h5>
                <form method="POST" action="/school/send_parent_message" class="mt-2 mb-3">
                    <select name="parent_id" class="form-select mb-2" required>
                        <option value="">-- Choose Parent --</option>
                        {parent_opts}
                    </select>
                    <textarea name="message" class="form-control mb-2" placeholder="Write a message to this parent (appears in their portal)..." required></textarea>
                    <button type="submit" class="btn btn-primary w-100">Send Message to Parent Portal</button>
                </form>
                <strong class="small text-muted">Scrollable Message History:</strong>
                <div class="scroll-feed mt-2">
                    <ul class="list-group">{inbox_html or '<li class="list-group-item text-muted">No messages yet.</li>'}</ul>
                </div>
            </div>
        </div>
        <div class="col-md-5 mb-3">
            <div class="card p-4 mb-3">
                <h5><i class="fas fa-bullhorn me-2"></i>Announcements</h5>
                <form method="POST" action="/school/announcements" class="mb-3">
                    <textarea name="message" class="form-control mb-2" placeholder="Post message for everyone..." required></textarea>
                    <button class="btn btn-primary w-100">Post</button>
                </form>
                <div class="scroll-feed">
                    <ul class="list-group">{ann_list or '<li class="list-group-item text-muted">No announcements yet.</li>'}</ul>
                </div>
            </div>
        </div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/school/manage_parents", methods=["GET", "POST"])
def manage_parents():
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  school = School.query.get(session["school_id"])
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked

  if request.method == "POST":
    action = request.form.get("action", "create_parent")
    if action == "create_parent":
      hashed = bcrypt.generate_password_hash(request.form["password"]).decode(
          "utf-8"
      )
      parent = Parent(
          school_id=school.id,
          full_name=request.form["full_name"],
          email=request.form["email"],
          phone=request.form.get("phone", ""),
          password=hashed,
      )
      db.session.add(parent)
      db.session.flush()
      child_id = request.form.get("student_id")
      if child_id:
        st = Student.query.get(int(child_id))
        if st:
          st.parent_id = parent.id
          if parent.phone:
            st.parent_contact = parent.phone
      if safe_commit("A parent with that email already exists."):
        flash("Parent account created and child linked.", "success")
    elif action == "link_child":
      parent_id = int(request.form["parent_id"])
      student_id = int(request.form["student_id"])
      parent = Parent.query.filter_by(id=parent_id, school_id=school.id).first()
      st = Student.query.get(student_id)
      if parent and st:
        st.parent_id = parent.id
        if parent.phone:
          st.parent_contact = parent.phone
        db.session.commit()
        flash(f"Linked {st.full_name} to {parent.full_name}.", "success")
    return redirect(url_for("manage_parents"))

  parents = Parent.query.filter_by(school_id=school.id).all()
  school_students = (
      Student.query.join(Classroom)
      .filter(Classroom.school_id == school.id)
      .all()
  )

  parent_rows = ""
  for p in parents:
    children = Student.query.filter_by(parent_id=p.id).all()
    c_names = ", ".join([c.full_name for c in children]) or "None linked"
    parent_rows += f"""
        <tr>
            <td><strong>{p.full_name}</strong><br><small class="text-muted">{p.email}</small></td>
            <td>{p.phone or '-'}</td>
            <td>{c_names}</td>
        </tr>
        """

  parent_opts = "".join(
      [f"<option value='{p.id}'>{p.full_name} ({p.email})</option>" for p in parents]
  )
  student_opts = "".join([
      f"<option value='{s.id}'>{s.full_name} ({s.email})</option>"
      for s in school_students
  ])

  content = f"""
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h3><i class="fas fa-users me-2"></i>Parents & Student Linking</h3>
        <a href="/school/dashboard" class="btn btn-outline-secondary btn-sm">Back to Dashboard</a>
    </div>
    <div class="row">
        <div class="col-md-6 mb-3">
            <div class="card p-4 mb-3">
                <h5>Create Parent Account</h5>
                <form method="POST">
                    <input type="hidden" name="action" value="create_parent">
                    <input class="form-control mb-2" name="full_name" placeholder="Parent Full Name" required>
                    <input class="form-control mb-2" name="email" type="email" placeholder="Parent Login Email" required>
                    <input class="form-control mb-2" name="phone" placeholder="Parent Phone (optional)">
                    <input class="form-control mb-2" name="password" type="password" placeholder="Password" required>
                    <label class="form-label small text-muted">Link Child Now (Optional)</label>
                    <select class="form-select mb-3" name="student_id">
                        <option value="">-- Select Student --</option>
                        {student_opts}
                    </select>
                    <button class="btn btn-primary w-100">Create Parent</button>
                </form>
            </div>
            <div class="card p-4">
                <h5>Link Existing Child to Parent</h5>
                <form method="POST">
                    <input type="hidden" name="action" value="link_child">
                    <select class="form-select mb-2" name="parent_id" required>
                        <option value="">-- Choose Parent --</option>
                        {parent_opts}
                    </select>
                    <select class="form-select mb-3" name="student_id" required>
                        <option value="">-- Choose Student --</option>
                        {student_opts}
                    </select>
                    <button class="btn btn-success w-100">Link Child</button>
                </form>
            </div>
        </div>
        <div class="col-md-6 mb-3">
            <div class="card p-4">
                <h5>School Parents</h5>
                <table class="table table-hover mt-2">
                    <thead class="table-light"><tr><th>Parent</th><th>Phone</th><th>Linked Children</th></tr></thead>
                    <tbody>{parent_rows or '<tr><td colspan="3">No parents created yet.</td></tr>'}</tbody>
                </table>
            </div>
        </div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/school/add_class", methods=["GET", "POST"])
def add_class():
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  school = School.query.get(session["school_id"])
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked
  if request.method == "POST":
    db.session.add(Classroom(school_id=school.id, name=request.form["name"]))
    db.session.commit()
    flash("Class added.", "success")
    return redirect(url_for("school_dashboard"))
  content = """
    <div class="container mt-5" style="max-width: 400px;"><div class="card p-4"><h4>Add Classroom</h4>
    <form method="POST"><input class="form-control mb-3" name="name" placeholder="e.g., Grade 12 A" required>
    <button class="btn btn-primary w-100">Save Class</button></form></div></div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/school/view_class/<int:class_id>", methods=["GET", "POST"])
def view_class(class_id):
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  school = School.query.get(session["school_id"])
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked
  classroom = Classroom.query.filter_by(
      id=class_id, school_id=school.id
  ).first_or_404()

  if request.method == "POST":
    hashed = bcrypt.generate_password_hash(request.form["password"]).decode(
        "utf-8"
    )
    currency = request.form.get("currency", "USD")
    total_fees = float(request.form.get("total_fees", 0))
    parent_id_val = request.form.get("parent_id")
    student = Student(
        classroom_id=classroom.id,
        parent_id=int(parent_id_val) if parent_id_val else None,
        full_name=request.form["full_name"],
        email=request.form["email"],
        password=hashed,
        parent_contact=request.form.get("parent_contact", ""),
    )
    db.session.add(student)
    db.session.flush()
    db.session.add(
        FeeRecord(
            student_id=student.id,
            currency=currency,
            total_fees=total_fees,
            is_cleared=(total_fees <= 0),
        )
    )
    if safe_commit("A student with that email already exists."):
      flash("Student enrolled.", "success")
      return redirect(url_for("view_class", class_id=classroom.id))

  parents = Parent.query.filter_by(school_id=school.id).all()
  parent_opts = "".join(
      [f"<option value='{p.id}'>{p.full_name}</option>" for p in parents]
  )
  students = Student.query.filter_by(classroom_id=classroom.id).all()
  rows = ""
  for s in students:
    pr = Parent.query.get(s.parent_id) if s.parent_id else None
    rows += f"""
        <tr>
            <td>{s.full_name}</td>
            <td>{s.email}</td>
            <td>{pr.full_name if pr else 'Unlinked'}</td>
            <td><a href="/report_card/{s.id}" class="btn btn-sm btn-outline-primary"><i class="fas fa-file-alt me-1"></i>Report</a></td>
        </tr>
        """

  content = f"""
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h3>{classroom.name} - Students</h3>
        <a href="/school/dashboard" class="btn btn-outline-secondary btn-sm">Back to Dashboard</a>
    </div>
    <div class="row">
        <div class="col-md-7 mb-3"><div class="card p-4"><table class="table"><thead><tr><th>Name</th><th>Email</th><th>Parent</th><th>Transcript</th></tr></thead><tbody>{rows or '<tr><td colspan="4">No students enrolled.</td></tr>'}</tbody></table></div></div>
        <div class="col-md-5 mb-3"><div class="card p-4"><h5>Enroll Student</h5>
            <form method="POST">
                <input class="form-control mb-2" name="full_name" placeholder="Student Full Name" required>
                <input class="form-control mb-2" name="email" type="email" placeholder="Student Email" required>
                <input class="form-control mb-2" name="password" type="password" placeholder="Password" required>
                <input class="form-control mb-2" name="parent_contact" placeholder="Parent Phone (optional)">
                <select class="form-select mb-2" name="parent_id">
                    <option value="">-- Link Parent (Optional) --</option>
                    {parent_opts}
                </select>
                <div class="row g-2 mb-3">
                    <div class="col-7"><input class="form-control" name="total_fees" type="number" step="0.01" placeholder="Tuition Fees" value="0"></div>
                    <div class="col-5">
                        <select name="currency" class="form-select">
                            <option value="USD">USD ($)</option>
                            <option value="LRD">LRD (L$)</option>
                        </select>
                    </div>
                </div>
                <button class="btn btn-success w-100">Add Student</button>
            </form>
        </div></div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/school/manage_teachers", methods=["GET", "POST"])
def manage_teachers():
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  school = School.query.get(session["school_id"])
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked
  classrooms = Classroom.query.filter_by(school_id=school.id).all()
  if request.method == "POST":
    action = request.form.get("action", "add_teacher")
    if action == "add_teacher":
      hashed = bcrypt.generate_password_hash(request.form["password"]).decode(
          "utf-8"
      )
      db.session.add(
          Teacher(
              school_id=school.id,
              classroom_id=int(request.form["classroom_id"]),
              full_name=request.form["full_name"],
              email=request.form["email"],
              password=hashed,
              salary=float(request.form.get("salary", 0)),
          )
      )
      if safe_commit("A teacher with that email already exists."):
        flash("Teacher added.", "success")
    elif action == "reassign_teacher":
      t = Teacher.query.filter_by(
          id=int(request.form["teacher_id"]), school_id=school.id
      ).first()
      if t:
        t.classroom_id = int(request.form["classroom_id"])
        db.session.commit()
        flash(f"Updated homeroom class for {t.full_name}.", "success")
    return redirect(url_for("manage_teachers"))

  teachers = Teacher.query.filter_by(school_id=school.id).all()
  rows = ""
  for t in teachers:
    cl = Classroom.query.get(t.classroom_id)
    cl_opts = "".join([
        f"<option value='{c.id}' {'selected' if c.id == t.classroom_id else ''}>{c.name}</option>"
        for c in classrooms
    ])
    rows += f"""
        <tr>
            <td><strong>{t.full_name}</strong><br><small class="text-muted">{t.email}</small></td>
            <td>{cl.name if cl else 'Unassigned'}</td>
            <td>
                <form method="POST" class="d-flex gap-1">
                    <input type="hidden" name="action" value="reassign_teacher">
                    <input type="hidden" name="teacher_id" value="{t.id}">
                    <select name="classroom_id" class="form-select form-select-sm">{cl_opts}</select>
                    <button type="submit" class="btn btn-sm btn-outline-primary">Change</button>
                </form>
            </td>
            <td><a href="/school/delete_teacher/{t.id}" class="btn btn-sm btn-outline-danger"><i class="fas fa-trash"></i></a></td>
        </tr>
        """

  opts = "".join(
      [f"<option value='{c.id}'>{c.name}</option>" for c in classrooms]
  )
  content = f"""
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h3><i class="fas fa-chalkboard-teacher me-2"></i>Manage & Reassign Teachers</h3>
        <a href="/school/dashboard" class="btn btn-outline-secondary btn-sm">Back to Dashboard</a>
    </div>
    <div class="row">
        <div class="col-md-7 mb-3"><div class="card p-4">
            <table class="table align-middle">
                <thead><tr><th>Teacher</th><th>Homeroom</th><th>Change Class</th><th>Remove</th></tr></thead>
                <tbody>{rows or '<tr><td colspan="4">No teachers yet.</td></tr>'}</tbody>
            </table>
        </div></div>
        <div class="col-md-5 mb-3"><div class="card p-4"><h5>Add Teacher</h5>
            <form method="POST">
                <input type="hidden" name="action" value="add_teacher">
                <input class="form-control mb-2" name="full_name" placeholder="Full Name" required>
                <input class="form-control mb-2" name="email" type="email" placeholder="Email" required>
                <input class="form-control mb-2" name="password" type="password" placeholder="Password" required>
                <label class="form-label small text-muted">Primary Homeroom Class</label>
                <select class="form-select mb-2" name="classroom_id" required>{opts}</select>
                <input class="form-control mb-3" name="salary" type="number" step="0.01" placeholder="Monthly Salary" value="0">
                <button class="btn btn-primary w-100">Save Teacher</button>
            </form>
        </div></div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/school/delete_teacher/<int:teacher_id>")
def school_delete_teacher(teacher_id):
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  t = Teacher.query.filter_by(
      id=teacher_id, school_id=session["school_id"]
  ).first_or_404()
  db.session.delete(t)
  db.session.commit()
  flash("Teacher removed.", "info")
  return redirect(url_for("manage_teachers"))


@app.route("/school/manage_cashiers", methods=["GET", "POST"])
def manage_cashiers():
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  school = School.query.get(session["school_id"])
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked
  if request.method == "POST":
    hashed = bcrypt.generate_password_hash(request.form["password"]).decode(
        "utf-8"
    )
    db.session.add(
        Cashier(
            school_id=school.id,
            full_name=request.form["full_name"],
            email=request.form["email"],
            password=hashed,
        )
    )
    if safe_commit("A cashier with that email already exists."):
      flash("Cashier added.", "success")
      return redirect(url_for("manage_cashiers"))
  cashiers = Cashier.query.filter_by(school_id=school.id).all()
  rows = "".join([
      f"<tr><td>{c.full_name}</td><td>{c.email}</td><td><a href='/school/delete_cashier/{c.id}' class='btn btn-sm btn-outline-danger'><i class='fas fa-trash'></i></a></td></tr>"
      for c in cashiers
  ])
  content = f"""
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h3>Manage Cashiers</h3>
        <a href="/school/dashboard" class="btn btn-outline-secondary btn-sm">Back to Dashboard</a>
    </div>
    <div class="row">
        <div class="col-md-7"><div class="card p-4"><table class="table"><thead><tr><th>Name</th><th>Email</th><th>Remove</th></tr></thead><tbody>{rows or '<tr><td colspan="3">No cashiers yet.</td></tr>'}</tbody></table></div></div>
        <div class="col-md-5"><div class="card p-4"><h5>Add Cashier</h5>
            <form method="POST">
                <input class="form-control mb-2" name="full_name" placeholder="Full Name" required>
                <input class="form-control mb-2" name="email" type="email" placeholder="Email" required>
                <input class="form-control mb-3" name="password" type="password" placeholder="Password" required>
                <button class="btn btn-info text-white w-100">Save Cashier</button>
            </form>
        </div></div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/school/delete_cashier/<int:cashier_id>")
def school_delete_cashier(cashier_id):
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  c = Cashier.query.filter_by(
      id=cashier_id, school_id=session["school_id"]
  ).first_or_404()
  db.session.delete(c)
  db.session.commit()
  flash("Cashier removed.", "info")
  return redirect(url_for("manage_cashiers"))


@app.route("/school/announcements", methods=["POST"])
def post_announcement():
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  school = School.query.get(session["school_id"])
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked
  db.session.add(
      Announcement(
          school_id=school.id,
          author_label="Principal",
          message=request.form["message"],
      )
  )
  db.session.commit()
  flash("Announcement posted.", "success")
  return redirect(url_for("school_dashboard"))


@app.route("/school/subscribe", methods=["GET", "POST"])
def school_subscribe():
  if not session.get("school_id"):
    return redirect(url_for("school_login"))
  school = School.query.get(session["school_id"])
  cfg = get_platform_config()

  if request.method == "POST":
    phone = request.form["phone"].strip()
    provider = request.form.get("provider", "MTN")
    tx_id = request.form.get("momo_tx_id", "").strip()
    ref = "SUB-" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=6)
    )
    initiate_momo_request(
        phone, cfg.subscription_amount, cfg.subscription_currency, ref, tx_id
    )
    db.session.add(
        PaymentRequest(
            school_id=school.id,
            amount=cfg.subscription_amount,
            currency=cfg.subscription_currency,
            provider=provider,
            payer_phone=phone,
            momo_tx_id=tx_id or ref,
            reference=ref,
        )
    )
    db.session.commit()
    flash(
        "Subscription payment proof"
        f" ({format_money(cfg.subscription_amount, cfg.subscription_currency)})"
        f" submitted! Ref: {ref}. Access unlocks once approved by Owner.",
        "success",
    )
    return redirect(url_for("school_login"))

  content = f"""
    <div class="container mt-5" style="max-width: 520px;">
        <div class="card p-5 border-primary">
            <h3 class="text-center text-primary mb-3"><i class="fas fa-mobile-alt me-2"></i>Subscription Payment</h3>
            <div class="alert alert-info text-center">
                <h4>Amount Due: {format_money(cfg.subscription_amount, cfg.subscription_currency)}</h4>
                <p class="mb-0">Send MoMo to Merchant Number: <strong>{cfg.merchant_number}</strong></p>
            </div>
            <form method="POST">
                <select class="form-select mb-3" name="provider" required>
                    <option value="MTN">MTN Mobile Money</option>
                    <option value="Orange">Orange Money</option>
                </select>
                <input type="tel" class="form-control mb-3" name="phone" placeholder="Your Mobile Money Number" required>
                <input type="text" class="form-control mb-3" name="momo_tx_id" placeholder="MoMo Transaction ID from SMS (e.g., 894512301)" required>
                <button type="submit" class="btn btn-success w-100 py-3">Submit Payment for Activation</button>
            </form>
        </div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


# ==========================================
# 7. CASHIER PORTAL
# ==========================================
@app.route("/cashier/login", methods=["GET", "POST"])
def cashier_login():
  if request.method == "POST":
    cashier = Cashier.query.filter_by(email=request.form["email"]).first()
    if cashier and bcrypt.check_password_hash(
        cashier.password, request.form["password"]
    ):
      session.clear()
      session["cashier_id"] = cashier.id
      session["school_id"] = cashier.school_id
      return redirect(url_for("cashier_dashboard"))
    flash("Invalid Credentials", "danger")
  content = """
    <div class="container mt-5" style="max-width: 400px;"><div class="card p-4"><h3 class="text-center mb-4">Cashier Login</h3>
    <form method="POST"><input class="form-control mb-3" name="email" placeholder="Email" required>
    <input class="form-control mb-3" name="password" type="password" placeholder="Password" required>
    <button class="btn btn-success w-100">Login</button></form></div></div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/cashier/delete_message/<int:msg_id>")
def cashier_delete_message(msg_id):
  if not session.get("cashier_id"):
    return redirect(url_for("cashier_login"))
  cashier = Cashier.query.get(session["cashier_id"])
  msg = PortalMessage.query.filter_by(
      id=msg_id, school_id=cashier.school_id
  ).first_or_404()
  db.session.delete(msg)
  db.session.commit()
  flash("Message deleted.", "info")
  return redirect(url_for("cashier_dashboard"))


@app.route("/cashier/dashboard")
def cashier_dashboard():
  if not session.get("cashier_id"):
    return redirect(url_for("cashier_login"))
  cashier = Cashier.query.get(session["cashier_id"])
  school = School.query.get(cashier.school_id)
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked

  students = (
      Student.query.join(Classroom)
      .filter(Classroom.school_id == school.id)
      .all()
  )
  rows = ""
  for s in students:
    fee = FeeRecord.query.filter_by(student_id=s.id).first()
    cur = fee.currency if fee else "USD"
    total = fee.total_fees if fee else 0.0
    paid = fee.amount_paid if fee else 0.0
    balance = max(0.0, total - paid)
    status = (
        '<span class="badge bg-success">Cleared</span>'
        if balance <= 0
        else '<span class="badge bg-danger">Owing</span>'
    )

    rows += f"""
        <tr>
            <td><strong>{s.full_name}</strong><br><small class="text-muted">{s.parent_contact or 'No phone'}</small></td>
            <td>{format_money(total, cur)}</td>
            <td>{format_money(paid, cur)}</td>
            <td><strong>{format_money(balance, cur)}</strong></td>
            <td>{status}</td>
            <td>
                <form method="POST" action="/cashier/set_fee/{s.id}" class="d-flex gap-1">
                    <input type="number" step="0.01" min="0" name="total_fees" class="form-control form-control-sm" value="{total}" style="width:85px;" required>
                    <select name="currency" class="form-select form-select-sm" style="width:75px;">
                        <option value="USD" {'selected' if cur=='USD' else ''}>USD</option>
                        <option value="LRD" {'selected' if cur=='LRD' else ''}>LRD</option>
                    </select>
                    <button type="submit" class="btn btn-sm btn-outline-dark">Set</button>
                </form>
            </td>
            <td>
                <form method="POST" action="/cashier/add_payment/{s.id}" class="d-flex gap-1">
                    <input type="number" step="0.01" min="0.01" name="amount" class="form-control form-control-sm" placeholder="Pay" style="width:85px;" required>
                    <button type="submit" class="btn btn-sm btn-success">Pay</button>
                </form>
            </td>
            <td>
                <a href="/receipt/{s.id}" class="btn btn-sm btn-outline-primary mb-1"><i class="fas fa-receipt"></i> Receipt</a>
                <form method="POST" action="/cashier/send_message/{s.id}" class="d-flex gap-1 mt-1">
                    <input type="text" name="message" class="form-control form-control-sm" placeholder="Fee note to parent..." required>
                    <button type="submit" class="btn btn-sm btn-primary">Send</button>
                </form>
            </td>
        </tr>
        """

  msgs = (
      PortalMessage.query.filter_by(school_id=school.id)
      .order_by(PortalMessage.id.desc())
      .all()
  )
  msg_feed = "".join([
      f"""
        <li class="list-group-item d-flex justify-content-between align-items-start gap-2">
            <div>
                <small class="text-muted">{m.created_at.strftime('%Y-%m-%d %H:%M')} • <strong>{m.sender_label}</strong></small><br>
                <span>{m.body}</span>
            </div>
            <a href="/cashier/delete_message/{m.id}" class="btn btn-sm btn-outline-danger"><i class="fas fa-trash"></i></a>
        </li>
        """
      for m in msgs
  ])

  content = f"""
    {render_unread_dm_banner(f"cashier:{cashier.id}")}
    <div class="d-flex align-items-center gap-3 mb-3">
        {school_logo_html(school, 48)}
        <div>
            <h2 class="mb-0">Cashier Dashboard — {cashier.full_name}</h2>
            <small class="text-muted">{school.name} • Manage USD/LRD tuition, print receipts & read parent replies</small>
        </div>
    </div>
    <div class="card p-3 mt-3 table-responsive mb-4">
        <table class="table table-hover align-middle">
            <thead class="table-dark">
                <tr><th>Student</th><th>Total Fee</th><th>Paid</th><th>Balance</th><th>Status</th><th>Set Fee & Currency</th><th>Record Payment</th><th>Receipt & Portal Msg</th></tr>
            </thead>
            <tbody>{rows or '<tr><td colspan="8">No students enrolled yet.</td></tr>'}</tbody>
        </table>
    </div>
    <div class="card p-4">
        <h5><i class="fas fa-comments text-primary me-2"></i>Fee Messages & Parent Responses</h5>
        <div class="scroll-feed mt-2">
            <ul class="list-group">{msg_feed or '<li class="list-group-item text-muted">No messages or parent replies yet.</li>'}</ul>
        </div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/cashier/set_fee/<int:student_id>", methods=["POST"])
def cashier_set_fee(student_id):
  if not session.get("cashier_id"):
    return redirect(url_for("cashier_login"))
  fee = FeeRecord.query.filter_by(student_id=student_id).first()
  total_fees = float(request.form["total_fees"])
  currency = request.form["currency"]
  if not fee:
    fee = FeeRecord(student_id=student_id)
    db.session.add(fee)
  fee.total_fees = total_fees
  fee.currency = currency
  fee.is_cleared = fee.amount_paid >= fee.total_fees
  db.session.commit()
  flash("Updated student fee and currency.", "success")
  return redirect(url_for("cashier_dashboard"))


@app.route("/cashier/add_payment/<int:student_id>", methods=["POST"])
def cashier_add_payment(student_id):
  if not session.get("cashier_id"):
    return redirect(url_for("cashier_login"))
  cashier = Cashier.query.get(session["cashier_id"])
  student = Student.query.get_or_404(student_id)
  amount = float(request.form["amount"])
  fee = FeeRecord.query.filter_by(student_id=student_id).first()
  if not fee:
    fee = FeeRecord(student_id=student_id, currency="USD")
    db.session.add(fee)
  rcp = "RCP-" + "".join(
      random.choices(string.ascii_uppercase + string.digits, k=7)
  )
  fee.amount_paid += amount
  fee.is_cleared = fee.amount_paid >= fee.total_fees
  fee.last_receipt_code = rcp
  fee.last_payment_date = datetime.now().strftime("%Y-%m-%d %H:%M")
  db.session.add(
      FeeTransaction(
          student_id=student.id,
          amount=amount,
          currency=fee.currency,
          receipt_code=rcp,
          recorded_by=cashier.full_name,
      )
  )
  balance = max(0.0, fee.total_fees - fee.amount_paid)
  db.session.commit()

  alert_msg = (
      f"School Fee Update for {student.full_name}: Payment of"
      f" {format_money(amount, fee.currency)} received (Receipt: {rcp})."
      f" Remaining balance: {format_money(balance, fee.currency)}."
  )
  send_parent_alert(
      student.parent_contact,
      alert_msg,
      student=student,
      sender_label=f"Cashier ({cashier.full_name})",
      direction="to_parent",
  )
  flash(
      f"Recorded {format_money(amount, fee.currency)} & sent receipt {rcp} to"
      " parent's portal.",
      "success",
  )
  return redirect(url_for("cashier_dashboard"))


@app.route("/cashier/send_message/<int:student_id>", methods=["POST"])
def cashier_send_message(student_id):
  if not session.get("cashier_id"):
    return redirect(url_for("cashier_login"))
  cashier = Cashier.query.get(session["cashier_id"])
  student = Student.query.get_or_404(student_id)
  message = request.form["message"].strip()
  send_parent_alert(
      student.parent_contact,
      f"[{student.full_name} Fees] {message}",
      student=student,
      sender_label=f"Cashier ({cashier.full_name})",
      direction="to_parent",
  )
  flash(
      f"Fee message sent to {student.full_name}'s parent portal.", "success"
  )
  return redirect(url_for("cashier_dashboard"))


# ==========================================
# 8. TEACHER PORTAL (REPORT GRADES + CONTINUOUS ASSESSMENTS: QUIZ/SEATWORK/ASSIGNMENT/TEST)
# ==========================================
@app.route("/teacher/login", methods=["GET", "POST"])
def teacher_login():
  if request.method == "POST":
    teacher = Teacher.query.filter_by(email=request.form["email"]).first()
    if teacher and bcrypt.check_password_hash(
        teacher.password, request.form["password"]
    ):
      session.clear()
      session["teacher_id"] = teacher.id
      session["school_id"] = teacher.school_id
      return redirect(url_for("teacher_dashboard"))
    flash("Invalid Credentials", "danger")
  content = """
    <div class="container mt-5" style="max-width: 400px;"><div class="card p-4"><h3 class="text-center mb-4">Teacher Login</h3>
    <form method="POST"><input class="form-control mb-3" name="email" placeholder="Email" required>
    <input class="form-control mb-3" name="password" type="password" placeholder="Password" required>
    <button class="btn btn-warning w-100">Login</button></form></div></div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/teacher/dashboard", methods=["GET", "POST"])
def teacher_dashboard():
  if not session.get("teacher_id"):
    return redirect(url_for("teacher_login"))
  teacher = Teacher.query.get(session["teacher_id"])
  school = School.query.get(teacher.school_id)
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked

  school_classes = Classroom.query.filter_by(school_id=school.id).all()

  if request.method == "POST":
    form_type = request.form.get("form_type", "assignment")
    if form_type == "assignment":
      target_class_id = int(
          request.form.get("target_classroom_id", teacher.classroom_id)
      )
      target_cl = Classroom.query.filter_by(
          id=target_class_id, school_id=school.id
      ).first()
      if target_cl:
        db.session.add(
            Assignment(
                teacher_id=teacher.id,
                classroom_id=target_cl.id,
                subject_tag=request.form.get("subject_tag", "General").strip()
                or "General",
                title=request.form["title"],
                description=request.form["description"],
                due_date=request.form["due_date"],
            )
        )
        db.session.commit()
        flash(f"Assignment published to {target_cl.name}.", "success")
    elif form_type == "announcement":
      db.session.add(
          Announcement(
              school_id=school.id,
              author_label=f"Teacher ({teacher.full_name})",
              message=request.form["message"],
          )
      )
      db.session.commit()
      flash("Announcement posted.", "success")
    return redirect(url_for("teacher_dashboard"))

  selected_class_id = request.args.get(
      "class_id", default=teacher.classroom_id, type=int
  )
  active_class = (
      Classroom.query.filter_by(
          id=selected_class_id, school_id=school.id
      ).first()
      or Classroom.query.get(teacher.classroom_id)
  )

  students = (
      Student.query.filter_by(classroom_id=active_class.id).all()
      if active_class
      else []
  )
  assignments = (
      Assignment.query.filter_by(teacher_id=teacher.id)
      .order_by(Assignment.id.desc())
      .all()
  )
  announcements = (
      Announcement.query.filter_by(school_id=school.id)
      .order_by(Announcement.date_posted.desc())
      .all()
  )

  rows = ""
  for s in students:
    att_list = Attendance.query.filter_by(student_id=s.id).all()
    grd_list = Grade.query.filter_by(student_id=s.id).all()
    ca_list = (
        AssessmentRecord.query.filter_by(student_id=s.id)
        .order_by(AssessmentRecord.id.desc())
        .all()
    )

    att = "".join([
        f"<div class='d-flex justify-content-between align-items-center small mb-1'><span>{a.date}: <strong>{a.status}</strong></span>"
        f"<a href='/teacher/delete_attendance/{a.id}' class='text-danger ms-1' title='Remove'><i class='fas fa-times'></i></a></div>"
        for a in att_list[-4:]
    ])
    grd = "".join([
        f"<div class='d-flex justify-content-between align-items-center small mb-1'><span>[{g.period}] {g.subject}: <strong>{g.score}%</strong></span>"
        f"<a href='/teacher/delete_grade/{g.id}' class='text-danger ms-1' title='Remove'><i class='fas fa-times'></i></a></div>"
        for g in grd_list[-5:]
    ])
    ca_html = "".join([
        f"<div class='d-flex justify-content-between align-items-center small mb-1'>"
        f"<span><span class='badge bg-light text-dark border'>{c.category}</span> <strong>{c.label}</strong> ({c.subject}): {c.score}/{c.max_score}</span>"
        f"<span><a href='/teacher/assessments/{s.id}' class='text-primary ms-1' title='Edit'><i class='fas fa-edit'></i></a></span></div>"
        for c in ca_list[:4]
    ])

    rows += f"""
        <tr>
            <td><strong>{s.full_name}</strong></td>
            <td>{att or '<span class="text-muted small">None</span>'}</td>
            <td>{grd or '<span class="text-muted small">None</span>'}</td>
            <td>{ca_html or '<span class="text-muted small">None</span>'}</td>
            <td>
                <a href='/teacher/attendance/{s.id}' class='btn btn-sm btn-primary mb-1'>Attend</a>
                <a href='/teacher/grades/{s.id}' class='btn btn-sm btn-success mb-1'>Report Grade</a>
                <a href='/teacher/assessments/{s.id}' class='btn btn-sm btn-info text-white mb-1'>Quiz/Test/Work</a>
                <a href='/report_card/{s.id}' class='btn btn-sm btn-outline-dark mb-1'>Report Card</a>
            </td>
        </tr>
        """

  class_opts = "".join([
      f"<option value='{c.id}' {'selected' if active_class and c.id == active_class.id else ''}>{c.name}</option>"
      for c in school_classes
  ])

  assign_html = ""
  for a in assignments:
    cl = Classroom.query.get(a.classroom_id)
    assign_html += f"""
        <li class='list-group-item d-flex justify-content-between align-items-start gap-2'>
            <div>
                <span class='badge bg-light text-dark border'>{cl.name if cl else 'Class'} • {a.subject_tag}</span><br>
                <strong>{a.title}</strong> <small class='text-danger'>(Due: {a.due_date})</small><br>
                <span class='small'>{a.description}</span>
            </div>
            <a href='/teacher/delete_assignment/{a.id}' class='btn btn-sm btn-outline-danger' title='Delete assignment'><i class='fas fa-trash'></i></a>
        </li>
        """

  ann_list = "".join([
      f"""
        <li class='list-group-item d-flex justify-content-between align-items-start gap-2'>
            <div><small class='text-muted'>{a.date_posted.strftime('%Y-%m-%d')} • {a.author_label}</small><br>{a.message}</div>
            <a href='/teacher/delete_announcement/{a.id}' class='btn btn-sm btn-outline-danger' title='Delete announcement'><i class='fas fa-trash'></i></a>
        </li>
        """
      for a in announcements
  ])

  content = f"""
    {render_unread_dm_banner(f"teacher:{teacher.id}")}
    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2 mb-3">
        <div class="d-flex align-items-center gap-3">
            {school_logo_html(school, 48)}
            <div>
                <h2 class="mb-0">Teacher: {teacher.full_name}</h2>
                <small class="text-muted">{school.name}</small>
            </div>
        </div>
        <form method="GET" action="/teacher/dashboard" class="d-flex align-items-center gap-2">
            <label class="small fw-bold mb-0">Viewing Class:</label>
            <select name="class_id" class="form-select form-select-sm" onchange="this.form.submit()">
                {class_opts}
            </select>
        </form>
    </div>

    <div class="row mt-3">
        <div class="col-md-7 mb-3">
            <div class="card p-4">
                <h4>Class Roster — {active_class.name if active_class else 'No Class'}</h4>
                <div class="table-responsive mt-2">
                    <table class="table table-hover align-middle">
                        <thead class="table-dark"><tr><th>Student</th><th>Attendance</th><th>Report Grades</th><th>Quizzes / Tests / Seat Work</th><th>Actions</th></tr></thead>
                        <tbody>{rows or '<tr><td colspan="5">No students in this class.</td></tr>'}</tbody>
                    </table>
                </div>
            </div>
        </div>
        <div class="col-md-5 mb-3">
            <div class="card p-4 mb-3">
                <h5><i class="fas fa-tasks me-2"></i>Send Assignment to Any Class</h5>
                <form method="POST">
                    <input type="hidden" name="form_type" value="assignment">
                    <div class="row g-2 mb-2">
                        <div class="col-6">
                            <label class="form-label small text-muted mb-1">Choose Target Class</label>
                            <select name="target_classroom_id" class="form-select form-select-sm" required>
                                {class_opts}
                            </select>
                        </div>
                        <div class="col-6">
                            <label class="form-label small text-muted mb-1">Subject</label>
                            <input class="form-control form-control-sm" name="subject_tag" placeholder="e.g., Biology" required>
                        </div>
                    </div>
                    <input class="form-control mb-2" name="title" placeholder="Assignment / Letter Title" required>
                    <textarea class="form-control mb-2" name="description" placeholder="Homework instructions or letter..." required></textarea>
                    <input type="date" class="form-control mb-2" name="due_date" required>
                    <button class="btn btn-primary w-100">Publish Assignment</button>
                </form>
                <div class="scroll-feed mt-3">
                    <ul class="list-group">{assign_html or '<li class="list-group-item text-muted">No active assignments.</li>'}</ul>
                </div>
            </div>
            <div class="card p-4">
                <h5><i class="fas fa-bullhorn me-2"></i>Announcements</h5>
                <form method="POST" class="mb-2">
                    <input type="hidden" name="form_type" value="announcement">
                    <div class="d-flex gap-2">
                        <input class="form-control form-control-sm" name="message" placeholder="Post class/school notice..." required>
                        <button class="btn btn-sm btn-primary">Post</button>
                    </div>
                </form>
                <div class="scroll-feed">
                    <ul class="list-group mt-2">{ann_list or '<li class="list-group-item text-muted">No announcements.</li>'}</ul>
                </div>
            </div>
        </div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/teacher/assessments/<int:student_id>", methods=["GET", "POST"])
def manage_student_assessments(student_id):
  if not session.get("teacher_id"):
    return redirect(url_for("teacher_login"))
  teacher = Teacher.query.get(session["teacher_id"])
  student = Student.query.get_or_404(student_id)

  if request.method == "POST":
    action = request.form.get("action", "create")
    if action == "create":
      category = request.form.get("category", "Quiz")
      label = request.form.get("label", "Quiz 1").strip() or "Quiz 1"
      subject = request.form["subject"].strip()
      score = float(request.form["score"])
      max_score = float(request.form.get("max_score", 100) or 100)
      rec = AssessmentRecord(
          student_id=student.id,
          teacher_id=teacher.id,
          category=category,
          label=label,
          subject=subject,
          score=score,
          max_score=max_score,
      )
      db.session.add(rec)
      db.session.commit()
      send_parent_alert(
          student.parent_contact,
          f"{category} Update ({label}) for {student.full_name} in {subject}:"
          f" scored {score}/{max_score}.",
          student=student,
          sender_label=f"Teacher ({teacher.full_name})",
          direction="to_parent",
      )
      flash(
          f"Saved {category} ({label}) for {student.full_name} & sent to linked"
          " parent!",
          "success",
      )
    elif action == "edit":
      rec_id = int(request.form["rec_id"])
      rec = AssessmentRecord.query.filter_by(
          id=rec_id, student_id=student.id
      ).first_or_404()
      rec.category = request.form.get("category", rec.category)
      rec.label = request.form.get("label", rec.label).strip() or rec.label
      rec.subject = request.form.get("subject", rec.subject).strip()
      rec.score = float(request.form["score"])
      rec.max_score = float(
          request.form.get("max_score", rec.max_score) or 100
      )
      db.session.commit()
      send_parent_alert(
          student.parent_contact,
          f"Updated {rec.category} ({rec.label}) for {student.full_name} in"
          f" {rec.subject}: {rec.score}/{rec.max_score}.",
          student=student,
          sender_label=f"Teacher ({teacher.full_name})",
          direction="to_parent",
      )
      flash(
          f"Updated {rec.label} ({rec.subject}) & notified linked parent.",
          "success",
      )
    return redirect(url_for("manage_student_assessments", student_id=student.id))

  records = (
      AssessmentRecord.query.filter_by(student_id=student.id)
      .order_by(AssessmentRecord.id.desc())
      .all()
  )
  rec_rows = ""
  for r in records:
    rec_rows += f"""
        <tr>
            <form method="POST">
                <input type="hidden" name="action" value="edit">
                <input type="hidden" name="rec_id" value="{r.id}">
                <td>
                    <select name="category" class="form-select form-select-sm">
                        <option {'selected' if r.category=='Quiz' else ''}>Quiz</option>
                        <option {'selected' if r.category=='Assignment' else ''}>Assignment</option>
                        <option {'selected' if r.category=='Seat Work' else ''}>Seat Work</option>
                        <option {'selected' if r.category=='Test' else ''}>Test</option>
                    </select>
                </td>
                <td><input name="label" class="form-control form-control-sm" value="{r.label}" required></td>
                <td><input name="subject" class="form-control form-control-sm" value="{r.subject}" required></td>
                <td class="d-flex gap-1 align-items-center">
                    <input name="score" type="number" step="0.1" class="form-control form-control-sm" value="{r.score}" style="width:72px;" required>
                    <span>/</span>
                    <input name="max_score" type="number" step="0.1" class="form-control form-control-sm" value="{r.max_score}" style="width:72px;" required>
                </td>
                <td class="d-flex gap-1">
                    <button type="submit" class="btn btn-sm btn-primary">Save</button>
                    <a href="/teacher/delete_assessment/{r.id}" class="btn btn-sm btn-outline-danger"><i class="fas fa-trash"></i></a>
                </td>
            </form>
        </tr>
        """

  content = f"""
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <div>
            <h3 class="mb-0">Quizzes, Assignments, Seat Work & Tests — {student.full_name}</h3>
            <small class="text-muted">Recorded separately from official Report Card period grades and sent automatically to linked parents.</small>
        </div>
        <a href="/teacher/dashboard?class_id={student.classroom_id}" class="btn btn-outline-secondary btn-sm">Back to Roster</a>
    </div>

    <div class="card p-4 mb-4">
        <h5>Add New Quiz / Seat Work / Assignment / Test Grade</h5>
        <form method="POST" class="row g-2 align-items-end mt-1">
            <input type="hidden" name="action" value="create">
            <div class="col-md-2">
                <label class="form-label small text-muted">Type</label>
                <select name="category" class="form-select">
                    <option value="Quiz">Quiz</option>
                    <option value="Assignment">Assignment</option>
                    <option value="Seat Work">Seat Work</option>
                    <option value="Test">Test</option>
                </select>
            </div>
            <div class="col-md-3">
                <label class="form-label small text-muted">Label (e.g., Quiz 1, Quiz 2)</label>
                <input name="label" class="form-control" placeholder="Quiz 1" value="Quiz 1" required>
            </div>
            <div class="col-md-3">
                <label class="form-label small text-muted">Subject</label>
                <input name="subject" class="form-control" placeholder="e.g., Physics" required>
            </div>
            <div class="col-md-2">
                <label class="form-label small text-muted">Score</label>
                <input name="score" type="number" step="0.1" class="form-control" placeholder="Score" required>
            </div>
            <div class="col-md-2">
                <label class="form-label small text-muted">Out Of</label>
                <input name="max_score" type="number" step="0.1" class="form-control" value="100" required>
            </div>
            <div class="col-12 mt-2">
                <button class="btn btn-success"><i class="fas fa-paper-plane me-1"></i>Save & Send to Linked Parent</button>
            </div>
        </form>
    </div>

    <div class="card p-4">
        <h5>Edit Recorded Quizzes, Seat Work, Assignments & Tests</h5>
        <div class="table-responsive mt-2">
            <table class="table table-hover align-middle">
                <thead class="table-light"><tr><th>Type</th><th>Label (Quiz 1, Quiz 2...)</th><th>Subject</th><th>Score / Max</th><th>Action</th></tr></thead>
                <tbody>{rec_rows or '<tr><td colspan="5">No quizzes, seat work, assignments, or tests recorded yet.</td></tr>'}</tbody>
            </table>
        </div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/teacher/delete_assessment/<int:rec_id>")
def teacher_delete_assessment(rec_id):
  if not session.get("teacher_id"):
    return redirect(url_for("teacher_login"))
  rec = AssessmentRecord.query.get_or_404(rec_id)
  sid = rec.student_id
  db.session.delete(rec)
  db.session.commit()
  flash("Assessment record deleted.", "info")
  return redirect(url_for("manage_student_assessments", student_id=sid))


@app.route("/teacher/delete_assignment/<int:assignment_id>")
def delete_assignment(assignment_id):
  if not session.get("teacher_id"):
    return redirect(url_for("teacher_login"))
  teacher = Teacher.query.get(session["teacher_id"])
  assignment = Assignment.query.filter_by(
      id=assignment_id, teacher_id=teacher.id
  ).first_or_404()
  db.session.delete(assignment)
  db.session.commit()
  flash("Assignment deleted and removed from student board.", "info")
  return redirect(url_for("teacher_dashboard"))


@app.route("/teacher/delete_announcement/<int:ann_id>")
def teacher_delete_announcement(ann_id):
  if not session.get("teacher_id"):
    return redirect(url_for("teacher_login"))
  teacher = Teacher.query.get(session["teacher_id"])
  ann = Announcement.query.filter_by(
      id=ann_id, school_id=teacher.school_id
  ).first_or_404()
  db.session.delete(ann)
  db.session.commit()
  flash("Announcement deleted.", "info")
  return redirect(url_for("teacher_dashboard"))


@app.route("/teacher/delete_grade/<int:grade_id>")
def teacher_delete_grade(grade_id):
  if not session.get("teacher_id"):
    return redirect(url_for("teacher_login"))
  g = Grade.query.get_or_404(grade_id)
  db.session.delete(g)
  db.session.commit()
  flash("Report grade entry removed.", "info")
  return redirect(url_for("teacher_dashboard"))


@app.route("/teacher/delete_attendance/<int:att_id>")
def teacher_delete_attendance(att_id):
  if not session.get("teacher_id"):
    return redirect(url_for("teacher_login"))
  a = Attendance.query.get_or_404(att_id)
  db.session.delete(a)
  db.session.commit()
  flash("Attendance entry removed.", "info")
  return redirect(url_for("teacher_dashboard"))


@app.route("/teacher/attendance/<int:student_id>", methods=["GET", "POST"])
def mark_attendance(student_id):
  if not session.get("teacher_id"):
    return redirect(url_for("teacher_login"))
  student = Student.query.get_or_404(student_id)
  if request.method == "POST":
    status = request.form["status"]
    db.session.add(Attendance(student_id=student_id, status=status))
    db.session.commit()
    send_parent_alert(
        student.parent_contact,
        f"Attendance for {student.full_name}: marked {status} today.",
        student=student,
        sender_label="Teacher",
        direction="to_parent",
    )
    flash(
        f"Attendance ({status}) saved & posted to parent's portal.", "success"
    )
    return redirect(url_for("teacher_dashboard", class_id=student.classroom_id))
  content = f"<div class='container mt-5' style='max-width:320px'><div class='card p-4'><h5>Mark {student.full_name}</h5><form method='POST'><select name='status' class='form-select mb-3'><option>Present</option><option>Absent</option></select><button class='btn btn-primary w-100'>Save & Send to Portal</button></form></div></div>"
  return render_template_string(BASE_HTML, content=content)


@app.route("/teacher/grades/<int:student_id>", methods=["GET", "POST"])
def add_grade(student_id):
  if not session.get("teacher_id"):
    return redirect(url_for("teacher_login"))
  student = Student.query.get_or_404(student_id)
  if request.method == "POST":
    period = request.form.get("period", "1st Period")
    subject = request.form["subject"]
    score = float(request.form["score"])
    db.session.add(
        Grade(
            student_id=student_id, period=period, subject=subject, score=score
        )
    )
    db.session.commit()
    send_parent_alert(
        student.parent_contact,
        f"Report Grade update ({period}) for {student.full_name}: scored"
        f" {score}% in {subject}.",
        student=student,
        sender_label="Teacher",
        direction="to_parent",
    )
    flash(
        f"Added Report Grade {score}% in {subject} ({period}) & posted to"
        " parent's portal.",
        "success",
    )
    return redirect(url_for("teacher_dashboard", class_id=student.classroom_id))
  content = f"""
    <div class='container mt-5' style='max-width:360px'>
        <div class='card p-4'>
            <h5>Official Report Grade — {student.full_name}</h5>
            <form method='POST'>
                <label class="form-label small text-muted">Marking Period / Term</label>
                <select name="period" class="form-select mb-2">
                    <option>1st Period</option>
                    <option>2nd Period</option>
                    <option>3rd Period</option>
                    <option>1st Semester Exam</option>
                    <option>4th Period</option>
                    <option>5th Period</option>
                    <option>6th Period</option>
                    <option>2nd Semester Exam</option>
                </select>
                <input name='subject' class='form-control mb-2' placeholder='Subject (e.g., Math)' required>
                <input name='score' type='number' step='0.1' min='0' max='100' class='form-control mb-3' placeholder='Score (0-100)' required>
                <button class='btn btn-success w-100'>Save & Send to Portal</button>
            </form>
        </div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


# ==========================================
# 9. STUDENT PORTAL + 6 MINI-GAMES (ALONE & WITH A FRIEND)
# ==========================================
@app.route("/student/login", methods=["GET", "POST"])
def student_login():
  if request.method == "POST":
    student = Student.query.filter_by(email=request.form["email"]).first()
    if student and bcrypt.check_password_hash(
        student.password, request.form["password"]
    ):
      session.clear()
      session["student_id"] = student.id
      return redirect(url_for("student_dashboard"))
    flash("Invalid Credentials", "danger")
  content = """
    <div class="container mt-5" style="max-width: 400px;"><div class="card p-4"><h3 class="text-center mb-4">Student Login</h3>
    <form method="POST"><input class="form-control mb-3" name="email" placeholder="Email" required>
    <input class="form-control mb-3" name="password" type="password" placeholder="Password" required>
    <button class="btn btn-dark w-100">Login</button></form></div></div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/student/dashboard")
def student_dashboard():
  if not session.get("student_id"):
    return redirect(url_for("student_login"))
  student = Student.query.get(session["student_id"])
  school = get_school_for_student(student)
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked

  grades = Grade.query.filter_by(student_id=student.id).all()
  ca_records = (
      AssessmentRecord.query.filter_by(student_id=student.id)
      .order_by(AssessmentRecord.id.desc())
      .all()
  )
  attendance_rows = Attendance.query.filter_by(student_id=student.id).all()
  assignments = (
      Assignment.query.filter_by(classroom_id=student.classroom_id)
      .order_by(Assignment.id.desc())
      .all()
  )
  announcements = (
      Announcement.query.filter_by(school_id=school.id)
      .order_by(Announcement.date_posted.desc())
      .all()
  )
  fee = FeeRecord.query.filter_by(student_id=student.id).first()
  rank_str, _ = compute_class_rank(student)

  grade_items = "".join([
      f"<li class='list-group-item d-flex justify-content-between'><span>[{g.period}] {g.subject}</span><strong>{g.score}%</strong></li>"
      for g in grades
  ])
  ca_items = "".join([
      f"<li class='list-group-item d-flex justify-content-between'><span><span class='badge bg-light text-dark border'>{c.category}</span> <strong>{c.label}</strong> ({c.subject})</span><strong>{c.score}/{c.max_score}</strong></li>"
      for c in ca_records
  ])
  att_items = "".join([
      f"<li class='list-group-item d-flex justify-content-between'><span>{a.date}</span><span>{a.status}</span></li>"
      for a in attendance_rows
  ])
  assign_items = "".join([
      f"<li class='list-group-item'><span class='badge bg-light text-dark border'>{a.subject_tag}</span> <strong>{a.title}</strong> <small class='text-danger'>(Due {a.due_date})</small><br><span class='small'>{a.description}</span></li>"
      for a in assignments
  ])
  ann_items = "".join([
      f"<li class='list-group-item'><small class='text-muted'>{a.date_posted.strftime('%Y-%m-%d')} • {a.author_label}</small><br>{a.message}</li>"
      for a in announcements
  ])

  cur = fee.currency if fee else "USD"
  bal = max(0.0, (fee.total_fees - fee.amount_paid)) if fee else 0.0
  fee_summary = (
      f"Total: {format_money(fee.total_fees, cur)} • Paid:"
      f" {format_money(fee.amount_paid, cur)} • Balance:"
      f" <strong>{format_money(bal, cur)}</strong>"
      if fee
      else "No fee record posted yet."
  )

  content = f"""
    {render_unread_dm_banner(f"student:{student.id}")}
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <div class="d-flex align-items-center gap-3">
            {school_logo_html(school, 48)}
            <div>
                <h3 class="mb-0">Welcome, {student.full_name}</h3>
                <small class="text-muted">{school.name} • Class Rank: <strong>{rank_str}</strong></small>
            </div>
        </div>
        <div class="d-flex flex-wrap gap-2">
            <a href="/student/games" class="btn btn-warning text-dark btn-sm"><i class="fas fa-gamepad me-1"></i>Play Mini-Games (6)</a>
            <a href="/chat" class="btn btn-dark btn-sm"><i class="fas fa-comments me-1"></i>Chat With Friends</a>
            <a href="/report_card/{student.id}" class="btn btn-primary btn-sm"><i class="fas fa-file-alt me-1"></i>Report Card</a>
            <a href="/receipt/{student.id}" class="btn btn-success btn-sm"><i class="fas fa-receipt me-1"></i>Fee Receipt</a>
        </div>
    </div>
    <div class="alert alert-light border mb-4"><i class="fas fa-wallet me-2"></i>{fee_summary}</div>
    <div class="row">
        <div class="col-md-4 mb-3"><div class="card p-4"><h5>Official Report Grades</h5><div class="scroll-feed"><ul class="list-group mt-2">{grade_items or '<li class="list-group-item text-muted">No official grades yet.</li>'}</ul></div></div></div>
        <div class="col-md-4 mb-3"><div class="card p-4"><h5>Quizzes, Tests & Seat Work</h5><div class="scroll-feed"><ul class="list-group mt-2">{ca_items or '<li class="list-group-item text-muted">No quizzes or seat work yet.</li>'}</ul></div></div></div>
        <div class="col-md-4 mb-3"><div class="card p-4"><h5>Assignments & Letters</h5><div class="scroll-feed"><ul class="list-group mt-2">{assign_items or '<li class="list-group-item text-muted">No active assignments.</li>'}</ul></div></div></div>
    </div>
    <div class="row mt-2">
        <div class="col-md-5 mb-3"><div class="card p-4"><h5>Attendance Log</h5><div class="scroll-feed"><ul class="list-group mt-2">{att_items or '<li class="list-group-item text-muted">No attendance records.</li>'}</ul></div></div></div>
        <div class="col-md-7 mb-3"><div class="card p-4"><h5><i class="fas fa-bullhorn me-2"></i>School Announcements</h5><div class="scroll-feed"><ul class="list-group mt-2">{ann_items or '<li class="list-group-item text-muted">No announcements.</li>'}</ul></div></div></div>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/student/games")
def student_games():
  if not session.get("student_id"):
    return redirect(url_for("student_login"))
  student = Student.query.get(session["student_id"])
  school = get_school_for_student(student)
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked

  content = """
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <div>
            <h3 class="mb-0"><i class="fas fa-gamepad text-primary me-2"></i>Student Break-Time Game Arcade</h3>
            <small class="text-muted">6 mini-games — switch any game between <strong>Play Alone</strong> and <strong>With a Friend</strong></small>
        </div>
        <div class="d-flex gap-2">
            <a href="/chat" class="btn btn-primary btn-sm"><i class="fas fa-comments me-1"></i>Back to Friend Chat</a>
            <a href="/student/dashboard" class="btn btn-outline-secondary btn-sm">Dashboard</a>
        </div>
    </div>

    <div class="row">
        <!-- 1. TIC-TAC-TOE -->
        <div class="col-md-6 col-lg-4 mb-4">
            <div class="card p-4 h-100 text-center">
                <h5>1. Tic-Tac-Toe</h5>
                <div class="btn-group btn-group-sm mb-2" role="group">
                    <button id="tttModeBot" onclick="setTTTMode('bot')" class="btn btn-primary active">Play Alone (vs Bot)</button>
                    <button id="tttModeP2" onclick="setTTTMode('friend')" class="btn btn-outline-primary">With a Friend</button>
                </div>
                <p id="tttStatus" class="small text-muted mb-2">Player X's turn</p>
                <div id="tttBoard" class="d-grid mx-auto mb-3" style="grid-template-columns: repeat(3, 64px); gap: 6px; width: 204px;"></div>
                <button onclick="resetTTT()" class="btn btn-sm btn-outline-secondary">Restart Game</button>
            </div>
        </div>

        <!-- 2. SNAKE -->
        <div class="col-md-6 col-lg-4 mb-4">
            <div class="card p-4 h-100 text-center">
                <h5>2. Snake Arena</h5>
                <div class="btn-group btn-group-sm mb-2" role="group">
                    <button id="snkModeSolo" onclick="setSnakeMode('solo')" class="btn btn-success active">Play Alone</button>
                    <button id="snkModeFriend" onclick="setSnakeMode('friend')" class="btn btn-outline-success">With a Friend (2P)</button>
                </div>
                <p id="snakeScoreLabel" class="small text-muted mb-2">Score: <strong id="snakeScore">0</strong></p>
                <canvas id="snakeCanvas" width="200" height="200" class="border rounded mx-auto mb-2 bg-dark"></canvas>
                <div class="small text-muted mb-1">
                    <span class="text-success fw-bold">P1 (Green):</span> Arrows / Buttons
                    <span id="p2SnakeHint" class="d-none text-info fw-bold ms-2">• P2 (Blue): WASD</span>
                </div>
                <div class="d-flex justify-content-center gap-1 mb-2">
                    <button onclick="setSnakeDir(1,0,-1)" class="btn btn-sm btn-light border">▲</button>
                    <button onclick="setSnakeDir(1,-1,0)" class="btn btn-sm btn-light border">◀</button>
                    <button onclick="setSnakeDir(1,1,0)" class="btn btn-sm btn-light border">▶</button>
                    <button onclick="setSnakeDir(1,0,1)" class="btn btn-sm btn-light border">▼</button>
                </div>
                <button onclick="startSnake()" class="btn btn-sm btn-success">Start / Reset Snake</button>
            </div>
        </div>

        <!-- 3. MEMORY PAIR MATCH -->
        <div class="col-md-6 col-lg-4 mb-4">
            <div class="card p-4 h-100 text-center">
                <h5>3. Memory Pair Match</h5>
                <div class="btn-group btn-group-sm mb-2" role="group">
                    <button id="memModeSolo" onclick="setMemMode('solo')" class="btn btn-primary active">Play Alone</button>
                    <button id="memModeFriend" onclick="setMemMode('friend')" class="btn btn-outline-primary">With a Friend</button>
                </div>
                <p id="memStatus" class="small text-muted mb-2">Moves: <strong id="memMoves">0</strong></p>
                <div id="memGrid" class="d-grid mx-auto mb-3" style="grid-template-columns: repeat(4, 48px); gap: 6px; width: 210px;"></div>
                <button onclick="initMemory()" class="btn btn-sm btn-outline-secondary">Shuffle Cards</button>
            </div>
        </div>

        <!-- 4. QUICK MATH BLITZ -->
        <div class="col-md-6 col-lg-4 mb-4">
            <div class="card p-4 h-100 text-center">
                <h5>4. Quick Math Blitz</h5>
                <div class="btn-group btn-group-sm mb-2" role="group">
                    <button id="mathModeSolo" onclick="setMathMode('solo')" class="btn btn-primary active">Play Alone</button>
                    <button id="mathModeFriend" onclick="setMathMode('friend')" class="btn btn-outline-primary">With a Friend</button>
                </div>
                <p id="mathStatus" class="small text-muted mb-2">Streak: <strong id="mathStreak">0</strong></p>
                <h4 id="mathQ" class="my-2 text-primary">7 + 8 = ?</h4>
                <div class="d-flex gap-2 justify-content-center mb-2">
                    <input type="number" id="mathAns" class="form-control form-control-sm text-center" style="width:100px;" placeholder="Answer">
                    <button onclick="checkMath()" class="btn btn-sm btn-primary">Check</button>
                </div>
                <small id="mathFeedback" class="text-muted"></small>
            </div>
        </div>

        <!-- 5. ROCK PAPER SCISSORS -->
        <div class="col-md-6 col-lg-4 mb-4">
            <div class="card p-4 h-100 text-center">
                <h5>5. Rock Paper Scissors</h5>
                <div class="btn-group btn-group-sm mb-2" role="group">
                    <button id="rpsModeBot" onclick="setRPSMode('bot')" class="btn btn-primary active">Play Alone (vs Bot)</button>
                    <button id="rpsModeFriend" onclick="setRPSMode('friend')" class="btn btn-outline-primary">With a Friend</button>
                </div>
                <p class="small text-muted mb-2"><span id="rpsLabel1">You</span>: <strong id="rpsP1">0</strong> • <span id="rpsLabel2">Bot</span>: <strong id="rpsP2">0</strong></p>
                <div class="d-flex justify-content-center gap-2 my-3">
                    <button onclick="playRPS('Rock')" class="btn btn-outline-dark btn-sm">🪨 Rock</button>
                    <button onclick="playRPS('Paper')" class="btn btn-outline-dark btn-sm">📄 Paper</button>
                    <button onclick="playRPS('Scissors')" class="btn btn-outline-dark btn-sm">✂️ Scissors</button>
                </div>
                <p id="rpsResult" class="small fw-bold text-primary mb-0">Pick a move!</p>
            </div>
        </div>

        <!-- 6. SECRET NUMBER GUESS -->
        <div class="col-md-6 col-lg-4 mb-4">
            <div class="card p-4 h-100 text-center">
                <h5>6. Secret Number (1–100)</h5>
                <div class="btn-group btn-group-sm mb-2" role="group">
                    <button id="guessModeSolo" onclick="setGuessMode('solo')" class="btn btn-success active">Play Alone</button>
                    <button id="guessModeFriend" onclick="setGuessMode('friend')" class="btn btn-outline-success">Friend Sets #</button>
                </div>
                <p class="small text-muted mb-2">Tries: <strong id="guessTries">0</strong></p>
                <div id="friendSecretBox" class="d-none justify-content-center gap-1 mb-2">
                    <input type="number" id="friendSecretInput" min="1" max="100" class="form-control form-control-sm text-center" style="width:120px;" placeholder="Friend's #">
                    <button onclick="setFriendSecret()" class="btn btn-sm btn-dark">Set Secret</button>
                </div>
                <div class="d-flex gap-2 justify-content-center my-2">
                    <input type="number" id="guessInput" min="1" max="100" class="form-control form-control-sm text-center" style="width:100px;" placeholder="1-100">
                    <button onclick="checkGuess()" class="btn btn-sm btn-success">Guess</button>
                </div>
                <p id="guessHint" class="small text-muted mb-2">Guess my secret number!</p>
                <button onclick="resetGuess()" class="btn btn-sm btn-outline-secondary">New Number</button>
            </div>
        </div>
    </div>

    <script>
    // 1. Tic-Tac-Toe
    let tttCells = Array(9).fill(''), tttOver = false, tttTurn = 'X', tttMode = 'bot';
    function setTTTMode(m) {
        tttMode = m;
        document.getElementById('tttModeBot').className = m==='bot' ? 'btn btn-primary active' : 'btn btn-outline-primary';
        document.getElementById('tttModeP2').className = m==='friend' ? 'btn btn-primary active' : 'btn btn-outline-primary';
        resetTTT();
    }
    function renderTTT() {
        const board = document.getElementById('tttBoard'); board.innerHTML = '';
        tttCells.forEach((val, idx) => {
            const btn = document.createElement('button');
            btn.className = 'btn btn-light border fw-bold fs-5'; btn.style.height = '64px';
            btn.textContent = val; btn.onclick = () => moveTTT(idx); board.appendChild(btn);
        });
    }
    function checkTTTWinner(b) {
        const lines = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
        for (let [a,c,d] of lines) { if (b[a] && b[a]===b[c] && b[a]===b[d]) return b[a]; }
        return b.includes('') ? null : 'Draw';
    }
    function moveTTT(i) {
        if (tttOver || tttCells[i]) return;
        tttCells[i] = tttTurn;
        let w = checkTTTWinner(tttCells);
        if (!w && tttMode === 'bot') {
            const empty = tttCells.map((v,idx)=>v===''?idx:null).filter(v=>v!==null);
            if (empty.length) tttCells[empty[Math.floor(Math.random()*empty.length)]] = 'O';
            w = checkTTTWinner(tttCells);
        } else if (!w && tttMode === 'friend') {
            tttTurn = (tttTurn === 'X') ? 'O' : 'X';
            document.getElementById('tttStatus').textContent = "Player " + tttTurn + "'s turn";
        }
        if (w) {
            tttOver = true;
            document.getElementById('tttStatus').textContent = w === 'Draw' ? 'Draw game!' : (tttMode==='bot' ? (w==='X'?'You win!':'Bot wins!') : 'Player ' + w + ' wins!');
        }
        renderTTT();
    }
    function resetTTT() {
        tttCells = Array(9).fill(''); tttOver = false; tttTurn = 'X';
        document.getElementById('tttStatus').textContent = tttMode==='bot' ? 'Your turn (X)' : "Player X's turn";
        renderTTT();
    }
    renderTTT();

    // 2. Snake
    let snakeMode = 'solo', snake1 = [{x:6,y:10}], dir1 = {x:1,y:0}, snake2 = [{x:13,y:10}], dir2 = {x:-1,y:0};
    let food = {x:10,y:5}, snakeTimer = null, score1 = 0, score2 = 0;
    function setSnakeMode(m) {
        snakeMode = m;
        document.getElementById('snkModeSolo').className = m==='solo' ? 'btn btn-success active' : 'btn btn-outline-success';
        document.getElementById('snkModeFriend').className = m==='friend' ? 'btn btn-success active' : 'btn btn-outline-success';
        document.getElementById('p2SnakeHint').className = m==='friend' ? 'text-info fw-bold ms-2' : 'd-none';
        startSnake();
    }
    function setSnakeDir(player, dx, dy) {
        if (player === 1 && (dx !== -dir1.x || dy !== -dir1.y)) dir1 = {x:dx, y:dy};
        if (player === 2 && (dx !== -dir2.x || dy !== -dir2.y)) dir2 = {x:dx, y:dy};
    }
    document.addEventListener('keydown', function(e) {
        if (e.key === 'ArrowUp') setSnakeDir(1, 0, -1);
        else if (e.key === 'ArrowDown') setSnakeDir(1, 0, 1);
        else if (e.key === 'ArrowLeft') setSnakeDir(1, -1, 0);
        else if (e.key === 'ArrowRight') setSnakeDir(1, 1, 0);
        else if (e.key === 'w' || e.key === 'W') setSnakeDir(2, 0, -1);
        else if (e.key === 's' || e.key === 'S') setSnakeDir(2, 0, 1);
        else if (e.key === 'a' || e.key === 'A') setSnakeDir(2, -1, 0);
        else if (e.key === 'd' || e.key === 'D') setSnakeDir(2, 1, 0);
    });
    function startSnake() {
        snake1 = [{x:6,y:10}]; dir1 = {x:1,y:0}; score1 = 0;
        snake2 = [{x:13,y:10}]; dir2 = {x:-1,y:0}; score2 = 0;
        updateSnakeScoreText();
        if (snakeTimer) clearInterval(snakeTimer);
        snakeTimer = setInterval(stepSnake, 150);
    }
    function updateSnakeScoreText() {
        if (snakeMode === 'solo') {
            document.getElementById('snakeScoreLabel').innerHTML = 'Score: <strong id="snakeScore">' + score1 + '</strong>';
        } else {
            document.getElementById('snakeScoreLabel').innerHTML = 'P1 (Green): <strong>' + score1 + '</strong> • P2 (Blue): <strong>' + score2 + '</strong>';
        }
    }
    function stepSnake() {
        const h1 = {x: (snake1[0].x + dir1.x + 20) % 20, y: (snake1[0].y + dir1.y + 20) % 20};
        if (snake1.some(p => p.x === h1.x && p.y === h1.y)) { clearInterval(snakeTimer); return; }
        snake1.unshift(h1);
        if (h1.x === food.x && h1.y === food.y) {
            score1 += 10; food = {x: Math.floor(Math.random()*20), y: Math.floor(Math.random()*20)};
        } else { snake1.pop(); }

        if (snakeMode === 'friend') {
            const h2 = {x: (snake2[0].x + dir2.x + 20) % 20, y: (snake2[0].y + dir2.y + 20) % 20};
            if (snake2.some(p => p.x === h2.x && p.y === h2.y)) { clearInterval(snakeTimer); return; }
            snake2.unshift(h2);
            if (h2.x === food.x && h2.y === food.y) {
                score2 += 10; food = {x: Math.floor(Math.random()*20), y: Math.floor(Math.random()*20)};
            } else { snake2.pop(); }
        }
        updateSnakeScoreText();
        const ctx = document.getElementById('snakeCanvas').getContext('2d');
        ctx.fillStyle = '#111827'; ctx.fillRect(0,0,200,200);
        ctx.fillStyle = '#ef4444'; ctx.fillRect(food.x*10, food.y*10, 9, 9);
        ctx.fillStyle = '#10b981'; snake1.forEach(p => ctx.fillRect(p.x*10, p.y*10, 9, 9));
        if (snakeMode === 'friend') {
            ctx.fillStyle = '#3b82f6'; snake2.forEach(p => ctx.fillRect(p.x*10, p.y*10, 9, 9));
        }
    }

    // 3. Memory Match
    let memMode = 'solo', memCards = [], memFlipped = [], memMatched = [], memMoves = 0, memTurn = 1, memP1 = 0, memP2 = 0;
    function setMemMode(m) {
        memMode = m;
        document.getElementById('memModeSolo').className = m==='solo' ? 'btn btn-primary active' : 'btn btn-outline-primary';
        document.getElementById('memModeFriend').className = m==='friend' ? 'btn btn-primary active' : 'btn btn-outline-primary';
        initMemory();
    }
    function updateMemStatus() {
        if (memMode === 'solo') {
            document.getElementById('memStatus').innerHTML = 'Moves: <strong id="memMoves">' + memMoves + '</strong>';
        } else {
            document.getElementById('memStatus').innerHTML = 'P1: <strong>' + memP1 + '</strong> • P2: <strong>' + memP2 + '</strong> (Turn: P' + memTurn + ')';
        }
    }
    function initMemory() {
        const icons = ['📚','🔬','🌍','🧮','🎨','⚽','🚀','🎵'];
        memCards = [...icons, ...icons].sort(() => Math.random() - 0.5);
        memFlipped = []; memMatched = []; memMoves = 0; memTurn = 1; memP1 = 0; memP2 = 0;
        updateMemStatus(); renderMemory();
    }
    function renderMemory() {
        const g = document.getElementById('memGrid'); g.innerHTML = '';
        memCards.forEach((icon, i) => {
            const b = document.createElement('button');
            b.className = 'btn btn-light border p-0 fs-5'; b.style.height = '48px';
            b.textContent = (memFlipped.includes(i) || memMatched.includes(i)) ? icon : '?';
            b.onclick = () => flipMem(i); g.appendChild(b);
        });
    }
    function flipMem(i) {
        if (memFlipped.length === 2 || memFlipped.includes(i) || memMatched.includes(i)) return;
        memFlipped.push(i); renderMemory();
        if (memFlipped.length === 2) {
            memMoves++; const [a, b] = memFlipped;
            if (memCards[a] === memCards[b]) {
                memMatched.push(a, b); memFlipped = [];
                if (memTurn === 1) memP1++; else memP2++;
                updateMemStatus(); renderMemory();
            } else {
                setTimeout(() => {
                    memFlipped = [];
                    if (memMode === 'friend') memTurn = memTurn === 1 ? 2 : 1;
                    updateMemStatus(); renderMemory();
                }, 650);
            }
        }
    }
    initMemory();

    // 4. Quick Math Blitz
    let mathMode = 'solo', mA = 7, mB = 8, mStreak = 0, mathTurn = 1, mathS1 = 0, mathS2 = 0;
    function setMathMode(m) {
        mathMode = m; mStreak = 0; mathTurn = 1; mathS1 = 0; mathS2 = 0;
        document.getElementById('mathModeSolo').className = m==='solo' ? 'btn btn-primary active' : 'btn btn-outline-primary';
        document.getElementById('mathModeFriend').className = m==='friend' ? 'btn btn-primary active' : 'btn btn-outline-primary';
        updateMathStatus(); nextMath();
    }
    function updateMathStatus() {
        if (mathMode === 'solo') {
            document.getElementById('mathStatus').innerHTML = 'Streak: <strong id="mathStreak">' + mStreak + '</strong>';
        } else {
            document.getElementById('mathStatus').innerHTML = 'P1: <strong>' + mathS1 + '</strong> • P2: <strong>' + mathS2 + '</strong> (P' + mathTurn + "'s turn)";
        }
    }
    function nextMath() {
        mA = Math.floor(Math.random()*20)+2; mB = Math.floor(Math.random()*20)+2;
        document.getElementById('mathQ').textContent = mA + ' + ' + mB + ' = ?';
        document.getElementById('mathAns').value = '';
    }
    function checkMath() {
        const val = parseInt(document.getElementById('mathAns').value, 10);
        const correct = (val === mA + mB);
        if (mathMode === 'solo') {
            if (correct) { mStreak++; document.getElementById('mathFeedback').textContent = 'Correct!'; }
            else { mStreak = 0; document.getElementById('mathFeedback').textContent = 'Answer was ' + (mA+mB); }
        } else {
            if (correct) {
                if (mathTurn === 1) mathS1++; else mathS2++;
                document.getElementById('mathFeedback').textContent = 'P' + mathTurn + ' got it right!';
            } else {
                document.getElementById('mathFeedback').textContent = 'P' + mathTurn + ' missed (was ' + (mA+mB) + ')';
            }
            mathTurn = mathTurn === 1 ? 2 : 1;
        }
        updateMathStatus(); nextMath();
    }

    // 5. Rock Paper Scissors
    let rpsMode = 'bot', rP1 = 0, rP2 = 0, friendP1Choice = null;
    function setRPSMode(m) {
        rpsMode = m; rP1 = 0; rP2 = 0; friendP1Choice = null;
        document.getElementById('rpsModeBot').className = m==='bot' ? 'btn btn-primary active' : 'btn btn-outline-primary';
        document.getElementById('rpsModeFriend').className = m==='friend' ? 'btn btn-primary active' : 'btn btn-outline-primary';
        document.getElementById('rpsLabel1').textContent = m==='bot' ? 'You' : 'Player 1';
        document.getElementById('rpsLabel2').textContent = m==='bot' ? 'Bot' : 'Player 2';
        document.getElementById('rpsP1').textContent = '0'; document.getElementById('rpsP2').textContent = '0';
        document.getElementById('rpsResult').textContent = m==='bot' ? 'Pick a move!' : 'Player 1: pick your move secretly';
    }
    function scoreRPS(c1, c2, name1, name2) {
        let res = 'Tie!';
        if ((c1==='Rock'&&c2==='Scissors')||(c1==='Paper'&&c2==='Rock')||(c1==='Scissors'&&c2==='Paper')) { rP1++; res = name1 + ' Wins!'; }
        else if (c1 !== c2) { rP2++; res = name2 + ' Wins!'; }
        document.getElementById('rpsP1').textContent = rP1; document.getElementById('rpsP2').textContent = rP2;
        document.getElementById('rpsResult').textContent = name1 + ': ' + c1 + ' vs ' + name2 + ': ' + c2 + ' — ' + res;
    }
    function playRPS(choice) {
        if (rpsMode === 'bot') {
            const opts = ['Rock','Paper','Scissors'];
            scoreRPS(choice, opts[Math.floor(Math.random()*3)], 'You', 'Bot');
        } else {
            if (!friendP1Choice) {
                friendP1Choice = choice;
                document.getElementById('rpsResult').textContent = 'Player 1 locked in! Now Player 2 picks...';
            } else {
                const c1 = friendP1Choice; friendP1Choice = null;
                scoreRPS(c1, choice, 'P1', 'P2');
            }
        }
    }

    // 6. Number Guess
    let guessMode = 'solo', secretNum = Math.floor(Math.random()*100)+1, gTries = 0;
    function setGuessMode(m) {
        guessMode = m;
        document.getElementById('guessModeSolo').className = m==='solo' ? 'btn btn-success active' : 'btn btn-outline-success';
        document.getElementById('guessModeFriend').className = m==='friend' ? 'btn btn-success active' : 'btn btn-outline-success';
        document.getElementById('friendSecretBox').className = m==='friend' ? 'd-flex justify-content-center gap-1 mb-2' : 'd-none';
        resetGuess();
    }
    function setFriendSecret() {
        const val = parseInt(document.getElementById('friendSecretInput').value, 10);
        if (val >= 1 && val <= 100) {
            secretNum = val; gTries = 0;
            document.getElementById('guessTries').textContent = '0';
            document.getElementById('friendSecretInput').value = '';
            document.getElementById('guessHint').textContent = "Friend's secret number is set! Start guessing!";
        }
    }
    function checkGuess() {
        const g = parseInt(document.getElementById('guessInput').value, 10);
        if (!g) return;
        gTries++; document.getElementById('guessTries').textContent = gTries;
        const h = document.getElementById('guessHint');
        if (g === secretNum) h.textContent = '🎉 Spot on! Number was ' + secretNum + '!';
        else if (g < secretNum) h.textContent = 'Too low — try higher!';
        else h.textContent = 'Too high — try lower!';
    }
    function resetGuess() {
        secretNum = Math.floor(Math.random()*100)+1; gTries = 0;
        document.getElementById('guessTries').textContent = '0';
        document.getElementById('guessHint').textContent = guessMode==='solo' ? 'Guess my secret number!' : 'Have your friend enter a number (1-100) above!';
    }
    </script>
    """
  return render_template_string(BASE_HTML, content=content)


# ==========================================
# 10. PARENT PORTAL (RECEIVES QUIZZES/TESTS/SEATWORK/ASSIGNMENTS + NOTIFICATIONS)
# ==========================================
@app.route("/parent/login", methods=["GET", "POST"])
def parent_login():
  if request.method == "POST":
    parent = Parent.query.filter_by(email=request.form["email"]).first()
    if parent and bcrypt.check_password_hash(
        parent.password, request.form["password"]
    ):
      session.clear()
      session["parent_id"] = parent.id
      return redirect(url_for("parent_dashboard"))
    flash("Invalid Credentials", "danger")
  content = """
    <div class="container mt-5" style="max-width: 400px;"><div class="card p-4"><h3 class="text-center mb-4">Parent Login</h3>
    <form method="POST"><input class="form-control mb-3" name="email" placeholder="Email" required>
    <input class="form-control mb-3" name="password" type="password" placeholder="Password" required>
    <button class="btn btn-dark w-100">Login</button></form></div></div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/parent/reply", methods=["POST"])
def parent_reply():
  if not session.get("parent_id"):
    return redirect(url_for("parent_login"))
  parent = Parent.query.get(session["parent_id"])
  school = School.query.get(parent.school_id)
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked

  reply_text = request.form["reply"].strip()
  student_id = request.form.get("student_id")
  student = (
      Student.query.get(int(student_id))
      if student_id
      else Student.query.filter_by(parent_id=parent.id).first()
  )
  if not reply_text:
    flash("Please enter a reply before sending.", "warning")
    return redirect(url_for("parent_dashboard"))

  send_parent_alert(
      parent.phone,
      reply_text,
      student=student,
      parent_id=parent.id,
      sender_label=f"Parent ({parent.full_name})",
      direction="from_parent",
  )
  flash("Your reply was sent to the Principal and Cashier.", "success")
  return redirect(url_for("parent_dashboard"))


@app.route("/parent/dashboard")
def parent_dashboard():
  if not session.get("parent_id"):
    return redirect(url_for("parent_login"))
  parent = Parent.query.get(session["parent_id"])
  school = School.query.get(parent.school_id)
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked

  children = Student.query.filter_by(parent_id=parent.id).all()
  child_blocks = ""
  for c in children:
    grades = Grade.query.filter_by(student_id=c.id).all()
    ca_records = (
        AssessmentRecord.query.filter_by(student_id=c.id)
        .order_by(AssessmentRecord.id.desc())
        .all()
    )
    att = Attendance.query.filter_by(student_id=c.id).all()
    fee = FeeRecord.query.filter_by(student_id=c.id).first()
    assignments = Assignment.query.filter_by(classroom_id=c.classroom_id).all()
    msgs = (
        PortalMessage.query.filter(
            (PortalMessage.student_id == c.id)
            | (PortalMessage.parent_id == parent.id)
        )
        .order_by(PortalMessage.id.desc())
        .all()
    )
    rank_str, _ = compute_class_rank(c)

    g_txt = (
        ", ".join([f"[{g.period}] {g.subject}: {g.score}%" for g in grades])
        or "None"
    )
    a_txt = (
        ", ".join([f"{a.date} ({a.status})" for a in att])
        or "No attendance logged"
    )
    as_txt = (
        ", ".join([f"{x.title} (Due {x.due_date})" for x in assignments])
        or "None"
    )
    if fee:
      bal = max(0.0, fee.total_fees - fee.amount_paid)
      f_txt = f"Paid {format_money(fee.amount_paid, fee.currency)} of {format_money(fee.total_fees, fee.currency)} (Balance: {format_money(bal, fee.currency)})"
    else:
      f_txt = "No fee record"

    ca_list = (
        "".join([
            f"<li class='list-group-item d-flex justify-content-between'><span><span class='badge bg-light text-dark border'>{r.category}</span> <strong>{r.label}</strong> — {r.subject}</span><strong>{r.score}/{r.max_score}</strong></li>"
            for r in ca_records
        ])
        or "<li class='list-group-item text-muted'>No quiz, seat work, assignment, or test scores recorded yet.</li>"
    )

    msg_list = (
        "".join([
            f"<li class='list-group-item'><small class='text-muted'>{m.created_at.strftime('%Y-%m-%d %H:%M')} • <strong>{m.sender_label}</strong></small><br>{m.body}</li>"
            for m in msgs
        ])
        or "<li class='list-group-item text-muted'>No messages yet.</li>"
    )

    child_blocks += f"""
        <div class="card p-4 mb-4">
            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
                <div>
                    <h5 class="mb-0"><i class="fas fa-user-graduate me-2"></i>{c.full_name}</h5>
                    <small class="text-muted">Class Position: <strong>{rank_str}</strong></small>
                </div>
                <div>
                    <a href="/report_card/{c.id}" class="btn btn-sm btn-outline-primary">Report Card</a>
                    <a href="/receipt/{c.id}" class="btn btn-sm btn-outline-success">Receipt</a>
                </div>
            </div>
            <p class="mb-1 mt-2"><strong>Fees:</strong> {f_txt}</p>
            <p class="mb-1"><strong>Official Report Grades:</strong> {g_txt}</p>
            <p class="mb-1"><strong>Attendance:</strong> {a_txt}</p>
            <p class="mb-3"><strong>Active Homework:</strong> {as_txt}</p>

            <div class="mb-3">
                <h6><i class="fas fa-clipboard-check text-success me-1"></i>Quizzes, Seat Work, Assignments & Tests</h6>
                <div class="scroll-feed" style="max-height:200px;">
                    <ul class="list-group">{ca_list}</ul>
                </div>
            </div>

            <div class="border-top pt-3">
                <h6><i class="fas fa-envelope-open-text text-primary me-1"></i>Fee & School Messages</h6>
                <div class="scroll-feed mb-3">
                    <ul class="list-group">{msg_list}</ul>
                </div>
                <form method="POST" action="/parent/reply" class="d-flex gap-2">
                    <input type="hidden" name="student_id" value="{c.id}">
                    <input type="text" name="reply" class="form-control" placeholder="Write a reply to the Principal or Cashier..." required>
                    <button type="submit" class="btn btn-primary">Reply</button>
                </form>
            </div>
        </div>
        """

  content = f"""
    {render_unread_dm_banner(f"parent:{parent.id}")}
    <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
        <div class="d-flex align-items-center gap-3">
            {school_logo_html(school, 48)}
            <div>
                <h3 class="mb-0">Parent Portal — {parent.full_name}</h3>
                <small class="text-muted">{school.name}</small>
            </div>
        </div>
        <a href="/chat" class="btn btn-primary btn-sm"><i class="fas fa-comments me-1"></i>Private Chat With Staff</a>
    </div>
    {child_blocks or '<div class="card p-4 mt-3"><p class="text-muted mb-0">No students linked to this parent account yet.</p></div>'}
    """
  return render_template_string(BASE_HTML, content=content)


# ==========================================
# 11. PRIVATE ROLE-SEPARATED SCHOOL CHAT (/chat + AUTO READ RECEIPT)
# ==========================================
@app.route("/chat", methods=["GET", "POST"])
def private_chat():
  school_id, actor_key, actor_name, role_group, dash_url = (
      get_current_chat_actor()
  )
  if not actor_key or not school_id:
    flash(
        "Please log in as a Student, Parent, Teacher, Cashier, or Principal to"
        " use Private Chat.",
        "warning",
    )
    return redirect(url_for("home"))

  school = School.query.get(school_id)
  locked = check_school_access_or_lockout(school)
  if locked:
    return locked

  contacts = get_allowed_chat_contacts(school_id, actor_key, role_group)
  allowed_map = {c["key"]: c for c in contacts}

  if request.method == "POST":
    to_key = request.form.get("to_key", "")
    body = request.form.get("body", "").strip()
    if to_key in allowed_map and body:
      target = allowed_map[to_key]
      db.session.add(
          DirectMessage(
              school_id=school_id,
              sender_key=actor_key,
              sender_name=actor_name,
              receiver_key=to_key,
              receiver_name=f"{target['name']} ({target['badge']})",
              body=body,
              is_read=False,
          )
      )
      db.session.commit()
    return redirect(url_for("private_chat", to=to_key))

  friend_q = request.args.get("q", "").strip().lower()
  filtered_contacts = [
      c
      for c in contacts
      if not friend_q
      or friend_q in c["name"].lower()
      or friend_q in c["badge"].lower()
  ]

  selected_key = request.args.get("to", "")
  if selected_key not in allowed_map and filtered_contacts:
    selected_key = filtered_contacts[0]["key"]

  if selected_key in allowed_map:
    unread_msgs = DirectMessage.query.filter_by(
        school_id=school_id,
        sender_key=selected_key,
        receiver_key=actor_key,
        is_read=False,
    ).all()
    if unread_msgs:
      for um in unread_msgs:
        um.is_read = True
      db.session.commit()
      contacts = get_allowed_chat_contacts(school_id, actor_key, role_group)
      allowed_map = {c["key"]: c for c in contacts}
      filtered_contacts = [
          c
          for c in contacts
          if not friend_q
          or friend_q in c["name"].lower()
          or friend_q in c["badge"].lower()
      ]

  contact_list_html = ""
  for c in filtered_contacts:
    active_cls = "active" if c["key"] == selected_key else ""
    unread_badge = (
        f"<span class='badge bg-danger float-end'>{c['unread']}</span>"
        if c["unread"] > 0
        else ""
    )
    contact_list_html += f"""
        <a href="/chat?to={c['key']}&q={friend_q}" class="list-group-item list-group-item-action {active_cls}">
            <div class="fw-bold">{c['name']} {unread_badge}</div>
            <small class="{'text-white-50' if active_cls else 'text-muted'}">{c['badge']}</small>
        </a>
        """

  thread_html = ""
  selected_target = allowed_map.get(selected_key)
  if selected_target:
    msgs = (
        DirectMessage.query.filter_by(school_id=school_id)
        .filter(
            (
                (DirectMessage.sender_key == actor_key)
                & (DirectMessage.receiver_key == selected_key)
            )
            | (
                (DirectMessage.sender_key == selected_key)
                & (DirectMessage.receiver_key == actor_key)
            )
        )
        .order_by(DirectMessage.id.asc())
        .all()
    )
    for m in msgs:
      is_me = m.sender_key == actor_key
      align = "justify-content-end" if is_me else "justify-content-start"
      bubble = "chat-bubble-me" if is_me else "chat-bubble-them"
      del_link = (
          f"<a href='/chat/delete/{m.id}?to={selected_key}' class='text-white-50 ms-2 small' title='Delete'><i class='fas fa-trash'></i></a>"
          if is_me
          else ""
      )
      thread_html += f"""
            <div class="d-flex {align} mb-2">
                <div class="{bubble}">
                    <div class="small fw-bold opacity-75">{m.sender_name} • {m.created_at.strftime('%H:%M')} {del_link}</div>
                    <div>{m.body}</div>
                </div>
            </div>
            """

  room_label = (
      "Student Friend Chat (Students Only)"
      if role_group == "student"
      else "Private Staff & Parent Chat"
  )
  games_btn = (
      '<a href="/student/games" class="btn btn-warning text-dark btn-sm"><i'
      ' class="fas fa-gamepad me-1"></i>Mini-Games</a>'
      if role_group == "student"
      else ""
  )

  content = f"""
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <div>
            <h3 class="mb-0"><i class="fas fa-comments text-primary me-2"></i>{room_label}</h3>
            <small class="text-muted">Signed in as <strong>{actor_name}</strong></small>
        </div>
        <div class="d-flex gap-2">
            {games_btn}
            <a href="{dash_url}" class="btn btn-outline-secondary btn-sm">Back to Dashboard</a>
        </div>
    </div>

    <div class="row">
        <div class="col-md-4 mb-3">
            <div class="card p-3">
                <form method="GET" action="/chat" class="d-flex gap-1 mb-2">
                    <input type="text" name="q" class="form-control form-control-sm" placeholder="Search friend / contact..." value="{friend_q}">
                    <button class="btn btn-sm btn-primary">Find</button>
                </form>
                <div class="scroll-feed" style="max-height:420px;">
                    <div class="list-group">
                        {contact_list_html or '<div class="text-muted small p-2">No contacts found.</div>'}
                    </div>
                </div>
            </div>
        </div>
        <div class="col-md-8 mb-3">
            <div class="card p-4">
                <h5 class="border-bottom pb-2 mb-3">{selected_target['name'] + ' — ' + selected_target['badge'] if selected_target else 'Select a contact to start chatting'}</h5>
                <div class="chat-thread mb-3" id="chatThreadBox">
                    {thread_html or '<p class="text-muted text-center my-5">No messages yet. Say hello!</p>'}
                </div>
                {f'''
                <form method="POST" class="d-flex gap-2">
                    <input type="hidden" name="to_key" value="{selected_key}">
                    <input type="text" name="body" class="form-control" placeholder="Type a private message..." required autofocus>
                    <button type="submit" class="btn btn-primary"><i class="fas fa-paper-plane me-1"></i>Send</button>
                </form>
                ''' if selected_target else ''}
            </div>
        </div>
    </div>
    <script>
        var box = document.getElementById('chatThreadBox');
        if (box) {{ box.scrollTop = box.scrollHeight; }}
    </script>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/chat/delete/<int:msg_id>")
def delete_chat_message(msg_id):
  _, actor_key, _, _, _ = get_current_chat_actor()
  if not actor_key:
    return redirect(url_for("home"))
  m = DirectMessage.query.filter_by(
      id=msg_id, sender_key=actor_key
  ).first_or_404()
  to_key = request.args.get("to", m.receiver_key)
  db.session.delete(m)
  db.session.commit()
  return redirect(url_for("private_chat", to=to_key))


# ==========================================
# 12. PRINTABLE REPORT CARDS (WITH CLASS RANK) & FEE RECEIPTS
# ==========================================
@app.route("/report_card/<int:student_id>")
def report_card(student_id):
  student = Student.query.get_or_404(student_id)
  classroom = Classroom.query.get(student.classroom_id)
  school = School.query.get(classroom.school_id) if classroom else None
  grades = Grade.query.filter_by(student_id=student.id).all()
  att_records = Attendance.query.filter_by(student_id=student.id).all()

  rank_str, avg_score = compute_class_rank(student)
  present_count = sum(1 for a in att_records if a.status.lower() == "present")
  total_days = len(att_records)

  grade_rows = "".join([
      f"<tr><td>{g.period}</td><td>{g.subject}</td><td><strong>{g.score}%</strong></td></tr>"
      for g in grades
  ])

  content = f"""
    <div class="card p-5 mx-auto" style="max-width: 760px;">
        <div class="d-flex justify-content-between align-items-start border-bottom pb-3 mb-4">
            <div class="d-flex align-items-center gap-3">
                {school_logo_html(school, 56)}
                <div>
                    <h2 class="mb-1">{school.name if school else 'EduSphere Academy'}</h2>
                    <p class="text-muted mb-0">Official Student Academic Report Card</p>
                </div>
            </div>
            <button onclick="window.print()" class="btn btn-primary no-print"><i class="fas fa-print me-1"></i>Print / Save PDF</button>
        </div>
        <div class="row mb-4">
            <div class="col-6"><strong>Student:</strong> {student.full_name}</div>
            <div class="col-6"><strong>Class:</strong> {classroom.name if classroom else 'N/A'}</div>
            <div class="col-6 mt-2"><strong>Average Score:</strong> {avg_score}%</div>
            <div class="col-6 mt-2"><strong>Class Rank / Position:</strong> <span class="badge bg-primary">{rank_str}</span></div>
            <div class="col-6 mt-2"><strong>Attendance:</strong> {present_count} / {total_days} Present</div>
        </div>
        <table class="table table-bordered">
            <thead class="table-light"><tr><th>Marking Period</th><th>Subject</th><th>Score</th></tr></thead>
            <tbody>{grade_rows or '<tr><td colspan="3">No official report grades recorded yet.</td></tr>'}</tbody>
        </table>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


@app.route("/receipt/<int:student_id>")
def fee_receipt(student_id):
  student = Student.query.get_or_404(student_id)
  classroom = Classroom.query.get(student.classroom_id)
  school = School.query.get(classroom.school_id) if classroom else None
  fee = FeeRecord.query.filter_by(student_id=student.id).first()
  txs = (
      FeeTransaction.query.filter_by(student_id=student.id)
      .order_by(FeeTransaction.id.desc())
      .all()
  )

  cur = fee.currency if fee else "USD"
  total = fee.total_fees if fee else 0.0
  paid = fee.amount_paid if fee else 0.0
  balance = max(0.0, total - paid)
  receipt_code = (
      fee.last_receipt_code
      if (fee and fee.last_receipt_code)
      else f"RCP-{student.id:04d}"
  )
  pay_date = (
      fee.last_payment_date
      if (fee and fee.last_payment_date)
      else datetime.now().strftime("%Y-%m-%d")
  )

  tx_rows = "".join([
      f"<tr><td>{t.created_at.strftime('%Y-%m-%d %H:%M')}</td><td>{t.receipt_code}</td><td>{format_money(t.amount, t.currency)}</td><td>{t.recorded_by}</td></tr>"
      for t in txs
  ])

  content = f"""
    <div class="card p-5 mx-auto" style="max-width: 720px;">
        <div class="d-flex justify-content-between align-items-start border-bottom pb-3 mb-4">
            <div class="d-flex align-items-center gap-3">
                {school_logo_html(school, 56)}
                <div>
                    <h2 class="mb-1">{school.name if school else 'EduSphere Academy'}</h2>
                    <p class="text-muted mb-0">Official Tuition & Fee Receipt • Latest Ref: <strong>{receipt_code}</strong></p>
                </div>
            </div>
            <button onclick="window.print()" class="btn btn-success no-print"><i class="fas fa-print me-1"></i>Print Receipt</button>
        </div>
        <p><strong>Student Name:</strong> {student.full_name}</p>
        <p><strong>Class:</strong> {classroom.name if classroom else 'N/A'}</p>
        <p><strong>Last Updated:</strong> {pay_date}</p>
        <hr>
        <p><strong>Total Tuition Fees:</strong> {format_money(total, cur)}</p>
        <p><strong>Total Amount Paid:</strong> {format_money(paid, cur)}</p>
        <p><strong>Remaining Balance:</strong> <strong>{format_money(balance, cur)}</strong></p>

        <h6 class="mt-4">Installment Payment History</h6>
        <table class="table table-sm table-bordered">
            <thead class="table-light"><tr><th>Date</th><th>Receipt #</th><th>Amount</th><th>Cashier</th></tr></thead>
            <tbody>{tx_rows or '<tr><td colspan="4">No individual payment records yet.</td></tr>'}</tbody>
        </table>
    </div>
    """
  return render_template_string(BASE_HTML, content=content)


if __name__ == "__main__":
  with app.app_context():
    db.create_all()
    ensure_sqlite_columns()
    get_platform_config()
  is_debug = os.environ.get("FLASK_DEBUG", "1") == "1"
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port, debug=is_debug)
