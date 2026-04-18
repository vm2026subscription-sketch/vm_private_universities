from pymongo import MongoClient
import json
import os
from io import BytesIO
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
import google.generativeai as genai
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# MongoDB connection (Atlas)
MONGODB_URI = os.getenv("MONGODB_URI")

try:
    client = MongoClient(MONGODB_URI)
    db = client["mvc_admissions"]

    users_collection = db["users"]
    contacts_collection = db["contacts"]
    universities_collection = db["universities"]

    # Test connection
    client.admin.command('ping')
    print("[OK] Connected to MongoDB Atlas ✅")

except Exception as e:
    print(f"[ERROR] MongoDB connection failed: {e}")
    users_collection = None
    contacts_collection = None
    universities_collection = None


# ✅ ADD THIS OUTSIDE try-except (VERY IMPORTANT)
if users_collection.find_one({"email": "test@gmail.com"}) is None:
    users_collection.insert_one({
        "name": "test",
        "email": "test@gmail.com",
        "password": "123",
        "favorites": []
    })
    print("Test user inserted")

    # LOAD UNIVERSITIES
import json

# Private universities
with open("data/private_university.json", encoding="utf-8") as f:
    private_data = json.load(f)

# Deemed universities
with open("data/deemed_university.json", encoding="utf-8") as f:
    deemed_data = json.load(f)

# Combine both
all_data = private_data + deemed_data

# Insert once
universities_collection.insert_many(all_data)

print("All universities inserted ✅")

def load_universities():
    uni_map = {}

    try:
        data = list(universities_collection.find({}, {"_id": 0}))

        for item in data:
            name = item.get("Name of the University", "").strip()

            if not name:
                continue

            raw_type = (item.get("Type") or "").lower()

            if "deemed" in raw_type:
                uni_type = "Deemed"
            elif "private" in raw_type:
                uni_type = "Private"
            else:
                uni_type = "Unknown"

            course = item.get("Courses", "")

            # If university already exists → append course
            if name in uni_map:
                if course and course not in uni_map[name]["programs"]:
                    uni_map[name]["programs"].append(course)

            else:
                uni_map[name] = {
                    "name": name,
                    "city": item.get("Address", "").split(",")[-1].strip() if item.get("Address") else "",
                    "type": uni_type,
                    "address": item.get("Address", ""),
                    "zip": item.get("Zip", ""),
                    "status": item.get("Status", ""),
                    "programs": [course] if course else []
                }

        print("Unique universities:", len(uni_map))

    except Exception as e:
        print("MongoDB error:", e)

    return list(uni_map.values())

    # ---------- PRIVATE ----------
    private_path = os.path.join(os.path.dirname(__file__), "data", "private_university.json")
    private_map = {}

    try:
        with open(private_path, "r") as f:
            private_data = json.load(f)

        for item in private_data:
            name = item.get("Name of the University", "")

            if name not in private_map:
                private_map[name] = {
                    "name": name,
                    "city": item.get("Address", "").split(",")[-1].strip() if item.get("Address") else "",
                    "established": None,
                    "type": "Private",
                    "accreditation": item.get("Status", ""),
                    "programs": [],
                    "website": item.get("Website", ""),
                    "address": item.get("Address", ""),
                    "zip": item.get("Zip", ""),
                    "status": item.get("Status", ""),
                }

            course = item.get("Courses", "")
            if course:
                private_map[name]["programs"].append(course)

        universities.extend(private_map.values())

    except Exception as e:
        app.logger.error(f"Private error: {e}")

    # ---------- DEEMED ----------
    deemed_path = os.path.join(os.path.dirname(__file__), "data", "deemed_university.json")
    deemed_map = {}

    try:
        with open(deemed_path, "r") as f:
            deemed_data = json.load(f)

        for item in deemed_data:
            name = item.get("Name of the University", "")

            if name not in deemed_map:
                deemed_map[name] = {
                    "name": name,
                    "city": item.get("Address", "").split(",")[-1].strip() if item.get("Address") else "",
                    "established": None,
                    "type": "Deemed",
                    "accreditation": item.get("Status", ""),
                    "programs": [],
                    "website": item.get("Website", ""),
                    "address": item.get("Address", ""),
                    "zip": item.get("Zip", ""),
                    "status": item.get("Status", ""),
                }

            course = item.get("Courses", "")
            if course:
                deemed_map[name]["programs"].append(course)

        universities.extend(deemed_map.values())

    except Exception as e:
        app.logger.error(f"Deemed error: {e}")

    return universities


UNIVERSITIES = load_universities()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def _pick_gemini_model():
    try:
        models = list(genai.list_models())
        for model in models:
            if "generateContent" in (model.supported_generation_methods or []):
                return model.name
    except Exception:
        return "gemini-1.0-pro"
    return "gemini-1.0-pro"


if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel(_pick_gemini_model())
else:
    gemini_model = None


def _local_chat_reply(message, language="en"):
    text = (message or "").lower()
    private_unis = [u for u in UNIVERSITIES if u.get("type") == "Private"]
    deemed_unis = [u for u in UNIVERSITIES if u.get("type") == "Deemed"]
    private_count = len(private_unis)
    deemed_count = len(deemed_unis)

    if any(word in text for word in ["count", "how many", "number", "किती", "संख्या"]):
        if language == "mr":
            return f"सध्या पोर्टलमध्ये {private_count} खाजगी आणि {deemed_count} मानित विद्यापीठांची नोंद आहे."
        return f"The portal currently lists {private_count} private universities and {deemed_count} deemed universities."

    if any(word in text for word in ["private", "खाजगी", "list", "names", "विद्यापीठ"]):
        top_private = [u.get("name") for u in private_unis[:5] if u.get("name")]
        if top_private:
            if language == "mr":
                return "उदाहरणार्थ काही खाजगी विद्यापीठे: " + ", ".join(top_private) + ". अधिक माहिती साठी Explore विभाग पहा."
            return "Some private universities include: " + ", ".join(top_private) + ". You can view more in the Explore section."

    if any(word in text for word in ["deemed", "मानित"]):
        top_deemed = [u.get("name") for u in deemed_unis[:5] if u.get("name")]
        if top_deemed:
            if language == "mr":
                return "काही मानित विद्यापीठे: " + ", ".join(top_deemed) + "."
            return "Some deemed universities are: " + ", ".join(top_deemed) + "."

    if language == "mr":
        return "मी मदत करू शकतो: विद्यापीठांची यादी, प्रवेश माहिती, पात्रता आणि अधिकृत वेबसाइट दुवे. कृपया तुमचा प्रश्न थोडा अधिक स्पष्ट लिहा."
    return "I can help with university lists, admissions info, eligibility, and official website links. Please share your question with a bit more detail."




@app.route("/")
def index():
    user_name = session.get("user_name")
    return render_template("index.html", universities=UNIVERSITIES, user_name=user_name)


from bson import ObjectId

@app.route("/save_college", methods=["POST"])
def save_college():
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "Login required"})

    college_name = request.json.get("name")

    users_collection.update_one(
        {"_id": ObjectId(session["user_id"])},
        {"$addToSet": {"favorites": college_name}}
    )

    return jsonify({"status": "success"})

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            if users_collection is None:
                return jsonify({"error": "Database connection failed"}), 500
            
            data = request.get_json()
            
            if not data:
                return jsonify({"error": "Invalid request format"}), 400
            
            email = (data.get("email") or "").strip().lower()
            password = data.get("password") or ""
            
            if not email or not password:
                return jsonify({"error": "Email and password are required"}), 400
            
            user = users_collection.find_one({"email": email})
            
            if user and check_password_hash(user["password"], password):
                session["user_id"] = str(user["_id"])
                session["user_email"] = user["email"]
                session["user_name"] = user["name"]
                return jsonify({"success": True, "message": "Login successful"}), 200
            
            return jsonify({"error": "Invalid email or password"}), 401
        except Exception as e:
            app.logger.error(f"Login error: {str(e)}")
            return jsonify({"error": f"Login failed: {str(e)}"}), 500
    
    user_name = session.get("user_name")
    return render_template("login.html", user_name=user_name)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        try:
            if users_collection is None:
                return jsonify({"error": "Database connection failed"}), 500
            
            data = request.get_json()
            
            if not data:
                return jsonify({"error": "Invalid request format"}), 400
            
            name = (data.get("name") or "").strip()
            email = (data.get("email") or "").strip().lower()
            password = data.get("password") or ""
            confirm_password = data.get("confirm_password") or ""
            
            if not name or not email or not password:
                return jsonify({"error": "All fields are required"}), 400
            
            if password != confirm_password:
                return jsonify({"error": "Passwords do not match"}), 400
            
            if len(password) < 6:
                return jsonify({"error": "Password must be at least 6 characters"}), 400
            
            existing_user = users_collection.find_one({"email": email})
            if existing_user:
                return jsonify({"error": "Email already registered"}), 400
            
            hashed_password = generate_password_hash(password)
            result = users_collection.insert_one({
                "name": name,
                "email": email,
                "password": hashed_password
            })
            
            session["user_id"] = str(result.inserted_id)
            session["user_email"] = email
            session["user_name"] = name
            
            return jsonify({"success": True, "message": "Account created successfully"}), 201
        except Exception as e:
            app.logger.error(f"Signup error: {str(e)}")
            return jsonify({"error": f"Signup failed: {str(e)}"}), 500
    
    user_name = session.get("user_name")
    return render_template("signup.html", user_name=user_name)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/contact", methods=["POST"])
def contact():
    try:
        if contacts_collection is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Invalid request format"}), 400
        
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        message = (data.get("message") or "").strip()
        
        if not name or not email or not message:
            return jsonify({"error": "All fields are required"}), 400
        
        if len(message) < 10:
            return jsonify({"error": "Message must be at least 10 characters"}), 400
        
        contacts_collection.insert_one({
            "name": name,
            "email": email,
            "message": message,
            "created_at": datetime.utcnow()
        })
        return jsonify({"success": True, "message": "Message sent successfully"}), 201
    except Exception as e:
        app.logger.error(f"Contact form error: {str(e)}")
        return jsonify({"error": f"Failed to send message: {str(e)}"}), 500


@app.route("/explore")
def explore():
    private_unis = [u for u in UNIVERSITIES if u['type'] == 'Private']
    deemed_unis = [u for u in UNIVERSITIES if u['type'] == 'Deemed']
    user_name = session.get("user_name")
    return render_template("explore.html", 
                         private_universities=private_unis, 
                         deemed_universities=deemed_unis,
                         total_count=len(UNIVERSITIES),
                         user_name=user_name)


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    language = payload.get("language", "en")  # Get language preference

    if not message:
        return jsonify({"error": "Message is required."}), 400

    if not gemini_model:
        return jsonify({"reply": _local_chat_reply(message, language), "source": "local"})

    # Build university context for Gemini
    private_unis = [u for u in UNIVERSITIES if u['type'] == 'Private']
    deemed_unis = [u for u in UNIVERSITIES if u['type'] == 'Deemed']
    
    private_context = "\n".join(
        [f"- {u['name']} ({u['city']}, Status: {u['status']})" for u in private_unis[:8]]
    )
    deemed_context = "\n".join(
        [f"- {u['name']} ({u['city']}, Status: {u['status']})" for u in deemed_unis[:8]]
    )

    # Build prompt based on language
    if language == "mr":
        prompt = (
            "तुम्ही रवि आहात, महाराष्ट्र विद्यापीठ प्रवेश पोर्टलसाठी एक मैत्रीपूर्ण आणि जाणकार पुरुष सहाय्यक.\n"
            "प्रवेश, पात्रता, कार्यक्रम किंवा विद्यापीठ तपशीलांबद्दल माहितीपूर्ण आणि संक्षिप्तपणे (1-2 वाक्यांमध्ये) उत्तर द्या.\n"
            "सर्व उत्तरे मराठीत द्या.\n"
            f"खाजगी विद्यापीठांमध्ये हे समाविष्ट आहेत:\n{private_context}\n\n"
            f"मानित विद्यापीठांमध्ये हे समाविष्ट आहेत:\n{deemed_context}\n\n"
            f"वापरकर्त्याचा प्रश्न: {message}"
        )
    else:
        prompt = (
            "You are Ravi, a friendly and knowledgeable male assistant for the Maharashtra Universities admissions portal.\n"
            "Answer helpfully and briefly (1-2 sentences) about admissions, eligibility, programs, or university details.\n"
            f"Private Universities include:\n{private_context}\n\n"
            f"Deemed Universities include:\n{deemed_context}\n\n"
            f"User question: {message}"
        )

    try:
        response = gemini_model.generate_content(
            prompt,
            request_options={"timeout": 20},
        )
        reply = (response.text or "").strip()
        if not reply:
            reply = _local_chat_reply(message, language)
            return jsonify({"reply": reply, "source": "local"})
        return jsonify({"reply": reply, "source": "gemini"})
    except Exception as exc:
        app.logger.exception("Gemini API error")
        return jsonify({
            "reply": _local_chat_reply(message, language),
            "source": "local",
            "note": "Fallback response used due to model error."
        })


@app.route("/download-brochure")
def download_brochure():
    """Generate and download a PDF brochure of all universities"""
    buffer = BytesIO()
    
    # Create PDF document
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                           rightMargin=40, leftMargin=40,
                           topMargin=60, bottomMargin=40)
    
    # Container for PDF elements
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    
    # Modern title styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=colors.HexColor('#f37a1f'),
        spaceAfter=8,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=32
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.HexColor('#6b7280'),
        spaceAfter=4,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    section_heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=18,
        textColor=colors.HexColor('#f37a1f'),
        spaceAfter=16,
        spaceBefore=24,
        fontName='Helvetica-Bold',
        borderWidth=2,
        borderColor=colors.HexColor('#f37a1f'),
        borderPadding=8,
        backColor=colors.HexColor('#fff8f2'),
        leftIndent=10,
        rightIndent=10
    )
    
    uni_name_style = ParagraphStyle(
        'UniName',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#1f2937'),
        fontName='Helvetica-Bold',
        spaceAfter=4
    )
    
    info_style = ParagraphStyle(
        'InfoStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#4b5563'),
        fontName='Helvetica',
        leading=12
    )
    
    # Add logo image at the top
    try:
        logo_path = os.path.join(os.path.dirname(__file__), "image.png")
        logo = Image(logo_path, width=4*inch, height=1.5*inch)
        logo.hAlign = 'CENTER'
        elements.append(logo)
        elements.append(Spacer(1, 0.15*inch))
    except Exception as e:
        app.logger.error(f"Failed to load logo: {e}")
    
    # Title and subtitle
    elements.append(Paragraph("Maharashtra Private Universities", title_style))
    elements.append(Paragraph("Unified Admissions Portal 2026", subtitle_style))
    elements.append(Paragraph("Complete Directory of Accredited Institutions", subtitle_style))
    elements.append(Spacer(1, 0.3*inch))
    
    # Separate universities by type
    private_unis = [u for u in UNIVERSITIES if u['type'] == 'Private']
    deemed_unis = [u for u in UNIVERSITIES if u['type'] == 'Deemed']
    
    # Summary statistics box
    stats_data = [
        [Paragraph("<b>Total Universities</b>", info_style), 
         Paragraph("<b>Private</b>", info_style), 
         Paragraph("<b>Deemed</b>", info_style)],
        [Paragraph(f"<font size=14 color='#f37a1f'><b>{len(UNIVERSITIES)}</b></font>", info_style),
         Paragraph(f"<font size=14 color='#f37a1f'><b>{len(private_unis)}</b></font>", info_style),
         Paragraph(f"<font size=14 color='#f37a1f'><b>{len(deemed_unis)}</b></font>", info_style)]
    ]
    
    stats_table = Table(stats_data, colWidths=[2.2*inch, 2.2*inch, 2.2*inch])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f37a1f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#fff8f2')),
        ('GRID', (0, 0), (-1, -1), 1.5, colors.HexColor('#e6e0d9')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(stats_table)
    elements.append(Spacer(1, 0.4*inch))
    
    # Private Universities Section
    elements.append(Paragraph(f"Private Universities ({len(private_unis)})", section_heading_style))
    elements.append(Spacer(1, 0.15*inch))
    
    for idx, uni in enumerate(private_unis, 1):
        # Create modern university card
        data = [
            [Paragraph(f"<b>{idx}. {uni['name']}</b>", uni_name_style)],
            [Table([
                [Paragraph("<b>Address:</b>", info_style), 
                 Paragraph(uni['address'], info_style)],
                [Paragraph("<b>Postal Code:</b>", info_style), 
                 Paragraph(str(uni.get('zip', 'N/A')), info_style)],
                [Paragraph("<b>Status:</b>", info_style), 
                 Paragraph(uni['status'], info_style)],
                [Paragraph("<b>Website:</b>", info_style), 
                 Paragraph(f"<link href='{uni['website']}'>{uni['website']}</link>", info_style)]
            ], colWidths=[1.2*inch, 5*inch], style=TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))]
        ]
        
        uni_table = Table(data, colWidths=[6.7*inch])
        uni_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fff3e8')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1f2937')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (0, 0), 10),
            ('BOTTOMPADDING', (0, 0), (0, 0), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#e6e0d9')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        
        elements.append(uni_table)
        elements.append(Spacer(1, 0.12*inch))
    
    # Page break before deemed universities
    elements.append(PageBreak())
    
    # Deemed Universities Section
    elements.append(Paragraph(f"Deemed Universities ({len(deemed_unis)})", section_heading_style))
    elements.append(Spacer(1, 0.15*inch))
    
    for idx, uni in enumerate(deemed_unis, 1):
        # Create modern university card
        data = [
            [Paragraph(f"<b>{idx}. {uni['name']}</b>", uni_name_style)],
            [Table([
                [Paragraph("<b>Address:</b>", info_style), 
                 Paragraph(uni['address'], info_style)],
                [Paragraph("<b>Postal Code:</b>", info_style), 
                 Paragraph(str(uni.get('zip', 'N/A')), info_style)],
                [Paragraph("<b>Status:</b>", info_style), 
                 Paragraph(uni['status'], info_style)],
                [Paragraph("<b>Website:</b>", info_style), 
                 Paragraph(f"<link href='{uni['website']}'>{uni['website']}</link>", info_style)]
            ], colWidths=[1.2*inch, 5*inch], style=TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))]
        ]
        
        uni_table = Table(data, colWidths=[6.7*inch])
        uni_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fff3e8')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1f2937')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (0, 0), 10),
            ('BOTTOMPADDING', (0, 0), (0, 0), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#e6e0d9')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        
        elements.append(uni_table)
        elements.append(Spacer(1, 0.12*inch))



    # Build PDF
    doc.build(elements)
    
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='Maharashtra_Universities_Brochure_2026.pdf'
    )


if __name__ == "__main__":
    app.run(debug=True)
