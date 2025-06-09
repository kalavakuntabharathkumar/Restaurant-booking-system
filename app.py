from flask import Flask, request, jsonify, render_template, session, send_file, redirect, url_for
from flask_mail import Mail, Message
from datetime import datetime
import json, os, random
from dotenv import load_dotenv
import google.generativeai as genai
import re
from io import BytesIO
from reportlab.pdfgen import canvas

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'a_very_secret_key_that_should_be_changed')

BOOKING_FILE = 'bookings.json'
FEEDBACK_FILE = 'feedback.json'
NEXT_BOOKING_ID_FILE = 'next_booking_id.txt'
OTP_STORE = {}

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_USERNAME")
mail = Mail(app)

# Gemini Setup
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

def _load_json(file_path):
    if not os.path.exists(file_path): return []
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except:
        return []

def _save_json(data, file_path):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def _get_next_booking_id():
    if not os.path.exists(NEXT_BOOKING_ID_FILE):
        with open(NEXT_BOOKING_ID_FILE, 'w') as f: f.write("1")
        return 1
    with open(NEXT_BOOKING_ID_FILE, 'r') as f:
        return int(f.read().strip() or 1)

def _increment_next_booking_id():
    current_id = _get_next_booking_id()
    with open(NEXT_BOOKING_ID_FILE, 'w') as f:
        f.write(str(current_id + 1))
    return current_id

def create_booking(name, email, phone, date, time, people):
    bookings = _load_json(BOOKING_FILE)
    booking_id_num = _increment_next_booking_id()
    booking_id = f"RD-{booking_id_num:05d}"

    booking = {
        "booking_id": booking_id,
        "name": name,
        "email": email,
        "phone": phone,
        "date": date,
        "time": time,
        "people": people,
        "status": "confirmed",
        "timestamp": datetime.now().isoformat()
    }
    bookings.append(booking)
    _save_json(bookings, BOOKING_FILE)

    try:
        msg = Message(subject="Royal Dine Booking Confirmation", recipients=[email])
        msg.body = f"""
        Hello {name},
        ✅ Your table has been booked!
        Booking ID: {booking_id}
        Guests: {people}
        Date: {date}
        Time: {time}
        """
        mail.send(msg)
    except Exception as e:
        print("Mail error:", e)

    return booking_id

def find_booking(bid):
    bookings = _load_json(BOOKING_FILE)
    return next((b for b in bookings if b.get("booking_id") == bid), None)

def cancel_booking(bid):
    bookings = _load_json(BOOKING_FILE)
    found = False
    for b in bookings:
        if b.get("booking_id") == bid:
            b["status"] = "cancelled"
            found = True
            break
    _save_json(bookings, BOOKING_FILE)
    return found

def save_feedback(bid, feedback):
    all_feedback = _load_json(FEEDBACK_FILE)
    all_feedback.append({"booking_id": bid, "feedback": feedback, "timestamp": datetime.now().isoformat()})
    _save_json(all_feedback, FEEDBACK_FILE)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/book', methods=['POST'])
def book_api():
    data = request.get_json()
    try:
        bid = create_booking(
            name=data['name'], email=data['email'], phone=data.get('phone', ''),
            date=data['date'], time=data['time'], people=data['people'])
        return jsonify({"success": True, "booking_id": bid})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/check', methods=['POST'])
def check_booking():
    bid = request.get_json().get('booking_id')
    booking = find_booking(bid)
    return jsonify({"found": bool(booking), "booking": booking})

@app.route('/api/cancel', methods=['POST'])
def cancel():
    bid = request.get_json().get('booking_id')
    success = cancel_booking(bid)
    return jsonify({"success": success})

@app.route('/api/feedback', methods=['POST'])
def feedback():
    data = request.get_json()
    try:
        save_feedback(data['booking_id'], data['feedback'])
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/pdf/<bid>')
def generate_pdf(bid):
    booking = find_booking(bid)
    if not booking:
        return "Booking not found or may have been deleted.", 404

    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(200, 820, "Royal Dine - Booking Receipt")

    p.setFont("Helvetica", 12)
    y = 780
    for label, value in [
        ("Booking ID", booking.get("booking_id", "N/A")),
        ("Name", booking.get("name", "N/A")),
        ("Email", booking.get("email", "N/A")),
        ("Phone", booking.get("phone", "N/A")),
        ("Date & Time", f"{booking.get('date', 'N/A')} {booking.get('time', 'N/A')}"),
        ("Guests", str(booking.get("people", "N/A"))),
        ("Status", booking.get("status", "N/A"))
    ]:
        p.drawString(100, y, f"{label}: {value}")
        y -= 20

    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True,
                     download_name=f"{bid}_receipt.pdf",
                     mimetype='application/pdf')

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '').lower()
    response = ""
    
    # Predefined responses
    if any(word in user_message for word in ["book", "reserve", "table"]):
        response = "To book a table:\n1. Go to the 'Book' tab\n2. Fill the form\n3. Get your Booking ID (RD-XXXXX)"
    elif any(word in user_message for word in ["check", "status", "booking id"]):
        response = "Check bookings:\n1. Visit 'Check/Cancel' tab\n2. Enter Booking ID (e.g. RD-12345)\n3. View details"
    elif any(word in user_message for word in ["cancel", "delete"]):
        response = "⚠️ Cancellation policy:\n- Free if cancelled 24h before\n- 50% charge within 24h\nGo to 'Check/Cancel' tab"
    elif any(word in user_message for word in ["hello", "hi", "hey"]):
        response = "👋 Hello! I'm Royal Dine Bot. Ask about:\n- Booking tables\n- Checking reservations\n- Cancellations"
    elif any(word in user_message for word in ["hour", "time", "open"]):
        response = "🕒 Restaurant hours:\n- Monday to Sunday: 11AM - 11PM\n- Happy Hour: 3PM-6PM (50% off drinks)"
    else:
        # Fallback to Gemini AI
        try:
            chat_session = model.start_chat()
            prompt = f"""
            You're Royal Dine's assistant. Respond concisely (max 2 sentences) about:
            - Table bookings (2-10 people)
            - Booking status (require RD-XXXXX ID)
            - Cancellation policy (24h notice)
            - Restaurant hours (11AM-11PM daily)
            - Location: 123 Food Street, Bangalore
            
            User asked: {user_message}
            """
            response = chat_session.send_message(prompt).text
        except Exception as e:
            response = "⚠️ Sorry, I'm having trouble. Please try again later."

    return jsonify({'response': response})

@app.route('/api/request-otp', methods=['POST'])
def request_otp():
    data = request.get_json()
    email = data.get("email")
    if not email:
        return jsonify({"success": False, "message": "Email required"})

    otp = str(random.randint(100000, 999999))
    OTP_STORE[email] = otp

    try:
        msg = Message(subject="Royal Dine OTP Login", recipients=[email])
        msg.body = f"Your OTP for Royal Dine is: {otp}"
        mail.send(msg)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email = data.get("email")
    otp = data.get("otp")
    if OTP_STORE.get(email) == otp:
        session['user'] = email
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Invalid OTP"})

@app.route('/google822db3c93823c933.html')
def google_verification():
    return "google-site-verification: google822db3c93823c933.html"

@app.route('/sitemap.xml')
def sitemap():
    return send_file('sitemap.xml')

if __name__ == '__main__':
    app.run()