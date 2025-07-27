import cv2
import base64
import uuid
import datetime
import time
import json # For handling JSON locations

# Google Cloud Imports
from google.cloud import vision_v1
from google.cloud import bigquery

# --- Configuration ---
# Your Google Cloud Project ID
PROJECT_ID = 'drishti-event-safety11'
# Your BigQuery Dataset ID
BIGQUERY_DATASET_ID = 'vision_analysis'
# Your BigQuery Table ID
BIGQUERY_TABLE_ID = 'person_detections'

# Vision AI client setup
vision_client = vision_v1.ImageAnnotatorClient()
# BigQuery client setup
bigquery_client = bigquery.Client(project=PROJECT_ID)
table_ref = bigquery_client.dataset(BIGQUERY_DATASET_ID).table(BIGQUERY_TABLE_ID)
bigquery_table = bigquery_client.get_table(table_ref) # Get table object for streaming inserts

# Camera settings
CAMERA_INDEX = 0  # Typically 0 for the default laptop camera
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
# Interval to send frames to Vision API (in seconds).
# Sending every frame will be very costly and might hit API limits.
# 1.0 means 1 frame per second. Adjust based on your needs and budget.
#API_CALL_INTERVAL_SEC = 1.0 
API_CALL_INTERVAL_SEC = 5.0 
# --- Main Logic ---
def run_drishti_vision_stream():
    cap = cv2.VideoCapture(CAMERA_INDEX)

    if not cap.isOpened():
        print(f"Error: Could not open camera at index {CAMERA_INDEX}.")
        print("Please check if the camera is connected and not in use by another application.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    last_api_call_time = time.time()

    print("Starting video stream... Press 'q' to quit.")
    print(f"Frames sent to Vision API every {API_CALL_INTERVAL_SEC} seconds.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame, exiting...")
                break

            current_time = time.time()

            # Process frame for Vision API at intervals
            if (current_time - last_api_call_time) >= API_CALL_INTERVAL_SEC:
                last_api_call_time = current_time
                
                # Convert frame to bytes for Vision API
                _, encoded_image = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                image_bytes = encoded_image.tobytes()

                image = vision_v1.Image(content=image_bytes)
                
                # Configure the feature to detect objects (including 'Person')
                features = [vision_v1.Feature(type_=vision_v1.Feature.Type.OBJECT_LOCALIZATION)]
                
                request = vision_v1.AnnotateImageRequest(image=image, features=features)

                person_count = 0
                person_locations = []
                
                try:
                    print("Sending frame to Vision AI...")
                    response = vision_client.annotate_image(request=request)

                    for obj in response.localized_object_annotations:
                        if obj.name == "Person":
                            person_count += 1
                            # Extract bounding box normalized vertices
                            vertices = [
                                {'x': v.x, 'y': v.y}
                                for v in obj.bounding_poly.normalized_vertices
                            ]
                            person_locations.append({
                                'score': obj.score,
                                'vertices': vertices
                            })
                    
                    # Prepare data for BigQuery streaming insert
                    current_timestamp_utc = datetime.datetime.now(datetime.timezone.utc)
                    row_id = str(uuid.uuid4()) # Unique ID for streaming inserts

                    rows_to_insert = [{
                        "timestamp": current_timestamp_utc.isoformat(timespec='microseconds'),
                        "frame_id": row_id,
                        "person_count": person_count,
                        "locations": json.dumps(person_locations) # BigQuery JSON type expects a JSON string
                    }]

                    errors = bigquery_client.insert_rows_json(bigquery_table, rows_to_insert, row_ids=[row_id])

                    if errors:
                        print(f"BigQuery streaming errors: {errors}")
                    else:
                        print(f"BigQuery: Inserted frame {row_id} | People Detected: {person_count}")
                        
                except Exception as e:
                    print(f"Error calling Vision AI or inserting to BigQuery: {e}")

            # --- Display the frame (optional) ---
            # You can draw bounding boxes on the frame here if you want local visualization
            # This part is omitted for brevity but can be added using OpenCV drawing functions
            # based on `response.localized_object_annotations`

            cv2.imshow('Drishti Live Vision - Press Q to Quit', frame)

            # Check for 'q' key press to exit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting...")
    finally:
        # Release resources
        cap.release()
        cv2.destroyAllWindows()
        print("Video capture released and windows closed.")

if __name__ == "__main__":
    # IMPORTANT: Replace with your actual GCP Project ID before running!
    # e.g., PROJECT_ID = 'my-unique-project-12345'
    if PROJECT_ID == 'your-gcp-project-id':
        print("ERROR: Please update PROJECT_ID in the script with your actual Google Cloud Project ID.")
        exit()

    run_drishti_vision_stream()