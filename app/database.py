def createUser(mysql, email, username, password) -> bool:
    """Register new user into the database

    Args:
        mysql: mysql object to connect to 
        username: username for account
        password: password for account

    Returns:
        bool: True if user was created in database, False otherwise.
    """

    # TO-DO: hash passwords before inserting into database
    cursor = mysql.connection.cursor()
    query = f"INSERT INTO users (username, email, password) VALUES ({username}, {email}, {password});"
    cursor.execute(query)
    return True
def userLogin(mysql, username, password) -> bool:
    return True
