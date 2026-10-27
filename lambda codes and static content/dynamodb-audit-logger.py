import json
import os
import boto3

def lambda_handler(event, context):
    print("Audit Logger invoked with event:", json.dumps(event))
    
    # Extract trace context / incoming records if triggered asynchronously or via DynamoDB Streams
    records = event.get('Records', [])
    for record in records:
        event_name = record.get('eventName') # e.g., INSERT, MODIFY, REMOVE
        dynamodb_data = record.get('dynamodb', {})
        print(f"DynamoDB Event Action: {event_name}, Data: {dynamodb_data}")
        
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Audit log processed successfully'})
    }