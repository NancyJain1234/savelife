import os
from flask import Flask, render_template, request, redirect, url_for, session, flash 
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user 

from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timezone
from urllib.parse import quote_plus
import certifi
from send_email import send_email 
from bson.binary import Binary
import base64
# --- Email (SendGrid) ---
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
# =======================
# Flask App Setup
# =======================
app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# =======================
# MongoDB Atlas Setup
# =======================
db_username = quote_plus("savelife")       # MongoDB Atlas username
db_password = quote_plus("Nancy@123")      # MongoDB Atlas password

# Substitute the variables into the URI
MONGO_URI = f"mongodb+srv://{db_username}:{db_password}@savelife.ua5gyhw.mongodb.net/?retryWrites=true&w=majority&appName=savelife"

try:
    client = MongoClient(
        MONGO_URI,
        tls=True,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=10000  # 10 sec timeout
    )
    db = client["savelife"]
    donors_col = db["donors"]
    users_col = db["users"]
    requests_col = db["requests"]
    print("✅ MongoDB connected successfully!")
except Exception as e:
    print("❌ MongoDB connection error:", e)
    donors_col = None
    users_col = None

# =======================
# Flask-Login Setup
# =======================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

class User(UserMixin):
    def __init__(self, user_doc):
        self.id = str(user_doc["_id"])   # Flask-Login expects string id
        self.name = user_doc.get("name")
        self.email = user_doc.get("email")
        self.phone = user_doc.get("phone")
        self.blood_group = user_doc.get("blood_group")
        self.address = user_doc.get("address")
        self.is_disabled = user_doc.get("is_disabled", False)
        self.photo = user_doc.get("photo")

    def get_id(self):
        return self.id   # ✅ Explicitly defined for Flask-Login


@login_manager.user_loader
def load_user(user_id):
    if users_col is None:
        return None
    try:
        user_data = users_col.find_one({"_id": ObjectId(user_id)})
        if user_data:
            return User(user_data)  # convert MongoDB document to User object
    except Exception as e:
        print("Error loading user:", e)
    return None


# =======================
# Helpers
# =======================
def find_donors(blood_group, city, state):
    """Return donors with emails for the given criteria."""
    if donors_col is None:
     return []
    query = {"blood_group": blood_group, "city": city, "state": state}
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
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        blood_group = request.form.get("blood_group", "").strip().upper()
        address = request.form.get("address", "").strip()

        # --- Check for duplicate by email or phone ---
        existing_user = users_col.find_one({
            "$or": [
                {"email": email},
                {"phone": phone}
            ]
        })

        if existing_user:
            flash("⚠️ A user with this Email or Phone number already exists.", "danger")
            return redirect(url_for("register"))

        # --- Insert user if unique ---
        users_col.insert_one({
            "name": name,
            "email": email,
            "phone": phone,
            "password": password,  # ⚠️ later we should hash this!
            "blood_group": blood_group,
            "address": address,
            "is_disabled": False,
            "created_at": datetime.utcnow()
        })

        flash("✅ Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/request_blood", methods=["GET", "POST"])
def request_blood():
    if request.method == "POST":
        blood_group = request.form.get("blood_group", "").strip()
        city = request.form.get("city", "").strip()
        state = request.form.get("state", "").strip()
        patient_name = request.form.get("patient_name", "").strip()
        patient_phone = request.form.get("patient_phone", "").strip()

        donors = find_donors(blood_group, city, state)
        emails = [d["email"] for d in donors if d.get("email")]

        if emails:
            subject = f"Urgent Blood Request for {patient_name}"
            body = f"""
                <h2>🚨 Urgent Blood Requirement</h2>
                <p>Dear Donor,</p>
                <p>We have an urgent request for blood donation:</p>
                <ul>
                    <li><b>Patient Name:</b> {patient_name}</li>
                    <li><b>Blood Group:</b> {blood_group}</li>
                    <li><b>Contact Number:</b> {patient_phone}</li>
                    <li><b>Location:</b> {city}, {state}</li>
                </ul>
                <p>Please contact the patient/hospital immediately if you can donate.</p>
                <p>Thank you for saving lives! ❤️</p>
            """
            if send_email(subject, emails, body):
                flash("📩 Blood request sent to matching donors!", "success")
            else:
                flash("⚠️ Could not send emails.", "warning")
        else:
            flash("⚠️ No matching donors found.", "warning")
    return render_template("request_blood.html")

@app.route("/find", methods=["GET", "POST"])
def find():
    form_submitted = False
    results = []
    success = False
    page = request.args.get('page', 1, type=int)
    per_page = 5

    if request.method == "POST":
        form_submitted = True
        request_data = {
            "name": request.form['your_name'],
            "gender": request.form['gender'],
            "mobile": request.form['your_mobile'],
            "email": request.form['email'],
            "blood_group": request.form['blood_group'],
            "city": request.form['city'],
            "state": request.form['state'],
            "request_date": datetime.now(timezone.utc)
        }
        db.requests.insert_one(request_data)
        success = True

        # Send confirmation email to requester
        subject = "Blood Request Confirmation"
        body = f"""
            <p>Hello {request_data['name']},</p>
            <p>Your request for <b>{request_data['blood_group']}</b> blood in
            {request_data['city']}, {request_data['state']} has been received.</p>
            <p>We will connect you with donors soon.</p>
        """
        send_email(subject, [request_data["email"]], body)

        # Find donors
        donors = find_donors(request_data["blood_group"], request_data["city"], request_data["state"])
        donor_emails = [d.get("email") for d in donors if d.get("email")]


        if donor_emails:
            subject = f"Urgent Blood Request for {request_data['name']}"
            body = f"""
                <h2>🚨 Urgent Blood Requirement</h2>
                <p>Dear Donor,</p>
                <p>Patient Name: {request_data['name']}</p>
                <p>Blood Group: {request_data['blood_group']}</p>
                <p>Contact Number: {request_data['mobile']}</p>
                <p>Location: {request_data['city']}, {request_data['state']}</p>
            """
            send_email(subject, donor_emails, body)
            flash(f"📩 Blood request sent to {len(donor_emails)} matching donors!", "success")
        else:
            flash("⚠️ No matching donors found.", "warning")

        # Pagination
        all_results = list(db.donors.find(
            {"blood_group": request_data["blood_group"],
             "city": request_data["city"],
             "state": request_data["state"]},
            {"email": 0}
        ))
        total_results = len(all_results)
        total_pages = (total_results + per_page - 1) // per_page
        start = (page - 1) * per_page
        end = start + per_page
        results = all_results[start:end]

        return render_template('find.html',
                               results=results,
                               form_submitted=form_submitted,
                               success=success,
                               page=page,
                               total_pages=total_pages,
                               selected_blood_group=request_data["blood_group"],
                               selected_city=request_data["city"],
                               selected_state=request_data["state"])

    # GET request
    return render_template('find.html',
                           results=None,
                           form_submitted=form_submitted,
                           success=success,
                           page=page,
                           total_pages=0,
                           selected_blood_group="",
                           selected_city="",
                           selected_state="")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if users_col.find_one({"email": email}):
            flash("Email already registered!", "danger")
            return redirect(url_for("signup"))

        users_col.insert_one({"name": name, "email": email, "password": password})
        flash("Signup successful! You can now login.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter both email and password", "warning")
            return render_template("login.html")

        user = users_col.find_one({"email": email})
        if user and user.get("password") == password:
            session["user_id"] = str(user["_id"])
            login_user(User(user))
            flash("Logged in successfully!", "success")
            return redirect(url_for("home"))

        flash("Invalid email or password", "danger")
        return render_template("login.html")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    session.pop("user_id", None)
    logout_user()
    flash("Logged out successfully!", "success")
    return redirect(url_for("login"))

# Simple health check
@app.route("/health")
def health():
    return {"status": "ok"}, 200



from flask import Response

# ----------------- PROFILE PAGE -----------------
@app.route("/profile")
@login_required
def profile():
    user_doc = users_col.find_one({"_id": ObjectId(current_user.id)})
    if not user_doc:
        flash("User not found.", "danger")
        return redirect(url_for("index"))

    # fetch all requests sent TO this user
    requests_list = list(requests_col.find({"to_user": ObjectId(current_user.id)}))

    # attach sender details
    for req in requests_list:
        from_user = users_col.find_one({"_id": ObjectId(req["from_user"])})
        req["from_user_name"] = from_user["name"] if from_user else "Unknown"

    return render_template("profile.html", user=user_doc, requests=requests_list)


# ----------------- SERVE PROFILE PHOTO -----------------
# ----------------- SERVE PROFILE PHOTO -----------------
@app.route("/photo/<user_id>")
def photo(user_id):
    """Serve uploaded profile photo or fallback to default."""
    user = users_col.find_one({"_id": ObjectId(user_id)})
    if user and "photo" in user:
        return redirect(url_for("static", filename="uploads/" + user["photo"]))
    else:
        return redirect(url_for("static", filename="default.jpg"))


# ----------------- UPLOAD PROFILE PHOTO -----------------
@app.route("/upload_photo", methods=["POST"])
@login_required
def upload_photo():
    if "photo" not in request.files:
        flash("No file part", "error")
        return redirect(url_for("profile"))

    file = request.files["photo"]

    if file.filename == "":
        flash("No selected file", "error")
        return redirect(url_for("profile"))

    if file:
        filename = f"{current_user.id}.jpg"   # saving as user_id.jpg
        filepath = os.path.join("static/uploads", filename)
        file.save(filepath)

        # Update user doc in DB
        users_col.update_one(
            {"_id": ObjectId(current_user.id)},
            {"$set": {"photo": filename}}
        )

        flash("Profile photo updated successfully!", "success")
        return redirect(url_for("profile"))


# ----------------- UPDATE PROFILE INFO -----------------
@app.route("/update_profile", methods=["POST"])
@login_required
def update_profile():
    user_id = session["user_id"]
    name = request.form.get("name")
    email = request.form.get("email")
    phone = request.form.get("phone")
    blood_group = request.form.get("blood_group")
    address = request.form.get("address")

    users_col.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "name": name,
            "email": email,
            "phone": phone,
            "blood_group": blood_group,
            "address": address
        }}
    )

    flash("Profile updated successfully!", "success")
    return redirect(url_for("profile"))


@app.route("/enable_profile", methods=["POST"])
def enable_profile():
    if "user_id" not in session:
        flash("You need to log in first.", "danger")
        return redirect(url_for("login"))

    users_col.update_one(
        {"_id": ObjectId(session["user_id"])},
        {"$set": {"is_donor": True}}
    )
    flash("Your profile has been enabled as a donor.", "success")
    return redirect(url_for("profile"))

@app.route("/disable_profile", methods=["POST"])
def disable_profile():
    if "user_id" not in session:
        flash("You need to log in first.", "danger")
        return redirect(url_for("login"))

    users_col.update_one(
        {"_id": ObjectId(session["user_id"])},
        {"$set": {"is_donor": False}}
    )
    flash("Your profile has been disabled.", "info")
    return redirect(url_for("profile"))



# ----------------- SEND REQUEST -----------------
@app.route("/send_request/<to_user_id>", methods=["POST"])
@login_required
def send_request(to_user_id):
    """Send a blood/help request to another user."""
    message = request.form.get("message")

    requests_col.insert_one({
        "from_user": ObjectId(current_user.id),
        "to_user": ObjectId(to_user_id),
        "message": message,
        "status": "pending",
        "timestamp": datetime.utcnow()
    })

    flash("Request sent successfully!", "success")
    return redirect(url_for("profile"))


# ----------------- HANDLE REQUEST -----------------
@app.route("/handle_request/<req_id>/<action>", methods=["POST"])
@login_required
def handle_request(req_id, action):
    """Accept or reject a received request."""
    req = requests_col.find_one({"_id": ObjectId(req_id)})
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
        {"$set": {"status": new_status}}
    )

    flash(f"Request {new_status}!", "success")
    return redirect(url_for("profile"))

@app.route("/toggle_profile", methods=["POST"])
@login_required
def toggle_profile():
    user_id = session["user_id"]  # assuming you store user_id in session
    user = users_col.find_one({"_id": ObjectId(user_id)})

    # Toggle donor status
    new_status = not user.get("is_disabled", False)
    users_col.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_disabled": new_status}})

    # Flash appropriate message
    if new_status:
        flash("Your profile is Inactive. You are not visible as a donor.", "info")
    else:
        flash("Your profile is Active. You are visible as a donor.", "success")

    return redirect(url_for("profile"))

# =======================
# Run App
# =======================
if __name__ == "__main__":
    app.run(debug=True)
