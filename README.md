MwamkoAI

MwamkoAI is a backend server for a route optimization engine designed for humanitarian aid. It helps prioritize areas affected by floods to efficiently distribute essential supplies like food, water, and clothing. The project emphasizes clean, maintainable code using Black, Isort, and Flake8.

Table of Contents

Overview

Requirements

Setup

Running the Server

Code Quality

Project Structure

Optional: pyproject.toml

Overview

The MwamkoAI server provides API endpoints for:

Fetching affected locations

Calculating optimized delivery routes

Prioritizing areas for humanitarian distribution

This project focuses solely on the backend logic. Frontend applications can integrate with the APIs to visualize routes or manage distribution priorities.

Requirements

Python 3.12+

PostgreSQL (if using psycopg2)

Virtual environment (venv)

Setup

Clone the repository:

git clone <your-repo-url>
cd MwamkoAI


Create and activate a virtual environment:

python3 -m venv myenv
source myenv/bin/activate


Install project dependencies:

pip install -r requirements.txt


Install code quality tools:

pip install flake8 black isort

Running the Server

Navigate to the API folder and start the server:

cd mwamko-api
uvicorn main:app --reload


The API will be available at:

http://127.0.0.1:8000


You can use tools like Postman or a frontend app to interact with the endpoints.

Code Quality

To maintain a clean, consistent codebase, use these tools:

Black – Formats Python code:

black mwamko-api mwamkoapp


⚠️ Note: Running black . over the whole repo can hang on large directories. Specify only your project folders (mwamko-api, mwamkoapp) to avoid this.

Isort – Sorts imports:

isort mwamko-api mwamkoapp


Flake8 – Lints code and checks for style issues:

flake8 mwamko-api mwamkoapp


Run these commands before committing or pushing code to ensure consistency.

Project Structure
MwamkoAI/
├─ mwamko-api/           # Backend API code
├─ mwamkoapp/            # Application logic / frontend (if any)
├─ notebooks/            # Jupyter notebooks (ignored in git)
├─ myenv/                # Python virtual environment (ignored in git)
├─ requirements.txt      # Project dependencies
├─ README.md

Optional: pyproject.toml for Code Formatting

You can create a pyproject.toml in the root of the project to configure Black, Isort, and Flake8 consistently:

[tool.black]
line-length = 88
target-version = ['py312']
include = '\.pyi?$'
exclude = '''
/(
    \.venv
  | myenv
  | migrations
  | __pycache__
)/
'''

[tool.isort]
profile = "black"
line_length = 88
known_first_party = ["mwamko_api", "mwamkoapp"]
known_third_party = ["fastapi", "uvicorn", "sqlalchemy", "pydantic"]
multi_line_output = 3
include_trailing_comma = true
force_grid_wrap = 0
use_parentheses = true

[tool.flake8]
max-line-length = 88
extend-ignore = ["E203", "W503"]
exclude = ".venv,myenv,__pycache__,notebooks"

What this does

Black – Automatically formats Python code to a consistent style.

Isort – Automatically sorts imports and groups them logically.

Flake8 – Checks code for style issues, line length, and basic errors.

⚠️ Tip: To avoid hanging or slowing down your machine, run these commands only on the main project folders:

black mwamko-api
isort mwamko-api
flake8 mwamko-api


This keeps linting and formatting fast while maintaining consistent code quality.

To automatically remove unused imports and variables and sort your imports, run:

# Install the tools
pip install autoflake isort

# Remove all unused imports and variables recursively in your API folder
autoflake --in-place --remove-unused-variables --remove-all-unused-imports -r mwamko-api/

# Sort imports neatly
isort mwamko-api/


What this does:

autoflake scans your code and removes any imports or variables that aren’t being used.

isort then organizes the remaining imports into a clean, consistent order.

Combined, this keeps your codebase tidy, readable, and professional with almost no effort.

Tip: Run these commands before committing your code to ensure your branch stays clean. Think of it as “magic for your imports” 🪄.