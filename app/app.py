from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
import os
# our stuff
from config import Config
from database import *
from scanner import *

app = Flask(__name__)
app.config.from_object(Config)
upload_path = "/home/anti-ats/submissions/" # adjust this later
app.secret_key = 'perfectchem1cal' # sign session cookies
mysql = MySQL(app)

@app.route("/", methods=["GET", "POST"])
def home():
    if "user_id" not in session:
        return redirect(url_for('login'))
    
    username = session.get("username")
    
    if request.method == "POST":
        file = request.files.get("file")
        if file:
            if file.filename.endswith('.pdf') or file.filename.endswith('docx') or file.filename.endswith('doc'):
                filename = secure_filename(file.filename) # no directory traversal here. removes all special characters
                user_dir = os.path.join(upload_path, username)
                
                if not os.path.exists(user_dir):
                    os.makedirs(user_dir)
                    
                file.save(os.path.join(user_dir, filename)) # finally save file
                
                flash("File uploaded successfully", "success")
                return redirect(url_for("home"))
            else:
                flash('Invalid file type', 'error')
                return redirect(url_for("home"))
    
    return render_template("index.html")  

@app.route("/<username>-files")
def my_resumes():
    if "username" not in session: # make sure they are logged in
        return redirect(url_for("login"))

    username = session["username"]
    files = get_user_files(username)

    if files:
        return render_template("user_files.html", username=username, files=files)
    else:
        flash("You don't have any resumes uploaded yet.", "info")
        return render_template("user_files.html", files=[])


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

        email = get_user_by_email(email)
        if email:
            flash(f'Already a user with this email. Please enter another email address')
            return render_template(url_for("register"))

        else:
            create_user(username, password, email)
            flash("Registered successfully")
            return redirect(url_for("login"))
    
    
    return render_template("register.html") # redirect to register.html with HTTP Redirect and implicit GET request






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
    app.run(debug=True)
    # default port is 5000
    # app.run(port=<port>) to change port number