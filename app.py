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
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")

# Flask-Mail Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_USERNAME") 
mail = Mail(app)

@app.route("/send-reset-link", methods=["POST"])
def send_reset_link():
    data = request.json
    email = data.get("email")

    if not email:
        return jsonify({"success": False, "message": "Email is required"}), 400

    # Simulate sending reset link
    try:
        reset_link = f"http://localhost:5000/reset-password?email={email}"
        msg = Message("Royal Dine - Password Reset Link", recipients=[email])
        msg.body = f"Click the link below to reset your password:\n\n{reset_link}"
        mail.send(msg)
        return jsonify({"success": True, "message": "Reset link sent to your email."})
    except Exception as e:
        print("Reset Link Email Error:", e)
        return jsonify({"success": False, "message": "Error sending reset link"}), 500


# Dummy data store for demo
bookings = {}
feedback_list = {}

# Load bookings from file (to persist after restart)
def load_bookings():
    global bookings
    if os.path.exists("bookings.json"):
        with open("bookings.json", "r") as f:
            bookings = json.load(f)

# Save bookings to file
def save_bookings():
    with open("bookings.json", "w") as f:
        json.dump(bookings, f)

load_bookings()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/send-otp", methods=["POST"])
def send_otp():
    data = request.json
    email = data.get("email")
    if not email:
        return jsonify({"success": False, "message": "Email required"}), 400

    otp = str(random.randint(100000, 999999))
    session["otp"] = otp
    session["otp_email"] = email

    try:
        msg = Message("Royal Dine OTP Verification", recipients=[email])
        msg.body = f"Your OTP for Royal Dine is: {otp}"
        mail.send(msg)
        return jsonify({"success": True, "message": "OTP sent successfully"})
    except Exception as e:
        print("Email error:", e)
        return jsonify({"success": False, "message": "Error sending OTP"}), 500

@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.json
    otp_input = data.get("otp")
    if otp_input == session.get("otp"):
        return jsonify({"success": True, "message": "OTP verified"})
    return jsonify({"success": False, "message": "Invalid OTP"})

from flask import make_response

@app.route("/download-receipt/<booking_id>")
def download_receipt(booking_id):
    if booking_id not in bookings:
        return "❌ Booking ID not found", 404

    try:
        booking = bookings[booking_id]
        buf = BytesIO()
        pdf = canvas.Canvas(buf)
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(100, 800, "🍽️ Royal Dine - Booking Receipt")
        pdf.setFont("Helvetica", 12)
        pdf.drawString(100, 770, f"Booking ID: {booking_id}")
        pdf.drawString(100, 750, f"Name: {booking['name']}")
        pdf.drawString(100, 730, f"Email: {booking['email']}")
        pdf.drawString(100, 710, f"Phone: {booking.get('phone', 'N/A')}")
        pdf.drawString(100, 690, f"Guests: {booking['guests']}")
        pdf.drawString(100, 670, f"Date/Time: {booking['datetime']}")
        pdf.drawString(100, 650, f"Special Requests: {booking.get('specialRequests', 'None')}")
        pdf.drawString(100, 620, "✅ Thank you for booking with Royal Dine!")
        pdf.save()

        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=f"{booking_id}_receipt.pdf")
    except Exception as e:
        print("PDF generation error:", e)
        return "❌ Failed to generate receipt", 500



@app.route("/book", methods=["POST"])
def book_table():
    data = request.json
    name = data.get("name")
    email = data.get("email")
    guests = data.get("guests")
    datetime_str = data.get("datetime")

    if not name or not email or not guests or not datetime_str:
        return jsonify({"success": False, "message": "Missing booking details"}), 400

    booking_id = f"RD-{random.randint(10000,99999)}"
    bookings[booking_id] = {
        "name": name,
        "email": email,
        "guests": guests,
        "datetime": datetime_str
    }

    try:
        msg = Message("Your Royal Dine Table Booking Confirmation", recipients=[email])
        msg.body = (
            f"Dear {name},\n\n"
            f"Your table has been successfully booked at Royal Dine!\n\n"
            f"📌 Booking ID: {booking_id}\n"
            f"👥 Guests: {guests}\n"
            f"🕓 Date & Time: {datetime_str}\n\n"
            f"🔗 Download your receipt here:\n"
            f"http://localhost:5000/download-receipt/{booking_id}\n\n"
            f"Thanks for choosing Royal Dine!\n"
        )
        mail.send(msg)
        print(f"✅ Booking confirmation sent to {email}")
    except Exception as e:
        print(f"❌ Email send error: {e}")
        return jsonify({"success": False, "message": "Booking saved, but email failed to send."})

    return jsonify({"success": True, "booking_id": booking_id})

@app.route("/check-booking", methods=["POST"])
def check_booking():
    data = request.json
    booking_id = data.get("booking_id", "")
    booking = bookings.get(booking_id)
    if booking:
        return jsonify({"found": True, "booking": booking})
    return jsonify({"found": False})

@app.route("/cancel-booking", methods=["POST"])
def cancel_booking():
    data = request.json
    booking_id = data.get("booking_id", "")
    if booking_id in bookings:
        del bookings[booking_id]
        save_bookings()
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Booking not found"})

@app.route("/submit-feedback", methods=["POST"])
def submit_feedback():
    data = request.json
    feedback_id = f"FB-{random.randint(1000, 9999)}"
    feedback_list[feedback_id] = data.get("message", "")
    return jsonify({"success": True, "message": "Thank you for your feedback!"})

@app.route("/chatbot", methods=["POST"])
def chatbot():
    user_msg = request.json.get("message", "").strip()
    if not user_msg:
        return jsonify({"response": "Please enter a message."})

    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(user_msg)
        return jsonify({"response": response.text})
    except Exception as e:
        print(f"Chatbot error: {e}")
        return jsonify({"response": "Sorry, I had trouble generating a response. Please try again later."})

@app.route("/test-mail")
def test_mail():
    try:
        msg = Message("Royal Dine Test Email", recipients=[os.getenv("MAIL_USERNAME")])
        msg.body = "✅ This is a test email sent from Royal Dine Flask app. If you're seeing this, your mail is working!"
        mail.send(msg)
        return "✅ Mail sent successfully! Check your inbox."
    except Exception as e:
        print("✖ Mail error:", e)
        return f"✖ Error: {e}"


if __name__ == "__main__":
    app.run(debug=True)
