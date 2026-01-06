# 🏸 BillShop – AI SQL Service (FastAPI)

This repository contains a **FastAPI-based AI service** that provides controlled access to the **SQL database** for the BillShop AI system using **LangChain SQLDatabase**.

The service acts as a **bridge between Large Language Models (LLMs) and the relational database**, enabling natural language queries to be safely translated into SQL operations.

---

## 🎯 Responsibilities of This Repository

This FastAPI service is responsible for:

- Providing database access for AI agents
- Supporting natural language to SQL workflows
- Executing read-only and controlled SQL queries
- Exposing database schema information to AI agents
- Ensuring safe and validated SQL execution

This repository does **not** handle UI rendering, authentication, or business logic.

---

## 🧠 AI SQL Architecture

The service is built around **LangChain's SQLDatabase abstraction**, enabling LLMs to reason over relational data.

Key characteristics:

- Database schema introspection
- SQL query generation and validation
- Controlled query execution
- Separation between AI reasoning and data access
- Stateless API design

This approach allows AI agents to answer data-driven questions while maintaining database safety.

---

## 🔗 LangChain Integration

The service integrates with LangChain using:

- `SQLDatabase` for database connectivity
- SQL query execution tools
- Schema inspection utilities
- Query validation before execution

It is designed to be called by **AI orchestration services** rather than end users directly.

---

## 🧩 Tech Stack

- Python
- FastAPI
- LangChain
- SQLAlchemy
- MySQL
- Uvicorn

---

## 🔐 Database Safety & Control

To reduce risks associated with AI-generated SQL:

- Queries are validated before execution
- Database access can be restricted to specific tables
- Write operations can be disabled or limited
- Errors are handled and sanitized before returning to the AI layer

This ensures reliable and predictable behavior when AI agents interact with the database.

---

## ⚙️ Environment Configuration

This service uses environment variables for configuration.

A `.env` file should be created locally based on `.env.example` before running the service.

Configuration typically includes:
- Database connection parameters
- Runtime environment settings
- Optional AI-related configuration

Sensitive values are not committed to version control.

---

## 🛠️ Installation

### Prerequisites

- Python 3.10 or later
- pip
- MySQL

---

### Step 1: Clone the repository
git clone https://github.com/thangle300403/fast_api_1212.git

### Step 2: Create a virtual environment
python -m venv venv

source venv/bin/activate

(On Windows: venv\Scripts\activate)

### Step 3: Install dependencies
pip install -r requirements.txt

### Step 4: Run the service
uvicorn main:app --reload

## 👨‍💻 Author

Lê Quốc Thắng

Software Engineering – Graduation Project

Ho Chi Minh City University of Technology and Education
