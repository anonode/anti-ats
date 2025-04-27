# anti-ats

## Setup

Make sure to create a `config.py` in the `app/` directory.

Should contain the following information:

```python
import os
class Config:
    MYSQL_HOST = os.environ.get("MYSQL_HOST")
    MYSQL_USER = os.environ.get("MYSQL_USER")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD")
    MYSQL_DB = os.environ.get("MYSQL_DB")

    SECRET_KEY = os.environ.get("SECRET_KEY")

    GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
```

Make sure to configure all of these options. OAUTH is nice to have, but if you don't want to set that up, then either place dummy data in the two environment variables pertaining to OAUTH or remove the code for it.

### Virtual Environment - Python

Next, create a virtual environment (venv) with `python -m venv venv` in the parent of the `app` folder
And then activate it with:
- Windows: `.\venv\Scripts\Activate`
- Linux: `. venv/bin/activate`

Once the virtual environment is activated, install the required dependencies with `pip install -r requirements.txt`


To run the project, enter `python app.py`

The app will default to `localhost:5000` in the browser, but the port number can be changed


To initialize the database: `mysql -u <username> -p < db.sql`

### Installs for NLP Scanner

Python Packages: 
`pip install docx2txt PyMuPDF nltk spacy`

Spacy Mode: 
`python -m spacy download en_core_web_md`

NLTK Data:
`python -m nltk.downloader stopwords` 
`python -m nltk.downloader punkt`