from flask import current_app
from flask_mysqldb import MySQL
from werkzeug.security import check_password_hash, generate_password_hash
import os

mysql = MySQL()
# TODO: add doc strings to all functions for clarity, readability, and makesenseinthefutureability

def create_user(username, password, email) -> bool:
    print(f"email: {email}\nusername: {username}\npassword: {password}")
    cur = mysql.connection.cursor()
    pass_hash = generate_password_hash(password)
    cur.execute("INSERT INTO users (username, password, email) VALUES (%s, %s, %s)", (username, pass_hash, email))
    mysql.connection.commit()
    cur.close()
    return True

def get_user_by_username(username):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id, username, password, email FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    return user

def get_user_by_email(email):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
    email = cursor.fetchone()
    cursor.close()
    return email

def get_user_files(username):
    user_folder = os.path.join('/home/anti-ats/submissions', username)
    
    if os.path.exists(user_folder):
        files = [f for f in os.listdir(user_folder) if os.path.isfile(os.path.join(user_folder, f))]
        
        file_paths = [os.path.join(user_folder, f) for f in files]
        
        return file_paths
    else:
        return None

def validate_user_password(stored_password, input_password):
    return check_password_hash(stored_password, input_password)
