import requests
import json

# Test signup
signup_url = "http://127.0.0.1:5000/signup"
signup_data = {
    "name": "Test User",
    "email": "test@example.com",
    "password": "password123",
    "confirm_password": "password123"
}

print("Testing signup endpoint...")
response = requests.post(signup_url, json=signup_data)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

# Test login
if response.status_code == 201:
    login_url = "http://127.0.0.1:5000/login"
    login_data = {
        "email": "test@example.com",
        "password": "password123"
    }
    
    print("\nTesting login endpoint...")
    response = requests.post(login_url, json=login_data)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

# Test contact
contact_url = "http://127.0.0.1:5000/contact"
contact_data = {
    "name": "John Doe",
    "email": "john@example.com",
    "message": "This is a test message for the contact form."
}

print("\nTesting contact endpoint...")
response = requests.post(contact_url, json=contact_data)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
