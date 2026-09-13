# SchemaGuard - Schema Drift Monitor

A Python Flask application for detecting schema drift in CSV datasets.

## Features

- CSV upload
- Baseline schema validation
- Added column detection
- Removed column detection
- Data type drift detection
- Nullability detection
- Required column validation
- Critical/warning/info severity
- Audit logging
- Log download
- Responsive dashboard

## Installation

Create a virtual environment:

python -m venv venv

Activate it.

Windows:

venv\Scripts\activate

Linux/Mac:

source venv/bin/activate

Install dependencies:

pip install -r requirements.txt

## Run

python app.py

Open:

http://127.0.0.1:5000

## Test files

Use:

data/users_valid.csv

Expected result:

PASS

Use:

data/users_added_column.csv

Expected result:

WARNING

Use:

data/users_removed_column.csv

Expected result:

CRITICAL

Use:

data/users_type_changed.csv

Expected result:

CRITICAL

Use:

data/users_multiple_drift.csv

Expected result:

CRITICAL
