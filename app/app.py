from flask import Flask, render_template, request, redirect, url_for, flash, session, request, send_file
from flask_dance.contrib.google import make_google_blueprint, google
from werkzeug.utils import secure_filename
import os, time
from datetime import datetime
from pathlib import Path
import json
import uuid
from io import BytesIO
# our stuff
from config import Config
from database import *
from ATSChecker import analyze_resume

app = Flask(__name__)
app.config.from_object(Config)
upload_path = "/home/anti-ats/submissions/"
#upload_path = "C:\\Users\\roliv\\Code\\anit-ats\\submissions\\"
app.secret_key = app.config["SECRET_KEY"] # sign session cookies
mysql = MySQL(app)

google_bp = make_google_blueprint(
    client_id=app.config["GOOGLE_OAUTH_CLIENT_ID"],
    client_secret=app.config["GOOGLE_OAUTH_CLIENT_SECRET"],
    redirect_to="google_login",
    scope=["profile", "email"]
)
app.register_blueprint(google_bp, url_prefix="/login")

@app.route("/", methods=["GET", "POST"])
def home():
    if "user_id" not in session:
        return redirect(url_for('login'))
    
    username = session.get("username")
    
    files = get_user_files(username)
    
    if request.method == "POST":
        file = request.files.get("file")
        if file:
            if file.filename.endswith('.pdf') or file.filename.endswith('docx') or file.filename.endswith('doc'):  # avoid malicious file uploads
                filename = secure_filename(file.filename)  # no directory traversal here. removes all special characters
                user_dir = os.path.join(upload_path, username)
                
                if not os.path.exists(user_dir):
                    os.makedirs(user_dir)
                    
                file.save(os.path.join(user_dir, filename))  # save the file
                
                flash("File uploaded successfully", "success")
                return redirect(url_for("home"))
            else:
                flash('Invalid file type', 'error')
                return redirect(url_for("home"))
        else:
            flash(f"No file submitted. Do not make empty POST requests. Illegal.", 'error')
            return redirect(url_for('home'))
    
    return render_template("index.html", files=files)



@app.route("/login", methods = ["GET", "POST"])
def login():
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        user = get_user_by_username(username)
        
        if user:
            user_id, stored_username, stored_password = user[:3]
            
            if validate_user_password(stored_password, password):
                session["user_id"] = user_id
                session["username"] = stored_username
                return redirect(url_for("home"))
            else:
                flash('Inavlid credentials. Please try again.', 'error')
                return redirect(url_for("login"))
        else:
            flash('This user does not exist. Consider registering an account with Anti-ATS!', 'error')
            return redirect(url_for("login"))  
                
    return render_template("login.html")

@app.route("/logout", methods = ["GET"])
def logout():
    if request.method == "GET":
        session.clear()
    return redirect(url_for("login"))

@app.route("/login/google_login", methods=["GET", "POST"])
def google_login():
    if not google.authorized:
        print("Google OAuth not yet complete. Redirecting to login...")
        return redirect(url_for("google.login"))  # triggers OAuth flow

    resp = google.get("/oauth2/v2/userinfo")
    print("Google OAuth successful. Fetching user info...")
    if not resp.ok:
        print("Failed to fetch user into from Google")
        flash("Failed to fetch user info from Google.", "error")
        return redirect(url_for("login"))

    user_info = resp.json()
    email = user_info["email"]
    username = user_info["name"]

    user = get_user_by_email(email)
    if not user: # check if user exists before proceeding. create user if they don't exist already
        create_user(username=username, password=None, email=email)
        user = get_user_by_email(email)
    
    user_id = user[0] # Log the user in
    session["user_id"] = user_id
    session["username"] = username
    flash("Logged in successfully with Google", "success")
    return redirect(url_for("home"))


@app.route("/register", methods = ["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        username = request.form.get("username")
        password = request.form.get("password")
        
        user = get_user_by_username(username)
        if user:
            flash(f'{username} is already taken. Please select another username', 'error')
            return render_template(url_for("register"))

        check_email = get_user_by_email(email)
        if check_email:
            flash(f'Already a user with this email. Please enter another email address')
            return render_template(url_for("register"))

        else:
            create_user(username, password, email)
            flash("Registered successfully")
            time.sleep(1) # ensure user sees successful flash message
            return redirect(url_for("login"))
    
    
    return render_template("register.html") # redirect to register.html with HTTP Redirect and implicit GET request


###### RESUME

@app.route('/scan_resume', methods=['POST'])
def scan_resume():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get form data
    selected_resume = request.form.get('selected_resume')
    job_description = request.form.get('job_description')
    job_type = request.form.get('job_type', 'technical')
    
    # Validate inputs
    if not selected_resume or not job_description:
        flash('Please select a resume and provide a job description.')
        return redirect(url_for('submissions'))
    
    # Determine file type
    file_type = 'pdf' if selected_resume.lower().endswith('.pdf') else 'docx'
    
    try:
        # Process the resume using our modified function
        results = analyze_resume(
            resume_path=selected_resume,
            job_description=job_description,
            file_type=file_type,
            job_type=job_type
        )
        
        # Check if analysis was successful
        if not results['success']:
            flash(f"Error analyzing resume: {results['error']['message']}")
            return redirect(url_for('submissions'))
        
        # Store results in session for potential future use
        session['last_scan_results'] = results
        
        # Pass the actual results to the template
        return render_template('results.html', 
                              results=results['results'], 
                              username=session.get('username'))
        
    except Exception as e:
        flash(f"An error occurred: {str(e)}")
        return redirect(url_for('submissions'))


@app.route('/download_report')
def download_report():
    if 'user_id' not in session or 'last_scan_results' not in session:
        return redirect(url_for('submissions'))
    
    results = session['last_scan_results']
    
    # Format the results as a text file
    report_text = f"""ATS SCAN RESULTS
====================

FILE: {results['results']['metadata']['file_name']}
SCAN DATE: {results['results']['metadata']['timestamp']}

OVERALL SCORE: {results['results']['summary']['overall_score']}%

DETAILED SCORES:
- Keyword Match: {results['results']['summary']['keyword_match']}%
- Skill Match: {results['results']['summary']['skill_match']}%
- Readability: {results['results']['summary']['readability']}%

MATCHED SKILLS:
{chr(10).join(['- ' + skill for skill in results['results']['skills']['matched']])}

MISSING SKILLS:
{chr(10).join(['- ' + skill for skill in results['results']['skills']['missing']])}

READABILITY METRICS:
- Average Sentence Length: {results['results']['readability_metrics']['avg_sentence_length']} words
- Complex Word Ratio: {results['results']['readability_metrics']['complex_word_ratio'] * 100:.2f}%

GENERATED BY ANTI-ATS RESUME SCANNER
© 2025 Anti-ATS
"""
    
    # Create a BytesIO object
    buffer = BytesIO()
    buffer.write(report_text.encode('utf-8'))
    buffer.seek(0)
    
    # Generate a filename with the resume name and current date
    filename = f"ATS_Scan_{results['results']['metadata']['file_name']}_{datetime.now().strftime('%Y%m%d')}.txt"
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='text/plain'
    )

@app.route('/submissions')
def submissions():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    username = session.get('username')
    folder = f'/home/anti-ats/submissions/{username}/'
    resumes = []
    files = get_user_files(username)
    for file in files:
        full_path = os.path.join(folder, file)
        if os.path.isfile(full_path):
            resumes.append({
                "name": os.path.basename(file),
                "path": full_path,
                "upload_date": datetime.fromtimestamp(os.path.getmtime(full_path)).strftime('%Y-%m-%d %I:%M:%S %p')
            })
    
    return render_template('submissions.html', username=username, resumes=resumes)


######## Obligatory #########

@app.route("/faq", methods = ["GET"])
def faq():
    return render_template("faq.html")

@app.route("/how-it-works", methods = ["GET"])
def howitworks():
    return render_template("howitworks.html")

@app.route("/about", methods = ["GET"])
def about():
    return render_template("about.html")


if __name__== '__main__':
    base = os.path.abspath(os.path.dirname(__file__)) # portability
    cert = os.path.join(base, 'cert.pem')
    key = os.path.join(base, 'key.pem')
    app.run(debug=True, ssl_context=(cert, key))
    # default port is 5000
    # app.run(port=<port>) to change port number
