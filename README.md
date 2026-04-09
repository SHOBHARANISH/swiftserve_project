# SwiftServe: Hyperlocal Delivery Platform

SwiftServe is a full-stack Python web application simulating a real-time, hyperlocal delivery service. It connects Customers, Restaurants, and Delivery Agents in a single platform , complete with live order tracking on a map.



This project is built with a Flask monolithic architecture , using PostgreSQL for the database and Flask-SocketIO for real-time communication.



# ⚙️ Prerequisites
Before you begin, ensure you have the following software installed on your system:

Python (Version 3.8 or newer)

Git (for cloning the repository)

PostgreSQL (the database management system)


PostGIS (The geospatial extension for PostgreSQL. This is essential for Module 4's geolocation features.)


# 🚀 Getting Started
Follow these steps to get your local development environment set up and running.

## 1. Clone the Repository
Clone the project to your local machine:



git clone https://github.com/your-username/swiftserve.git
cd swiftserve

## 2. Set Up the Python Environment
It is highly recommended to use a virtual environment to manage project dependencies.

Bash

## Create a virtual environment
python -m venv .venv

## Activate the environment
## On macOS/Linux:
source .venv/bin/activate
## On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

## 3. Install Dependencies
The required Python libraries are listed in requirements.txt.

Bash

pip install -r requirements.txt

Your requirements.txt file should contain:

Flask
Flask-SQLAlchemy
Flask-Login
Flask-Bcrypt
psycopg2-binary
Flask-SocketIO
python-dotenv
(Note: Add python-dotenv if you don't have it, as it's the best way to manage configuration.)

## 4. Configure the Database (PostgreSQL + PostGIS)
This is the most critical setup step.

Start PostgreSQL: Make sure your PostgreSQL server is running.

Create a Database: Use a tool like psql or a GUI (like DBeaver or pgAdmin) to create a new database.

SQL

CREATE DATABASE swiftserve;
Enable PostGIS: You must enable the PostGIS extension on your new database.

SQL

-- Connect to the new database
\c swiftserve
-- Enable the extension
CREATE EXTENSION postgis;

## 5. Configure Environment Variables
Create a file named .env in the root of your project. This file will securely store your secret key and database connection string.

Your .env file should look like this:

## Flask Secret Key (change this to a random string)
SECRET_KEY='your_very_strong_and_secret_key'

## PostgreSQL Database URL
## Format: postgresql://[USERNAME]:[PASSWORD]@[HOSTNAME]:[PORT]/[DATABASE_NAME]
SQLALCHEMY_DATABASE_URI='postgresql://postgres:your_password@localhost:5432/swiftserve'
(Make sure to update your_password and other details to match your local PostgreSQL setup.)

## 6. Run the Application
The application is set up to automatically create all the necessary database tables on its first run.

Bash

python app.py

Your application should now be running! Open your web browser and go to:

http://127.0.0.1:5000