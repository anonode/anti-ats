from flask import Flask, render_template, request, redirect, url_for, flash, session, current_app, request, abort
import requests
import secrets # for OAuth
from urllib.parse import urlencode
from flask_dance.contrib.google import make_google_blueprint, google
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from werkzeug.utils import secure_filename
import os, time
# our stuff
from config import Config
from database import *
from ATSChecker import ATSChecker

app = Flask(__name__)
app.config.from_object(Config)
upload_path = "/home/anti-ats/submissions/" # adjust this later
#upload_path = "C:\\Users\\roliv\\Code\\anit-ats\\submissions\\"
app.secret_key = app.config["SECRET_KEY"] # sign session cookies
mysql = MySQL(app)

app.config['OAUTH2_PROVIDERS'] = {
    # Google OAuth 2.0 documentation:
    # https://developers.google.com/identity/protocols/oauth2/web-server#httprest
    'google': {
        'client_id': os.environ.get("GOOGLE_OAUTH_CLIENT_ID"),
        'client_secret': os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET"),
        'authorize_url': 'https://accounts.google.com/o/oauth2/auth',
        'token_url': 'https://accounts.google.com/o/oauth2/token',
        'userinfo': {
            'url': 'https://www.googleapis.com/oauth2/v3/userinfo',
            'email': lambda json: json['email'],
        },
        'scopes': ['https://www.googleapis.com/auth/userinfo.email'],
    }
}

login = LoginManager(app)
login.login_view =  'home'
'''google_bp = make_google_blueprint(
    client_id=app.config["GOOGLE_OAUTH_CLIENT_ID"],
    client_secret=app.config["GOOGLE_OAUTH_CLIENT_SECRET"],
    redirect_to="google_login",
    scope=["profile", "email"]
)
app.register_blueprint(google_bp, url_prefix="/login")
'''
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


@app.route("/results", methods = ["GET", "POST"])
def results():
    if "user_id" not in session:
        return redirect(url_for('login'))
    
    username = session.get("username")
    
    # MORE CODE HERE. GET THE USER'S CHOICE
    file_path = "C:\\Users\\roliv\\Code\\anti-ats\\submissions\\RichardOlivarri.pdf"
    #file_path = "/home/rakpa/repos/CADP_Resume.pdf"
    job_description = """ 
        Python Developer Position
        
        Requirements:
        Bachelor Degree in Computer Science, Software engineering, or equivalent.
        Strong planning, organizational, analytical, interpersonal, decision making, oral and written communication skills strongly preferred. 
        Software development experience is a must. C# or Python experience is preferred.
        Database experience (Postgres, MySql, etc ) is preferred.
        Familiarity with DOD Software practices, systems, and publications is helpful.
        Thorough knowledge of MS Office product suite (Excel, Access, Word, PowerPoint).
        Ability to understand company instruction, company process and quality manuals.
        Must be a US Citizen. Make this into a single sentence for me
        
        Responsibilities:
        Develop cloud hosted applications 
        Provide support to the deployment, automation, management, and maintenance of AWS production applications.
        Develop and deploy fully functional architecture and tools to the AWS cloud 
        Support the development and migration of web applications to the cloud (Ideally AWS Govcloud and/or Cloud One) 
        Troubleshooting and problem solving across different application domains and platforms.
        Pre-deployment acceptance testing.
        Carry out and/or oversee critical system security testing.
        Analyze and provide recommendations for architecture and process improvements.
        Deployment of metrics, logging, and monitoring systems on AWS platform.
        Design, maintenance and management tools for automation of different operational processes.
        Participates in projects as a team member and/or team project leader.
        Coordinates activities with the Manager of Engineering.
        Manages approved project timelines. Produces periodic project status reports comparing actual to forecasted timeline.
        Writes detailed technical reports to document information related to the understanding of relevant failure modes and the results of reliability analyses, prepares proposals & develops work instructions. Prepares and delivers presentations of analysis results to appropriate staff and customers.
        Carries out special duties as assigned.
        Performs other related duties as assigned.
        """
    
    checker = ATSChecker()
    ats_data = checker.resCheck(file_path=file_path, jobDesc=job_description, file_type="pdf", job_type="technical")    
    return render_template("results.html", ats_data=ats_data, username=username)

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

@app.route('/authorize/<provider>')
def oauth2_authorize(provider):
    #if not current_user.is_anonymous:
     #   return redirect(url_for('index'))

    provider_data = current_app.config['OAUTH2_PROVIDERS'].get(provider)
    if provider_data is None:
        abort(404)

    # generate a random string for the state parameter
    session['oauth2_state'] = secrets.token_urlsafe(16)

    # create a query string with all the OAuth2 parameters
    qs = urlencode({
        'client_id': provider_data['client_id'],
        'redirect_uri': url_for('oauth2_callback', provider=provider,
                                _external=True),
        'response_type': 'code',
        'scope': ' '.join(provider_data['scopes']),
        'state': session['oauth2_state'],
    })

    # redirect the user to the OAuth2 provider authorization URL
    return redirect(provider_data['authorize_url'] + '?' + qs)

@app.route('/callback/<provider>')
def oauth2_callback(provider):
    if not current_user.is_anonymous:
        return redirect(url_for('index'))

    provider_data = current_app.config['OAUTH2_PROVIDERS'].get(provider)
    if provider_data is None:
        abort(404)

    # if there was an authentication error, flash the error messages and exit
    if 'error' in request.args:
        for k, v in request.args.items():
            if k.startswith('error'):
                flash(f'{k}: {v}')
        return redirect(url_for('index'))

    # make sure that the state parameter matches the one we created in the
    # authorization request
    if request.args['state'] != session.get('oauth2_state'):
        abort(401)

    # make sure that the authorization code is present
    if 'code' not in request.args:
        abort(401)

    # exchange the authorization code for an access token
    response = requests.post(provider_data['token_url'], data={
        'client_id': provider_data['client_id'],
        'client_secret': provider_data['client_secret'],
        'code': request.args['code'],
        'grant_type': 'authorization_code',
        'redirect_uri': url_for('oauth2_callback', provider=provider,
                                _external=True),
    }, headers={'Accept': 'application/json'})
    if response.status_code != 200:
        abort(401)
    oauth2_token = response.json().get('access_token')
    if not oauth2_token:
        abort(401)

    # use the access token to get the user's email address
    response = requests.get(provider_data['userinfo']['url'], headers={
        'Authorization': 'Bearer ' + oauth2_token,
        'Accept': 'application/json',
    })
    if response.status_code != 200:
        abort(401)
    email = provider_data['userinfo']['email'](response.json())

    # find or create the user in the database
    # Retrieve the user by email
    user = get_user_by_email(email)

    # If user doesn't exist, create a new one
    if not user:
        # Create a new user with the provided email and username
        username = email.split('@')[0]  # using the part before "@" in email as the username
        create_user(username=username, password=None, email=email)
        # Re-fetch the user to get the newly created one
        user = get_user_by_email(email)

    # Now `user` is either the existing user or the newly created one
    user_id = user[0]  # Assuming the user is a tuple where the first element is user_id
    session["user_id"] = user_id
    session["username"] = username
    flash("Logged in successfully with Google", "success")
    return redirect(url_for("home"))


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
