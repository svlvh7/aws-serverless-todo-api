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
- [Design Decisions](#design-decisions)
- [Data Model](#data-model)
- [API Reference](#api-reference)
- [Security](#security)
- [Testing and Evidence](#testing-and-evidence)
- [Lessons Learned](#lessons-learned)

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
- **Protection:** AWS WAF on CloudFront with rate limiting and AWS managed rule sets
  (common, known bad inputs, SQL injection, IP reputation).
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

Numbers match the circles in the architecture diagram.

1. **User opens the site** from the internet at the CloudFront domain.
2. **CloudFront + AWS WAF.** Every request is inspected by AWS WAF (global scope,
   us-east-1) before it is served. The web ACL applies a per-IP rate limit and the
   AWS managed rule sets: Common, Known Bad Inputs, SQL injection and Amazon IP
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
| Rate limit exceeded, or SQLi / XSS / bad-input pattern | WAF at CloudFront | `403` |
| Missing, expired or tampered token | Cognito authorizer at API Gateway | `401` |
| Valid user asks for another user's task | Lambda / DynamoDB key lookup | `404` |

## AWS Services Used

| Service | Role in this project |
|---|---|
| Amazon CloudFront | CDN, single entry point, two origins (S3 and API Gateway) |
| AWS WAF | Rate-based rule + AWS managed Common rule set |
| Amazon S3 | Private static frontend bucket |
| Amazon Cognito | User pool, hosted UI, JWT tokens |
| Amazon API Gateway (REST) | Routes, Cognito User Pool authorizer, throttling, usage plan, optional caching |
| AWS Lambda (x2) | CRUD handler; DynamoDB Streams consumer |
| Amazon DynamoDB | On-demand table, GSI, Streams |
| AWS X-Ray | Distributed tracing and service map |
| AWS IAM | Least-privilege roles per function |

## Design Decisions

<!-- One short paragraph each. This is the section that shows Solutions Architect thinking. -->

- **Why serverless:** ...
- **Why DynamoDB on-demand:** ...
- **Why CloudFront in front of API Gateway:** ...
- **Why OAC and a private bucket:** ...
- **Why a Cognito User Pool authorizer:** ... (REST APIs use User Pool authorizers with the ID token; JWT authorizers are an HTTP API feature)
- **Why Lambda outside a VPC:** ...
- **Why arm64 Lambda:** ...
- **WAF scope and bot protection:** Rate-based rule and the Common rule set are used as the low-cost mitigation. WAF Bot Control and geo blocking were considered; Bot Control carries a separate subscription cost, and geo blocking is a one-rule addition for production. ...
- **Trade-offs and what I would change for production:** ...

## Data Model

| Attribute | Type | Notes |
|---|---|---|
| `userId` (PK) | String | Cognito `sub` |
| `todoId` (SK) | String | ULID/UUID |
| `title` | String | |
| `status` | String | `open` / `done` |
| `createdAt` | String | ISO 8601 |
| `statusCreatedAt` | String | GSI sort key, format `status#createdAt`, e.g. `open#2026-10-22T15:00:00Z` |

**GSI `userId-status-index`:** PK `userId`, SK `statusCreatedAt` (value `status#createdAt`), projection All. Used to list tasks by status without a scan.

## API Reference

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/todos` | List current user's tasks | Cognito ID token |
| POST | `/todos` | Create a task | Cognito ID token |
| GET | `/todos/{id}` | Get one task | Cognito ID token |
| PUT | `/todos/{id}` | Update a task | Cognito ID token |
| DELETE | `/todos/{id}` | Delete a task | Cognito ID token |

Full details and examples: [`docs/api-reference.md`](docs/api-reference.md) · OpenAPI export: [`deployment/openapi.yaml`](deployment/openapi.yaml)

## Security

- Authentication with Cognito; every API route requires a valid token, checked by the User Pool authorizer
- WAF rate limiting and managed rules at the edge
- S3 bucket private; access only through CloudFront OAC
- Per-user data isolation using `userId` from the token claims, never from the request body
- Least-privilege IAM roles scoped to the table and index ARNs
- API Gateway usage plan and stage throttling limit abuse per client
- HTTPS only; no secrets in the repo

Details and Well-Architected Security Pillar mapping: [`docs/security.md`](docs/security.md)


## Testing and Evidence

| Test | Expected | Result | Evidence |
| :--- | :---: | :---: | :--- |
| Request without token | 401 | 401 | [View Screenshot](./screenshots/without-token.png) |
| Request with valid ID token | 201 | 201 | [View Screenshot](./screenshots/with-token.png) |
| User A cannot read User B's tasks | empty / 404 | — | [View Screenshot](./screenshots/isolation-test.png) |
| Rate limit exceeded | 403 from WAF | — | [View Screenshot](./screenshots/rate-limit.png) |
| Stream triggers Lambda 2 | log line in CloudWatch | — | [View Screenshot](./screenshots/cloudwatch-logs.png) |



## Lessons Learned
too many things learned after completing the project, how to architect the best practicing solution for the application, what is the important things to put in thee head while building an application such as the right database type and the right deployment for the application and the right configurations all the way to the last price which is the running application from the first to the end point
