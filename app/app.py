from flask import Flask, render_template, request, redirect, url_for, flash
from flask_mysqldb import MySQL
from datetime import datetime, timedelta
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
# app.secret_key = 'perfectchemical' # may not need this. used for signing session cookies

mysql = MySQL(app)


















if __name__== '__main__':
    app.run(debug=True)
    # default port is 5000
    # app.run(port=<port>) to change port number