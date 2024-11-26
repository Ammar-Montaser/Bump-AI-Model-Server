import math
import os
import json
import pickle
from flask import Flask, request, jsonify
from firebase_admin import credentials, firestore, initialize_app
from datetime import datetime

# Initialize Firebase using credentials from an environment variable
firebase_credentials = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')  # Environment variable holding JSON content
if not firebase_credentials:
    raise ValueError("FIREBASE_CREDENTIALS environment variable is not set")

cred = credentials.Certificate(json.loads(firebase_credentials))
initialize_app(cred)
db = firestore.client()

# Load the pre-trained model
model_path = "modelrf.pkl"  # Update this path
with open(model_path, "rb") as file:
    model = pickle.load(file)

app = Flask(__name__)

# Helper function to calculate age difference
def calculate_age_difference(age1, age2):
    return abs(age1 - age2)

# Endpoint for recommendations
@app.route('/recommend_users', methods=['POST'])
def recommend_users():
    try:
        data = request.json
        user_id = data.get('user_id')
        target_user_id = data.get('target_user_id')  # Assuming we are comparing with another specific user

        if not user_id or not target_user_id:
            return jsonify({"error": "Missing user_id or target_user_id"}), 400

        # Fetch the requesting user's data
        user_doc = db.collection('users').document(user_id).get()
        target_user_doc = db.collection('users').document(target_user_id).get()

        if not user_doc.exists or not target_user_doc.exists:
            return jsonify({"error": "One or both users not found"}), 404

        user_data = user_doc.to_dict()
        target_user_data = target_user_doc.to_dict()

        # Get the 'interests' subcollection for both users
        user_interests = db.collection('users').document(user_id).collection('interests').document('ratings').get()
        target_interests = db.collection('users').document(target_user_id).collection('interests').document('ratings').get()

        if not user_interests.exists or not target_interests.exists:
            return jsonify({"error": "Interest ratings missing for one or both users"}), 404

        user_interests_data = user_interests.to_dict()
        target_interests_data = target_interests.to_dict()

        # Ensure all required interest fields are present
        interest_fields = [
            "sports", "tvsports", "exercise", "dining", "museums", "art", "hiking", "gaming",
            "clubbing", "reading", "tv", "theater", "movies", "concerts", "music", "shopping", "yoga"
        ]
        for field in interest_fields:
            if field not in user_interests_data or field not in target_interests_data:
                return jsonify({"error": f"Missing interest field {field} for one or both users"}), 400

        # Calculate features
        features = {
            "iid": user_id,
            "pid": target_user_id,
            "match": None,  # This is what the model predicts
            "age_o": target_user_data.get("age"),
            "age": user_data.get("age"),
            "dif": calculate_age_difference(user_data.get("age"), target_user_data.get("age")),
        }

        # Add user interests
        for field in interest_fields:
            features[field] = user_interests_data[field]

        # Add target user interests (as _p fields)
        for field in interest_fields:
            features[f"{field}_p"] = target_interests_data[field]

        # Prepare the feature list in the required order for prediction
        feature_order = [
            "iid", "pid", "match", "age_o", "age", "dif",
            *interest_fields,
            *(f"{field}_p" for field in interest_fields)
        ]
        feature_values = [features[field] for field in feature_order if field in features]

        # Predict using the model
        prediction = model.predict([feature_values])[0]  # Assuming binary classification (0 or 1)

        # Return the prediction
        return jsonify({
            "prediction": prediction,
            "features": features
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
