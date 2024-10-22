from flask import Flask, request, jsonify
from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from openai import OpenAI
from dotenv import load_dotenv
import os
import re
import traceback
from datetime import datetime, timedelta
import math


# Load environment variables
load_dotenv()

app = Flask(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize Firestore client
try:
    db = firestore.Client.from_service_account_json('firebasesdk.json')
    collection = db.collection('videos')
except Exception as e:
    print(f"Error initializing Firestore: {str(e)}")
    print(traceback.format_exc())

def get_embedding(text):
    try:
        response = client.embeddings.create(
            input=text,
            model='text-embedding-ada-002'
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error getting embedding: {str(e)}")
        print(traceback.format_exc())
        raise

def process_topics(topics):
    # Convert string representation of list to actual list if necessary
    if isinstance(topics, str):
        topics = eval(topics)
    
    # Process each topic
    processed_topics = []
    for topic in topics:
        # Remove speech marks, podcast, OR, discussion, interview
        cleaned = re.sub(r'[""]|podcast|OR|discussion|interview', '', topic, flags=re.IGNORECASE)
        # Split by spaces and add each word as a separate topic
        words = [word.strip() for word in cleaned.split() if word.strip()]
        processed_topics.extend(words)
    
    # Remove duplicates while preserving original capitalization
    processed_topics = list(dict.fromkeys(processed_topics))
    
    return processed_topics

@app.route('/api/vector-search', methods=['POST'])
def vector_search():
    data = request.json
    query_text = data.get('query')
    limit = data.get('limit', 10)

    if not query_text:
        return jsonify({"error": "No query provided"}), 400

    try:
        query_embedding = get_embedding(query_text)

        vector_query = collection.find_nearest(
            vector_field='embedding_field',
            query_vector=Vector(query_embedding),
            distance_measure=DistanceMeasure.COSINE,
            limit=limit,
            distance_result_field='vector_distance'
        )

        results = []
        for doc in vector_query.stream():
            doc_dict = doc.to_dict()
            channel_data = doc_dict.get('channel', '')
            
            # Format the guest name properly before returning
            results.append({
                "id": doc.id,
                "title": doc_dict.get('title', ''),
                "description": doc_dict.get('description', ''),
                "performance": doc_dict.get('performance', 0),
                "search_query": doc_dict.get('search_query', ''),
                "upload_date": doc_dict.get('upload_date', ''),
                "url": doc_dict.get('url', ''),
                "video_id": doc_dict.get('video_id', ''),
                "views": doc_dict.get('views', 0),
                "guest_name": format_guest_name(doc_dict.get('guest_name', '')),  # Format the guest name
                "channel": {
                    "name": channel_data.get('name', ''),
                    "avg_views_per_video_in_range": channel_data.get('avg_views_per_video_in_range', 0)
                },
                "distance": doc_dict.get('vector_distance', 1)
            })

        # Sort results by performance in descending order
        results.sort(key=lambda x: x['performance'], reverse=True)

        return jsonify(results)

    except Exception as e:
        print(f"Error in vector search: {str(e)}")  
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route('/api/top-videos', methods=['GET'])
def get_top_videos():
    limit = request.args.get('limit', default=20, type=int)

    try:
        videos_query = collection.order_by('performance', direction=firestore.Query.DESCENDING).limit(limit)
        
        results = []
        for doc in videos_query.stream():
            doc_dict = doc.to_dict()
            channel_data = doc_dict.get('channel', {})
            results.append({
                "id": doc.id,
                "title": doc_dict.get('title', ''),
                "description": doc_dict.get('description', ''),
                "performance": doc_dict.get('performance', 0),
                "search_query": doc_dict.get('search_query', ''),
                "upload_date": doc_dict.get('upload_date', ''),
                "url": doc_dict.get('url', ''),
                "video_id": doc_dict.get('video_id', ''),
                "views": doc_dict.get('views', 0),
                "guest_name": doc_dict.get('guest_name', ''),
                "channel": {
                    "name": channel_data.get('name', ''),
                    "avg_views_per_video_in_range": channel_data.get('avg_views_per_video_in_range', 0)
                }
            })

        return jsonify(results)

    except Exception as e:
        print(f"Error fetching top videos: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500
    
def format_guest_name(guest_name):
    # Replace underscores and multiple spaces with a single space and title-case it (e.g., 'elon_musk' -> 'Elon Musk')
    formatted_name = re.sub(r'[\s_]+', ' ', guest_name).strip().title()
    return formatted_name


@app.route('/api/top-guests', methods=['GET'])
def get_top_guests():
    limit = request.args.get('limit', default=20, type=int)

    try:
        guest_collection = db.collection('guests_with_embeddings')
        
        # Fetch guests, sorted by combined_score
        guests_query = guest_collection.order_by('combined_score', direction=firestore.Query.DESCENDING).limit(limit)
        
        results = []
        for doc in guests_query.stream():
            guest_dict = doc.to_dict()
            
            results.append({
                "guest_name": format_guest_name(doc.id),
                "avg_performance": guest_dict.get('avg_performance', 0),
                "avg_views": guest_dict.get('avg_views', 0),
                "avg_views_per_video_across_channels": guest_dict.get('avg_views_per_video_across_channels', 0),
                "episode_descriptions": guest_dict.get('episode_descriptions', ''),
                "episode_titles": guest_dict.get('episode_titles', ''),
                "most_recent_date": format_date(guest_dict.get('most_recent_date', '')),
                "no_episodes": guest_dict.get('no_episodes', 0),
                "recent_channel": guest_dict.get('recent_channel', ''),
                "topics": process_topics(guest_dict.get('topics', [])),
                "combined_score": guest_dict.get('combined_score', 0)
            })

        return jsonify(results)

    except Exception as e:
        print(f"Error fetching top guests: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


def format_date(date_value):
    if isinstance(date_value, dict) and '$date' in date_value:
        # If it's already in the desired format, return as is
        return date_value
    elif isinstance(date_value, str):
        # Try to parse the string date
        try:
            parsed_date = datetime.strptime(date_value, "%d %B %Y at %H:%M:%S %Z%z")
            return {"$date": parsed_date.isoformat()}
        except ValueError:
            # If parsing fails, return the original string
            return {"$date": date_value}
    else:
        # For any other type, convert to ISO format string
        return {"$date": date_value.isoformat() if isinstance(date_value, datetime) else str(date_value)}


@app.route('/api/vector-search-guests', methods=['POST'])
def vector_search_guests():
    data = request.json
    query_text = data.get('query')
    limit = data.get('limit', 10)

    if not query_text:
        return jsonify({"error": "No query provided"}), 400

    try:
        query_embedding = get_embedding(query_text)

        guest_collection = db.collection('guests_with_embeddings')
        vector_query = guest_collection.find_nearest(
            vector_field='average_embedding',
            query_vector=Vector(query_embedding),
            distance_measure=DistanceMeasure.COSINE,
            limit=limit,
            distance_result_field='vector_distance'
        )

        results = []
        for doc in vector_query.stream():
            guest_dict = doc.to_dict()
            results.append({
                "guest_name": format_guest_name(doc.id),
                "avg_performance": guest_dict.get('avg_performance', 0),
                "avg_views": guest_dict.get('avg_views', 0),
                "avg_views_per_video_across_channels": guest_dict.get('avg_views_per_video_across_channels', 0),
                "episode_descriptions": guest_dict.get('episode_descriptions', ''),
                "episode_titles": guest_dict.get('episode_titles', ''),
                "most_recent_date": format_date(guest_dict.get('most_recent_date', '')),
                "no_episodes": guest_dict.get('no_episodes', 0),
                "recent_channel": guest_dict.get('recent_channel', ''),
                "topics": process_topics(guest_dict.get('topics', [])),
                "distance": guest_dict.get('vector_distance', 1)
            })

        # Sort results by avg_performance in descending order
        results.sort(key=lambda x: x['avg_performance'], reverse=True)

        return jsonify(results)

    except Exception as e:
        print(f"Error in vector search guests: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
