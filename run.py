from werkzeug.serving import run_simple
from app import app


if __name__ == '__main__':
    run_simple('localhost', 5000, app)