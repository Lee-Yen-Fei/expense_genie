from flask import Flask
from dotenv import load_dotenv
import os

def create_app():
    app = Flask(__name__)
    
    # Load environment variables from .env file
    load_dotenv()  # Ensure python-dotenv is installed
    
    # Configure your app with environment variables
    app.config['UPSTAGE_API_KEY'] = os.getenv('UPSTAGE_API_KEY')
    app.config['TOGETHER_API_KEY'] = os.getenv('TOGETHER_API_KEY')

    # Configure the upload folder
    app.config['UPLOAD_FOLDER'] = './uploads'
    
    # Make sure the upload folder exists
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    # Register blueprints
    from .routes import main  # Import blueprint from routes
    app.register_blueprint(main)

    return app
