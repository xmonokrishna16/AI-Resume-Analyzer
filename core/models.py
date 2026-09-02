from flask_login import UserMixin
from core.db import get_db_connection

class User(UserMixin):
    def __init__(self, id, name, email, password_hash, role='individual', phone_whatsapp=None, address=None):
        self.id = id
        self.name = name
        self.email = email
        self.password_hash = password_hash
        self.role = role
        self.phone_whatsapp = phone_whatsapp
        self.address = address

    @staticmethod
    def get(user_id):
        """Fetch user by ID for Flask-Login."""
        conn = get_db_connection()
        if not conn:
            return None
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()

        if user_data:
            return User(
                id=user_data['id'],
                name=user_data['name'],
                email=user_data['email'],
                password_hash=user_data['password_hash'],
                role=user_data.get('role', 'individual'),
                phone_whatsapp=user_data.get('phone_whatsapp'),
                address=user_data.get('address')
            )
        return None

    @staticmethod
    def find_by_email(email):
        """Fetch user by email."""
        conn = get_db_connection()
        if not conn:
            return None
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Users WHERE email = %s", (email,))
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()

        if user_data:
            return User(
                id=user_data['id'],
                name=user_data['name'],
                email=user_data['email'],
                password_hash=user_data['password_hash'],
                role=user_data.get('role', 'individual'),
                phone_whatsapp=user_data.get('phone_whatsapp'),
                address=user_data.get('address')
            )
        return None