# College Resource Management System (CRMS)

A full-stack project built with Flask (Python), HTML, CSS, and JavaScript.

## Features (12 Modules)
1.  **Authentication & Role Management**: Student & Admin Login, Role-based access.
2.  **Student Profile Management**: Update profile, Roll No assignment, Dashboard.
3.  **Course & Subject Management**: Admin can manage courses and subjects.
4.  **Marks & Result Management**: Internal/Semester marks upload, PDF Result generation.
5.  **Attendance Management**: Daily attendance tracking.
6.  **Assignment & Submission**: Assignment creation by admin.
7.  **Notice & Notification**: Announcements on the home page.
8.  **Certification & Achievement**: (Models included).
9.  **Placement & Internship**: Job posting and viewing.
10. **Analytics & Reports**: Visual charts for performance and course statistics.
11. **Feedback & Grievance**: Students can submit feedback and complaints.
12. **Admin Dashboard**: Real-time stats and management tools.

## Tech Stack
- **Frontend**: HTML5, CSS3, JavaScript (Bootstrap 5, Chart.js)
- **Backend**: Python (Flask)
- **Database**: SQLite (SQLAlchemy)
- **PDF Generation**: ReportLab

## How to Run
1.  **Install Python** (if not already installed).
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run the application**:
    ```bash
    python app.py
    ```
4.  **Access the application**:
    Open `http://127.0.0.1:5000` in your browser.

## Run with Docker

Docker Compose starts the Flask application and MongoDB together:

```bash
docker compose up --build
```

Open `http://localhost:5000`. Stop the services with `docker compose down`.

The `Build and test Docker image` workflow runs automatically for pushes and pull requests targeting `main` or `master`. It is also available under the **Actions** tab for manual runs.

## Default Credentials
- **Admin**: `admin@crms.com` / `admin123`
- **Student**: You can register a new student account from the register page.
