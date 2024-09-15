import sqlite3
import os
from dotenv import load_dotenv
import requests
from together import Together  # Ensure this is the correct library
import re
from openai import OpenAI

load_dotenv()

# API keys from .env
UPSTAGE_API_KEY = os.getenv('UPSTAGE_API_KEY')
TOGETHER_API_KEY = os.getenv('TOGETHER_API_KEY')

# Initialize UpStage client
# (Ensure to use the correct UpStage client initialization if different)
upstage_client = requests.Session()
upstage_client.headers.update({'Authorization': f'Bearer {UPSTAGE_API_KEY}'})

# Initialize TogetherAI client
together_client = Together(api_key=TOGETHER_API_KEY)

def parse_pdf(pdf_path):
    """
    Parse PDF using UpStage Document-Parse API.
    Extract expenses with 'from', 'to', and 'amount' fields.
    """
    url = "https://api.upstage.ai/v1/document-ai/document-parse"
    files = {"document": open(pdf_path, "rb")}

    response = upstage_client.post(url, files=files)
    response.raise_for_status()

    parsed_data = response.json()
    print(f"Raw Parsed Data: {parsed_data}")

    html_content = parsed_data['content']['html']
    expenses = extract_expenses_from_html(html_content)
    # print(f"Parsed Expenses: {expenses}")
    return expenses

def extract_expenses_from_html(html_content):
    """
    Extract expenses from HTML content using UpStage Solar LLM.
    """
    # Construct the prompt
    prompt = (
    """\
    Given an HTML file containing data of a bank statement, extract the expenses and structure them for SQL insertion. 
    The data should be formatted with the following attributes: 'date', 'account', 'amount', 'category'. 
    'account' is inferred from 'DESCRIPTION'. The account name or 'account' can only be either a standalone or successive combination of nouns and/or acronyms, take the last combination. For example: 'account' for "FUND TRANSFER TO A/ RAJ" is "RAJ". 
    'category' should be inferred from the 'account'. Personal names like "Ted", "Lia", "Minji" have 'category' of "transfers", whereas other names are companies and the 'category' should be based on the company's sector such as "utilities", "education", "entertainment", "food", "accommodation", "onetime". "subscriptions" is negative if a "-" is at the end and positive for "+". 
    Provide the data in a list of dictionaries, each formatted for SQL insertion without any extra strings or text. Ignore the "Total" entry.

    Expected Output Format: 
    [
        {{"date": "YYYY-MM-DD", "account": "account Name", "amount": 123.45, "category": "Category Name"}},
        ...
    ]

    HTML: {html_content}
    """
    )

    client = OpenAI(
        api_key=UPSTAGE_API_KEY,
        base_url="https://api.upstage.ai/v1/solar"
    )

    try:
        # Request a completion from the model
        response = client.chat.completions.create(
            model="solar-pro",
            messages=[{
                "role": "user",
                "content": prompt.format(html_content=html_content)
            }],
        )

        # Log the entire response for debugging
        print("API Response:", response)

        if hasattr(response, 'choices') and len(response.choices) > 0:
            content = response.choices[0].message.content  # Access message content with dot notation
            print("Response Content:", content)
    
            # Convert string to list of dictionaries
            try:
                import json
                expenses = json.loads(content)  # Use json.loads to parse JSON string
                print("Parsed Expenses:", expenses)
            except (ValueError, SyntaxError) as e:
                print(f"Error parsing content: {e}")
                expenses = None

            return expenses
        else:
            print("Error: Response does not contain choices.")
            return None

    except Exception as err:
        print(f"Error in extract_expenses_from_html: {err}")  # Log the error
        raise

def insert_expenses_into_db(expenses, db_path="expenses.db"):
    """
    Insert categorized expenses into the SQLite database.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create the table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            account TEXT,
            amount REAL,
            category TEXT
        )
    ''')

    # Insert each expense into the database
    for expense in expenses:
        cursor.execute('''
            INSERT INTO expenses (date, account, amount, category)
            VALUES (?, ?, ?, ?)
        ''', (expense['date'], expense['account'], expense['amount'], expense['category']))

    # Commit and close the connection
    conn.commit()
    conn.close()

def process_pdf(pdf_path):
    # Step 1: Parse the PDF to get HTML content and extract expenses
    expenses = parse_pdf(pdf_path)

    # Step 2: Insert categorized expenses into the SQLite database
    if expenses is not None:
        insert_expenses_into_db(expenses)
    else:
        print("No expenses extracted from HTML.")

    return expenses

def generate_query(question):
    """
    Generate SQL query using TogetherAI Llama model.
    """
    url = "https://api.together.xyz/v1/chat/completions"
    payload = {
        "messages": [
            {
                "role": "user",
                "content": f"""Given a database, expenses with the columns: date in YYYY-MM-DD, account in company or person's name with all capitalized letters, amount where positive indicates received money and negative indicates lost money, and category that depends on the company's name and personal names are 'transfers'. Generate a complete and executable SQLite query for the following question: {question}. Ensure the query is in a single line without any extra characters, and ends with a semicolon. The output should be a valid SQL query only. Do not include any additional text or formatting."""
            }
        ],
        "model": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        "stop": ["<|eot_id|>", "<|eom_id|>"],
        "max_tokens": 150,
        "temperature": 0.5,
        "top_p": 0.7,
        "top_k": 50,
        "repetition_penalty": 1
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {TOGETHER_API_KEY}"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        response_data = response.json()
        
        print("Response from TogetherAI:", response_data)  # Debug print
        
        query_instruction = response_data['choices'][0]['message']['content']
        print("Raw Query Instruction:", query_instruction)  # Debug print
        
        # Updated regex to handle simpler format
        match = re.search(r'SELECT .*;', query_instruction, re.DOTALL)
        if match:
            return match.group(0).strip()
        else:
            print("Error: SQL query not found in response.")
            return None
    except Exception as e:
        print(f"Error in generate_query: {str(e)}")
        raise

def generate_answer(question, data):
    """
    Generate final answer using TogetherAI Llama model.
    """
    url = "https://api.together.xyz/v1/chat/completions"
    data_str = str(data)  # Convert data to string if it's a single aggregated result
    
    payload = {
        "messages": [
            {
                "role": "user",
                "content": f"Based on the following data: {data_str}\nAnswer this question: {question}"
            }
        ],
        "model": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        "stop": ["<|eot_id|>", "<|eom_id|>"],
        "max_tokens": 512,
        "temperature": 0.7,
        "top_p": 0.7,
        "top_k": 50,
        "repetition_penalty": 1
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {TOGETHER_API_KEY}"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        response_data = response.json()
        
        # Extract the content of the first choice message
        answer = response_data['choices'][0]['message']['content']
        print(answer)
        return answer.strip()
    except Exception as e:
        print(f"Error in generate_answer: {str(e)}")
        raise

def fetch_data(query):
    """
    Fetch data from SQLite database based on SQL query.
    """
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()

    cursor.execute(query)
    data = cursor.fetchone()

    conn.close()
    print(data)
    return data
