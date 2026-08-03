import os
import re
import secrets as crypto_secrets
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

from bson import ObjectId as BsonObjectId


import bcrypt
import certifi
from bson.objectid import ObjectId
from dotenv import load_dotenv
from flask import (Flask, Response, flash, redirect, render_template,
                   request, session, url_for)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import (LoginManager, UserMixin, current_user,
                         login_required, login_user, logout_user)
from pymongo import MongoClient
from werkzeug.utils import secure_filename

from send_email import send_email

# =======================
# Load environment variables
# =======================
load_dotenv()

# =======================
# Flask App Setup
# =======================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key or "change-this" in app.secret_key:
    raise RuntimeError(
        "SECRET_KEY must be set to a strong random value in the .env file. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

# =======================
# Rate Limiting
# =======================
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# =======================
# Secure Response Headers
# =======================
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "font-src 'self' https://cdnjs.cloudflare.com; "
        "img-src 'self' data:; "
        "script-src 'self' 'unsafe-inline'"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Server"] = ""  # Hide server header
    return response

# =======================
# MongoDB Atlas Setup
# =======================
MONGO_USERNAME = quote_plus(os.environ.get("MONGO_USERNAME", ""))
MONGO_PASSWORD = quote_plus(os.environ.get("MONGO_PASSWORD", ""))
MONGO_CLUSTER = os.environ.get("MONGO_CLUSTER", "")
MONGO_DB = os.environ.get("MONGO_DB", "savelife")

if not all([MONGO_USERNAME, MONGO_PASSWORD, MONGO_CLUSTER]):
    raise RuntimeError("MongoDB credentials (USERNAME, PASSWORD, CLUSTER) must be set in .env file")

MONGO_URI = (
    f"mongodb+srv://{MONGO_USERNAME}:{MONGO_PASSWORD}"
    f"@{MONGO_CLUSTER}/{MONGO_DB}?retryWrites=true&w=majority"
)

try:
    client = MongoClient(
        MONGO_URI,
        tls=True,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=10000,
    )
    db = client[MONGO_DB]
    donors_col = db["donors"]
    users_col = db["users"]
    requests_col = db["requests"]
    print("✅ MongoDB connected successfully!")
except Exception as e:
    print("❌ MongoDB connection error:", e)
    donors_col = None
    users_col = None
    requests_col = None

# =======================
# Flask-Login Setup
# =======================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.session_protection = "strong"


class User(UserMixin):
    def __init__(self, user_doc):
        self.id = str(user_doc["_id"])
        self.name = user_doc.get("name")
        self.email = user_doc.get("email")
        self.phone = user_doc.get("phone")
        self.blood_group = user_doc.get("blood_group")
        self.address = user_doc.get("address")
        self.is_disabled = user_doc.get("is_disabled", False)
        self.photo = user_doc.get("photo")

    def get_id(self):
        return self.id


@login_manager.user_loader
def load_user(user_id):
    if users_col is None:
        return None
    try:
        user_data = users_col.find_one({"_id": ObjectId(user_id)})
        if user_data:
            return User(user_data)
    except Exception as e:
        print("Error loading user:", e)
    return None


# =======================
# CSRF Protection
# =======================
def generate_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = crypto_secrets.token_hex(32)
    return session["_csrf_token"]


def validate_csrf():
    token = request.form.get("_csrf_token", "")
    stored = session.get("_csrf_token", "")
    if not token or not stored or not crypto_secrets.compare_digest(token, stored):
        flash("Invalid form submission. Please refresh the page and try again.", "danger")
        return False
    return True


app.jinja_env.globals["csrf_token"] = generate_csrf_token


# =======================
# Input Validation Helpers
# =======================
VALID_BLOOD_GROUPS = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
ALLOWED_PHOTO_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
ALLOWED_PHOTO_MIMETYPES = {"image/png", "image/jpeg", "image/gif"}
MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5 MB


def sanitize_string(value, max_length=200):
    """Strip whitespace, limit length, strip control characters."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    # Remove control characters except common whitespace
    value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value)
    return value[:max_length]


def validate_email(email):
    """Validate and normalize email address."""
    email = (email or "").strip().lower()
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return None
    if len(email) > 254:
        return None
    return email


def validate_phone(phone):
    """Validate Indian mobile number (10 digits, starts with 6-9)."""
    phone = re.sub(r'\D', '', phone or "")
    if re.match(r'^[6-9]\d{9}$', phone):
        return phone
    return None


def validate_blood_group(bg):
    """Validate blood group against allowed values."""
    bg = (bg or "").strip().upper()
    return bg if bg in VALID_BLOOD_GROUPS else None


def hash_password(password):
    """Hash a password using bcrypt with 12 rounds."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))


def check_password(password, hashed):
    """Verify a password against its bcrypt hash."""
    if isinstance(hashed, str):
        hashed = hashed.encode('utf-8')
    return bcrypt.checkpw(password.encode('utf-8'), hashed)


# =======================
# Helpers
# =======================

# --------------------------------
# Blood Compatibility Matrix (RBC Donation)
# --------------------------------
# Maps recipient blood group → list of donor blood groups that can donate to them
BLOOD_COMPATIBILITY = {

    "O-":  ["O-"],
    "O+":  ["O-", "O+"],
    "A-":  ["O-", "A-"],
    "A+":  ["O-", "O+", "A-", "A+"],
    "B-":  ["O-", "B-"],
    "B+":  ["O-", "O+", "B-", "B+"],
    "AB-": ["O-", "A-", "B-", "AB-"],
    "AB+": ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"],
}

# O- is the universal donor (appears in every recipient's list)
# AB+ is the universal acceptor (can receive from all blood groups)


def get_compatible_donor_groups(recipient_blood_group):
    """Return list of blood groups that can donate to the given recipient."""
    return BLOOD_COMPATIBILITY.get(recipient_blood_group, [recipient_blood_group])


DONOR_STATUS_AVAILABLE = "AVAILABLE"
DONOR_STATUS_TEMP_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"
DONOR_STATUS_MANUALLY_DISABLED = "MANUALLY_DISABLED"


def infer_donor_status(doc):
    """Backward-compatible status inference for existing users/donors."""
    if not doc:
        return DONOR_STATUS_AVAILABLE

    status = doc.get("status")
    if status:
        return status

    # Legacy boolean flag fallback
    if doc.get("is_disabled", False):
        return DONOR_STATUS_MANUALLY_DISABLED
    return DONOR_STATUS_AVAILABLE


def find_donors(blood_group, city, state):
    """Return donors with compatible blood groups for the given recipient.

    Only AVAILABLE donors are returned.
    Also supports legacy data where `status` might not exist yet.
    """
    if donors_col is None:
        return []
    compatible_groups = get_compatible_donor_groups(blood_group)

    # AVAILABLE donors OR legacy donors that are not disabled
    query = {
        "blood_group": {"$in": compatible_groups},
        "city": {"$regex": f"^{re.escape(city)}$", "$options": "i"},
        "state": {"$regex": f"^{re.escape(state)}$", "$options": "i"},
        "$or": [
            {"status": DONOR_STATUS_AVAILABLE},
            {"status": {"$exists": False}, "is_disabled": {"$ne": True}},
            {"status": None, "is_disabled": {"$ne": True}},
        ],
    }

    donors = list(donors_col.find(query, {"_id": 0, "email": 1, "name": 1}))
    return donors



# =======================
# Routes
# =======================
@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/home")
@login_required
def home():
    return render_template("home.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/faq")
def faq():
    return render_template("faq.html")


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def register():
    if request.method == "POST":
        if not validate_csrf():
            return render_template("register.html")

        # ---- Validate inputs server-side ----
        name = sanitize_string(request.form.get("name", ""))
        email = validate_email(request.form.get("email", ""))
        phone = validate_phone(request.form.get("phone", ""))
        password = request.form.get("password", "")
        blood_group = validate_blood_group(request.form.get("blood_group", ""))
        address = sanitize_string(request.form.get("address", ""), max_length=500)

        errors = []
        if not name:
            errors.append("Name is required.")
        if not email:
            errors.append("A valid email address is required.")
        if not phone:
            errors.append("A valid 10-digit phone number is required.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if not blood_group:
            errors.append("A valid blood group is required.")

        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template("register.html")

        # Check for existing email in users_col
        if users_col.find_one({"email": email}):
            flash("Email already registered!", "danger")
            return render_template("register.html")

        hashed_pw = hash_password(password)
        now = datetime.now(timezone.utc)

        # Insert into users_col (for authentication)
        users_col.insert_one({
            "name": name,
            "email": email,
            "phone": phone,
            "password": hashed_pw,
            "blood_group": blood_group,
            "address": address,
            "is_disabled": False,
            "is_donor": True,
            "created_at": now,
        })

        # Also insert into donors_col (for donor search functionality)
        donors_col.insert_one({
            "name": name,
            "email": email,
            "phone": phone,
            "password": hashed_pw,
            "blood_group": blood_group,
            "address": address,
            "is_disabled": False,
            "created_at": now,
        })

        # Send welcome email
        subject = "Welcome to LIFE_CONNECT"
        body = f"<p>Hello {name},</p><p>Thank you for registering on <b>LIFE_CONNECT</b>. Your account is now created.</p>"
        send_email(subject, [email], body)

        flash("✅ Registration successful!", "success")
        return redirect(url_for("home"))

    return render_template("register.html")


@app.route("/request_blood", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def request_blood():
    if request.method == "POST":
        if not validate_csrf():
            return redirect(url_for("request_blood"))

        blood_group = validate_blood_group(request.form.get("blood_group", ""))
        city = sanitize_string(request.form.get("city", ""))
        state = sanitize_string(request.form.get("state", ""))
        patient_name = sanitize_string(request.form.get("patient_name", ""))
        patient_phone = validate_phone(request.form.get("patient_phone", ""))

        if not all([blood_group, city, state, patient_name, patient_phone]):
            flash("All fields are required with valid values.", "danger")
            return render_template("request_blood.html")

        donors = find_donors(blood_group, city, state)
        emails = [d["email"] for d in donors if d.get("email")]

        if emails:
            subject = f"Urgent Blood Request for {patient_name}"
            body = (
                f"<h2>🚨 Urgent Blood Requirement</h2>"
                f"<p>Dear Donor,</p><p>We have an urgent request for blood donation:</p>"
                f"<ul><li><b>Patient Name:</b> {patient_name}</li>"
                f"<li><b>Blood Group:</b> {blood_group}</li>"
                f"<li><b>Contact Number:</b> {patient_phone}</li>"
                f"<li><b>Location:</b> {city}, {state}</li></ul>"
                f"<p>Please contact the patient/hospital immediately if you can donate.</p>"
                f"<p>Thank you for saving lives! ❤️</p>"
            )
            if send_email(subject, emails, body):
                flash("📩 Blood request sent to matching donors!", "success")
            else:
                flash("⚠️ Could not send emails.", "warning")
        else:
            flash("⚠️ No matching donors found.", "warning")
    return render_template("request_blood.html")


@app.route("/find", methods=["GET", "POST"])
@limiter.limit("20 per hour")
@login_required
def find():
    form_submitted = False
    results = []
    success = False
    page = request.args.get('page', 1, type=int)
    per_page = 5

    if request.method == "POST":
        if not validate_csrf():
            return redirect(url_for("find"))

        form_submitted = True

        name = sanitize_string(request.form.get("your_name", ""))
        gender = request.form.get("gender", "")
        mobile = validate_phone(request.form.get("your_mobile", ""))
        email = validate_email(request.form.get("email", ""))
        blood_group = validate_blood_group(request.form.get("blood_group", ""))
        city = sanitize_string(request.form.get("city", ""))
        state = sanitize_string(request.form.get("state", ""))

        if not all([name, mobile, email, blood_group, city, state]):
            flash("All fields are required with valid values.", "danger")
            return render_template("find.html",
                                   results=None, form_submitted=False, success=False,
                                   page=1, total_pages=0,
                                   selected_blood_group="", selected_city="", selected_state="")

        request_data = {
            "name": name,
            "gender": gender,
            "mobile": mobile,
            "email": email,
            "blood_group": blood_group,
            "city": city,
            "state": state,
            "request_date": datetime.now(timezone.utc),
        }
        requests_col.insert_one(request_data)
        success = True

        # Send confirmation email to requester
        subject = "Blood Request Confirmation"
        body = (
            f"<p>Hello {name},</p>"
            f"<p>Your request for <b>{blood_group}</b> blood in {city}, {state} has been received.</p>"
            f"<p>We will connect you with donors soon.</p>"
        )
        send_email(subject, [email], body)

        # Notify matching donors
        donors = find_donors(blood_group, city, state)
        donor_emails = [d.get("email") for d in donors if d.get("email")]

        if donor_emails:
            subject = f"Urgent Blood Request for {name}"
            body = (
                f"<h2>🚨 Urgent Blood Requirement</h2><p>Dear Donor,</p>"
                f"<p>Patient Name: {name}</p><p>Blood Group: {blood_group}</p>"
                f"<p>Contact Number: {mobile}</p><p>Location: {city}, {state}</p>"
            )
            send_email(subject, donor_emails, body)
            flash(f"📩 Blood request sent to {len(donor_emails)} matching donors!", "success")
        else:
            flash("⚠️ No matching donors found.", "warning")

        # Paginate results using compatible blood groups (hide sensitive fields)
        compatible_groups = get_compatible_donor_groups(blood_group)
        all_results = list(donors_col.find(
            {
                "blood_group": {"$in": compatible_groups},
                "city": {"$regex": f"^{re.escape(city)}$", "$options": "i"},
                "state": {"$regex": f"^{re.escape(state)}$", "$options": "i"},
                "is_disabled": {"$ne": True},
            },
            {"email": 0, "password": 0}
        ))
        total_results = len(all_results)
        total_pages = (total_results + per_page - 1) // per_page
        start = (page - 1) * per_page
        end = start + per_page
        results = all_results[start:end]

        return render_template('find.html',
                               results=results, form_submitted=form_submitted,
                               success=success, page=page, total_pages=total_pages,
                               selected_blood_group=blood_group,
                               selected_city=city, selected_state=state)

    return render_template('find.html',
                           results=None, form_submitted=False, success=False,
                           page=1, total_pages=0,
                           selected_blood_group="", selected_city="", selected_state="")


@app.route("/signup", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def signup():
    if request.method == "POST":
        if not validate_csrf():
            return redirect(url_for("signup"))

        name = sanitize_string(request.form.get("name", ""))
        email = validate_email(request.form.get("email", ""))
        password = request.form.get("password", "")

        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for("signup"))
        if not email:
            flash("A valid email address is required.", "danger")
            return redirect(url_for("signup"))
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(url_for("signup"))

        if users_col.find_one({"email": email}):
            flash("Email already registered!", "danger")
            return redirect(url_for("signup"))

        users_col.insert_one({
            "name": name,
            "email": email,
            "password": hash_password(password),
            "created_at": datetime.now(timezone.utc),
        })
        flash("Signup successful! You can now login.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if request.method == "POST":
        if not validate_csrf():
            return render_template("login.html")

        email = validate_email(request.form.get("email", ""))
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter both email and password.", "warning")
            return render_template("login.html")

        user = users_col.find_one({"email": email})
        if user and check_password(password, user.get("password", "")):
            session["user_id"] = str(user["_id"])
            login_user(User(user))
            flash("Logged in successfully!", "success")
            return redirect(url_for("home"))

        # Use a generic message to avoid user enumeration
        flash("Invalid email or password.", "danger")
        return render_template("login.html")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    session.pop("user_id", None)
    session.pop("_csrf_token", None)
    logout_user()
    flash("Logged out successfully!", "success")
    return redirect(url_for("login"))


@app.route("/health")
@limiter.exempt
def health():
    return {"status": "ok"}, 200


# ----------------- PROFILE PAGE -----------------
@app.route("/profile")
@login_required
def profile():
    user_doc = users_col.find_one({"_id": ObjectId(current_user.id)})
    if not user_doc:
        flash("User not found.", "danger")
        return redirect(url_for("index"))

    requests_list = list(requests_col.find({"to_user": ObjectId(current_user.id)}))
    for req in requests_list:
        try:
            from_user = users_col.find_one({"_id": ObjectId(req["from_user"])})
            req["from_user_name"] = from_user["name"] if from_user else "Unknown"
        except Exception:
            req["from_user_name"] = "Unknown"

    return render_template("profile.html", user=user_doc, requests=requests_list)


# ----------------- SERVE PROFILE PHOTO -----------------
@app.route("/photo/<user_id>")
def photo(user_id):
    try:
        user = users_col.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return redirect(url_for("static", filename="default.jpg"))

    if user and user.get("photo"):
        filename = secure_filename(user["photo"])
        return redirect(url_for("static", filename="uploads/" + filename))
    return redirect(url_for("static", filename="default.jpg"))


# ----------------- UPLOAD PROFILE PHOTO -----------------
@app.route("/upload_photo", methods=["POST"])
@login_required
def upload_photo():
    if not validate_csrf():
        return redirect(url_for("profile"))

    if "photo" not in request.files:
        flash("No file part.", "danger")
        return redirect(url_for("profile"))

    file = request.files["photo"]

    if not file or file.filename == "":
        flash("No selected file.", "danger")
        return redirect(url_for("profile"))

    # Validate file extension
    filename = secure_filename(file.filename)
    if "." not in filename:
        flash("Invalid file type.", "danger")
        return redirect(url_for("profile"))

    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        flash("Only PNG, JPG, JPEG, and GIF files are allowed.", "danger")
        return redirect(url_for("profile"))

    # Validate MIME type
    if file.content_type not in ALLOWED_PHOTO_MIMETYPES:
        flash("Invalid file type.", "danger")
        return redirect(url_for("profile"))

    # Check file size by reading the stream
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > MAX_PHOTO_SIZE:
        flash("File size must be under 5 MB.", "danger")
        return redirect(url_for("profile"))

    # Save with user ID as filename (prevents path traversal)
    safe_filename = f"{current_user.id}.{ext}"
    filepath = os.path.join("static/uploads", safe_filename)
    file.save(filepath)

    users_col.update_one(
        {"_id": ObjectId(current_user.id)},
        {"$set": {"photo": safe_filename}},
    )

    flash("Profile photo updated successfully!", "success")
    return redirect(url_for("profile"))


# ----------------- UPDATE PROFILE INFO -----------------
@app.route("/update_profile", methods=["POST"])
@login_required
def update_profile():
    if not validate_csrf():
        return redirect(url_for("profile"))

    name = sanitize_string(request.form.get("name", ""))
    email = validate_email(request.form.get("email", ""))
    phone = validate_phone(request.form.get("phone", ""))
    blood_group = validate_blood_group(request.form.get("blood_group", ""))
    address = sanitize_string(request.form.get("address", ""), max_length=500)

    update_fields = {}
    if name:
        update_fields["name"] = name
    if email:
        update_fields["email"] = email
    if phone:
        update_fields["phone"] = phone
    if blood_group:
        update_fields["blood_group"] = blood_group
    if address is not None:
        update_fields["address"] = address

    if update_fields:
        users_col.update_one(
            {"_id": ObjectId(current_user.id)},
            {"$set": update_fields},
        )
        flash("Profile updated successfully!", "success")
    else:
        flash("No valid fields to update.", "warning")

    return redirect(url_for("profile"))


@app.route("/enable_profile", methods=["POST"])
@login_required
def enable_profile():
    if not validate_csrf():
        return redirect(url_for("profile"))
    users_col.update_one(
        {"_id": ObjectId(current_user.id)},
        {"$set": {"is_donor": True}},
    )
    flash("Your profile has been enabled as a donor.", "success")
    return redirect(url_for("profile"))


@app.route("/disable_profile", methods=["POST"])
@login_required
def disable_profile():
    # Legacy endpoint. Now treated as a manual disable to match new status system.
    if not validate_csrf():
        return redirect(url_for("profile"))

    now = datetime.now(timezone.utc)
    users_col.update_one(
        {"_id": ObjectId(current_user.id)},
        {
            "$set": {
                "is_donor": False,
                "status": DONOR_STATUS_MANUALLY_DISABLED,
                "disabledAt": now,
                "disabledUntil": None,
                "lastStatusChange": now,
                "lastReminderSent": None,
            }
        },
    )
    flash("Your profile has been disabled.", "info")
    return redirect(url_for("profile"))




# ----------------- SEND REQUEST -----------------
@app.route("/send_request/<to_user_id>", methods=["POST"])
@login_required
def send_request(to_user_id):
    if not validate_csrf():
        return redirect(url_for("profile"))

    try:
        to_user_oid = ObjectId(to_user_id)
    except Exception:
        flash("Invalid user ID.", "danger")
        return redirect(url_for("profile"))

    message = sanitize_string(request.form.get("message", ""), max_length=1000)

    requests_col.insert_one({
        "from_user": ObjectId(current_user.id),
        "to_user": to_user_oid,
        "message": message,
        "status": "pending",
        "timestamp": datetime.now(timezone.utc),
    })

    flash("Request sent successfully!", "success")
    return redirect(url_for("profile"))


# ----------------- HANDLE REQUEST -----------------
@app.route("/handle_request/<req_id>/<action>", methods=["POST"])
@login_required
def handle_request(req_id, action):
    if not validate_csrf():
        return redirect(url_for("profile"))

    try:
        req = requests_col.find_one({"_id": ObjectId(req_id)})
    except Exception:
        flash("Invalid request ID.", "danger")
        return redirect(url_for("profile"))

    if not req or str(req["to_user"]) != current_user.id:
        flash("Invalid request.", "danger")
        return redirect(url_for("profile"))

    if action == "accept":
        new_status = "accepted"
    elif action == "reject":
        new_status = "rejected"
    else:
        flash("Invalid action.", "danger")
        return redirect(url_for("profile"))

    requests_col.update_one(
        {"_id": ObjectId(req_id)},
        {"$set": {"status": new_status}},
    )

    flash(f"Request {new_status}!", "success")
    return redirect(url_for("profile"))


@app.route("/toggle_profile", methods=["POST"])
@login_required
def toggle_profile():
    if not validate_csrf():
        return redirect(url_for("profile"))

    user = users_col.find_one({"_id": ObjectId(current_user.id)})
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("profile"))

    new_status = not user.get("is_disabled", False)
    users_col.update_one(
        {"_id": ObjectId(current_user.id)},
        {"$set": {"is_disabled": new_status}},
    )

    if new_status:
        flash("Your profile is Inactive. You are not visible as a donor.", "info")
    else:
        flash("Your profile is Active. You are visible as a donor.", "success")

    return redirect(url_for("profile"))


# =======================
# Run App
# =======================
if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
    