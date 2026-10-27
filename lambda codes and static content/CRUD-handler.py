import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

# Set an environment variable TABLE_NAME=ToDo on the function
TABLE_NAME = os.environ.get("TABLE_NAME", "ToDo")
table = boto3.resource("dynamodb").Table(TABLE_NAME)

# Table schema: partition key = userID (String), sort key = todoID (String)
# GSI: userId-status-index (used by GET /todos?status=...)


def lambda_handler(event, context):
    method = event.get("httpMethod")

    # Identity comes from the verified Cognito token, never from the request body
    claims = (event.get("requestContext", {}).get("authorizer") or {}).get("claims") or {}
    user_id = claims.get("sub")
    if not user_id:
        return respond(401, {"error": "Unauthorized"})

    # Method is /{proxy+}, so the path arrives as pathParameters["proxy"],
    # e.g. "todos", "todos/<todoID>", or "api/todos" when called through CloudFront
    proxy = (event.get("pathParameters") or {}).get("proxy", "")
    parts = [p for p in proxy.split("/") if p]

    # CloudFront forwards /api/* as-is, so drop a leading "api" segment
    if parts and parts[0] == "api":
        parts = parts[1:]

    if not parts or parts[0] != "todos":
        return respond(404, {"error": "Not found"})
    todo_id = parts[1] if len(parts) > 1 else None

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return respond(400, {"error": "Invalid JSON body"})
    if not isinstance(body, dict):
        return respond(400, {"error": "Body must be a JSON object"})

    try:
        if method == "GET":
            if todo_id:
                res = table.get_item(Key={"userID": user_id, "todoID": todo_id})
                if "Item" not in res:
                    return respond(404, {"error": "Item not found"})
                return respond(200, res["Item"])

            status = (event.get("queryStringParameters") or {}).get("status")
            if status:
                res = table.query(
                    IndexName="userId-status-index",
                    KeyConditionExpression=Key("userID").eq(user_id) & Key("status").eq(status),
                )
            else:
                res = table.query(KeyConditionExpression=Key("userID").eq(user_id))
            return respond(200, res.get("Items", []))

        if method == "POST":
            title = (body.get("title") or "").strip()
            if not title:
                return respond(400, {"error": "Missing required field: title"})
            item = {
                "userID": user_id,
                "todoID": str(uuid.uuid4()),
                "title": title,
                "status": body.get("status", "pending"),
                "createdAt": datetime.now(timezone.utc).isoformat(),
            }
            table.put_item(Item=item)
            return respond(201, item)

        if method == "PUT":
            if not todo_id:
                return respond(400, {"error": "Missing todoID in path"})
            title = (body.get("title") or "").strip()
            if not title:
                return respond(400, {"error": "Missing required field: title"})
            res = table.update_item(
                Key={"userID": user_id, "todoID": todo_id},
                UpdateExpression="SET #t = :t, #s = :s, updatedAt = :u",
                ConditionExpression="attribute_exists(todoID)",
                ExpressionAttributeNames={"#t": "title", "#s": "status"},
                ExpressionAttributeValues={
                    ":t": title,
                    ":s": body.get("status", "pending"),
                    ":u": datetime.now(timezone.utc).isoformat(),
                },
                ReturnValues="ALL_NEW",
            )
            return respond(200, res["Attributes"])

        if method == "DELETE":
            if not todo_id:
                return respond(400, {"error": "Missing todoID in path"})
            table.delete_item(
                Key={"userID": user_id, "todoID": todo_id},
                ConditionExpression="attribute_exists(todoID)",
            )
            return respond(200, {"message": "Item deleted", "todoID": todo_id})

        if method == "OPTIONS":
            return respond(200, {})

        return respond(405, {"error": f"Method {method} not allowed"})

    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ConditionalCheckFailedException":
            return respond(404, {"error": "Item not found"})
        print(f"DynamoDB error: {code}")
        return respond(500, {"error": "Internal server error"})
    except Exception as e:
        print(f"Unexpected error: {e}")
        return respond(500, {"error": "Internal server error"})


def _default(o):
    # DynamoDB returns numbers as Decimal, which json can't serialize
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    raise TypeError


def respond(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
        },
        "body": json.dumps(body, default=_default),
    }