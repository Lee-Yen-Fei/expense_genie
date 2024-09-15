from flask import Blueprint, request, jsonify, render_template, current_app as app
from .models import process_pdf, generate_query, fetch_data, generate_answer
import os
import sqlite3
from werkzeug.utils import secure_filename

main = Blueprint('main', __name__)

# Initialize SQLite database
DATABASE = 'expenses.db'

def init_db():
    """Create the SQLite database and table if they don't exist."""
    if not os.path.exists('uploads'):
        os.makedirs('uploads')

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                account TEXT,
                amount REAL,
                category TEXT
            )
        ''')
        conn.commit()

@main.route('/')
def home():
    return render_template('index.html')

@main.route('/upload', methods=['GET', 'POST'])
def upload_pdf():
    if request.method == 'POST':
        # Check if a file is provided
        if 'pdf_file' not in request.files:
            return "No file part", 400
        
        pdf_file = request.files['pdf_file']
        
        # Check if a valid file is uploaded
        if pdf_file.filename == '':
            return "No selected file", 400

        # Save the file to the upload folder
        if pdf_file:
            filename = secure_filename(pdf_file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            pdf_file.save(file_path)
            
            # Process the PDF
            expenses = process_pdf(file_path)
            # Debugging statement
            print("Expenses passed to template:", expenses)
            return render_template('upload_pdf_results.html', expenses=expenses)
    
    return render_template('upload.html')  # Render your upload form

@main.route('/ask-question', methods=['POST'])
def ask_question_route():
    """Handles question input, generates SQL query, fetches data, and renders results in an HTML page."""
    
    # Fetch question from form submission (not JSON since you're using traditional form submission)
    question = request.form.get("question")
    print(question)

    if not question:
        return jsonify({'error': 'Question is required'}), 400

    try:
        # Generate SQL query from the question
        query = generate_query(question)
        
        if not query:
            return jsonify({'error': 'Failed to generate SQL query'}), 500

        # Fetch data from the database using the generated query
        data = fetch_data(query)

        if not data:
            return jsonify({'error': 'No data found for the generated query'}), 404

        # Generate an answer from the data
        answer = generate_answer(question, data)

        # Render HTML template with question and answer
        return render_template('ask_questions_results.html', question=question, answer=answer)

    except Exception as e:
        print(f"Error in ask_question_route: {str(e)}")
        return jsonify({'error': str(e)}), 500


