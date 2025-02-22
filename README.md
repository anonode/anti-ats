# anti-ats

## Setup

Make sure to create a `config.py` in the `app/` directory.

Should contain the following information:

```python
class Config:
    MYSQL_HOST = 'localhost'  # or whatever IP address. 
    MYSQL_USER = '<replace>' # your root username in MySQL
    MYSQL_PASSWORD = '<replace>' # password to access database instance in MySQL
    MYSQL_DB = '<replace>' # the name of the database being accessed
```

Next, create a virtual environment (venv) with `python -m venv venv` in the parent of the `app` folder
And then activate it with:
- Windows: `.\venv\Scripts\Activate`
- Linux: `. venv/bin/activate`

Once the virtual environment is activated, install the required dependencies with `pip install -r requirements.txt`


To run the project, enter `python app.py`

The app will default to `localhost:5000` in the browser, but the port number can be changed