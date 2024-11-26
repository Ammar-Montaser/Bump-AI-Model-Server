import math
import os
import json
import pickle
from datetime import datetime, date
from flask import Flask, request, jsonify
from firebase_admin import credentials, firestore, initialize_app

# Initialize Firebase using credentials from an environment variable
firebase_credentials = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')  # Environment variable holding JSON content
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

# Helper function to calculate age from birthday
def calculate_age(birthday):
    today = date.today()
    return today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))

# Load the model using pickle
model_path = os.getenv('MODEL_PATH', 'model.pkl')  # Path to the model file
if not os.path.exists(modelrf.pkl):
    raise FileNotFoundError("Model file not found at specified path")

with open(model_path, 'rb') as model_file:
    model = pickle.load(model_file)

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
        if not requesting_user.exists():
            return jsonify({'error': 'User not found'}), 404

        requesting_user_data = requesting_user.to_dict()
        requesting_user_location = requesting_user_data.get('location', None)
        if requesting_user_location is None:
            return jsonify({'error': 'User location not available'}), 400

        requesting_lat = requesting_user_location.latitude
        requesting_lon = requesting_user_location.longitude

        # Calculate requesting user's age
        requesting_birthday_str = requesting_user_data.get('birthday')
        if not requesting_birthday_str:
            return jsonify({'error': 'User birthday not available'}), 400

        requesting_birthday = datetime.strptime(requesting_birthday_str, "%Y-%m-%d").date()
        requesting_user_age = calculate_age(requesting_birthday)

        # Fetch interests for the requesting user
        requesting_interests_ref = requesting_user_ref.collection('interests').document('ratings')
        requesting_interests_doc = requesting_interests_ref.get()
        if not requesting_interests_doc.exists():
            return jsonify({'error': 'User interests not available'}), 400

        requesting_interests = requesting_interests_doc.to_dict()

        # Fetch the list of friends
        friends_snapshot = db.collection('users').document(requesting_user_id).collection('friends').stream()
        friend_ids = {friend.id for friend in friends_snapshot}

        # Fetch users that have been swiped by the requesting user
        swipes_snapshot = db.collection('users').document(requesting_user_id).collection('swipes').stream()
        swiped_user_ids = {swiped.id for swiped in swipes_snapshot}

        # Fetch all users
        users_ref = db.collection('users')
        all_users = users_ref.stream()

        # Fetch the existing recommended users from the subcollection
        recommended_users_ref = requesting_user_ref.collection('recommended_users')
        recommended_user_ids = {doc.id for doc in recommended_users_ref.stream()}

        # Filter users to recommend
        recommended_users = []
        for user in all_users:
            user_data = user.to_dict()
            user_id = user.id

            # Skip if the user is the requesting user, already recommended, a friend, or swiped
            if user_id == requesting_user_id or user_id in recommended_user_ids or user_id in friend_ids or user_id in swiped_user_ids:
                continue

            user_location = user_data.get('location', None)
            if user_location:
                user_lat = user_location.latitude
                user_lon = user_location.longitude

                # Calculate distance
                if user_lat is not None and user_lon is not None:
                    distance = calculate_distance(requesting_lat, requesting_lon, user_lat, user_lon)
                    if distance <= distance_limit:
                        # Fetch interests for the potential user
                        user_interests_ref = db.collection('users').document(user_id).collection('interests').document('ratings')
                        user_interests_doc = user_interests_ref.get()
                        if not user_interests_doc.exists():
                            continue

                        user_interests = user_interests_doc.to_dict()

                        # Calculate user's age
                        user_birthday_str = user_data.get('birthday')
                        if not user_birthday_str:
                            continue

                        user_birthday = datetime.strptime(user_birthday_str, "%Y-%m-%d").date()
                        user_age = calculate_age(user_birthday)

                        # Prepare input for the model
                        model_input = [
                            user_id,  # iid
                            requesting_user_id,  # pid
                            0,  # Placeholder for match (output)
                            user_age,
                            requesting_user_age,
                            abs(user_age - requesting_user_age),
                            *[requesting_interests.get(key, 0) for key in requesting_interests.keys()],
                            *[user_interests.get(key, 0) for key in user_interests.keys()]
                        ]

                        # Predict match score
                        match_score = model.predict([model_input])[0]

                        if match_score > 0.5:  # Example threshold for recommendation
                            recommended_users.append({
                                'user_id': db.collection('users').document(user_id),  # Return document reference
                                'name': user_data.get('display_name'),
                                'distance': distance,
                                'match_score': match_score
                            })

            # Stop once we have 25 recommended users
            if len(recommended_users) == 25:
                break

        # Add recommended users to the subcollection
        for recommended_user in recommended_users:
            recommended_users_ref.document(recommended_user['user_id'].id).set({
                'user_id': recommended_user['user_id'],
                'name': recommended_user['name'],
                "isSwipped": False,
                'match_score': recommended_user['match_score'],
                'recommended_at': datetime.now()  # Add timestamp of recommendation
            })

        return jsonify({'recommended_users': recommended_users}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
