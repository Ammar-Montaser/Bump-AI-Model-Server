import math
import os
import json
from flask import Flask, request, jsonify
from firebase_admin import credentials, firestore, initialize_app

# Initialize Firebase using credentials from an environment variable
firebase_credentials = os.getenv('FIREBASE_CREDENTIALS')  # Environment variable holding JSON content
if not firebase_credentials:
    raise ValueError("FIREBASE_CREDENTIALS environment variable is not set")

cred = credentials.Certificate(json.loads(firebase_credentials))
initialize_app(cred)
db = firestore.client()

app = Flask(__name__)

# Helper function to calculate distance between two coordinates
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth's radius in kilometers
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Endpoint to recommend users
@app.route('/recommend_users', methods=['POST'])
def recommend_users():
    try:
        data = request.json
        requesting_user_id = data.get('user_id')
        distance_limit = data.get('distance_limit', 50)  # Default to 50 km if not specified

        # Fetch the requesting user's data
        requesting_user_ref = db.collection('users').document(requesting_user_id)
        requesting_user = requesting_user_ref.get()
        if not requesting_user.exists:
            return jsonify({'error': 'User not found'}), 404

        requesting_user_data = requesting_user.to_dict()
        requesting_user_location = requesting_user_data.get('location', {})
        requesting_lat = requesting_user_location.get('latitude')
        requesting_lon = requesting_user_location.get('longitude')

        if requesting_lat is None or requesting_lon is None:
            return jsonify({'error': 'User location not available'}), 400

        # Fetch previously recommended users
        previously_recommended = requesting_user_data.get('recommended_users', [])

        # Fetch friends of the requesting user
        friends_snapshot = db.collection('users').document(requesting_user_id).collection('friends').stream()
        friend_ids = {friend.id for friend in friends_snapshot}

        # Fetch all users
        users_ref = db.collection('users')
        all_users = users_ref.stream()

        # Filter users
        recommended_users = []
        for user in all_users:
            user_data = user.to_dict()
            user_id = user.id
            if user_id == requesting_user_id or user_id in previously_recommended or user_id in friend_ids:
                continue

            user_location = user_data.get('location', {})
            user_lat = user_location.get('latitude')
            user_lon = user_location.get('longitude')

            if user_lat is not None and user_lon is not None:
                distance = calculate_distance(requesting_lat, requesting_lon, user_lat, user_lon)
                if distance <= distance_limit or len(recommended_users) < 25:
                    recommended_users.append({
                        'user_id': user_id,
                        'name': user_data.get('name'),
                        'distance': distance
                    })

            if len(recommended_users) == 25:
                break

        # Update the requesting user's recommended_users list
        previously_recommended.extend([user['user_id'] for user in recommended_users])
        requesting_user_ref.update({'recommended_users': previously_recommended})

        return jsonify({'recommended_users': recommended_users}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
