from flask import Flask, render_template, request, redirect, url_for, flash
from flask_mysqldb import MySQL
from datetime import datetime, timedelta
from config import Config
import os

app = Flask(__name__)
app.config.from_object(Config)
# app.secret_key = 'perfectchemical' # may not need this. used for signing session cookies

mysql = MySQL(app)



@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        file = request.files.get("file")  ##: modify to only accept a certain file. 
        if file:
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], file.filename))
            return "File uploaded successfully!"
    
    return render_template("index.html")  


@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/register")
def register():
    return render_template("register.html")











if __name__== '__main__':
    app.run(debug=True)
    # default port is 5000
    # app.run(port=<port>) to change port number