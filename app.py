from fastapi import FastAPI, HTTPException
import os
from functions import get_traffic_events, convert_to_df, upload_to_db
from dotenv import load_dotenv

app = FastAPI()

load_dotenv()

supabase_url = os.getenv('supabase_url')
supabase_key = os.getenv('supabase_key')
table_name = os.getenv('table_name')
api_key = os.getenv('api_key')

@app.post("/upload-traffic-events")
async def upload_traffic_events():
    try:
        print("Starting API call...")
        # Make API call
        data = get_traffic_events(api_key)
        print("API call completed")
        
        print("Converting data to DataFrame...")
        # Convert JSON to DataFrame
        df = convert_to_df(data)
        print("Data conversion complete")
        
        print("Uploading data to database...")
        # Upload to database
        upload_to_db(df, table_name, supabase_key, supabase_url)
        print('Data upload complete')

        return {"message": "Data uploaded successfully"}
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to upload data: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)

