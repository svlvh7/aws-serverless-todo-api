# Serverless To-Do REST API on AWS

A serverless REST API for managing to-do items, secured with Amazon Cognito and AWS WAF, backed by DynamoDB, traced with AWS X-Ray, and delivered through Amazon CloudFront.

**Region:** eu-central-1 (WAF web ACL for CloudFront lives in us-east-1) · **Built with:** AWS Management Console·


**Live demo / video:** https://drive.google.com/file/d/10f1RL5s1PCREJD0LlN-F7Evx77ZrtYfq/view?usp=drive_link

**`Note: Resources were deleted after the demo to stop charges.`**

## Table of Contents

- [Solution Overview](#solution-overview)
- [Architecture Diagram](#architecture-diagram)
- [Request Flow](#request-flow)
- [AWS Services Used](#aws-services-used)
- [API Reference](#api-reference)
- [Security](#security)
- [Testing and Evidence](#testing-and-evidence)

## Solution Overview

This project is a serverless to-do application on AWS. Users sign up and sign in
with Amazon Cognito, then create, complete and delete their own tasks through a
REST API. There are no servers to manage, and the stack scales to zero when idle.

**How it works**
- **Frontend:** a static single-page app in a private S3 bucket, served through CloudFront.
- **API:** API Gateway (REST) behind the same CloudFront distribution at `/api/*`,
  with a Cognito authorizer that validates the JWT on every request.
- **Compute:** a Lambda function (Python) handling GET, POST, PUT and DELETE on `/todos`.
- **Data:** a DynamoDB table (`userID` partition key, `todoID` sort key) with on-demand capacity.
- **Protection:** AWS WAF on CloudFront with AWS managed rule sets
  (common known bad inputs, SQL injection, IP reputation).
- **Observability:** X-Ray tracing, and WAF logs in CloudWatch Logs.

**What it demonstrates**
- Token-based authentication and per-user data isolation (the Lambda reads the
  user id from the verified token, never from the request body).
- Layered security: edge filtering (WAF), authentication (Cognito), authorization
  (per-user keys), and input handling (parameterized DynamoDB calls, text-only rendering).
- A low-cost, pay-per-use architecture built entirely in the AWS Management Console.

## Architecture Diagram
<img width="4323" height="2140" alt="Serverless REST API Architecture" src="https://github.com/user-attachments/assets/1e529e32-e085-41f2-879c-51ae2ffa1831" />


- Editable source: 
https://lucid.app/lucidchart/2733f9d1-730d-4e13-ad8b-ea3f0b4b05a9/edit?viewport_loc=-2683%2C-673%2C2542%2C1763%2C0_0&invitationId=inv_e5b5e0be-9710-49a0-a462-5571f41660de

## Request Flow


1. **User opens the site** from the internet at the CloudFront domain.
2. **CloudFront + AWS WAF.** Every request is inspected by AWS WAF (global scope,
   us-east-1) before it is served. and the
   AWS managed rule sets. Common Known Bad Inputs, SQL injection and Amazon IP
   reputation. Blocked requests receive `403` and never reach the origins.
3. **Static content.** The default CloudFront behavior serves the single-page app
   (HTML/JS) from a private **S3** bucket through Origin Access Control. (verify)
4. **Sign-up / sign-in.** The app's own login page calls **Amazon Cognito** directly
   (this call does not pass through CloudFront). New users confirm their email with
   a verification code. Cognito returns JWT tokens (ID, access and refresh), which
   the browser keeps in session storage and clears on sign-out.
5. **API call.** The browser calls `/api/*` on the same domain with the ID token in
   the `Authorization` header. CloudFront routes this path to **API Gateway**, whose
   **Cognito User Pool authorizer** validates the token. A missing or invalid token
   gets `401` and the request stops there.
6. **Compute.** API Gateway invokes **Lambda 1** (CRUD handler) for
   `GET/POST /todos` and `PUT/DELETE /todos/{id}`. The handler takes the user's id
   from the validated token (`sub`), never from the request body.
7. **Data.** Lambda 1 reads and writes **DynamoDB** (partition key `userID`, sort key
   `todoID`), so every call is scoped to the signed-in user. **DynamoDB Streams**
   triggers **Lambda 2** (audit / stream processor) on every change. (verify)
8. **Observability.** API Gateway and the Lambda functions send traces to **X-Ray**.
   WAF logs go to CloudWatch Logs (`aws-waf-logs-todo`, with the `Authorization`
   header redacted), and Lambda logs and metrics go to **CloudWatch**.

### Failure paths

| Situation | Where it stops | Response |
|---|---|---|
|SQLi / XSS / bad-input pattern | WAF at CloudFront | `403` |
| Missing, expired or tampered token | Cognito authorizer at API Gateway | `401` |
| Valid user asks for another user's task | Lambda / DynamoDB key lookup | `404` |

## AWS Services Used

| Service | Role in this project |
|---|---|
| Amazon CloudFront | CDN, single entry point, two origins (S3 and API Gateway) |
| AWS WAF |  AWS managed Common rules set |
| Amazon S3 | Private static frontend bucket |
| Amazon Cognito | User pool, hosted UI, JWT tokens |
| Amazon API Gateway (REST) | Routes, Cognito User Pool authorizer, throttling, usage plan, optional caching |
| AWS Lambda (x2) | CRUD handler; DynamoDB Streams consumer |
| Amazon DynamoDB | On-demand table, GSI, Streams |
| AWS X-Ray | Distributed tracing and service map |
| AWS IAM | Least-privilege roles per function |



## API Reference

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/todos` | List current user's tasks | Cognito ID token |
| POST | `/todos` | Create a task | Cognito ID token |
| GET | `/todos/{id}` | Get one task | Cognito ID token |
| PUT | `/todos/{id}` | Update a task | Cognito ID token |
| DELETE | `/todos/{id}` | Delete a task | Cognito ID token |


## Security

- Authentication with Cognito; every API route requires a valid token, checked by the User Pool authorizer
- S3 bucket private; access only through CloudFront OAC
- Per-user data isolation using `userId` from the token claims, never from the request body
- Least-privilege IAM roles scoped to the table and index ARNs
- API Gateway usage plan and stage throttling limit abuse per client
- HTTPS only; no secrets in the repo


